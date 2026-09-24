"""F-13 시뮬레이터: 기본 파라미터 분포가 규격 기준값(03-pricing §1.3·§1.4)과 맞는지 확인."""

from __future__ import annotations

from dataclasses import replace

import pytest

from study_invest.params import EventParams
from study_invest.simulator import SimulationReport, format_report, quantile, simulate_coin


@pytest.fixture(scope="module")
def report() -> SimulationReport:
    return simulate_coin(replace(EventParams(), coin_price_cap=None), paths=20_000, seed=20261006)


def test_daily_statistics(report: SimulationReport) -> None:
    assert report.up_ratio == pytest.approx(0.30, abs=0.01)
    assert report.mean_down == pytest.approx(-1 / 6, abs=0.003)  # -0.5·E[X²]
    assert report.mean_up == pytest.approx(0.75, abs=0.02)  # 3·E[X³]
    assert report.mean == pytest.approx(0.108, abs=0.01)
    assert report.mean_log == pytest.approx(-0.003, abs=0.01)
    daily = dict(report.daily_quantiles)
    assert daily[0.05] == pytest.approx(-0.43, abs=0.01)
    assert daily[0.25] == pytest.approx(-0.21, abs=0.01)
    assert daily[0.95] == pytest.approx(1.74, abs=0.08)


def test_cumulative_matches_v02_table(report: SimulationReport) -> None:
    q = dict(report.multiple_quantiles)
    assert q[0.50] == pytest.approx(0.88, abs=0.05)
    assert q[0.25] == pytest.approx(0.38, abs=0.03)
    assert q[0.75] == pytest.approx(2.25, abs=0.15)
    above = dict(report.prob_above)
    assert above[20.0] == pytest.approx(0.02, abs=0.005)


def test_cap_is_applied() -> None:
    capped = simulate_coin(EventParams(), paths=5_000, seed=1)
    assert dict(capped.prob_above)[20.0] == 0
    assert 0.005 < capped.cap_hit_ratio < 0.05


def test_seed_reproducible() -> None:
    a = simulate_coin(EventParams(), paths=200, seed=7)
    b = simulate_coin(EventParams(), paths=200, seed=7)
    assert a == b
    assert "병더리움 시뮬레이션" in format_report(a)


def test_quantile_interpolation() -> None:
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert quantile([5.0], 0.99) == 5.0
