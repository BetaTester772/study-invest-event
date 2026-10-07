"""FastAPI 의존성: 앱 상태, DB 세션, 시계, 인증.

비동기 원칙: I/O가 전혀 없는 의존성만 `async def`로 둔다(이벤트 루프에서 바로 실행되어
스레드풀을 소모하지 않는다). DB·파일을 건드리는 것은 모두 동기 `def`로 두어 스레드풀에서
실행한다. `async def` 안에서 동기 I/O를 하면 그동안 서버 전체가 멈춘다.

연결 반납 원칙: 동기 의존성·라우트는 각각 따로 스레드를 받아 실행된다. 한 단계가 DB 연결을 쥔 채
끝나면, 그 요청은 연결을 쥐고 다음 단계의 스레드를 기다린다. 동시 요청이 많으면 스레드는 모두
연결을 기다리고 연결은 모두 스레드를 기다려 api 풀 대기 시간(10초)마다만 조금씩 풀린다
(2026-10-07 스트레스 테스트). 그래서 DB를 읽는 의존성은 끝날 때 `release_connection`으로,
라우트는 `SessionReleasingRoute`로 연결을 돌려준다.
"""

from __future__ import annotations

import functools
import inspect
import logging
import random
import secrets
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Executor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session, sessionmaker

from ..captcha import CaptchaUnavailable, CaptchaVerifier, NoCaptcha
from ..clock import OffsetClock, ScaledClock
from ..config import Settings
from ..db import DatabasePools
from ..event_calendar import EventCalendar
from ..logging_setup import bind
from ..mail import Mailer
from ..models import Participant
from ..params import EventParams
from ..services import auth
from ..services.common import DomainError, get_params

log = logging.getLogger("study_invest")

MAIL_CONCURRENCY = 8
"""동시 SMTP 발송 상한. 스레드풀(기본 40) 중 이 이상은 메일 대기에 쓰지 않는다."""


@dataclass
class AppState:
    settings: Settings
    pools: DatabasePools
    session_factory: sessionmaker[Session]
    """api 풀 세션(HTTP 요청)."""
    batch_session_factory: sessionmaker[Session]
    """batch 풀 세션(공시·정산·수동 가격, 스케줄러)."""
    calendar: EventCalendar
    clock: Callable[[], datetime]
    rng: random.Random
    mailer: Mailer
    """인증 메일 발송(SmtpMailer, SMTP 미설정이면 LogMailer)."""
    mail_slots: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(MAIL_CONCURRENCY)
    )
    """동시에 SMTP로 보내는 메일 수 상한. 느린 SMTP가 공용 스레드풀을 다 차지하지 않게 한다."""
    captcha: CaptchaVerifier = field(default_factory=NoCaptcha)
    """봇 확인(Turnstile). 키가 없으면 NoCaptcha(확인하지 않음)."""
    time_scale: float = 1.0
    """clock의 배속. 스케줄러는 다음 배치까지 남은 시계 초를 이 값으로 나눠 실제로 기다린다."""
    cpu_executor: Executor | None = field(default=None)
    """CPU 작업(시뮬레이터)용 프로세스 풀. None이면 스레드로 실행한다."""


async def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.study_invest
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def get_session(state: StateDep) -> Iterator[Session]:
    """요청 단위 세션. 라우트가 명시적으로 커밋하고, 예외 시 롤백한다.

    동기 제너레이터이므로 스레드풀에서 열고 닫힌다. 이 세션을 쓰는 라우트·의존성도
    반드시 동기 def여야 한다(async def에서 쓰면 이벤트 루프가 막힌다).
    """
    with state.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


SessionDep = Annotated[Session, Depends(get_session)]


def release_connection(s: Session) -> None:
    """읽기만 한 의존성이 끝날 때 트랜잭션을 끝내 연결을 api 풀에 돌려준다(모듈 설명 참고).

    expire_on_commit=False라 읽어 둔 객체(참가자 등)는 그대로 쓸 수 있고, 라우트가 다시 DB를
    쓰면 그때 새 트랜잭션이 연결을 받는다. 쓰기가 없으므로 커밋은 롤백과 같다."""
    if s.in_transaction():
        s.commit()


def _close_sessions_after(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(endpoint)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = endpoint(*args, **kwargs)
        for value in kwargs.values():
            if isinstance(value, Session):
                value.close()
        return result

    return wrapper


class SessionReleasingRoute(APIRoute):
    """동기 라우트가 정상 반환하면 받은 세션을 바로 닫아 연결을 돌려준다(모듈 설명 참고).

    FastAPI는 동기 라우트의 반환값 검증(response_model)을 또 다른 스레드에서 하고, 세션은 그 뒤
    의존성 정리 때 닫힌다. 라우트는 커밋을 직접 하므로 여기서 닫아도 결과는 정리 때 닫는 것과
    같다(커밋하지 않은 변경은 원래도 버려진다). 닫힌 세션의 객체는 읽어 둔 값으로 직렬화된다.
    예외가 나면 그대로 두어 get_session이 롤백한다."""

    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        if not inspect.iscoroutinefunction(endpoint):
            endpoint = _close_sessions_after(endpoint)
        super().__init__(path, endpoint, **kwargs)


def get_batch_session(state: StateDep) -> Iterator[Session]:
    """배치 전용 풀의 세션. 관리자 배치 API가 api 풀 대기열 뒤에 서지 않게 한다."""
    with state.batch_session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


BatchSessionDep = Annotated[Session, Depends(get_batch_session)]


async def get_now(state: StateDep) -> datetime:
    return state.clock()


NowDep = Annotated[datetime, Depends(get_now)]


async def get_real_now(state: StateDep) -> datetime:
    """실제 시각. 인증 코드 유효시간·재발송 간격처럼 사람이 기다리는 시간은 테스트 시계 배속을
    따르지 않는다(배속 24면 10분이 25초가 된다). 테스트가 주입한 시계는 그대로 쓴다."""
    clock = state.clock
    if isinstance(clock, OffsetClock):
        return clock.real()
    return clock.source() if isinstance(clock, ScaledClock) else clock()


RealNowDep = Annotated[datetime, Depends(get_real_now)]


def current_params(s: SessionDep) -> EventParams:
    params = get_params(s)
    release_connection(s)
    return params


ParamsDep = Annotated[EventParams, Depends(current_params)]


async def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


TokenDep = Annotated[str | None, Depends(bearer_token)]


def optional_participant(s: SessionDep, token: TokenDep) -> Participant | None:
    # DB 조회 → 동기 def(스레드풀)
    if not token:
        return None
    # 만료·폐기된 토큰의 요청도 같은 세션 ID로 남아 "왜 갑자기 401인지" 추적할 수 있다.
    bind(session_id=auth.session_id(token))
    participant = auth.participant_by_token(s, token)
    release_connection(s)
    if participant is not None:
        bind(participant_id=participant.id)
    return participant


async def current_participant(
    participant: Annotated[Participant | None, Depends(optional_participant)],
) -> Participant:
    if participant is None:
        raise DomainError("UNAUTHORIZED", "로그인이 필요합니다.", 401)
    return participant


MeDep = Annotated[Participant, Depends(current_participant)]
OptionalMeDep = Annotated[Participant | None, Depends(optional_participant)]


def verified_participant(participant: MeDep, s: SessionDep) -> Participant:
    """주문용. 관리자가 '인증된 참가자만 거래'(verified_only_trading)를 켰으면 미인증 계정은 403.

    파라미터를 DB에서 읽으므로 동기 def(스레드풀)."""
    verified_only = get_params(s).verified_only_trading
    release_connection(s)
    if not participant.verified and verified_only:
        raise DomainError(
            "VERIFICATION_REQUIRED",
            "지금은 인증된 참가자만 거래할 수 있습니다. 학교 메일 인증을 마쳐 주세요.",
            403,
        )
    return participant


VerifiedMeDep = Annotated[Participant, Depends(verified_participant)]


async def require_admin(
    state: StateDep, x_admin_key: Annotated[str | None, Header()] = None
) -> None:
    expected = state.settings.admin_key
    # 바이트로 비교한다. str 비교는 비ASCII 헤더에서 TypeError(500)가 난다.
    if (
        not expected
        or not x_admin_key
        or not secrets.compare_digest(x_admin_key.encode(), expected.encode())
    ):
        raise DomainError("UNAUTHORIZED", "관리자 키가 올바르지 않습니다.", 401)
    bind(admin=True)


def require_captcha(action: str, *, fail_open: bool = False) -> Callable[..., None]:
    """봇 확인 의존성. 라우트의 `dependencies=[Depends(...)]`에 넣으면 DB 세션을 열기 전에 돈다
    (siteverify를 기다리는 동안 api 풀 연결을 잡지 않는다).

    action: 위젯의 action과 같아야 한다(다른 화면에서 받은 토큰 거절).
    fail_open: siteverify에 닿지 못하면 통과시킨다(로그인처럼 막히면 안 되는 곳). 끄면 503.
    """

    # siteverify 호출(네트워크 I/O) → 동기 def(스레드풀)
    def check(state: StateDep, x_turnstile_token: Annotated[str | None, Header()] = None) -> None:
        captcha = state.captcha
        if captcha.site_key is None:
            return
        try:
            ok = captcha.verify(x_turnstile_token or "", action)
        except CaptchaUnavailable:
            log.warning("봇 확인 서버에 닿지 못함(action=%s, fail_open=%s)", action, fail_open)
            if fail_open:
                return
            raise DomainError(
                "CAPTCHA_UNAVAILABLE",
                "지금은 보안 확인을 할 수 없습니다. 잠시 후 다시 시도하세요.",
                503,
                context={"action": action},
            ) from None
        if not ok:
            raise DomainError(
                "CAPTCHA_FAILED",
                "보안 확인에 실패했습니다. 확인이 끝난 뒤 다시 시도하거나 페이지를 새로고침하세요.",
                403,
                context={"action": action, "token_present": bool(x_turnstile_token)},
            )

    return check
