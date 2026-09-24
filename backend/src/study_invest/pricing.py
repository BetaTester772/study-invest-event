"""가격 산정 알고리즘 (03-pricing).

순수 함수만 둔다. 난수는 호출자가 주입한다(정산 로그에 p, X를 남기기 위해).
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from .money import PRICE_UNIT, exact, round_half_up
from .params import PRICE_MAX, STOCK_DAILY_LIMIT, EventParams

# --- 병더리움 (03-pricing §1) -----------------------------------------------------


@dataclass(frozen=True)
class CoinMove:
    p: float
    """방향 추출 난수 p ~ U(0, 1)."""
    x: float
    """폭 추출 난수 X ~ U(0, 1)."""
    direction: Literal["up", "down"]
    rate: float
    old_price: int
    new_price: int


def coin_rate(p: float, x: float, params: EventParams) -> tuple[Literal["up", "down"], float]:
    """SPEC-COIN-1~4: p < p_up이면 상승일(cap·X^up_exp), 아니면 하락일(floor·X^down_exp)."""
    if not (0.0 <= p < 1.0 and 0.0 <= x <= 1.0):
        raise ValueError("p must be in [0, 1) and x in [0, 1]")
    if p < params.coin_p_up:
        return "up", params.coin_cap * x**params.coin_up_exp
    return "down", params.coin_floor * x**params.coin_down_exp


def next_coin_price(price: int, rate: float, params: EventParams) -> int:
    """P' = round(P × (1 + r), 10원). 표시 상한을 적용하고 [10원, PRICE_MAX]를 보장한다."""
    new = round_half_up(Fraction(price) * (1 + Fraction(rate)))
    cap = params.coin_price_cap if params.coin_price_cap is not None else PRICE_MAX
    return max(PRICE_UNIT, min(new, cap, PRICE_MAX))


def draw_coin(price: int, params: EventParams, rng: random.Random) -> CoinMove:
    """균등난수 두 개(p, X)로 코인 1회 변동을 추출한다."""
    p = rng.random()
    x = rng.random()
    direction, rate = coin_rate(p, x, params)
    return CoinMove(p, x, direction, rate, price, next_coin_price(price, rate, params))


# --- 주식 (03-pricing §2) ---------------------------------------------------------


@dataclass(frozen=True)
class StockMove:
    code: str
    buy_amount: int
    """당일 매수금액 Bᵢ."""
    adjusted_amount: int
    """Bᵢ′ = Bᵢ + L."""
    concentration: Fraction | None
    """쏠림 지수 rᵢ = n·Bᵢ′ / B_total. B_total = 0이면 None."""
    rate: Fraction
    old_price: int
    new_price: int


def stock_rate(concentration: Fraction, sensitivity: float) -> Fraction:
    """변동률 = clamp(계수 × (1 − rᵢ), −30%, +30%)."""
    raw = exact(sensitivity) * (1 - concentration)
    return max(-STOCK_DAILY_LIMIT, min(STOCK_DAILY_LIMIT, raw))


def next_stock_price(price: int, rate: Fraction, min_price: int) -> int:
    """새 가격 = max(하한, round(현재가 × (1 + 변동률), 10원)). PRICE_MAX를 넘지 않는다."""
    return max(min_price, min(round_half_up(Fraction(price) * (1 + rate)), PRICE_MAX))


def settle_stocks(
    prices: Mapping[str, int], buy_amounts: Mapping[str, int], params: EventParams
) -> dict[str, StockMove]:
    """주식 전 종목의 다음 시작가를 산출한다. 기준선은 종목 수(4)로 나눈 평균이다."""
    if not prices:
        return {}
    unknown = set(buy_amounts) - set(prices)
    if unknown:
        raise ValueError(f"buy amounts for unknown stocks: {sorted(unknown)}")
    adjusted = {code: buy_amounts.get(code, 0) + params.virtual_liquidity for code in prices}
    if any(v < 0 for v in adjusted.values()):
        raise ValueError("buy amounts must be non-negative")
    total = sum(adjusted.values())
    n = len(prices)
    moves: dict[str, StockMove] = {}
    for code, price in prices.items():
        if total == 0:  # 03-pricing §2.3: 전 종목 매수 0 → 변동률 0%
            concentration, rate = None, Fraction(0)
        else:
            concentration = Fraction(n * adjusted[code], total)
            rate = stock_rate(concentration, params.stock_sensitivity)
        moves[code] = StockMove(
            code=code,
            buy_amount=buy_amounts.get(code, 0),
            adjusted_amount=adjusted[code],
            concentration=concentration,
            rate=rate,
            old_price=price,
            new_price=next_stock_price(price, rate, params.stock_min_price),
        )
    return moves
