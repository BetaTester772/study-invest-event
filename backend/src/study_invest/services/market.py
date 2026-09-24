"""장 운영 배치: 09:00 시작가 공시·보상 지급, 18:00 정산 (04-trading §3, F-05, F-08).

서비스 함수는 커밋하지 않는다. 호출자가 한 트랜잭션으로 커밋하므로 배치 도중 실패하면
아무것도 기록되지 않는다(당일 정산 무효·전일 가격 유지 후 재실행, 04-trading §3.5).
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from fractions import Fraction
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..instruments import BY_CODE, COIN, INSTRUMENTS, STOCKS
from ..models import (
    MarketDay,
    Order,
    OrderStatus,
    PriceHistory,
    PriceSource,
    SettlementLog,
    Side,
)
from ..money import PRICE_UNIT
from ..params import MARKET_CLOSE, MARKET_OPEN
from ..pricing import draw_coin, settle_stocks
from . import certification
from .common import (
    DomainError,
    audit,
    batch_lock,
    get_params,
    latest_opened_day,
    lock_market_day,
    market_day,
    prices_on,
)


@dataclass
class BatchResult:
    action: str
    day: date
    detail: dict[str, Any] = field(default_factory=dict)


def _price_before(s: Session, code: str, day: date) -> int | None:
    return s.scalar(
        select(PriceHistory.price)
        .where(PriceHistory.code == code, PriceHistory.day < day)
        .order_by(PriceHistory.day.desc())
        .limit(1)
    )


def _ratio(new: int, old: int | None) -> float | None:
    return None if not old else float(Fraction(new - old, old))


# --- 09:00 공시 ------------------------------------------------------------------


def open_day(s: Session, day: date, now: datetime, calendar: EventCalendar) -> BatchResult:
    """day의 시작가를 확정·공시하고 밀린 인증 보상을 지급한다."""
    batch_lock(s)  # 다른 배치와 직렬화(재진입 가능)
    if not calendar.is_operating_day(day):
        raise DomainError("NOT_OPERATING_DAY", f"{day}는 운영일이 아닙니다.", 422)
    if to_kst(now).date() < day:
        raise DomainError("TOO_EARLY", f"{day} 이전에는 공시할 수 없습니다.")
    if market_day(s, day) is not None:
        raise DomainError("ALREADY_OPENED", f"{day}는 이미 공시되었습니다.")
    latest = latest_opened_day(s)
    if latest is not None and latest > day:
        raise DomainError("OUT_OF_ORDER", f"이후 운영일({latest})이 이미 공시되었습니다.")

    existing = {r.code: r for r in s.scalars(select(PriceHistory).where(PriceHistory.day == day))}
    sources: dict[str, str] = {}
    for inst in INSTRUMENTS:
        if inst.code in existing:
            sources[inst.code] = existing[inst.code].source.value
            continue
        previous = _price_before(s, inst.code, day)
        if previous is None:  # 1일차(또는 이력 없음): 종목 마스터 시작가
            price, prev, source = inst.initial_price, None, PriceSource.INITIAL
        else:  # 전일 정산 없음: 전일 가격 유지
            price, prev, source = previous, previous, PriceSource.CARRY_OVER
        s.add(
            PriceHistory(
                code=inst.code,
                day=day,
                price=price,
                previous_price=prev,
                source=source,
                created_at=now,
            )
        )
        sources[inst.code] = source.value
    s.add(MarketDay(day=day, opened_at=now))
    s.flush()

    paid = certification.pay_rewards(s, day, now, get_params(s))
    prices = prices_on(s, day)
    audit(s, now, "system", "market.open", day=day.isoformat(), prices=prices, sources=sources)
    return BatchResult("open", day, {"prices": prices, "sources": sources, "rewards_paid": paid})


# --- 18:00 정산 ------------------------------------------------------------------


def buy_amounts(s: Session, day: date) -> dict[str, int]:
    """당일 종목별 체결 매수금액 Bᵢ (매도는 집계하지 않는다)."""
    rows = s.execute(
        select(Order.code, func.sum(Order.amount))
        .where(
            Order.trade_day == day,
            Order.side == Side.BUY,
            Order.status == OrderStatus.FILLED,
        )
        .group_by(Order.code)
    )
    return {code: int(total or 0) for code, total in rows}


def settle_day(
    s: Session, day: date, now: datetime, calendar: EventCalendar, rng: random.Random
) -> BatchResult:
    batch_lock(s)  # 다른 배치와 직렬화(재진입 가능)
    round_no = calendar.round_of(day)
    if round_no is None:
        raise DomainError("NO_ROUND", f"{day} 정산은 반영일이 없어 실행하지 않습니다.")
    # 배타 잠금: 진행 중인 주문(공유 잠금)이 끝난 뒤 집계하고, 이후 주문은 거부된다.
    md = lock_market_day(s, day, shared=False)
    if md is None:
        raise DomainError("NOT_OPENED", f"{day}는 공시되지 않았습니다.")
    if md.settled_at is not None:
        raise DomainError("ALREADY_SETTLED", f"{day}는 이미 정산되었습니다.")
    local = to_kst(now)
    if (local.date(), local.time()) < (day, MARKET_CLOSE):
        raise DomainError("TOO_EARLY", "장 마감(18:00) 이후에 정산할 수 있습니다.")
    effective = calendar.next_operating_day(day)
    assert effective is not None
    if market_day(s, effective) is not None:
        raise DomainError("NEXT_DAY_OPENED", f"다음 운영일({effective})이 이미 공시되었습니다.")

    params = get_params(s)
    prices = prices_on(s, day)
    amounts = buy_amounts(s, day)
    stock_moves = settle_stocks(
        {i.code: prices[i.code] for i in STOCKS},
        {c: a for c, a in amounts.items() if c in {i.code for i in STOCKS}},
        params,
    )
    coin = draw_coin(prices[COIN.code], params, rng)

    new_prices = {code: m.new_price for code, m in stock_moves.items()}
    new_prices[COIN.code] = coin.new_price
    manual = {
        r.code
        for r in s.scalars(
            select(PriceHistory).where(
                PriceHistory.day == effective, PriceHistory.source == PriceSource.MANUAL
            )
        )
    }
    for code, price in new_prices.items():
        if code in manual:  # 수동 개입가가 정산 결과보다 우선한다
            continue
        s.merge(
            PriceHistory(
                code=code,
                day=effective,
                price=price,
                previous_price=prices[code],
                source=PriceSource.SETTLEMENT,
                created_at=now,
            )
        )

    stocks_log = [
        {
            "code": m.code,
            "buy_amount": m.buy_amount,
            "adjusted_amount": m.adjusted_amount,
            "concentration": None if m.concentration is None else float(m.concentration),
            "rate": float(m.rate),
            "old_price": m.old_price,
            "new_price": m.new_price,
        }
        for m in stock_moves.values()
    ]
    coin_log = {
        "p": coin.p,
        "x": coin.x,
        "direction": coin.direction,
        "rate": coin.rate,
        "old_price": coin.old_price,
        "new_price": coin.new_price,
    }
    s.add(
        SettlementLog(
            round_no=round_no,
            trade_day=day,
            effective_day=effective,
            created_at=now,
            stocks=stocks_log,
            coin=coin_log,
            params=params.to_dict(),
        )
    )
    md.settled_at = now
    audit(
        s,
        now,
        "system",
        "market.settle",
        day=day.isoformat(),
        round=round_no,
        new_prices=new_prices,
        manual_kept=sorted(manual),
    )
    return BatchResult(
        "settle",
        day,
        {
            "round": round_no,
            "effective_day": effective.isoformat(),
            "new_prices": new_prices,
            "manual_kept": sorted(manual),
        },
    )


# --- 스케줄러용: 현재 시각에 밀린 배치 실행 ---------------------------------------------


def run_due(
    session_factory: Callable[[], Session],
    now: datetime,
    calendar: EventCalendar,
    rng: random.Random,
) -> list[BatchResult | dict[str, Any]]:
    """전일 미정산 → 오늘 공시 → 오늘 정산 순으로, 시각이 된 배치를 각각 별도 트랜잭션으로 실행한다.

    - 여러 번 호출해도 안전하다. 각 단계는 배치 잠금을 잡은 뒤 필요 여부를 다시 확인한다.
    - 다른 프로세스(워커·레플리카)가 배치 잠금을 잡고 있으면 조용히 멈춘다(그쪽이 처리 중).
    - 전일 정산이 실패해도 오늘 공시는 진행해 전일 가격을 이월한다(04-trading §3.5).
      그 밖의 단계가 실패하면 롤백하고 멈춘다.
    """
    local = to_kst(now)
    today = local.date()
    prev = calendar.previous_operating_day(today)
    results: list[BatchResult | dict[str, Any]] = []

    def prev_settle_due(s: Session) -> bool:
        if prev is None or calendar.round_of(prev) is None:
            return False
        md = market_day(s, prev)
        return md is not None and md.settled_at is None and market_day(s, today) is None

    def open_due(s: Session) -> bool:
        if not calendar.is_operating_day(today) or local.time() < MARKET_OPEN:
            return False
        latest = latest_opened_day(s)
        return market_day(s, today) is None and (latest is None or latest < today)

    def today_settle_due(s: Session) -> bool:
        if local.time() < MARKET_CLOSE or calendar.round_of(today) is None:
            return False
        md = market_day(s, today)
        return md is not None and md.settled_at is None

    def settle_prev(s: Session) -> BatchResult:
        assert prev is not None  # prev_settle_due가 보장
        return settle_day(s, prev, now, calendar, rng)

    plan: list[tuple[str, date | None, Callable[[Session], bool], Callable[[Session], BatchResult]]]
    plan = [
        ("settle", prev, prev_settle_due, settle_prev),
        ("open", today, open_due, lambda s: open_day(s, today, now, calendar)),
        ("settle", today, today_settle_due, lambda s: settle_day(s, today, now, calendar, rng)),
    ]
    for index, (action, day, due, run) in enumerate(plan):
        with session_factory() as s:
            try:
                if not batch_lock(s, wait=False):
                    return results  # 다른 스케줄러가 배치 실행 중
                if not due(s):
                    s.rollback()
                    continue
                results.append(run(s))
                s.commit()
            except Exception as exc:  # 배치 실패: 롤백 후 다음 호출에서 재실행
                s.rollback()
                code = exc.code if isinstance(exc, DomainError) else type(exc).__name__
                results.append({"action": action, "day": day, "error": code, "message": str(exc)})
                if index == 0:
                    continue  # 전일 정산 실패 → 공시가 전일 가격을 이월한다
                return results
    return results


# --- 관리자 수동 가격 개입 (F-11) ---------------------------------------------------


def set_manual_price(
    s: Session,
    day: date,
    code: str,
    price: int,
    reason: str,
    now: datetime,
    calendar: EventCalendar,
) -> PriceHistory:
    """아직 공시되지 않은 운영일의 시작가를 지정한다. 장중 가격은 바꿀 수 없다."""
    batch_lock(s)  # 공시와 겹치지 않게
    if code not in BY_CODE:
        raise DomainError("UNKNOWN_INSTRUMENT", "존재하지 않는 종목입니다.", 404)
    if not calendar.is_operating_day(day):
        raise DomainError("NOT_OPERATING_DAY", f"{day}는 운영일이 아닙니다.", 422)
    if market_day(s, day) is not None:
        raise DomainError("DAY_ALREADY_OPENED", "이미 공시된 운영일의 가격은 바꿀 수 없습니다.")
    if price < PRICE_UNIT or price % PRICE_UNIT:
        raise DomainError("INVALID_PRICE", "가격은 10원 단위의 양수여야 합니다.", 422)
    if not reason.strip():
        raise DomainError("REASON_REQUIRED", "개입 사유를 입력하세요.", 422)
    previous = _price_before(s, code, day)
    record = s.merge(
        PriceHistory(
            code=code,
            day=day,
            price=price,
            previous_price=previous,
            source=PriceSource.MANUAL,
            created_at=now,
        )
    )
    audit(
        s, now, "admin", "price.manual", day=day.isoformat(), code=code, price=price, reason=reason
    )
    return record


def change_rate(record: PriceHistory) -> float | None:
    return _ratio(record.price, record.previous_price)
