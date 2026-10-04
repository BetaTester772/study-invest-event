"""고정 상수 및 관리자 조정 파라미터 (02-parameters)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import date, time, timedelta, timezone
from fractions import Fraction

from .money import PRICE_UNIT

# --- 고정 상수 (02-parameters §1) -------------------------------------------------

KST = timezone(timedelta(hours=9), "KST")
"""운영 시간대. 한국은 서머타임이 없으므로 고정 오프셋으로 충분하다."""

INITIAL_CASH = 1_000_000
"""초기 시드(원). 중도 참가자도 동일."""

EVENT_START = date(2026, 10, 6)
EVENT_END = date(2026, 10, 16)

MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(18, 0)

# --- 수치 한계 -------------------------------------------------------------------
# 모든 가격·수량·금액이 DB의 BIGINT(최대 약 9.2×10^18)와 정수 연산 범위 안에 머물도록 하는 상한.
# 가격 × 수량 ≤ PRICE_MAX × QUANTITY_MAX = 10^18 이므로 한 주문의 금액도 BIGINT를 넘지 않는다.
PRICE_MAX = 1_000_000_000
"""모든 가격의 상한(10억 원). 가격 산정 결과·수동 개입가·가격 파라미터에 적용."""
QUANTITY_MAX = 1_000_000_000
"""한 주문 수량의 상한."""
REWARD_CASH_MAX = 100_000_000
"""인증 1건당 보상 현금 상한(1억 원). 매일 받아 최저가 종목에 넣고 그 종목이 PRICE_MAX까지 올라도
현금·평가금액이 BIGINT 안에 머문다."""
AMOUNT_MAX = 10**15
"""금액 파라미터(가상 유동성 등)의 상한."""
COIN_CAP_MAX = 10.0
"""코인 일일 상승 상한 파라미터의 최대값(+1000%)."""
CALM_ROUNDS_MAX = 100
"""코인 초반 안정기 회차 수 파라미터의 최대값."""
STOCK_NOISE_MAX = 2.0
"""주식 매수지분 잡음 세기 τ 파라미터의 최대값."""

STOCK_DAILY_LIMIT = Fraction(3, 10)
"""주식 일일 변동률 한계 ±30% (SPEC-STOCK-2). 감도 계수와 별개로 고정."""


# --- 관리자 조정 파라미터 (02-parameters §2, F-11) -------------------------------


@dataclass(frozen=True)
class EventParams:
    """관리자 조정 파라미터. 기본값은 규격서 기본값이며 F-13 시뮬레이션으로 확정한다."""

    # 병더리움 (03-pricing §1)
    coin_p_up: float = 0.30
    """상승일 발생 확률."""
    coin_up_exp: float = 2
    """상승폭 지수: 변동률 = cap × X^up_exp."""
    coin_down_exp: float = 2
    """하락폭 지수: 변동률 = floor × X^down_exp."""
    coin_cap: float = 0.80
    """상승일 최대 변동률(+80%)."""
    coin_floor: float = -0.40
    """하락일 최대 변동률(-40%). 상한과 함께 줄여 로그 기대값을 0 근처(약 -0.004)로 유지한다."""
    coin_price_cap: int | None = 5_000_000
    """코인 운영상 표시 상한(원, 권장). None이면 상한 없음."""
    coin_calm_rounds: int = 3
    """초반 안정기 회차 수. 1회차부터 이 회차까지는 안정기 상·하한을 쓴다. 0이면 안정기 없음."""
    coin_calm_cap: float = 0.30
    """안정기 상승일 최대 변동률(+30%)."""
    coin_calm_floor: float = -0.10
    """안정기 하락일 최대 변동률(-10%)."""

    # 주식 (03-pricing §2, 06-abuse-risk §1)
    stock_sensitivity: float = 0.30
    """감도 계수: 변동률 = 계수 × (1 − rᵢ), ±30% 클램프."""
    stock_min_price: int = 1_000
    """주식 최저가 하한(원)."""
    virtual_liquidity: int = 5_000_000
    """종목별 가상 유동성 L(원). Bᵢ′ = Bᵢ + L."""
    stock_noise_scale: float = 0.10
    """매수지분 잡음 세기 τ: Bᵢ″ = Bᵢ′ × exp(τ·(Gᵢ − γ)), Gᵢ ~ Gumbel(0, 1). 0이면 잡음 없음
    (변동률이 당일 매수만으로 결정된다). 0.1이면 매수가 전혀 없을 때 종목당 대략 ±5%(5~95%)."""

    # 거래 (04-trading §2)
    daily_buy_limit_ratio: float = 0.40
    """1일 1종목 매수 상한(총자산 대비 비율)."""

    # 인증 (05-certification)
    reward_cash: int = INITIAL_CASH // 4
    """승인된 인증 1건당 지급하는 현금(원). 기본은 시드의 1/4인 250,000원(2026-10-01 결정)."""
    certification_cutoff: time = field(default=time(23, 59))
    """인증 접수 마감 시각. 해당 분(分)까지 당일로 집계한다."""

    # 부정 대응 (06-abuse-risk §2)
    verified_only_trading: bool = False
    """켜면 인증된 참가자(학교 메일 코드 또는 관리자 확인)만 주문할 수 있다. 평소에는 끄고,
    이벤트 중 부정 행위가 보이면 관리자가 켠다."""

    def __post_init__(self) -> None:
        floats = {
            "coin_p_up": self.coin_p_up,
            "coin_up_exp": self.coin_up_exp,
            "coin_down_exp": self.coin_down_exp,
            "coin_cap": self.coin_cap,
            "coin_floor": self.coin_floor,
            "coin_calm_cap": self.coin_calm_cap,
            "coin_calm_floor": self.coin_calm_floor,
            "stock_sensitivity": self.stock_sensitivity,
            "stock_noise_scale": self.stock_noise_scale,
            "daily_buy_limit_ratio": self.daily_buy_limit_ratio,
        }
        for name, value in floats.items():  # NaN·Infinity는 모든 계산을 깨뜨린다
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")

        def price_ok(v: int) -> bool:
            return PRICE_UNIT <= v <= PRICE_MAX and v % PRICE_UNIT == 0

        checks = [
            (0 < self.coin_p_up < 1, "coin_p_up must be in (0, 1)"),
            (0 < self.coin_up_exp <= 100, "coin_up_exp must be in (0, 100]"),
            (0 < self.coin_down_exp <= 100, "coin_down_exp must be in (0, 100]"),
            (0 < self.coin_cap <= COIN_CAP_MAX, f"coin_cap must be in (0, {COIN_CAP_MAX:g}]"),
            (-1 < self.coin_floor < 0, "coin_floor must be in (-1, 0)"),
            (
                self.coin_price_cap is None or price_ok(self.coin_price_cap),
                f"coin_price_cap must be a multiple of 10 in [10, {PRICE_MAX:,}] or None",
            ),
            # 안정기 상·하한은 평소 상·하한과 따로 검사한다. 저장된 파라미터가 서로 엇갈려도
            # (예: 평소 상한을 안정기보다 낮춤) 파라미터를 읽지 못해 배치가 멈추는 일은 없어야 한다.
            (
                0 <= self.coin_calm_rounds <= CALM_ROUNDS_MAX,
                f"coin_calm_rounds must be in [0, {CALM_ROUNDS_MAX}]",
            ),
            (
                0 < self.coin_calm_cap <= COIN_CAP_MAX,
                f"coin_calm_cap must be in (0, {COIN_CAP_MAX:g}]",
            ),
            (-1 < self.coin_calm_floor < 0, "coin_calm_floor must be in (-1, 0)"),
            (0 < self.stock_sensitivity <= 10, "stock_sensitivity must be in (0, 10]"),
            (
                0 <= self.stock_noise_scale <= STOCK_NOISE_MAX,
                f"stock_noise_scale must be in [0, {STOCK_NOISE_MAX:g}]",
            ),
            (
                price_ok(self.stock_min_price),
                f"stock_min_price must be a multiple of 10 in [10, {PRICE_MAX:,}]",
            ),
            (
                0 <= self.virtual_liquidity <= AMOUNT_MAX,
                f"virtual_liquidity must be in [0, {AMOUNT_MAX:,}]",
            ),
            (0 < self.daily_buy_limit_ratio <= 1, "daily_buy_limit_ratio must be in (0, 1]"),
            (
                0 <= self.reward_cash <= REWARD_CASH_MAX,
                f"reward_cash must be in [0, {REWARD_CASH_MAX:,}]",
            ),
        ]
        for ok, message in checks:
            if not ok:
                raise ValueError(message)

    # --- 직렬화 (DB 저장·API) ---------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            f.name: (
                getattr(self, f.name).strftime("%H:%M")
                if f.name == "certification_cutoff"
                else getattr(self, f.name)
            )
            for f in fields(self)
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EventParams:
        # 모르는 키는 버리고 없는 키는 기본값을 쓴다. 이전 규칙으로 저장된 파라미터(예: v0.3의
        # reward_coin_quantity)도 그대로 읽힌다.
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        cutoff = values.get("certification_cutoff")
        if isinstance(cutoff, str):
            values["certification_cutoff"] = time.fromisoformat(cutoff)
        return cls(**values)  # type: ignore[arg-type]
