"""매수·매도 주문과 포트폴리오 (04-trading §2, F-03, F-04)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..instruments import BY_CODE, INSTRUMENTS, InstrumentKind
from ..models import (
    Holding,
    Order,
    OrderStatus,
    Participant,
    ParticipantStatus,
    RejectReason,
    Side,
)
from ..money import exact, round_half_up
from ..params import INITIAL_CASH, EventParams
from .common import current_prices, market_day, prices_on, total_assets

MAX_QUANTITY = 1_000_000_000


def bought_today(s: Session, participant_id: int, day: date) -> dict[str, int]:
    rows = s.execute(
        select(Order.code, func.sum(Order.amount))
        .where(
            Order.participant_id == participant_id,
            Order.trade_day == day,
            Order.side == Side.BUY,
            Order.status == OrderStatus.FILLED,
        )
        .group_by(Order.code)
    )
    return {code: int(total or 0) for code, total in rows}


def buy_limit_amount(total: int, params: EventParams) -> int:
    """1일 1종목 매수 상한 금액 = floor(총자산 × 비율)."""
    return int(exact(params.daily_buy_limit_ratio) * total)


def _holding(participant: Participant, code: str) -> Holding:
    for h in participant.holdings:
        if h.code == code:
            return h
    h = Holding(code=code, quantity=0, cost=0)
    participant.holdings.append(h)
    return h


def place_order(
    s: Session,
    participant: Participant,
    code: str,
    side: Side,
    quantity: int,
    now: datetime,
    calendar: EventCalendar,
    params: EventParams,
) -> Order:
    """주문을 검증하고 즉시 체결한다. 거부된 주문도 사유와 함께 기록한다(F-09)."""
    # 동시 주문 대비 참가자 행 잠금(PostgreSQL 등). SQLite는 무시된다.
    s.execute(select(Participant.id).where(Participant.id == participant.id).with_for_update())
    trade_day = to_kst(now).date()
    reason: RejectReason | None = None
    price: int | None = None

    if participant.status is ParticipantStatus.DISQUALIFIED:
        reason = RejectReason.DISQUALIFIED
    elif (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or not (1 <= quantity <= MAX_QUANTITY)
    ):
        reason = RejectReason.INVALID_QUANTITY
    elif code not in BY_CODE:
        reason = RejectReason.UNKNOWN_INSTRUMENT
    elif not calendar.is_market_open(now):
        reason = RejectReason.MARKET_CLOSED
    else:
        md = market_day(s, trade_day)
        if md is None:
            reason = RejectReason.MARKET_NOT_OPENED
        elif md.settled_at is not None:
            reason = RejectReason.MARKET_CLOSED
        else:
            prices = prices_on(s, trade_day)
            price = prices[code]
            cost = price * quantity
            if side is Side.BUY:
                if participant.cash < cost:
                    reason = RejectReason.INSUFFICIENT_CASH
                else:
                    limit = buy_limit_amount(total_assets(participant, prices), params)
                    already = bought_today(s, participant.id, trade_day).get(code, 0)
                    if already + cost > limit:
                        reason = RejectReason.DAILY_BUY_LIMIT
            else:
                held = next((h.quantity for h in participant.holdings if h.code == code), 0)
                if held < quantity:
                    reason = RejectReason.INSUFFICIENT_HOLDINGS

    amount: int | None = price * quantity if price is not None and reason is None else None
    if amount is not None:
        holding = _holding(participant, code)
        if side is Side.BUY:
            participant.cash -= amount
            holding.quantity += quantity
            holding.cost += amount
        else:
            removed = round_half_up(Fraction(holding.cost * quantity, holding.quantity), 1)
            holding.quantity -= quantity
            holding.cost = 0 if holding.quantity == 0 else holding.cost - removed
            participant.cash += amount

    order = Order(
        participant_id=participant.id,
        code=code[:16],
        side=side,
        quantity=quantity if isinstance(quantity, int) else 0,
        price=price,
        amount=amount,
        status=OrderStatus.REJECTED if reason else OrderStatus.FILLED,
        reject_reason=reason,
        trade_day=trade_day if calendar.is_operating_day(trade_day) else None,
        created_at=now,
    )
    s.add(order)
    s.flush()
    return order


@dataclass(frozen=True)
class HoldingView:
    code: str
    name: str
    kind: InstrumentKind
    quantity: int
    avg_price: int
    price: int
    value: int
    cost: int
    profit: int
    profit_rate: float | None


@dataclass(frozen=True)
class PortfolioView:
    cash: int
    holdings: list[HoldingView]
    holdings_value: int
    total_assets: int
    initial_cash: int
    return_rate: float
    day: date | None
    limit_ratio: float
    limit_amount: int
    remaining: dict[str, int]


def portfolio(
    s: Session, participant: Participant, now: datetime, params: EventParams
) -> PortfolioView:
    day, prices = current_prices(s)
    views: list[HoldingView] = []
    for inst in INSTRUMENTS:
        h = next((h for h in participant.holdings if h.code == inst.code), None)
        if h is None or h.quantity == 0:
            continue
        price = prices[inst.code]
        value = h.quantity * price
        views.append(
            HoldingView(
                code=inst.code,
                name=inst.name,
                kind=inst.kind,
                quantity=h.quantity,
                avg_price=round_half_up(Fraction(h.cost, h.quantity), 1),
                price=price,
                value=value,
                cost=h.cost,
                profit=value - h.cost,
                profit_rate=float(Fraction(value - h.cost, h.cost)) if h.cost else None,
            )
        )
    total = total_assets(participant, prices)
    limit = buy_limit_amount(total, params)
    today = to_kst(now).date()
    spent = bought_today(s, participant.id, today) if day == today else {}
    return PortfolioView(
        cash=participant.cash,
        holdings=views,
        holdings_value=sum(v.value for v in views),
        total_assets=total,
        initial_cash=INITIAL_CASH,
        return_rate=float(Fraction(total - INITIAL_CASH, INITIAL_CASH)),
        day=day,
        limit_ratio=params.daily_buy_limit_ratio,
        limit_amount=limit,
        remaining={i.code: max(0, limit - spent.get(i.code, 0)) for i in INSTRUMENTS},
    )
