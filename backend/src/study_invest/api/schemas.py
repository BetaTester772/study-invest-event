"""요청·응답 스키마 (docs/dev/api.md)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ..event_calendar import to_kst
from ..models import (
    CertStatus,
    OrderStatus,
    ParticipantStatus,
    PriceSource,
    RejectReason,
    Side,
)


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _kst(self, value: Any) -> Any:
        return to_kst(value).isoformat() if isinstance(value, datetime) else value


# --- 공개 ---------------------------------------------------------------------


class MarketInfo(Schema):
    is_open: bool
    opens_at: str
    closes_at: str
    day_opened: bool
    day_settled: bool
    round: int | None


class CertificationInfo(Schema):
    cutoff: str
    target_date: date
    reward_coin_quantity: int


class EventInfo(Schema):
    start: date
    end: date
    operating_days: list[date]
    total_rounds: int
    now: datetime
    today: date
    is_operating_day: bool
    market: MarketInfo
    certification: CertificationInfo
    initial_cash: int
    daily_buy_limit_ratio: float


class Instrument(Schema):
    code: str
    name: str
    alias: str
    kind: Literal["stock", "coin"]
    price: int
    previous_price: int | None
    change_rate: float | None
    day: date | None


class PricePoint(Schema):
    day: date
    price: int
    change_rate: float | None
    source: PriceSource


class RankingEntry(Schema):
    rank: int
    nickname: str
    total_assets: int
    return_rate: float
    certified_days: int
    streak: int
    is_me: bool = False


class Ranking(Schema):
    day: date | None
    entries: list[RankingEntry]


# --- 인증 ---------------------------------------------------------------------


class RegisterRequest(BaseModel):
    identity: str = Field(min_length=1, max_length=128)
    nickname: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("identity", "nickname")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("공백만 입력할 수 없습니다.")
        return v


class LoginRequest(BaseModel):
    identity: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class Participant(Schema):
    id: int
    nickname: str
    status: ParticipantStatus
    joined_at: datetime


class AuthResponse(Schema):
    token: str
    participant: Participant


# --- 참가자 ---------------------------------------------------------------------


class HoldingView(Schema):
    code: str
    name: str
    kind: Literal["stock", "coin"]
    quantity: int
    avg_price: int
    price: int
    value: int
    cost: int
    profit: int
    profit_rate: float | None


class BuyLimit(Schema):
    ratio: float
    limit_amount: int
    remaining: dict[str, int]


class Portfolio(Schema):
    cash: int
    holdings: list[HoldingView]
    holdings_value: int
    total_assets: int
    initial_cash: int
    return_rate: float
    day: date | None
    buy_limit: BuyLimit


class OrderRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    side: Side
    quantity: int = Field(strict=True)


class Order(Schema):
    id: int
    code: str
    side: Side
    quantity: int
    price: int | None
    amount: int | None
    status: OrderStatus
    reject_reason: RejectReason | None
    reject_message: str | None
    trade_day: date | None
    created_at: datetime


class Certification(Schema):
    id: int
    target_date: date
    status: CertStatus
    reject_reason: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    rewarded_at: datetime | None
    reward_quantity: int | None
    image_url: str | None


# --- 관리자 ---------------------------------------------------------------------


class AdminParticipant(Participant):
    identity: str
    cash: int
    total_assets: int
    rejected_certifications: int
    approved_certifications: int


class ParticipantPatch(BaseModel):
    status: ParticipantStatus


class AdminCertification(Certification):
    participant_id: int
    nickname: str
    image_hash: str
    duplicate_of: int | None


class ReviewRequest(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=500)


class Params(Schema):
    coin_p_up: float
    coin_up_exp: float
    coin_down_exp: float
    coin_cap: float
    coin_floor: float
    coin_price_cap: int | None
    stock_sensitivity: float
    stock_min_price: int
    virtual_liquidity: int
    daily_buy_limit_ratio: float
    reward_coin_quantity: int
    certification_cutoff: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("certification_cutoff")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        time.fromisoformat(v)
        return v


class ManualPriceRequest(BaseModel):
    price: int = Field(strict=True)
    reason: str = Field(max_length=500)


class BatchRequest(BaseModel):
    day: date | None = None


class BatchResult(Schema):
    action: str
    day: date
    detail: dict[str, Any]


class StockSettlement(Schema):
    code: str
    buy_amount: int
    adjusted_amount: int
    concentration: float | None
    rate: float
    old_price: int
    new_price: int


class CoinSettlement(Schema):
    p: float
    x: float
    direction: Literal["up", "down"]
    rate: float
    old_price: int
    new_price: int


class SettlementLog(Schema):
    id: int
    round: int
    trade_day: date
    effective_day: date
    created_at: datetime
    stocks: list[StockSettlement]
    coin: CoinSettlement
    params: Params


class AuditEntry(Schema):
    id: int
    at: datetime
    actor: str
    action: str
    detail: dict[str, Any]


class SimulateRequest(BaseModel):
    paths: int = Field(default=10_000, ge=1, le=100_000)
    rounds: int = Field(default=10, ge=1, le=100)
    seed: int | None = None
    use_price_cap: bool = False
