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
    VerifyMethod,
)
from ..normalize import (
    normalize_identity,
    normalize_nickname,
    normalize_student_id,
    normalize_text,
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


class SignupInfo(Schema):
    """가입·인증 운영 설정(화면이 가입 폼과 안내를 고른다)."""

    email_verification: bool
    """true면 가입할 때 학교 메일 인증 코드가 필요하다. false면 메일 주소만 받고 미인증으로 가입."""
    verified_only_trading: bool
    """true면 인증된 참가자만 주문할 수 있다(관리자가 부정 대응으로 켠다)."""


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
    signup: SignupInfo


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


# 이름·학번·학과(관리자만 본다). 길이 상한은 DB 컬럼(name 30, student_id 16, department 50) 이내.
Name = Annotated[str, _before(normalize_text), StringConstraints(min_length=1, max_length=30)]
StudentId = Annotated[str, _before(normalize_student_id), StringConstraints(pattern=r"^[0-9]{10}$")]
Department = Annotated[str, _before(normalize_text), StringConstraints(min_length=1, max_length=50)]

# 형식·도메인 검사는 서비스(email_verification.parse)가 업무 오류 코드로 한다.
Email = Annotated[str, StringConstraints(min_length=1, max_length=254)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{6}$")]


class EmailCodeRequest(BaseModel):
    email: Email


class EmailCodeResponse(Schema):
    email: str
    """코드를 보낸 주소. 등록 메일로 보냈으면 가린 주소(k***@g.skku.edu)."""
    expires_in: int
    """코드 유효시간(초)."""
    resend_after: int
    """다시 요청할 수 있을 때까지(초)."""


class RegisterRequest(BaseModel):
    email: Email
    """학교 메일. 메일 인증을 꺼도 받는다(비밀번호 재설정 코드를 받는 주소)."""
    code: Code | None = None
    """학교 메일 인증 코드. 메일 인증을 켠 운영(signup.email_verification)에서만 필요하다."""
    name: Name
    student_id: StudentId
    """숫자 10자리. 한 학번에 한 계정."""
    department: Department
    nickname: Nickname
    password: str = Field(min_length=8, max_length=128)
    privacy_consent: bool
    """개인정보(학교 메일·이름·학번·학과) 수집·이용 동의. true여야 한다."""


class MyEmailCodeRequest(BaseModel):
    email: Email | None = None
    """비우면 등록 메일로 보낸다. 다른 주소로 인증하려면 그 주소."""


class VerifyEmailRequest(BaseModel):
    """학교 메일 코드 인증. 보통은 코드만 보낸다(등록 메일로 받은 코드).

    email: 다른 주소로 코드를 받았으면 그 주소(인증하면 등록 메일이 그 주소로 바뀐다).
    이름·학번·학과·동의는 그 정보가 없는 계정(Participant.needs_profile, 메일 인증 도입 전
    가입)만 함께 보낸다.
    """

    email: Email | None = None
    code: Code
    name: Name | None = None
    student_id: StudentId | None = None
    department: Department | None = None
    privacy_consent: bool = False


class PasswordResetCodeRequest(BaseModel):
    identity: Identity
    """학번(학교 메일도 받는다). 코드는 그 계정의 등록 메일로만 간다."""


class PasswordResetVerifyRequest(BaseModel):
    identity: Identity
    """코드를 요청할 때와 같은 학번(또는 학교 메일)."""
    code: Code


class PasswordResetRequest(BaseModel):
    identity: Identity
    """코드를 요청할 때와 같은 학번(또는 학교 메일)."""
    code: Code
    password: str = Field(min_length=8, max_length=128)
    """새 비밀번호."""


class LoginRequest(BaseModel):
    identity: Identity
    """학번(숫자 10자리). 학교 메일(@skku.edu·@g.skku.edu)이나 메일 인증 도입 전 식별자도 받는다."""
    password: str = Field(min_length=1, max_length=128)


class Participant(Schema):
    id: int
    nickname: str
    status: ParticipantStatus
    joined_at: datetime
    masked_email: str | None
    """가린 등록 메일(k***@g.skku.edu). 본인 응답에도 전체 주소는 싣지 않는다. 없으면 null."""
    verified: bool
    """인증(학교 메일 코드 또는 관리자 확인)을 마쳤는지. signup.verified_only_trading이면 false인
    동안 주문할 수 없다."""
    email_verified: bool
    """학교 메일 코드로 인증했다(등록 메일이 본인 것으로 확인됨). false면 메일 인증을 할 수 있다
    (미인증이거나 관리자 인증만 받은 계정)."""
    needs_profile: bool
    """이름·학번·학과가 없다(메일 인증 도입 전 계정). 인증할 때 함께 받는다."""


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
    identity: str | None
    """메일 인증 도입 전 식별자. 그 뒤 가입한 참가자는 null."""
    email: str | None
    """등록 학교 메일 전체 주소(코드를 보내는 주소). 관리자만 본다."""
    name: str | None
    student_id: str | None
    department: str | None
    """이름·학번·학과. 재인증 전 계정이거나 이벤트 후 파기했으면 null."""
    verified_at: datetime | None
    verified_via: VerifyMethod | None
    """email(학교 메일 코드) 또는 admin(관리자 확인). 미인증이면 null."""
    cash: int
    total_assets: int
    principal: int
    """투입 원금 = 시드 + 받은 인증 보상."""
    return_rate: float
    """(total_assets − principal) / principal."""
    rejected_certifications: int
    approved_certifications: int


class ParticipantPatch(BaseModel):
    """바꿀 항목만 보낸다."""

    status: ParticipantStatus | None = None
    verified: bool | None = None
    """true면 관리자 인증 처리, false면 인증 취소."""


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
    stock_noise_scale: float
    """매수지분 잡음 세기 τ(0~2). 0이면 잡음 없이 당일 매수만으로 변동률을 정한다."""
    daily_buy_limit_ratio: float
    reward_cash: int
    certification_cutoff: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    verified_only_trading: bool | None = None
    """인증된 참가자만 거래. null이면 현재 값 유지(바꾸려면 PUT /api/admin/trading-access)."""

    @field_validator("certification_cutoff")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        time.fromisoformat(v)
        return v


class TradingAccess(BaseModel):
    verified_only: bool
    """true면 인증된 참가자만 주문할 수 있다."""


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
    noise_factor: float | None = None
    """매수지분 잡음 배수 exp(τ·(G − γ)). 잡음 없음(τ = 0)이거나 도입 전 기록이면 None."""
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
