"""고정 상수 및 관리자 조정 파라미터 (02-parameters)."""

from __future__ import annotations

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

STOCK_DAILY_LIMIT = Fraction(3, 10)
"""주식 일일 변동률 한계 ±30% (SPEC-STOCK-2). 감도 계수와 별개로 고정."""


# --- 관리자 조정 파라미터 (02-parameters §2, F-11) -------------------------------


@dataclass(frozen=True)
class EventParams:
    """관리자 조정 파라미터. 기본값은 규격서 기본값이며 F-13 시뮬레이션으로 확정한다."""

    # 병더리움 (03-pricing §1)
    coin_p_up: float = 0.30
    """상승일 발생 확률."""
    coin_up_exp: float = 3
    """상승폭 지수: 변동률 = cap × X^up_exp."""
    coin_down_exp: float = 2
    """하락폭 지수: 변동률 = floor × X^down_exp."""
    coin_cap: float = 3.00
    """상승일 최대 변동률(+300%)."""
    coin_floor: float = -0.50
    """하락일 최대 변동률(-50%)."""
    coin_price_cap: int | None = 5_000_000
    """코인 운영상 표시 상한(원, 권장). None이면 상한 없음."""

    # 주식 (03-pricing §2, 06-abuse-risk §1)
    stock_sensitivity: float = 0.30
    """감도 계수: 변동률 = 계수 × (1 − rᵢ), ±30% 클램프."""
    stock_min_price: int = 1_000
    """주식 최저가 하한(원)."""
    virtual_liquidity: int = 5_000_000
    """종목별 가상 유동성 L(원). Bᵢ′ = Bᵢ + L."""

    # 거래 (04-trading §2)
    daily_buy_limit_ratio: float = 0.40
    """1일 1종목 매수 상한(총자산 대비 비율)."""

    # 인증 (05-certification)
    reward_coin_quantity: int = 1
    """승인된 인증 1건당 지급하는 병더리움 수량. 시세와 무관한 수량 고정(2026-09-24 결정)."""
    certification_cutoff: time = field(default=time(23, 59))
    """인증 접수 마감 시각. 해당 분(分)까지 당일로 집계한다."""

    def __post_init__(self) -> None:
        checks = [
            (0 < self.coin_p_up < 1, "coin_p_up must be in (0, 1)"),
            (self.coin_up_exp > 0, "coin_up_exp must be positive"),
            (self.coin_down_exp > 0, "coin_down_exp must be positive"),
            (self.coin_cap > 0, "coin_cap must be positive"),
            (-1 < self.coin_floor < 0, "coin_floor must be in (-1, 0)"),
            (
                self.coin_price_cap is None
                or (self.coin_price_cap >= PRICE_UNIT and self.coin_price_cap % PRICE_UNIT == 0),
                "coin_price_cap must be a positive multiple of 10 or None",
            ),
            (self.stock_sensitivity > 0, "stock_sensitivity must be positive"),
            (
                self.stock_min_price > 0 and self.stock_min_price % PRICE_UNIT == 0,
                "stock_min_price must be a positive multiple of 10",
            ),
            (self.virtual_liquidity >= 0, "virtual_liquidity must be non-negative"),
            (0 < self.daily_buy_limit_ratio <= 1, "daily_buy_limit_ratio must be in (0, 1]"),
            (self.reward_coin_quantity >= 0, "reward_coin_quantity must be non-negative"),
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
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        cutoff = values.get("certification_cutoff")
        if isinstance(cutoff, str):
            values["certification_cutoff"] = time.fromisoformat(cutoff)
        return cls(**values)  # type: ignore[arg-type]
