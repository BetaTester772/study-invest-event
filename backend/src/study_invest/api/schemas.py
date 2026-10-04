"""요청·응답 스키마 (docs/dev/api.md)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

from ..event_calendar import to_kst
from ..models import (
    BIGINT_MAX,
    BIGINT_MIN,
    CertStatus,
    OrderStatus,
    ParticipantStatus,
    PriceSource,
    RejectReason,
    Side,
)
from ..normalize import normalize_identity, normalize_nickname


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
    reward_cash: int
    """승인 1건당 다음 운영일 09:00에 지급하는 현금(원)."""


class CoinInfo(Schema):
    """병더리움 하루 변동폭(참가자 안내용). 실제 값은 정산 때의 파라미터를 따른다."""

    cap: float
    """평소 상승일 최대 변동률(2.0 = +200%)."""
    floor: float
    """평소 하락일 최대 변동률(-0.4 = -40%)."""
    calm_rounds: int
    """초반 안정기 회차 수(이벤트 회차 수 이내). 0이면 안정기 없음."""
    calm_until: date | None
    """안정기 마지막 회차가 반영되는 운영일. 그날 시작가까지 좁게 움직인다."""
    calm_cap: float
    calm_floor: float


class ClockInfo(Schema):
    """테스트 시계(STUDY_INVEST_TIME_*) 안내용 실제 시각."""

    scale: float
    """배속. 24면 실제 1시간이 이벤트 하루."""
    real_now: datetime
    next_open_at: datetime | None
    """다음 운영일 09:00(공시·주문 시작)이 되는 실제 시각. 남은 운영일이 없으면 null."""
    next_close_at: datetime | None
    """다음 운영일 18:00(장 마감·정산)이 되는 실제 시각. 남은 운영일이 없으면 null."""


class EventInfo(Schema):
    start: date
    end: date | None
    """무제한 모드(QA)면 null."""
    operating_days: list[date]
    """운영일 목록. 무제한 모드면 시작일부터 오늘·최신 공시일 중 늦은 날까지만."""
    total_rounds: int | None
    """무제한 모드면 null."""
    now: datetime
    today: date
    is_operating_day: bool
    market: MarketInfo
    certification: CertificationInfo
    coin: CoinInfo
    initial_cash: int
    daily_buy_limit_ratio: float
    clock: ClockInfo | None = None
    """테스트 시계로 돌 때만 채운다. 실제 시계(운영)면 null."""


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
    """총자산 순위(1~3위 시상). 동점은 공동 순위."""
    nickname: str
    total_assets: int
    principal: int
    """투입 원금 = 시드 + 받은 인증 보상."""
    profit: int
    """투자 손익 = total_assets − principal."""
    return_rate: float
    """profit / principal."""
    return_rank: int
    """수익률 순위(높은 순). 동점은 공동 순위."""
    certified_days: int
    streak: int
    is_me: bool = False


class Ranking(Schema):
    day: date | None
    entries: list[RankingEntry]


# --- 인증 ---------------------------------------------------------------------


def _before(fn: Callable[[str], str]) -> BeforeValidator:
    """문자열이면 정규화한 뒤 길이 등 제약을 검사한다(타입 오류는 pydantic에 맡김)."""
    return BeforeValidator(lambda v: fn(v) if isinstance(v, str) else v)


# 정규화 → 길이 검사 순서. 길이 상한은 DB 컬럼(participants.identity 128, nickname 32) 이내.
Identity = Annotated[
    str, _before(normalize_identity), StringConstraints(min_length=1, max_length=128)
]
Nickname = Annotated[
    str, _before(normalize_nickname), StringConstraints(min_length=2, max_length=20)
]


class RegisterRequest(BaseModel):
    identity: Identity
    nickname: Nickname
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    identity: Identity
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
    rewards_received: int
    """지금까지 받은 인증 보상 현금 합계."""
    principal: int
    """투입 원금 = initial_cash + rewards_received."""
    profit: int
    """투자 손익 = total_assets − principal."""
    return_rate: float
    """profit / principal."""
    day: date | None
    buy_limit: BuyLimit


class OrderRequest(BaseModel):
    # 저장 가능한 값만 받는다: 코드는 orders.code(16자), 수량은 orders.quantity(BIGINT) 범위.
    # 범위 안의 잘못된 수량(0, 음수, 상한 초과)은 거부 주문으로 기록된다(INVALID_QUANTITY).
    code: str = Field(min_length=1, max_length=16)
    side: Side
    quantity: int = Field(strict=True, ge=BIGINT_MIN, le=BIGINT_MAX)


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
    reward_cash: int | None
    image_url: str | None


class CertificationStatus(Schema):
    target_date: date
    cutoff: str
    can_submit: bool
    reason: Literal["DISQUALIFIED", "OUTSIDE_EVENT", "ALREADY_CERTIFIED"] | None
    message: str | None
    existing: Certification | None


# --- 관리자 ---------------------------------------------------------------------


class AdminParticipant(Participant):
    identity: str
    cash: int
    total_assets: int
    principal: int
    """투입 원금 = 시드 + 받은 인증 보상."""
    return_rate: float
    """(total_assets − principal) / principal."""
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
    coin_calm_rounds: int
    coin_calm_cap: float
    coin_calm_floor: float
    stock_sensitivity: float
    stock_min_price: int
    virtual_liquidity: int
    daily_buy_limit_ratio: float
    reward_cash: int
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


class QaStatus(Schema):
    enabled: bool


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
    calm: bool = False
    """초반 안정기 상·하한으로 뽑았는지. 안정기 도입(v0.4) 전 기록은 false."""


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
    # 입력 한계는 여기 한 곳에만 둔다. 화면은 GET /api/admin/simulate/options로 받아 쓴다.
    paths: int = Field(default=10_000, ge=1, le=100_000)
    rounds: int = Field(default=10, ge=1, le=100)
    seed: int | None = None
    use_price_cap: bool = False


class IntRange(Schema):
    min: int
    max: int
    default: int


class SimulateOptions(Schema):
    paths: IntRange
    rounds: IntRange


def int_range(model: type[BaseModel], field: str) -> IntRange:
    """모델 필드의 ge/le 제약과 기본값을 그대로 꺼낸다(한계를 한 곳에서만 정의)."""
    info = model.model_fields[field]
    bounds: dict[str, int] = {}
    for meta in info.metadata:
        if getattr(meta, "ge", None) is not None:
            bounds["min"] = meta.ge
        if getattr(meta, "le", None) is not None:
            bounds["max"] = meta.le
    return IntRange(min=bounds["min"], max=bounds["max"], default=info.default)
