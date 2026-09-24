"""ORM 모델 (01-data-model §2).

시각은 모두 UTC로 저장하고 aware datetime으로 돌려준다(AwareDateTime).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class AwareDateTime(TypeDecorator[datetime]):
    """aware datetime을 UTC naive로 저장하고, 읽을 때 UTC aware로 복원한다."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


BIGINT_MIN = -(2**63)
BIGINT_MAX = 2**63 - 1
"""BigInteger 컬럼이 담을 수 있는 범위. API 입력은 이 범위 밖을 받지 않는다."""


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class ParticipantStatus(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    DISQUALIFIED = "disqualified"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"


class RejectReason(StrEnum):
    MARKET_CLOSED = "MARKET_CLOSED"
    MARKET_NOT_OPENED = "MARKET_NOT_OPENED"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_HOLDINGS = "INSUFFICIENT_HOLDINGS"
    DAILY_BUY_LIMIT = "DAILY_BUY_LIMIT"
    DISQUALIFIED = "DISQUALIFIED"


REJECT_MESSAGES: dict[RejectReason, str] = {
    RejectReason.MARKET_CLOSED: "주문 접수 시간(09:00–18:00)이 아닙니다.",
    RejectReason.MARKET_NOT_OPENED: "오늘 시작가가 아직 공시되지 않았습니다.",
    RejectReason.INVALID_QUANTITY: "수량은 1 이상의 정수여야 합니다.",
    RejectReason.UNKNOWN_INSTRUMENT: "존재하지 않는 종목입니다.",
    RejectReason.INSUFFICIENT_CASH: "현금 잔고가 부족합니다.",
    RejectReason.INSUFFICIENT_HOLDINGS: "보유 수량이 부족합니다.",
    RejectReason.DAILY_BUY_LIMIT: "1일 1종목 매수 상한(총자산의 일정 비율)을 초과합니다.",
    RejectReason.DISQUALIFIED: "실격 처리된 참가자는 거래할 수 없습니다.",
}


class CertStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PriceSource(StrEnum):
    INITIAL = "initial"
    SETTLEMENT = "settlement"
    CARRY_OVER = "carry_over"
    MANUAL = "manual"


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity: Mapped[str] = mapped_column(String(128), unique=True)
    """정규화된 1인 1계정 식별자."""
    nickname: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    cash: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[ParticipantStatus] = mapped_column(
        _enum(ParticipantStatus), default=ParticipantStatus.NORMAL
    )
    joined_at: Mapped[datetime] = mapped_column(AwareDateTime())

    holdings: Mapped[list[Holding]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())


class Holding(Base):
    __tablename__ = "holdings"

    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    quantity: Mapped[int] = mapped_column(BigInteger, default=0)
    cost: Mapped[int] = mapped_column(BigInteger, default=0)
    """매입금액 합계(원). 평균단가 = cost / quantity. 보상 코인은 0원으로 편입."""

    participant: Mapped[Participant] = relationship(back_populates="holdings")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    side: Mapped[Side] = mapped_column(_enum(Side))
    quantity: Mapped[int] = mapped_column(BigInteger)
    price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus))
    reject_reason: Mapped[RejectReason | None] = mapped_column(_enum(RejectReason), nullable=True)
    trade_day: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())


class MarketDay(Base):
    """운영일별 배치 상태. 09:00 공시 시 생성, 18:00 정산 시 settled_at 기록."""

    __tablename__ = "market_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    opened_at: Mapped[datetime] = mapped_column(AwareDateTime())
    settled_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)


class PriceHistory(Base):
    __tablename__ = "price_history"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    price: Mapped[int] = mapped_column(BigInteger)
    previous_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[PriceSource] = mapped_column(_enum(PriceSource))
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())


class SettlementLog(Base):
    __tablename__ = "settlement_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_no: Mapped[int] = mapped_column(BigInteger)
    trade_day: Mapped[date] = mapped_column(Date, unique=True)
    effective_day: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())
    stocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    coin: Mapped[dict[str, Any]] = mapped_column(JSON)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)


class StudyCertification(Base):
    __tablename__ = "certifications"
    __table_args__ = (UniqueConstraint("participant_id", "target_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """저장 파일명(upload_dir 기준). 개인정보 삭제 후 None."""
    image_content_type: Mapped[str] = mapped_column(String(64))
    image_hash: Mapped[str] = mapped_column(String(64), index=True)
    duplicate_of: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[CertStatus] = mapped_column(_enum(CertStatus), default=CertStatus.PENDING)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(AwareDateTime())
    reviewed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    rewarded_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    reward_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    participant: Mapped[Participant] = relationship()


class ParamsRecord(Base):
    """관리자 파라미터 변경 이력. 가장 최근 행이 현재값."""

    __tablename__ = "params_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())


class AuditLog(Base):
    """주문·정산·지급·관리자 조치 이력 (F-09)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(AwareDateTime(), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
