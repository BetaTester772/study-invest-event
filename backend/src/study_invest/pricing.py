"""가격 산정 알고리즘 (03-pricing).

순수 함수만 둔다. 난수는 호출자가 주입한다(정산 로그에 p, X를 남기기 위해).
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
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
    calm: bool
    """초반 안정기 상·하한으로 뽑았는지."""


def is_calm_round(round_no: int, params: EventParams) -> bool:
    """SPEC-COIN-6: 1회차부터 coin_calm_rounds회차까지는 초반 안정기다."""
    return 1 <= round_no <= params.coin_calm_rounds


def coin_rate(
    p: float, x: float, params: EventParams, *, calm: bool = False
) -> tuple[Literal["up", "down"], float]:
    """SPEC-COIN-1~4: p < p_up이면 상승일(상한·X^up_exp), 아니면 하락일(하한·X^down_exp).

    calm이면 평소 상·하한 대신 안정기 상·하한을 쓴다. 확률과 지수(분포 모양)는 같다.
    """
    if not (0.0 <= p < 1.0 and 0.0 <= x <= 1.0):
        raise ValueError("p must be in [0, 1) and x in [0, 1]")
    cap, floor = (
        (params.coin_calm_cap, params.coin_calm_floor)
        if calm
        else (params.coin_cap, params.coin_floor)
    )
    if p < params.coin_p_up:
        return "up", cap * x**params.coin_up_exp
    return "down", floor * x**params.coin_down_exp


def next_coin_price(price: int, rate: float, params: EventParams) -> int:
    """P' = round(P × (1 + r), 10원). 표시 상한을 적용하고 [10원, PRICE_MAX]를 보장한다."""
    new = round_half_up(Fraction(price) * (1 + Fraction(rate)))
    cap = params.coin_price_cap if params.coin_price_cap is not None else PRICE_MAX
    return max(PRICE_UNIT, min(new, cap, PRICE_MAX))


def draw_coin(
    price: int, params: EventParams, rng: random.Random, *, calm: bool = False
) -> CoinMove:
    """균등난수 두 개(p, X)로 코인 1회 변동을 추출한다. calm이면 안정기 상·하한을 쓴다."""
    p = rng.random()
    x = rng.random()
    direction, rate = coin_rate(p, x, params, calm=calm)
    return CoinMove(p, x, direction, rate, price, next_coin_price(price, rate, params), calm)


# --- 주식 (03-pricing §2) ---------------------------------------------------------


EULER_GAMMA = 0.5772156649015329
"""오일러 상수 γ. 표준 Gumbel(0, 1)의 평균이므로, 빼면 평균 0인 잡음이 된다."""


@dataclass(frozen=True)
class StockMove:
    code: str
    buy_amount: int
    """당일 매수금액 Bᵢ."""
    adjusted_amount: int
    """Bᵢ′ = Bᵢ + L."""
    noise_factor: float | None
    """매수지분 잡음 배수 exp(τ·(Gᵢ − γ)). 잡음을 쓰지 않았으면 None."""
    concentration: Fraction | None
    """쏠림 지수 rᵢ = n·Bᵢ″ / B_total (Bᵢ″ = Bᵢ′ × 잡음 배수). B_total = 0이면 None."""
    rate_factor: float | None
    """종목별 변동 배율 kᵢ. 배율을 쓰지 않았으면 None(= 1)."""
    rate: Fraction
    """쏠림 변동률 = clamp(계수 × (1 − rᵢ) × kᵢ, ±30%). 뉴스 효과는 포함하지 않는다."""
    news_rate: Fraction | None
    """그날 호재·악재 효과(부호 포함). 뉴스가 없으면 None."""
    total_rate: Fraction
    """실제 적용 변동률 = (1 + rate)(1 + news_rate) − 1."""
    old_price: int
    new_price: int


@dataclass(frozen=True)
class NewsDraw:
    """무작위 뉴스 추출 결과(03-pricing §3). 제목은 서비스가 headline_pick으로 고른다."""

    code: str
    kind: Literal["good", "bad"]
    rate: float
    """효과 크기(양수, 0.01 단위)."""
    headline_pick: float
    """제목 선택용 균등난수 U(0, 1)."""


def draw_news(codes: Sequence[str], params: EventParams, rng: random.Random) -> list[NewsDraw]:
    """균등난수로 다음 운영일의 무작위 뉴스를 뽑는다: 호재 news_good_per_day건, 이어서 악재
    news_bad_per_day건. 종목은 서로 달라서 한 종목에 호재와 악재가 함께 붙지 않는다.

    뉴스마다 순서대로: 종목(아직 뉴스가 없는 종목 중 균등) → 크기 U(min, max)를 0.01 단위로 → 제목.
    종류는 건수로 정해지므로 난수를 쓰지 않는다. 건수가 0이거나 종목이 모자라면 그만큼만 뽑는다.
    """
    lo, hi = sorted((params.news_rate_min, params.news_rate_max))
    kinds: list[Literal["good", "bad"]] = ["good"] * params.news_good_per_day
    kinds += ["bad"] * params.news_bad_per_day
    remaining = list(codes)
    draws: list[NewsDraw] = []
    for kind in kinds:
        if not remaining:
            break
        code = remaining.pop(min(int(rng.random() * len(remaining)), len(remaining) - 1))
        rate = min(hi, max(lo, round(lo + (hi - lo) * rng.random(), 2)))
        draws.append(NewsDraw(code, kind, rate, rng.random()))
    return draws


def gumbel(rng: random.Random) -> float:
    """표준 Gumbel(0, 1) 난수 G = −ln(−ln U), U ~ U(0, 1). 균등난수 하나로 만든다."""
    u = rng.random()
    while not 0.0 < u < 1.0:  # U=0은 ln(0)이라 다시 뽑는다
        u = rng.random()
    return -math.log(-math.log(u))


def draw_stock_noise(
    codes: Iterable[str], params: EventParams, rng: random.Random
) -> dict[str, float] | None:
    """종목별 매수지분 잡음 배수 exp(τ·(Gᵢ − γ))를 뽑는다. τ = 0이면 None(잡음 없음).

    로그 매수지분 ln Bᵢ′에 Gumbel 잡음을 더하는 것과 같다(Gumbel-max: 쏠린 종목이 매수금액에
    비례해 확률적으로 '쏠린 것'으로 판정된다). 모든 종목에 같은 배수가 걸리면 지분이 그대로이므로
    잡음은 종목 사이의 상대 지분만 흔든다.
    """
    tau = params.stock_noise_scale
    if tau == 0:
        return None
    return {code: math.exp(tau * (gumbel(rng) - EULER_GAMMA)) for code in codes}


def draw_stock_rate_factor(
    codes: Iterable[str], params: EventParams, rng: random.Random
) -> dict[str, float] | None:
    """종목별 변동 배율 kᵢ = 1 − w + 2w·Uᵢ ~ U(1 − w, 1 + w)를 뽑는다. w = 0이면 None(배율 없음).

    매수지분 잡음(draw_stock_noise)은 지분만 다시 나눠 4종목 변동률의 합이 0으로 남지만, 배율은
    종목마다 따로 곱해지므로 이 합이 0으로 고정되지 않는다. Uᵢ = 0.5이면 kᵢ = 1이다.
    """
    w = params.stock_rate_jitter
    if w == 0:
        return None
    return {code: 1 - w + 2 * w * rng.random() for code in codes}


def stock_rate(
    concentration: Fraction, sensitivity: float, factor: float | None = None
) -> Fraction:
    """변동률 = clamp(계수 × (1 − rᵢ) × kᵢ, −30%, +30%). factor가 None이면 kᵢ = 1."""
    raw = exact(sensitivity) * (1 - concentration)
    if factor is not None:
        raw *= exact(factor)
    return max(-STOCK_DAILY_LIMIT, min(STOCK_DAILY_LIMIT, raw))


def next_stock_price(price: int, rate: Fraction, min_price: int) -> int:
    """새 가격 = max(하한, round(현재가 × (1 + 변동률), 10원)). PRICE_MAX를 넘지 않는다."""
    return max(min_price, min(round_half_up(Fraction(price) * (1 + rate)), PRICE_MAX))


def combined_rate(rate: Fraction, news_rate: Fraction | None) -> Fraction:
    """쏠림 변동률에 뉴스 효과를 곱으로 얹는다: (1 + rate)(1 + news) − 1. ±30%는 쏠림에만."""
    if news_rate is None:
        return rate
    return (1 + rate) * (1 + news_rate) - 1


def settle_stocks(
    prices: Mapping[str, int],
    buy_amounts: Mapping[str, int],
    params: EventParams,
    noise: Mapping[str, float] | None = None,
    news: Mapping[str, Fraction] | None = None,
    rate_factor: Mapping[str, float] | None = None,
) -> dict[str, StockMove]:
    """주식 전 종목의 다음 시작가를 산출한다. 기준선은 종목 수(4)로 나눈 평균이다.

    noise는 draw_stock_noise()가 뽑은 종목별 잡음 배수다. None이면 잡음 없이(τ = 0과 같게)
    당일 매수만으로 결정한다. 호출자가 뽑아 넘기므로 정산 로그에 그대로 남길 수 있다.
    news는 그날 호재·악재의 부호 있는 효과(종목 → 변동률)다. 쏠림 변동률(클램프 뒤)에 곱으로 얹는다.
    rate_factor는 draw_stock_rate_factor()가 뽑은 종목별 변동 배율이다. 클램프 전에 곱한다.
    """
    if not prices:
        return {}
    unknown = set(buy_amounts) - set(prices)
    if unknown:
        raise ValueError(f"buy amounts for unknown stocks: {sorted(unknown)}")
    if news:
        unknown = set(news) - set(prices)
        if unknown:
            raise ValueError(f"news for unknown stocks: {sorted(unknown)}")
        if any(not (-1 < r <= 1) for r in news.values()):
            raise ValueError("news rates must be in (-1, 1]")
    if noise is not None:
        missing = set(prices) - set(noise)
        if missing:
            raise ValueError(f"noise missing for stocks: {sorted(missing)}")
        if any(not (math.isfinite(f) and f > 0) for f in noise.values()):
            raise ValueError("noise factors must be positive finite numbers")
    if rate_factor is not None:
        missing = set(prices) - set(rate_factor)
        if missing:
            raise ValueError(f"rate factor missing for stocks: {sorted(missing)}")
        if any(not (math.isfinite(k) and k > 0) for k in rate_factor.values()):
            raise ValueError("rate factors must be positive finite numbers")
    adjusted = {code: buy_amounts.get(code, 0) + params.virtual_liquidity for code in prices}
    if any(v < 0 for v in adjusted.values()):
        raise ValueError("buy amounts must be non-negative")
    # Bᵢ″ = Bᵢ′ × 잡음 배수. 배수는 양수라 B_total = 0 판정은 잡음과 무관하다.
    weights = {
        code: Fraction(v) if noise is None else v * exact(noise[code])
        for code, v in adjusted.items()
    }
    total = sum(weights.values())
    n = len(prices)
    moves: dict[str, StockMove] = {}
    for code, price in prices.items():
        factor = None if rate_factor is None else rate_factor[code]
        if total == 0:  # 03-pricing §2.3: 전 종목 매수 0 → 변동률 0%
            concentration, rate = None, Fraction(0)
        else:
            concentration = n * weights[code] / total
            rate = stock_rate(concentration, params.stock_sensitivity, factor)
        news_rate = news.get(code) if news else None
        total_rate = combined_rate(rate, news_rate)
        moves[code] = StockMove(
            code=code,
            buy_amount=buy_amounts.get(code, 0),
            adjusted_amount=adjusted[code],
            noise_factor=None if noise is None else noise[code],
            concentration=concentration,
            rate_factor=factor,
            rate=rate,
            news_rate=news_rate,
            total_rate=total_rate,
            old_price=price,
            new_price=next_stock_price(price, total_rate, params.stock_min_price),
        )
    return moves
