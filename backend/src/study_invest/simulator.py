"""정산 시뮬레이터 (F-13): 현재 파라미터로 코인 가격 경로를 반복 생성해 분포를 확인한다.

실제 정산과 같은 draw_coin()을 사용하므로 반올림·상한까지 그대로 반영된다.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .instruments import COIN
from .params import EventParams
from .pricing import draw_coin

DAILY_QUANTILES = (0.05, 0.25, 0.50, 0.70, 0.85, 0.95, 0.99)
MULTIPLE_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90, 0.99)
PROB_ABOVE = (1.0, 2.0, 5.0, 10.0, 20.0)


@dataclass(frozen=True)
class SimulationReport:
    paths: int
    rounds: int
    seed: int | None
    price_cap: int | None
    up_ratio: float
    mean_up: float
    mean_down: float
    mean: float
    mean_log: float
    daily_quantiles: tuple[tuple[float, float], ...]
    multiple_quantiles: tuple[tuple[float, float], ...]
    prob_above: tuple[tuple[float, float], ...]
    cap_hit_ratio: float
    """경로 중 한 번이라도 표시 상한에 걸린 비율."""

    def to_dict(self) -> dict[str, object]:
        return {
            "paths": self.paths,
            "rounds": self.rounds,
            "seed": self.seed,
            "price_cap": self.price_cap,
            "daily": {
                "up_ratio": self.up_ratio,
                "mean_up": self.mean_up,
                "mean_down": self.mean_down,
                "mean": self.mean,
                "mean_log": self.mean_log,
                "quantiles": [{"q": q, "rate": v} for q, v in self.daily_quantiles],
            },
            "cumulative": {
                "quantiles": [{"q": q, "multiple": v} for q, v in self.multiple_quantiles],
                "prob_above": [{"multiple": m, "prob": p} for m, p in self.prob_above],
                "cap_hit_ratio": self.cap_hit_ratio,
            },
        }


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """선형 보간 분위수(numpy 기본 방식과 동일)."""
    if not sorted_values:
        raise ValueError("empty sequence")
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def simulate_coin(
    params: EventParams,
    paths: int = 10_000,
    rounds: int = 10,
    seed: int | None = None,
    initial_price: int = COIN.initial_price,
) -> SimulationReport:
    if paths < 1 or rounds < 1:
        raise ValueError("paths and rounds must be positive")
    rng = random.Random(seed)
    rates: list[float] = []
    ups: list[float] = []
    downs: list[float] = []
    multiples: list[float] = []
    cap_hits = 0
    for _ in range(paths):
        price = initial_price
        hit = False
        for _ in range(rounds):
            move = draw_coin(price, params, rng)
            rates.append(move.rate)
            (ups if move.direction == "up" else downs).append(move.rate)
            price = move.new_price
            if params.coin_price_cap is not None and price >= params.coin_price_cap:
                hit = True
        multiples.append(price / initial_price)
        cap_hits += hit

    rates_sorted = sorted(rates)
    multiples_sorted = sorted(multiples)
    days = len(rates)
    return SimulationReport(
        paths=paths,
        rounds=rounds,
        seed=seed,
        price_cap=params.coin_price_cap,
        up_ratio=len(ups) / days,
        mean_up=sum(ups) / len(ups) if ups else 0.0,
        mean_down=sum(downs) / len(downs) if downs else 0.0,
        mean=sum(rates) / days,
        mean_log=sum(math.log1p(r) for r in rates) / days,
        daily_quantiles=tuple((q, quantile(rates_sorted, q)) for q in DAILY_QUANTILES),
        multiple_quantiles=tuple((q, quantile(multiples_sorted, q)) for q in MULTIPLE_QUANTILES),
        prob_above=tuple((m, sum(v > m for v in multiples) / paths) for m in PROB_ABOVE),
        cap_hit_ratio=cap_hits / paths,
    )


def format_report(report: SimulationReport) -> str:
    def pct(v: float) -> str:
        return f"{v * 100:+.1f}%"

    cap = f"{report.price_cap:,}원" if report.price_cap else "없음"
    lines = [
        f"병더리움 시뮬레이션 — 경로 {report.paths:,}회 × {report.rounds}회차"
        f" (seed={report.seed}, 표시 상한={cap})",
        "",
        "[일일 변동률]",
        f"  상승일 비율        {report.up_ratio * 100:.1f}%",
        f"  상승일 평균        {pct(report.mean_up)}",
        f"  하락일 평균        {pct(report.mean_down)}",
        f"  산술 평균          {pct(report.mean)}",
        f"  로그 기대값        {report.mean_log:+.4f}",
    ]
    lines += [f"  분위 {q * 100:>4.0f}%        {pct(v)}" for q, v in report.daily_quantiles]
    lines += ["", f"[{report.rounds}회 누적 배수]"]
    lines += [f"  분위 {q * 100:>4.0f}%        {v:.2f}배" for q, v in report.multiple_quantiles]
    lines += [f"  {m:g}배 초과 확률     {p * 100:.2f}%" for m, p in report.prob_above]
    if report.price_cap is not None:
        lines.append(f"  표시 상한 도달     {report.cap_hit_ratio * 100:.2f}%")
    return "\n".join(lines)


def run(
    paths: int, rounds: int, seed: int | None, use_price_cap: bool, params: EventParams | None
) -> SimulationReport:
    params = params or EventParams()
    if not use_price_cap:
        params = replace(params, coin_price_cap=None)
    return simulate_coin(params, paths=paths, rounds=rounds, seed=seed)
