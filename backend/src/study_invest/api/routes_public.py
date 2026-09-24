"""공개 API: 이벤트 정보, 시세(F-02), 랭킹(F-10), 참가 등록·로그인(F-01)."""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import select

from ..event_calendar import to_kst
from ..instruments import BY_CODE, INSTRUMENTS
from ..models import MarketDay, PriceHistory
from ..params import INITIAL_CASH, MARKET_CLOSE, MARKET_OPEN
from ..services import auth, market, ranking
from ..services.common import DomainError, current_prices, get_params
from . import schemas
from .deps import NowDep, OptionalMeDep, SessionDep, StateDep, TokenDep

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/event", response_model=schemas.EventInfo)
def event_info(state: StateDep, s: SessionDep, now: NowDep) -> schemas.EventInfo:
    cal = state.calendar
    params = get_params(s)
    today = to_kst(now).date()
    md = s.get(MarketDay, today)
    day_opened = md is not None
    day_settled = md is not None and md.settled_at is not None
    return schemas.EventInfo(
        start=cal.start,
        end=cal.end,
        operating_days=list(cal.operating_days),
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
            reward_coin_quantity=params.reward_coin_quantity,
        ),
        initial_cash=INITIAL_CASH,
        daily_buy_limit_ratio=params.daily_buy_limit_ratio,
    )


@router.get("/instruments", response_model=list[schemas.Instrument])
def instruments(s: SessionDep) -> list[schemas.Instrument]:
    day, prices = current_prices(s)
    records = (
        {r.code: r for r in s.scalars(select(PriceHistory).where(PriceHistory.day == day))}
        if day
        else {}
    )
    result = []
    for inst in INSTRUMENTS:
        rec = records.get(inst.code)
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
            )
        )
    return result


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
                return_rate=e.return_rate,
                certified_days=e.certified_days,
                streak=e.streak,
                is_me=me is not None and me.id == e.participant_id,
            )
            for e in entries
        ],
    )


@router.post("/auth/register", response_model=schemas.AuthResponse, status_code=201)
def register(
    body: schemas.RegisterRequest, state: StateDep, s: SessionDep, now: NowDep
) -> schemas.AuthResponse:
    participant, token = auth.register(
        s, body.identity, body.nickname, body.password, now, state.calendar
    )
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
