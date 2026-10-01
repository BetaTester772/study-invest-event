"""F-13 시뮬레이터: 기본 파라미터 분포가 규격 기준값(03-pricing §1.3·§1.4·§1.5)과 맞는지 확인."""

from __future__ import annotations

from dataclasses import replace

import pytest

from study_invest.params import EventParams
from study_invest.simulator import (
    DailyStats,
    SimulationReport,
    format_report,
    quantile,
    simulate_coin,
)

UNCAPPED = replace(EventParams(), coin_price_cap=None)


@pytest.fixture(scope="module")
def report() -> SimulationReport:
    """기본 파라미터(초반 안정기 1~3회차 포함)."""
    return simulate_coin(UNCAPPED, paths=20_000, seed=20261006)


@pytest.fixture(scope="module")
def no_calm() -> SimulationReport:
    """안정기 없는 v0.3 조건. 규격 v0.2 누적 분포표와 비교한다."""
    return simulate_coin(replace(UNCAPPED, coin_calm_rounds=0), paths=20_000, seed=20261006)


def daily(r: SimulationReport) -> DailyStats:
    assert r.daily is not None
    return r.daily


def calm_daily(r: SimulationReport) -> DailyStats:
    assert r.calm_daily is not None
    return r.calm_daily


def test_daily_statistics(report: SimulationReport) -> None:
    """평소 회차의 일일 통계는 안정기와 섞이지 않고 규격 기준값 그대로다."""
    d = daily(report)
    assert d.days == 20_000 * 7  # 10회 중 4~10회차
    assert d.up_ratio == pytest.approx(0.30, abs=0.01)
    assert d.mean_down == pytest.approx(-1 / 6, abs=0.003)  # -0.5·E[X²]
    assert d.mean_up == pytest.approx(0.75, abs=0.02)  # 3·E[X³]
    assert d.mean == pytest.approx(0.108, abs=0.01)
    assert d.mean_log == pytest.approx(-0.003, abs=0.01)
    q = dict(d.quantiles)
    assert q[0.05] == pytest.approx(-0.43, abs=0.01)
    assert q[0.25] == pytest.approx(-0.21, abs=0.01)
    assert q[0.95] == pytest.approx(1.74, abs=0.08)


def test_calm_daily_statistics(report: SimulationReport) -> None:
    """SPEC-COIN-6: 안정기는 하루 [-10%, +30%]에서 움직이고 로그 기대값은 평소처럼 ≈ -0.003."""
    assert report.calm_rounds == 3
    c = calm_daily(report)
    assert c.days == 20_000 * 3
    assert c.up_ratio == pytest.approx(0.30, abs=0.01)
    assert c.mean_up == pytest.approx(0.075, abs=0.003)  # 0.3·E[X³]
    assert c.mean_down == pytest.approx(-1 / 30, abs=0.001)  # -0.1·E[X²]
    assert c.mean_log == pytest.approx(-0.0033, abs=0.002)
    q = dict(c.quantiles)
    assert q[0.05] >= -0.1 and q[0.99] <= 0.3
    assert q[0.95] == pytest.approx(0.174, abs=0.01)


def test_calm_keeps_median_and_narrows_spread(
    report: SimulationReport, no_calm: SimulationReport
) -> None:
    """안정기는 누적 중앙값(약 0.88배)을 유지하면서 양쪽 꼬리를 좁힌다(03-pricing §1.5)."""
    with_calm, without = dict(report.multiple_quantiles), dict(no_calm.multiple_quantiles)
    assert with_calm[0.50] == pytest.approx(0.88, abs=0.05)
    assert with_calm[0.25] == pytest.approx(0.43, abs=0.03)
    assert with_calm[0.75] == pytest.approx(1.96, abs=0.15)
    assert with_calm[0.10] > without[0.10] and with_calm[0.90] < without[0.90]
    assert dict(report.prob_above)[20.0] == pytest.approx(0.009, abs=0.004)


def test_cumulative_matches_v02_table(no_calm: SimulationReport) -> None:
    assert no_calm.calm_rounds == 0 and no_calm.calm_daily is None
    q = dict(no_calm.multiple_quantiles)
    assert q[0.50] == pytest.approx(0.88, abs=0.05)
    assert q[0.25] == pytest.approx(0.38, abs=0.03)
    assert q[0.75] == pytest.approx(2.25, abs=0.15)
    above = dict(no_calm.prob_above)
    assert above[20.0] == pytest.approx(0.02, abs=0.005)


def test_all_calm_rounds_have_no_normal_daily() -> None:
    r = simulate_coin(UNCAPPED, paths=100, rounds=2, seed=1)
    assert r.calm_rounds == 2 and r.daily is None and r.calm_daily is not None
    body = r.to_dict()
    assert body["daily"] is None and body["calm_rounds"] == 2
    assert "안정기 1~2회차" in format_report(r)


def test_cap_is_applied() -> None:
    capped = simulate_coin(replace(EventParams(), coin_calm_rounds=0), paths=5_000, seed=1)
    assert dict(capped.prob_above)[20.0] == 0
    assert 0.005 < capped.cap_hit_ratio < 0.05


def test_seed_reproducible() -> None:
    a = simulate_coin(EventParams(), paths=200, seed=7)
    b = simulate_coin(EventParams(), paths=200, seed=7)
    assert a == b
    text = format_report(a)
    assert "병더리움 시뮬레이션" in text and "평소 회차" in text and "안정기 1~3회차" in text


def test_quantile_interpolation() -> None:
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert quantile([5.0], 0.99) == 5.0
