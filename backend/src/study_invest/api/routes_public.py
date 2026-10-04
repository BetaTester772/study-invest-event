"""공개 API: 이벤트 정보, 시세(F-02), 랭킹(F-10), 학교 메일 인증·참가 등록·로그인(F-01)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import ScaledClock
from ..event_calendar import EventCalendar, to_kst
from ..instruments import BY_CODE, INSTRUMENTS
from ..mail import NoMailer
from ..models import CodePurpose, MarketDay, PriceHistory
from ..normalize import mask_email
from ..params import INITIAL_CASH, MARKET_CLOSE, MARKET_OPEN
from ..services import auth, email_verification, market, news, ranking
from ..services.common import DomainError, current_prices, get_params, latest_opened_day
from . import schemas, views
from .deps import AppState, NowDep, OptionalMeDep, RealNowDep, SessionDep, StateDep, TokenDep
from .email_codes import consume_code

log = logging.getLogger("study_invest")

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, str]:  # I/O 없음 → async(스레드풀이 가득 차도 응답)
    return {"status": "ok"}


def _clock_info(
    clock: Callable[[], datetime], now: datetime, calendar: EventCalendar
) -> schemas.ClockInfo | None:
    """테스트 시계면 화면 안내용 실제 시각을 만든다. 실제 시계면 None.

    다음 공시·마감은 운영일 기준이다(이벤트 전날 18:00처럼 아무 일도 없는 시각은 건너뛴다).
    """
    if not isinstance(clock, ScaledClock):
        return None

    def next_real(t: time) -> datetime | None:
        at = calendar.next_operating_time(now, t)
        return None if at is None else clock.to_real(at)

    return schemas.ClockInfo(
        scale=clock.scale,
        real_now=clock.to_real(now),
        next_open_at=next_real(MARKET_OPEN),
        next_close_at=next_real(MARKET_CLOSE),
    )


@router.get("/event", response_model=schemas.EventInfo)
def event_info(state: StateDep, s: SessionDep, now: NowDep) -> schemas.EventInfo:
    cal = state.calendar
    params = get_params(s)
    today = to_kst(now).date()
    md = s.get(MarketDay, today)
    day_opened = md is not None
    day_settled = md is not None and md.settled_at is not None
    calm_rounds = params.coin_calm_rounds
    if cal.total_rounds is not None:
        calm_rounds = min(calm_rounds, cal.total_rounds)
    if cal.end is None:  # 무제한: 끝이 없으니 지금까지(시계·공시 중 앞선 쪽)의 운영일만 보낸다
        days = cal.days_through(max(today, latest_opened_day(s) or cal.start, cal.start))
    else:
        days = cal.operating_days
    return schemas.EventInfo(
        start=cal.start,
        end=cal.end,
        operating_days=list(days),
        total_rounds=cal.total_rounds,
        now=now,
        today=today,
        is_operating_day=cal.is_operating_day(today),
        market=schemas.MarketInfo(
            is_open=cal.is_market_open(now) and day_opened and not day_settled,
            opens_at=MARKET_OPEN.strftime("%H:%M"),
            closes_at=MARKET_CLOSE.strftime("%H:%M"),
            day_opened=day_opened,
            day_settled=day_settled,
            round=cal.round_of(today),
        ),
        certification=schemas.CertificationInfo(
            cutoff=params.certification_cutoff.strftime("%H:%M"),
            target_date=cal.certification_target_date(now, params.certification_cutoff),
            reward_cash=params.reward_cash,
        ),
        coin=schemas.CoinInfo(
            cap=params.coin_cap,
            floor=params.coin_floor,
            calm_rounds=calm_rounds,
            # n회차 정산은 n+1번째 운영일 시작가에 반영된다
            calm_until=cal.start + timedelta(days=calm_rounds) if calm_rounds else None,
            calm_cap=params.coin_calm_cap,
            calm_floor=params.coin_calm_floor,
        ),
        initial_cash=INITIAL_CASH,
        daily_buy_limit_ratio=params.daily_buy_limit_ratio,
        clock=_clock_info(state.clock, now, cal),
        signup=schemas.SignupInfo(
            email_verification=state.settings.email_verification,
            verified_only_trading=params.verified_only_trading,
        ),
    )


@router.get("/instruments", response_model=list[schemas.Instrument])
def instruments(s: SessionDep) -> list[schemas.Instrument]:
    day, prices = current_prices(s)
    records = (
        {r.code: r for r in s.scalars(select(PriceHistory).where(PriceHistory.day == day))}
        if day
        else {}
    )
    today_news = {n.code: n for n in news.news_on(s, day)} if day else {}
    result = []
    for inst in INSTRUMENTS:
        rec = records.get(inst.code)
        item = today_news.get(inst.code)
        result.append(
            schemas.Instrument(
                code=inst.code,
                name=inst.name,
                alias=inst.alias,
                kind=inst.kind.value,
                price=prices[inst.code],
                previous_price=rec.previous_price if rec else None,
                change_rate=market.change_rate(rec) if rec else None,
                day=day,
                news=views.news_item(item) if item else None,
            )
        )
    return result


@router.get("/news", response_model=list[schemas.NewsItem])
def news_list(s: SessionDep) -> list[schemas.NewsItem]:
    """공시된 운영일까지의 호재·악재, 최신 날짜부터. 공시 전 날짜의 뉴스는 보이지 않는다."""
    return [views.news_item(n) for n in news.published_news(s)]


@router.get("/instruments/{code}/history", response_model=list[schemas.PricePoint])
def price_history(code: str, s: SessionDep) -> list[schemas.PricePoint]:
    if code not in BY_CODE:
        raise DomainError("NOT_FOUND", "존재하지 않는 종목입니다.", 404)
    rows = s.scalars(
        select(PriceHistory)
        .join(MarketDay, MarketDay.day == PriceHistory.day)  # 공시된 운영일만
        .where(PriceHistory.code == code)
        .order_by(PriceHistory.day)
    )
    return [
        schemas.PricePoint(
            day=r.day, price=r.price, change_rate=market.change_rate(r), source=r.source
        )
        for r in rows
    ]


@router.get("/ranking", response_model=schemas.Ranking)
def get_ranking(s: SessionDep, now: NowDep, me: OptionalMeDep) -> schemas.Ranking:
    day, entries = ranking.ranking(s, to_kst(now).date())
    return schemas.Ranking(
        day=day,
        entries=[
            schemas.RankingEntry(
                rank=e.rank,
                nickname=e.nickname,
                total_assets=e.total_assets,
                principal=e.principal,
                profit=e.profit,
                return_rate=e.return_rate,
                return_rank=e.return_rank,
                certified_days=e.certified_days,
                streak=e.streak,
                is_me=me is not None and me.id == e.participant_id,
            )
            for e in entries
        ],
    )


def send_code(
    state: AppState,
    s: Session,
    raw_email: str,
    now: datetime,
    purpose: CodePurpose,
    *,
    requester_id: int | None = None,
    shown: Callable[[str], str] = lambda address: address,
) -> schemas.EmailCodeResponse:
    """코드를 발급하고 메일로 보낸다. shown: 응답에 보여 줄 주소(등록 메일이면 가린 주소)."""
    if isinstance(state.mailer, NoMailer):  # 코드를 만들기 전에 거절한다(재요청 대기에 안 걸리게)
        raise DomainError(
            "MAIL_NOT_CONFIGURED",
            "지금은 인증 메일을 보낼 수 없습니다. 운영진에게 문의하세요.",
            503,
        )
    # 느린 SMTP가 공용 스레드풀을 다 차지하지 않게 동시 발송 수를 제한한다. 꽉 차면 코드를 만들기
    # 전에 바로 거절한다(재요청 대기에 걸리지 않게).
    if not state.mail_slots.acquire(blocking=False):
        raise DomainError(
            "MAIL_BUSY", "인증 메일 요청이 몰리고 있습니다. 잠시 후 다시 시도하세요.", 503
        )
    try:
        email, _, code = email_verification.request_code(
            s, raw_email, now, state.settings.mail_daily_limit, purpose, requester_id
        )
        # 먼저 커밋해 DB 연결·발급 잠금을 돌려준다. SMTP를 기다리는 동안 api 풀을 잡지 않는다.
        s.commit()
        try:
            state.mailer.send(email.address, *email_verification.message(code, purpose))
        except Exception as exc:
            # 코드 기록은 지우지 않는다: 재요청 대기·한도에 계속 센다. 연결 종료 중 오류처럼
            # 메일이 실제로 갔을 수도 있으니 코드도 그대로 유효하다.
            log.exception("인증 메일 발송 실패")
            raise DomainError(
                "MAIL_SEND_FAILED", "인증 메일을 보내지 못했습니다. 1분 뒤 다시 시도하세요.", 503
            ) from exc
    finally:
        state.mail_slots.release()
    return schemas.EmailCodeResponse(
        email=shown(email.address),
        expires_in=int(email_verification.CODE_TTL.total_seconds()),
        resend_after=int(email_verification.RESEND_COOLDOWN.total_seconds()),
    )


@router.post("/auth/email-code", response_model=schemas.EmailCodeResponse, status_code=202)
def request_email_code(
    body: schemas.EmailCodeRequest,
    state: StateDep,
    s: SessionDep,
    now: NowDep,
    real_now: RealNowDep,
) -> schemas.EmailCodeResponse:
    """학교 메일로 6자리 인증 코드를 보낸다(참가 신청·미인증 계정의 인증 공용)."""
    auth.ensure_registration_open(now, state.calendar)
    return send_code(state, s, body.email, real_now, CodePurpose.VERIFY)


@router.post("/auth/register", response_model=schemas.AuthResponse, status_code=201)
def register(
    body: schemas.RegisterRequest, state: StateDep, s: SessionDep, now: NowDep, real_now: RealNowDep
) -> schemas.AuthResponse:
    auth.ensure_registration_open(now, state.calendar)
    auth.ensure_privacy_consent(body.privacy_consent)
    # 코드가 있으면 확인해 인증된 채로 가입한다. 메일 인증을 켠 운영이면 코드가 꼭 있어야 한다.
    # 끈 운영(기본)이면 주소만 받아 미인증으로 가입한다(나중에 메일 코드나 관리자가 인증).
    verify = body.code is not None
    if verify:
        assert body.code is not None
        email = consume_code(s, body.email, body.code, real_now)
    elif state.settings.email_verification:
        raise DomainError("CODE_REQUIRED", "학교 메일로 받은 인증 코드를 입력하세요.", 422)
    else:
        email = email_verification.parse(body.email)
    profile = auth.Profile(body.name, body.student_id, body.department)
    participant, token = auth.register(
        s, email, profile, body.nickname, body.password, now, state.calendar, verified=verify
    )
    s.commit()
    return schemas.AuthResponse(
        token=token, participant=schemas.Participant.model_validate(participant)
    )


@router.post("/auth/password-reset/code", response_model=schemas.EmailCodeResponse, status_code=202)
def request_password_reset_code(
    body: schemas.PasswordResetCodeRequest, state: StateDep, s: SessionDep, real_now: RealNowDep
) -> schemas.EmailCodeResponse:
    """학번(또는 학교 메일)으로 찾은 계정의 등록 메일로 재설정 코드를 보낸다. 응답 주소는 가린다."""
    participant = auth.account_for_reset(s, body.identity)
    assert participant.email_address is not None
    return send_code(
        state,
        s,
        participant.email_address,
        real_now,
        CodePurpose.RESET_PASSWORD,
        shown=mask_email,
    )


@router.post("/auth/password-reset/verify", status_code=204)
def verify_password_reset_code(
    body: schemas.PasswordResetVerifyRequest, s: SessionDep, real_now: RealNowDep
) -> Response:
    """새 비밀번호를 받기 전에 코드만 확인한다. 코드는 쓰지 않는다(재설정 요청에 다시 보낸다).

    틀린 횟수는 재설정 요청과 함께 센다.
    """
    participant = auth.account_for_reset(s, body.identity)
    assert participant.email_address is not None
    consume_code(
        s, participant.email_address, body.code, real_now, CodePurpose.RESET_PASSWORD, consume=False
    )
    return Response(status_code=204)


@router.post("/auth/password-reset", response_model=schemas.AuthResponse)
def reset_password(
    body: schemas.PasswordResetRequest, s: SessionDep, real_now: RealNowDep
) -> schemas.AuthResponse:
    """코드를 확인하고 비밀번호를 바꾼 뒤 로그인시킨다. 다른 기기의 로그인은 끊는다."""
    participant = auth.account_for_reset(s, body.identity)
    assert participant.email_address is not None
    consume_code(s, participant.email_address, body.code, real_now, CodePurpose.RESET_PASSWORD)
    participant, token = auth.reset_password(s, participant, body.password, real_now)
    s.commit()
    return schemas.AuthResponse(
        token=token, participant=schemas.Participant.model_validate(participant)
    )


@router.post("/auth/login", response_model=schemas.AuthResponse)
def login(body: schemas.LoginRequest, s: SessionDep, now: NowDep) -> schemas.AuthResponse:
    participant, token = auth.login(s, body.identity, body.password, now)
    s.commit()
    return schemas.AuthResponse(
        token=token, participant=schemas.Participant.model_validate(participant)
    )


@router.post("/auth/logout", status_code=204)
def logout(s: SessionDep, token: TokenDep) -> Response:
    if token:
        auth.revoke_token(s, token)
        s.commit()
    return Response(status_code=204)
