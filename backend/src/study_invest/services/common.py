"""서비스 공용: 도메인 오류, 파라미터 조회, 감사 로그, 가격 조회."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..instruments import INSTRUMENTS
from ..models import AuditLog, MarketDay, ParamsRecord, Participant, PriceHistory
from ..params import EventParams


class DomainError(Exception):
    """API에서 `{"detail": {"code", "message"}}`로 변환되는 업무 오류."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def audit(s: Session, now: datetime, actor: str, action: str, **detail: Any) -> None:
    s.add(AuditLog(at=now, actor=actor, action=action, detail=detail))


# --- 파라미터 ------------------------------------------------------------------


def get_params(s: Session) -> EventParams:
    record = s.scalars(select(ParamsRecord).order_by(ParamsRecord.id.desc()).limit(1)).first()
    return EventParams.from_dict(record.values) if record else EventParams()


def set_params(s: Session, params: EventParams, now: datetime, actor: str = "admin") -> EventParams:
    before = get_params(s).to_dict()
    after = params.to_dict()
    s.add(ParamsRecord(values=after, created_at=now))
    changed = {k: [before[k], v] for k, v in after.items() if before.get(k) != v}
    audit(s, now, actor, "params.update", changed=changed)
    return params


# --- 장 상태·가격 -----------------------------------------------------------------


def market_day(s: Session, day: date) -> MarketDay | None:
    return s.get(MarketDay, day)


def latest_opened_day(s: Session) -> date | None:
    return s.scalar(select(func.max(MarketDay.day)))


def prices_on(s: Session, day: date) -> dict[str, int]:
    rows = s.scalars(select(PriceHistory).where(PriceHistory.day == day))
    return {r.code: r.price for r in rows}


def current_prices(s: Session) -> tuple[date | None, dict[str, int]]:
    """최신 공시일과 그날 시작가. 공시 전이면 (None, 1일차 시작가)."""
    day = latest_opened_day(s)
    if day is None:
        return None, {i.code: i.initial_price for i in INSTRUMENTS}
    return day, prices_on(s, day)


def total_assets(participant: Participant, prices: dict[str, int]) -> int:
    return participant.cash + sum(h.quantity * prices[h.code] for h in participant.holdings)
