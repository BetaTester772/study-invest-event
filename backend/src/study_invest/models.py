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
from .normalize import mask_email


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


class VerifyMethod(StrEnum):
    EMAIL = "email"
    """학교 메일 인증 코드."""
    ADMIN = "admin"
    """관리자가 확인(메일 인증을 끈 운영)."""


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
    identity: Mapped[str | None] = mapped_column(String(128), unique=True)
    """메일 인증 도입 전에 쓰던 자유 입력 식별자(정규화됨). 그 뒤 가입한 참가자는 None."""
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    """학교 메일의 1인 1계정 키(normalize.SchoolEmail.canonical, ID@g.skku.edu). 메일 인증을 끈
    운영에서는 확인하지 않은 채 저장된다. 이벤트 후 파기하면 None."""
    email_address: Mapped[str | None] = mapped_column(String(254))
    """인증·재설정 코드를 보내는 주소(입력한 도메인 그대로). skku.edu와 g.skku.edu는 같은 ID여도
    메일함이 다를 수 있어 키(email)와 따로 둔다. 이벤트 후 파기하면 None."""
    verified_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    """인증 시각(학교 메일 코드 또는 관리자 확인). None이면 미인증이라, 관리자가 '인증된 참가자만
    거래'(EventParams.verified_only_trading)를 켜면 주문할 수 없다."""
    verified_via: Mapped[VerifyMethod | None] = mapped_column(_enum(VerifyMethod))
    """어떻게 인증됐는지(email·admin)."""
    name: Mapped[str | None] = mapped_column(String(30))
    """실명. 메일 인증 도입 전 계정은 재인증할 때 받는다. 이벤트 후 파기하면 None."""
    student_id: Mapped[str | None] = mapped_column(String(16), unique=True)
    """학번(숫자 10자리). 한 학번에 한 계정. 이벤트 후 파기하면 None."""
    department: Mapped[str | None] = mapped_column(String(50))
    """학과. 이벤트 후 파기하면 None."""
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

    @property
    def verified(self) -> bool:
        return self.verified_at is not None

    @property
    def masked_email(self) -> str | None:
        """본인에게 보여 주는 가린 등록 메일(k***@g.skku.edu)."""
        return mask_email(self.email_address) if self.email_address else None

    @property
    def email_verified(self) -> bool:
        """학교 메일 코드로 인증했다(등록 메일이 본인 것으로 확인됨). 관리자 인증과 구분."""
        return self.verified_via == VerifyMethod.EMAIL

    @property
    def needs_profile(self) -> bool:
        """이름·학번·학과가 없다(메일 인증 도입 전 계정, 또는 이벤트 후 파기)."""
        return self.student_id is None


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())


class CodePurpose(StrEnum):
    VERIFY = "verify"
    """참가 신청·재인증(아직 아무 계정도 쓰지 않은 학교 메일)."""
    RESET_PASSWORD = "reset_password"
    """비밀번호 재설정(이미 가입한 학교 메일)."""


class EmailVerification(Base):
    """학교 메일 인증 코드. 코드는 해시로만 저장한다. 메일별로 가장 최근 코드만 유효하다."""

    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    """1인 1계정 키(normalize.SchoolEmail.canonical)."""
    purpose: Mapped[CodePurpose] = mapped_column(
        _enum(CodePurpose), default=CodePurpose.VERIFY, server_default=CodePurpose.VERIFY.value
    )
    """코드 용도. 다른 용도로 받은 코드는 쓸 수 없다."""
    requested_by: Mapped[int | None] = mapped_column(index=True)
    """로그인한 참가자가 요청했으면 그 id(계정 기준 재요청 대기·한도). 가입·재설정 요청은 None."""
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), index=True)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime())
    attempts: Mapped[int] = mapped_column(default=0)
    """틀린 코드 입력 횟수."""
    consumed_at: Mapped[datetime | None] = mapped_column(AwareDateTime())


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
    reward_cash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    """지급한 보상 현금(원). 참가자의 투입 원금(수익률의 분모)에 더해진다."""

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
