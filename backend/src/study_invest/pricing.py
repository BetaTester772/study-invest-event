"""가격 산정 알고리즘 (03-pricing).

순수 함수만 둔다. 난수는 호출자가 주입한다(정산 로그에 p, X를 남기기 위해).
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from .money import PRICE_UNIT, exact, round_half_up
from .params import PRICE_MAX, EventParams

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


@dataclass(frozen=True)
class StockDraw:
    """종목 하나의 정산 난수. 코인처럼 균등난수 두 개만 쓴다."""

    u: float
    """방향 추출 난수 u ~ U(0, 1). u < 상승 확률이면 상승."""
    x: float
    """폭 추출 난수 X ~ U(0, 1). 변동률 크기 = 폭 상한 × X."""


@dataclass(frozen=True)
class StockMove:
    code: str
    buy_amount: int
    """당일 체결 매수금액 Bᵢ."""
    sell_amount: int
    """당일 체결 매도금액 Sᵢ."""
    net_amount: int
    """순매수 Nᵢ = Bᵢ − Sᵢ (음수면 순매도)."""
    signal: Fraction
    """순매수 신호 zᵢ = Nᵢ / (|Nᵢ| + L) ∈ (−1, 1)."""
    p_up: Fraction
    """상승 확률 = 1/2 + δ·zᵢ."""
    move_limit: Fraction
    """폭 상한 = M_min + (M_max − M_min)·(1 − |zᵢ|). 순매수·순매도가 클수록 작다."""
    u: float
    x: float
    direction: Literal["up", "down"]
    rate: Fraction
    """확률 변동률 = ±폭 상한 × X. 뉴스 효과는 포함하지 않는다."""
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


def draw_stock_randoms(codes: Iterable[str], rng: random.Random) -> dict[str, StockDraw]:
    """종목마다 (u, X)를 순서대로 뽑는다. 파라미터와 무관하게 종목당 늘 두 개를 쓴다."""
    draws: dict[str, StockDraw] = {}
    for code in codes:
        u = rng.random()
        draws[code] = StockDraw(u, rng.random())
    return draws


def flow_signal(net_amount: int, liquidity: int) -> Fraction:
    """순매수 신호 zᵢ = Nᵢ / (|Nᵢ| + L). L = 0이면 순매수 부호(±1), 순매수도 0이면 0."""
    denominator = abs(net_amount) + liquidity
    return Fraction(0) if denominator == 0 else Fraction(net_amount, denominator)


def up_probability(signal: Fraction, params: EventParams) -> Fraction:
    """상승 확률 = 1/2 + δ·zᵢ. 많이 살수록 오를 확률이, 많이 팔수록 내릴 확률이 높다."""
    return Fraction(1, 2) + exact(params.stock_p_shift) * signal


def move_limit(signal: Fraction, params: EventParams) -> Fraction:
    """폭 상한 = M_min + (M_max − M_min)·(1 − |zᵢ|). 많이 사거나 팔수록 작아진다.

    두 값이 엇갈려 저장돼 있으면 정렬해 쓴다(파라미터를 읽지 못해 배치가 멈추지 않게).
    """
    lo, hi = sorted((exact(params.stock_move_min), exact(params.stock_move_max)))
    return lo + (hi - lo) * (1 - abs(signal))


def stock_rate(
    draw: StockDraw, p_up: Fraction, limit: Fraction
) -> tuple[Literal["up", "down"], Fraction]:
    """u < p_up이면 상승(+limit × X), 아니면 하락(−limit × X)."""
    if not (0.0 <= draw.u < 1.0 and 0.0 <= draw.x <= 1.0):
        raise ValueError("u must be in [0, 1) and x in [0, 1]")
    magnitude = limit * exact(draw.x)
    return ("up", magnitude) if exact(draw.u) < p_up else ("down", -magnitude)


def next_stock_price(price: int, rate: Fraction, min_price: int) -> int:
    """새 가격 = max(하한, round(현재가 × (1 + 변동률), 10원)). PRICE_MAX를 넘지 않는다."""
    return max(min_price, min(round_half_up(Fraction(price) * (1 + rate)), PRICE_MAX))


def combined_rate(rate: Fraction, news_rate: Fraction | None) -> Fraction:
    """확률 변동률에 뉴스 효과를 곱으로 얹는다: (1 + rate)(1 + news) − 1."""
    if news_rate is None:
        return rate
    return (1 + rate) * (1 + news_rate) - 1


def settle_stocks(
    prices: Mapping[str, int],
    buy_amounts: Mapping[str, int],
    sell_amounts: Mapping[str, int],
    params: EventParams,
    draws: Mapping[str, StockDraw],
    news: Mapping[str, Fraction] | None = None,
) -> dict[str, StockMove]:
    """주식 전 종목의 다음 시작가를 산출한다(03-pricing §2).

    종목마다 순매수 신호 zᵢ로 상승 확률과 폭 상한을 정하고, draws(draw_stock_randoms())의
    (u, X)로 방향과 크기를 뽑는다. 호출자가 난수를 넘기므로 정산 로그에 그대로 남길 수 있다.
    news는 그날 호재·악재의 부호 있는 효과(종목 → 변동률)다. 확률 변동률에 곱으로 얹는다.
    """
    for name, amounts in (("buy", buy_amounts), ("sell", sell_amounts)):
        unknown = set(amounts) - set(prices)
        if unknown:
            raise ValueError(f"{name} amounts for unknown stocks: {sorted(unknown)}")
        if any(v < 0 for v in amounts.values()):
            raise ValueError(f"{name} amounts must be non-negative")
    missing = set(prices) - set(draws)
    if missing:
        raise ValueError(f"draws missing for stocks: {sorted(missing)}")
    if news:
        unknown = set(news) - set(prices)
        if unknown:
            raise ValueError(f"news for unknown stocks: {sorted(unknown)}")
        if any(not (-1 < r <= 1) for r in news.values()):
            raise ValueError("news rates must be in (-1, 1]")
    moves: dict[str, StockMove] = {}
    for code, price in prices.items():
        buy, sell = buy_amounts.get(code, 0), sell_amounts.get(code, 0)
        signal = flow_signal(buy - sell, params.virtual_liquidity)
        p_up = up_probability(signal, params)
        limit = move_limit(signal, params)
        draw = draws[code]
        direction, rate = stock_rate(draw, p_up, limit)
        news_rate = news.get(code) if news else None
        total_rate = combined_rate(rate, news_rate)
        moves[code] = StockMove(
            code=code,
            buy_amount=buy,
            sell_amount=sell,
            net_amount=buy - sell,
            signal=signal,
            p_up=p_up,
            move_limit=limit,
            u=draw.u,
            x=draw.x,
            direction=direction,
            rate=rate,
            news_rate=news_rate,
            total_rate=total_rate,
            old_price=price,
            new_price=next_stock_price(price, total_rate, params.stock_min_price),
        )
    return moves
