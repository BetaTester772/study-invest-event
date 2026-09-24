"""서비스 공용: 도메인 오류, 파라미터 조회, 감사 로그, 가격 조회."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..instruments import INSTRUMENTS
from ..models import AuditLog, Holding, MarketDay, ParamsRecord, Participant, PriceHistory
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


# --- 동시성: 잠금 ------------------------------------------------------------------

BATCH_LOCK_KEY = 7_720_261_006
"""배치(공시·정산·수동 가격) 직렬화용 PostgreSQL advisory lock 키."""


def batch_lock(s: Session, *, wait: bool = True) -> bool:
    """트랜잭션 범위 advisory lock. 여러 워커·레플리카의 배치가 겹치지 않게 한다.

    wait=False면 다른 프로세스가 잡고 있을 때 바로 False를 돌려준다(스케줄러용).
    같은 세션 안에서는 재진입 가능하다. PostgreSQL 외(테스트용 SQLite)에서는 항상 True.
    """
    if s.get_bind().dialect.name != "postgresql":
        return True
    if wait:
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": BATCH_LOCK_KEY})
        return True
    return bool(s.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": BATCH_LOCK_KEY}))


def lock_market_day(s: Session, day: date, *, shared: bool) -> MarketDay | None:
    """운영일 행을 잠그고 최신 값으로 읽는다.

    주문은 공유 잠금(FOR SHARE), 정산은 배타 잠금(FOR UPDATE)을 잡는다. 그래서 정산은 진행 중인
    주문이 끝날 때까지 기다린 뒤 집계하고, 정산 이후 주문은 settled_at을 보고 거부된다.
    """
    return s.scalars(
        select(MarketDay)
        .where(MarketDay.day == day)
        .with_for_update(read=shared)
        .execution_options(populate_existing=True)
    ).first()


# --- 참가자 자산 변경 -------------------------------------------------------------


def lock_participant(s: Session, participant_id: int) -> Participant:
    """참가자 행을 FOR UPDATE로 잠그고 최신 값(현금·보유)으로 다시 읽는다.

    참가자의 현금·보유를 바꾸는 모든 경로(주문 체결, 인증 보상)는 반드시 이 함수를 먼저
    거친다. 그래서 어떤 두 변경도 같은 참가자에 대해 동시에 진행되지 않고, 요청 초반에 읽은
    오래된 값 위에 덮어쓰지 않는다. (SQLite는 잠금이 없어 직렬화만 보장되지 않는다.)
    """
    participant = s.scalars(
        select(Participant)
        .where(Participant.id == participant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    # 보유 행도 잠금 이후 값으로 다시 읽는다. 세션에 이미 있던 Holding 객체는 그냥 조회하면
    # 옛 값이 그대로 돌아오므로(identity map) populate_existing으로 덮어쓴다.
    s.scalars(
        select(Holding)
        .where(Holding.participant_id == participant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    s.expire(participant, ["holdings"])  # 컬렉션 목록(새로 생긴 종목 포함)도 다시 구성
    return participant


def holding_of(participant: Participant, code: str) -> Holding:
    """잠근 참가자의 종목 보유 행. 없으면 수량 0으로 만든다(같은 세션에서 중복 생성 없음)."""
    for holding in participant.holdings:
        if holding.code == code:
            return holding
    holding = Holding(code=code, quantity=0, cost=0)
    participant.holdings.append(holding)
    return holding


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
