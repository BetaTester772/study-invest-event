"""FastAPI 의존성: 앱 상태, DB 세션, 시계, 인증.

비동기 원칙: I/O가 전혀 없는 의존성만 `async def`로 둔다(이벤트 루프에서 바로 실행되어
스레드풀을 소모하지 않는다). DB·파일을 건드리는 것은 모두 동기 `def`로 두어 스레드풀에서
실행한다. `async def` 안에서 동기 I/O를 하면 그동안 서버 전체가 멈춘다.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Callable, Iterator
from concurrent.futures import Executor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..event_calendar import EventCalendar
from ..models import Participant
from ..params import EventParams
from ..services import auth
from ..services.common import DomainError, get_params


@dataclass
class AppState:
    settings: Settings
    session_factory: sessionmaker[Session]
    calendar: EventCalendar
    clock: Callable[[], datetime]
    rng: random.Random
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


async def get_now(state: StateDep) -> datetime:
    return state.clock()


NowDep = Annotated[datetime, Depends(get_now)]


def current_params(s: SessionDep) -> EventParams:
    return get_params(s)


ParamsDep = Annotated[EventParams, Depends(current_params)]


async def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


TokenDep = Annotated[str | None, Depends(bearer_token)]


def optional_participant(s: SessionDep, token: TokenDep) -> Participant | None:
    # DB 조회 → 동기 def(스레드풀)
    return auth.participant_by_token(s, token) if token else None


async def current_participant(
    participant: Annotated[Participant | None, Depends(optional_participant)],
) -> Participant:
    if participant is None:
        raise DomainError("UNAUTHORIZED", "로그인이 필요합니다.", 401)
    return participant


MeDep = Annotated[Participant, Depends(current_participant)]
OptionalMeDep = Annotated[Participant | None, Depends(optional_participant)]


async def require_admin(
    state: StateDep, x_admin_key: Annotated[str | None, Header()] = None
) -> None:
    expected = state.settings.admin_key
    if not expected or not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise DomainError("UNAUTHORIZED", "관리자 키가 올바르지 않습니다.", 401)
