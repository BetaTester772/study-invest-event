"""정산 시뮬레이터 (F-13): 현재 파라미터로 코인 가격 경로를 반복 생성해 분포를 확인한다.

실제 정산과 같은 draw_coin()·is_calm_round()를 사용하므로 반올림·상한·초반 안정기까지 그대로
반영된다. 일일 통계는 평소 회차와 안정기 회차를 따로 낸다(변동폭이 달라 섞으면 둘 다 흐려진다).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .instruments import COIN
from .params import EventParams
from .pricing import CoinMove, draw_coin, is_calm_round

DAILY_QUANTILES = (0.05, 0.25, 0.50, 0.70, 0.85, 0.95, 0.99)
MULTIPLE_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90, 0.99)
PROB_ABOVE = (1.0, 2.0, 5.0, 10.0, 20.0)


@dataclass(frozen=True)
class DailyStats:
    """한 변동폭 구간(평소 또는 안정기)의 일일 변동률 통계."""

    days: int
    """집계한 변동 횟수(경로 수 × 해당 회차 수)."""
    up_ratio: float
    mean_up: float
    mean_down: float
    mean: float
    mean_log: float
    quantiles: tuple[tuple[float, float], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "days": self.days,
            "up_ratio": self.up_ratio,
            "mean_up": self.mean_up,
            "mean_down": self.mean_down,
            "mean": self.mean,
            "mean_log": self.mean_log,
            "quantiles": [{"q": q, "rate": v} for q, v in self.quantiles],
        }


class _DailyTally:
    """일일 변동률 누적. 분위수용 목록과 합계만 둔다(상승·하락 목록을 따로 들지 않는다)."""

    def __init__(self) -> None:
        self.rates: list[float] = []
        self.ups = 0
        self.up_sum = 0.0
        self.down_sum = 0.0
        self.log_sum = 0.0

    def add(self, move: CoinMove) -> None:
        self.rates.append(move.rate)
        self.log_sum += math.log1p(move.rate)
        if move.direction == "up":
            self.ups += 1
            self.up_sum += move.rate
        else:
            self.down_sum += move.rate

    def stats(self) -> DailyStats | None:
        days = len(self.rates)
        if days == 0:
            return None
        downs = days - self.ups
        rates = sorted(self.rates)
        return DailyStats(
            days=days,
            up_ratio=self.ups / days,
            mean_up=self.up_sum / self.ups if self.ups else 0.0,
            mean_down=self.down_sum / downs if downs else 0.0,
            mean=(self.up_sum + self.down_sum) / days,
            mean_log=self.log_sum / days,
            quantiles=tuple((q, quantile(rates, q)) for q in DAILY_QUANTILES),
        )


@dataclass(frozen=True)
class SimulationReport:
    paths: int
    rounds: int
    seed: int | None
    price_cap: int | None
    calm_rounds: int
    """경로마다 안정기 상·하한으로 돈 회차 수(1회차부터)."""
    daily: DailyStats | None
    """평소 회차의 일일 통계. 모든 회차가 안정기면 None."""
    calm_daily: DailyStats | None
    """안정기 회차의 일일 통계. 안정기가 없으면 None."""
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
            "calm_rounds": self.calm_rounds,
            "daily": self.daily.to_dict() if self.daily else None,
            "calm_daily": self.calm_daily.to_dict() if self.calm_daily else None,
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
    normal, calm = _DailyTally(), _DailyTally()
    multiples: list[float] = []
    cap_hits = 0
    for _ in range(paths):
        price = initial_price
        hit = False
        for round_no in range(1, rounds + 1):
            move = draw_coin(price, params, rng, calm=is_calm_round(round_no, params))
            (calm if move.calm else normal).add(move)
            price = move.new_price
            if params.coin_price_cap is not None and price >= params.coin_price_cap:
                hit = True
        multiples.append(price / initial_price)
        cap_hits += hit

    multiples_sorted = sorted(multiples)
    return SimulationReport(
        paths=paths,
        rounds=rounds,
        seed=seed,
        price_cap=params.coin_price_cap,
        calm_rounds=min(params.coin_calm_rounds, rounds),
        daily=normal.stats(),
        calm_daily=calm.stats(),
        multiple_quantiles=tuple((q, quantile(multiples_sorted, q)) for q in MULTIPLE_QUANTILES),
        prob_above=tuple((m, sum(v > m for v in multiples) / paths) for m in PROB_ABOVE),
        cap_hit_ratio=cap_hits / paths,
    )


def _format_daily(title: str, daily: DailyStats) -> list[str]:
    def pct(v: float) -> str:
        return f"{v * 100:+.1f}%"

    lines = [
        "",
        title,
        f"  상승일 비율        {daily.up_ratio * 100:.1f}%",
        f"  상승일 평균        {pct(daily.mean_up)}",
        f"  하락일 평균        {pct(daily.mean_down)}",
        f"  산술 평균          {pct(daily.mean)}",
        f"  로그 기대값        {daily.mean_log:+.4f}",
    ]
    lines += [f"  분위 {q * 100:>4.0f}%        {pct(v)}" for q, v in daily.quantiles]
    return lines


def format_report(report: SimulationReport) -> str:
    cap = f"{report.price_cap:,}원" if report.price_cap else "없음"
    calm = (
        ("1회차" if report.calm_rounds == 1 else f"1~{report.calm_rounds}회차")
        if report.calm_rounds
        else "없음"
    )
    lines = [
        f"병더리움 시뮬레이션 — 경로 {report.paths:,}회 × {report.rounds}회차"
        f" (seed={report.seed}, 표시 상한={cap}, 초반 안정기={calm})",
    ]
    if report.daily is not None:
        lines += _format_daily("[일일 변동률 — 평소 회차]", report.daily)
    if report.calm_daily is not None:
        lines += _format_daily(f"[일일 변동률 — 안정기 {calm}]", report.calm_daily)
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
