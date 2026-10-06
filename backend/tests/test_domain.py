"""순수 도메인 로직: 반올림, 가격 산정, 운영 달력, 파라미터."""

from __future__ import annotations

import math
import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from fractions import Fraction
from typing import Any, ClassVar

import pytest

from study_invest.event_calendar import EventCalendar
from study_invest.instruments import INSTRUMENTS, STOCKS
from study_invest.money import exact, round_half_up
from study_invest.params import (
    CALM_ROUNDS_MAX,
    INITIAL_CASH,
    KST,
    REWARD_CASH_MAX,
    STOCK_NOISE_MAX,
    STOCK_RATE_JITTER_MAX,
    EventParams,
)
from study_invest.pricing import (
    EULER_GAMMA,
    coin_rate,
    combined_rate,
    draw_coin,
    draw_news,
    draw_stock_noise,
    draw_stock_rate_factor,
    gumbel,
    is_calm_round,
    next_coin_price,
    next_stock_price,
    settle_stocks,
)

P = EventParams()
P0 = replace(P, virtual_liquidity=0)
PRICES = {i.code: i.initial_price for i in STOCKS}
MAN = 10_000


class TestMoney:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (52_505, 52_510),
            (52_504, 52_500),
            (15, 20),
            (Fraction(29_999, 2), 15_000),
            (14.999, 10),
            (0, 0),
            (-15, -20),
        ],
    )
    def test_round_half_up(self, value: int | float | Fraction, expected: int) -> None:
        assert round_half_up(value) == expected

    def test_exact_uses_decimal_literal(self) -> None:
        assert exact(0.3) == Fraction(3, 10)
        assert exact(0.4) * 1_000_000 == 400_000


class TestInstruments:
    def test_master(self) -> None:
        assert [(i.code, i.initial_price) for i in INSTRUMENTS] == [
            ("SAMSU", 75_000),
            ("SKLOW", 170_000),
            ("MIRAE", 40_000),
            ("LB", 14_000),
            ("BYUNG", 250_000),
        ]
        assert len(STOCKS) == 4


class TestCoin:
    def test_up_day_below_p_up(self) -> None:
        assert coin_rate(0.29, 1.0, P) == ("up", 0.8)
        assert coin_rate(0.0, 0.5, P) == ("up", 0.8 * 0.25)

    def test_down_day_at_or_above_p_up(self) -> None:
        assert coin_rate(0.30, 1.0, P) == ("down", -0.4)
        assert coin_rate(0.99, 0.5, P) == ("down", -0.4 * 0.25)

    def test_zero_width(self) -> None:
        assert coin_rate(0.1, 0.0, P)[1] == 0
        assert coin_rate(0.9, 0.0, P)[1] == 0

    def test_range_spec_coin_2(self) -> None:
        rng = random.Random(1)
        for _ in range(10_000):
            _, r = coin_rate(rng.random(), rng.random(), P)
            assert -0.4 <= r <= 0.8

    def test_invalid_draw(self) -> None:
        with pytest.raises(ValueError):
            coin_rate(1.0, 0.5, P)

    def test_next_price_rounds_to_10(self) -> None:
        assert next_coin_price(250_000, -0.123456, P) == 219_140  # 219,136 → 219,140
        assert next_coin_price(250_000, 3.0, P) == 1_000_000

    def test_display_cap(self) -> None:
        assert next_coin_price(4_000_000, 3.0, P) == 5_000_000
        assert next_coin_price(4_000_000, 3.0, replace(P, coin_price_cap=None)) == 16_000_000

    def test_min_price_guard(self) -> None:
        assert next_coin_price(10, -0.5, P) == 10

    def test_draw_uses_two_uniforms(self) -> None:
        class Seq(random.Random):
            def __init__(self) -> None:
                super().__init__()
                self.values = [0.1, 1.0]

            def random(self) -> float:
                return self.values.pop(0)

        move = draw_coin(250_000, P, Seq())
        assert (move.p, move.x, move.direction, move.new_price) == (0.1, 1.0, "up", 450_000)
        assert move.calm is False


class TestCoinCalmPeriod:
    """SPEC-COIN-6: 초반 안정기(기본 1~3회차)는 같은 분포 모양에 좁은 상·하한을 쓴다."""

    def test_calm_rounds_from_first_round(self) -> None:
        assert [is_calm_round(n, P) for n in range(0, 6)] == [False, True, True, True, False, False]
        assert not any(is_calm_round(n, replace(P, coin_calm_rounds=0)) for n in range(1, 11))
        assert is_calm_round(4, replace(P, coin_calm_rounds=4))

    def test_calm_bounds(self) -> None:
        assert coin_rate(0.29, 1.0, P, calm=True) == ("up", 0.3)
        assert coin_rate(0.30, 1.0, P, calm=True) == ("down", -0.1)
        assert coin_rate(0.0, 0.5, P, calm=True) == ("up", 0.3 * 0.25)  # X² 모양 유지
        assert coin_rate(0.99, 0.5, P, calm=True) == ("down", -0.1 * 0.25)  # X² 모양 유지

    def test_calm_range(self) -> None:
        rng = random.Random(2)
        for _ in range(10_000):
            _, r = coin_rate(rng.random(), rng.random(), P, calm=True)
            assert -0.1 <= r <= 0.3

    def test_draw_calm(self) -> None:
        class Seq(random.Random):
            def __init__(self) -> None:
                super().__init__()
                self.values = [0.1, 1.0]

            def random(self) -> float:
                return self.values.pop(0)

        move = draw_coin(250_000, P, Seq(), calm=True)
        assert (move.direction, move.rate, move.new_price, move.calm) == ("up", 0.3, 325_000, True)


class TestStock:
    def test_spec_example_table(self) -> None:
        """03-pricing §2.4: L=0, 총매수 4,000만원."""
        buys = {"SAMSU": 2000 * MAN, "SKLOW": 1200 * MAN, "MIRAE": 600 * MAN, "LB": 200 * MAN}
        moves = settle_stocks(PRICES, buys, P0)
        assert {c: m.concentration for c, m in moves.items()} == {
            "SAMSU": 2,
            "SKLOW": Fraction(6, 5),
            "MIRAE": Fraction(3, 5),
            "LB": Fraction(1, 5),
        }
        assert {c: m.rate for c, m in moves.items()} == {
            "SAMSU": Fraction(-3, 10),
            "SKLOW": Fraction(-6, 100),
            "MIRAE": Fraction(12, 100),
            "LB": Fraction(24, 100),
        }
        assert {c: m.new_price for c, m in moves.items()} == {
            "SAMSU": 52_500,
            "SKLOW": 159_800,
            "MIRAE": 44_800,
            "LB": 17_360,
        }

    def test_clamped_at_minus_30(self) -> None:
        moves = settle_stocks(PRICES, {"SAMSU": 100 * MAN}, P0)  # r = 4
        assert moves["SAMSU"].rate == Fraction(-3, 10)
        assert moves["SKLOW"].rate == Fraction(3, 10)  # r = 0 → +30%

    def test_no_buys_without_liquidity(self) -> None:
        moves = settle_stocks(PRICES, {}, P0)
        assert all(m.rate == 0 and m.concentration is None for m in moves.values())
        assert {c: m.new_price for c, m in moves.items()} == PRICES

    def test_virtual_liquidity_dampens(self) -> None:
        buys = {"SAMSU": 2000 * MAN, "SKLOW": 1200 * MAN, "MIRAE": 600 * MAN, "LB": 200 * MAN}
        with_l = settle_stocks(PRICES, buys, P)  # L = 500만원
        # B′ = 2500/1700/1100/700만, 총 6000만 → r_SAMSU = 10/6
        assert with_l["SAMSU"].concentration == Fraction(10, 6)
        assert with_l["SAMSU"].rate == Fraction(-1, 5)
        assert settle_stocks(PRICES, {}, P)["LB"].rate == 0  # 전원 L → r=1

    def test_sensitivity_above_limit_is_clamped(self) -> None:
        moves = settle_stocks(PRICES, {"SAMSU": 100}, replace(P0, stock_sensitivity=0.9))
        assert moves["SKLOW"].rate == Fraction(3, 10)

    def test_min_price_floor(self) -> None:
        assert next_stock_price(1_200, Fraction(-3, 10), 1_000) == 1_000
        assert next_stock_price(14_000, Fraction(24, 100), 1_000) == 17_360

    def test_unknown_stock_rejected(self) -> None:
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {"BYUNG": 1}, P)


class TestStockNoise:
    """03-pricing §2.5: 매수지분에 Gumbel 잡음 배수 exp(τ·(G − γ))를 곱한다."""

    buys: ClassVar[dict[str, int]] = {
        "SAMSU": 2000 * MAN,
        "SKLOW": 1200 * MAN,
        "MIRAE": 600 * MAN,
        "LB": 200 * MAN,
    }

    def test_default_scale_and_range(self) -> None:
        assert P.stock_noise_scale == 0.10
        EventParams(stock_noise_scale=0)
        EventParams(stock_noise_scale=STOCK_NOISE_MAX)
        for bad in (-0.1, STOCK_NOISE_MAX + 0.1, float("nan")):
            with pytest.raises(ValueError):
                EventParams(stock_noise_scale=bad)

    def test_no_noise_when_scale_is_zero(self) -> None:
        rng = random.Random(1)
        assert draw_stock_noise(PRICES, replace(P, stock_noise_scale=0), rng) is None
        moves = settle_stocks(PRICES, self.buys, P0, noise=None)
        assert all(m.noise_factor is None for m in moves.values())
        assert moves["SAMSU"].rate == Fraction(-3, 10)  # §2.4 표와 같다

    def test_equal_factors_cancel(self) -> None:
        """전 종목 같은 배수면 지분이 그대로다(테스트 StubRandom의 0.5 고정값이 이 경우)."""
        plain = settle_stocks(PRICES, self.buys, P0)
        same = settle_stocks(PRICES, self.buys, P0, noise=dict.fromkeys(PRICES, 0.9))
        assert {c: m.rate for c, m in same.items()} == {c: m.rate for c, m in plain.items()}
        assert [m.new_price for m in same.values()] == [m.new_price for m in plain.values()]
        assert all(m.noise_factor == 0.9 for m in same.values())

    def test_noise_moves_prices_without_orders(self) -> None:
        """아무도 안 사도(전 종목 L만) 잡음이 있으면 가격이 움직이고, 변동률 합은 0이다."""
        noise = {"SAMSU": 1.1, "SKLOW": 1.0, "MIRAE": 1.0, "LB": 1.0}
        moves = settle_stocks(PRICES, {}, P, noise=noise)
        assert moves["SAMSU"].concentration == Fraction(44, 41)
        assert moves["SAMSU"].rate < 0 < moves["LB"].rate
        assert sum(m.rate for m in moves.values()) == 0  # Σ(1 − rᵢ) = 0 이므로 클램프 전 합은 0
        assert moves["SAMSU"].adjusted_amount == P.virtual_liquidity  # B′는 잡음 전 값

    def test_noise_is_clamped_like_any_rate(self) -> None:
        noise = {"SAMSU": 100.0, "SKLOW": 1.0, "MIRAE": 1.0, "LB": 1.0}
        moves = settle_stocks(PRICES, {}, P, noise=noise)
        assert moves["SAMSU"].concentration == Fraction(400, 103)  # 원 변동률 −86% → −30%
        assert moves["SAMSU"].rate == Fraction(-3, 10)
        assert 0 < moves["LB"].rate < Fraction(3, 10)  # rᵢ > 0이라 +30%에는 닿지 않는다

    def test_noise_validation(self) -> None:
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, P, noise={"SAMSU": 1.0})  # 종목 누락
        for bad in (0.0, -1.0, float("inf"), float("nan")):
            with pytest.raises(ValueError):
                settle_stocks(PRICES, {}, P, noise=dict.fromkeys(PRICES, bad))

    def test_gumbel_draw(self) -> None:
        assert gumbel(Seq([0.0, 0.5])) == pytest.approx(0.36651292)  # U=0은 버린다
        assert gumbel(Seq([math.exp(-1)])) == pytest.approx(0.0)  # 최빈값
        # 균등난수 0.5 고정이면 모든 종목이 같은 배수 → 지분 불변
        rng = StubHalf()
        factors = draw_stock_noise(PRICES, P, rng)
        assert factors is not None and len(set(factors.values())) == 1
        assert factors["SAMSU"] == pytest.approx(math.exp(0.1 * (0.36651292 - EULER_GAMMA)))

    def test_noise_statistics(self) -> None:
        """ln 배수의 평균 ≈ 0, 표준편차 ≈ τ·π/√6 (Gumbel 분산 π²/6)."""
        rng = random.Random(2026)
        tau = 0.1
        params = replace(P, stock_noise_scale=tau)
        logs = [
            math.log(f)
            for _ in range(5_000)
            for f in (draw_stock_noise(PRICES, params, rng) or {}).values()
        ]
        n = len(logs)
        mean = sum(logs) / n
        sd = math.sqrt(sum((v - mean) ** 2 for v in logs) / n)
        assert abs(mean) < 0.005
        assert sd == pytest.approx(tau * math.pi / math.sqrt(6), abs=0.01)


class TestStockRateFactor:
    """03-pricing §2.6: 종목별 변동 배율 kᵢ ~ U(1 − w, 1 + w)를 쏠림 변동률(클램프 전)에 곱한다."""

    buys: ClassVar[dict[str, int]] = TestStockNoise.buys

    class Fixed(random.Random):
        def __init__(self, u: float) -> None:
            super().__init__(0)
            self.u = u

        def random(self) -> float:
            return self.u

    def test_default_and_range(self) -> None:
        assert P.stock_rate_jitter == 0.10
        EventParams(stock_rate_jitter=0)
        EventParams(stock_rate_jitter=STOCK_RATE_JITTER_MAX)
        for bad in (-0.01, STOCK_RATE_JITTER_MAX + 0.01, float("nan")):
            with pytest.raises(ValueError):
                EventParams(stock_rate_jitter=bad)

    def test_draw(self) -> None:
        off = replace(P, stock_rate_jitter=0)
        assert draw_stock_rate_factor(PRICES, off, random.Random(1)) is None
        # 균등난수 0.5(테스트 StubRandom 기본값)면 k = 1 → 기존 정산 결과가 그대로다
        assert draw_stock_rate_factor(PRICES, P, self.Fixed(0.5)) == dict.fromkeys(PRICES, 1.0)
        assert draw_stock_rate_factor(PRICES, P, self.Fixed(0.0)) == dict.fromkeys(PRICES, 0.9)
        high = draw_stock_rate_factor(PRICES, P, self.Fixed(1.0))
        assert high is not None and all(k == pytest.approx(1.1) for k in high.values())

    def test_range_in_practice(self) -> None:
        rng = random.Random(2026)
        ks = [
            k for _ in range(5_000) for k in (draw_stock_rate_factor(PRICES, P, rng) or {}).values()
        ]
        assert min(ks) >= 0.9 and max(ks) <= 1.1
        assert sum(ks) / len(ks) == pytest.approx(1.0, abs=0.002)

    def test_scales_rate_before_clamp(self) -> None:
        """§2.4: SKLOW -6% × 1.1 = -6.6%, MIRAE +12% × 0.9 = +10.8%.

        SAMSU -30% × 1.1 = -33%는 ±30% 제한으로 다시 -30%.
        """
        k = {"SAMSU": 1.1, "SKLOW": 1.1, "MIRAE": 0.9, "LB": 1.0}
        moves = settle_stocks(PRICES, self.buys, P0, rate_factor=k)
        assert moves["SKLOW"].rate == Fraction(-66, 1000)
        assert moves["MIRAE"].rate == Fraction(108, 1000)
        assert moves["SAMSU"].rate == Fraction(-3, 10)  # ±30% 제한은 배율 뒤에도 지킨다
        assert moves["LB"].rate == Fraction(24, 100)
        assert moves["SKLOW"].rate_factor == 1.1
        # 쏠림만으로는 합이 0이지만, 배율이 종목마다 달라 합이 0으로 고정되지 않는다
        assert sum(m.rate for m in settle_stocks(PRICES, self.buys, P0).values()) == 0
        assert sum(m.rate for m in moves.values()) != 0

    def test_news_multiplies_after_scaled_rate(self) -> None:
        k = dict.fromkeys(PRICES, 0.9)
        moves = settle_stocks(PRICES, self.buys, P0, rate_factor=k, news={"MIRAE": Fraction(1, 10)})
        mirae = moves["MIRAE"]
        assert mirae.rate == Fraction(108, 1000)
        assert mirae.total_rate == Fraction(1108, 1000) * Fraction(11, 10) - 1

    def test_without_factor_matches_before(self) -> None:
        plain = settle_stocks(PRICES, self.buys, P0)
        ones = settle_stocks(PRICES, self.buys, P0, rate_factor=dict.fromkeys(PRICES, 1.0))
        assert all(m.rate_factor is None for m in plain.values())
        assert [m.new_price for m in ones.values()] == [m.new_price for m in plain.values()]

    def test_validation(self) -> None:
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, P, rate_factor={"SAMSU": 1.0})  # 종목 누락
        for bad in (0.0, -1.0, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                settle_stocks(PRICES, {}, P, rate_factor=dict.fromkeys(PRICES, bad))


class StubHalf(random.Random):
    def __init__(self) -> None:
        super().__init__(0)

    def random(self) -> float:
        return 0.5


class Seq(random.Random):
    """정해진 균등난수를 순서대로 돌려준다."""

    def __init__(self, values: list[float]) -> None:
        super().__init__(0)
        self.values = values

    def random(self) -> float:
        return self.values.pop(0)


class TestNews:
    """03-pricing §3: 호재·악재는 쏠림 변동률에 곱으로 얹힌다."""

    buys: ClassVar[dict[str, int]] = {
        "SAMSU": 2000 * MAN,
        "SKLOW": 1200 * MAN,
        "MIRAE": 600 * MAN,
        "LB": 200 * MAN,
    }

    def test_combined_rate(self) -> None:
        assert combined_rate(Fraction(1, 10), None) == Fraction(1, 10)
        assert combined_rate(Fraction(1, 10), Fraction(-1, 5)) == Fraction(-12, 100)

    def test_news_multiplies_after_clamp(self) -> None:
        """SAMSU는 쏠림으로 -30%(클램프)인데 호재 +15%가 그 위에 곱해져 -19.5%가 된다."""
        moves = settle_stocks(PRICES, self.buys, P0, news={"SAMSU": Fraction(15, 100)})
        samsu = moves["SAMSU"]
        assert samsu.rate == Fraction(-3, 10)
        assert samsu.news_rate == Fraction(15, 100)
        assert samsu.total_rate == Fraction(-195, 1000)
        assert samsu.new_price == 60_380  # 75,000 × 0.805 = 60,375 → 10원 사사오입
        lb = moves["LB"]
        assert lb.news_rate is None and lb.total_rate == lb.rate == Fraction(24, 100)
        assert lb.new_price == 17_360  # §2.4 표와 같다

    def test_bad_news_can_exceed_daily_limit(self) -> None:
        """뉴스는 ±30% 클램프에 묶이지 않는다: 악재 -20% × 쏠림 -30% → -44%."""
        moves = settle_stocks(PRICES, self.buys, P0, news={"SAMSU": Fraction(-1, 5)})
        assert moves["SAMSU"].total_rate == Fraction(-44, 100)
        assert moves["SAMSU"].new_price == 42_000

    def test_news_validation(self) -> None:
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, P, news={"BYUNG": Fraction(1, 10)})
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, P, news={"LB": Fraction(-1)})

    def test_draw_news_sequence(self) -> None:
        """발생 여부 → 종목 → 호재·악재 → 크기 → 제목 순으로 균등난수를 쓴다."""
        codes = [i.code for i in STOCKS]
        assert draw_news(codes, P, Seq([0.5])) is None  # u ≥ 0.5 → 뉴스 없음
        draw = draw_news(codes, P, Seq([0.1, 0.3, 0.2, 0.5, 0.9]))
        assert draw is not None
        assert (draw.code, draw.kind, draw.rate, draw.headline_pick) == ("SKLOW", "good", 0.15, 0.9)
        bad = draw_news(codes, P, Seq([0.0, 0.99, 0.5, 0.333, 0.0]))
        assert bad is not None and (bad.code, bad.kind, bad.rate) == ("LB", "bad", 0.13)
        # 하한·상한이 엇갈려 저장돼 있어도 정렬해 쓴다
        swapped = replace(P, news_rate_min=0.2, news_rate_max=0.1)
        d = draw_news(codes, swapped, Seq([0.0, 0.0, 0.0, 0.0, 0.0]))
        assert d is not None and d.rate == 0.1
        assert draw_news([], P, Seq([])) is None

    def test_params_range(self) -> None:
        assert (P.news_probability, P.news_rate_min, P.news_rate_max) == (0.5, 0.1, 0.2)
        EventParams(news_probability=0, news_rate_min=1, news_rate_max=1)
        for bad in (
            {"news_probability": -0.1},
            {"news_probability": 1.1},
            {"news_rate_min": 0},
            {"news_rate_max": 1.5},
        ):
            with pytest.raises(ValueError):
                EventParams(**bad)


class TestCalendar:
    cal = EventCalendar()

    def test_period(self) -> None:
        days = self.cal.operating_days
        assert len(days) == 11 and days[0] == date(2026, 10, 6) and days[-1] == date(2026, 10, 16)
        assert self.cal.total_rounds == 10

    def test_unlimited(self) -> None:
        cal = EventCalendar(date(2026, 10, 6), None)
        far = date(2027, 10, 6)
        assert cal.unlimited and cal.total_rounds is None
        assert cal.is_operating_day(far) and not cal.is_operating_day(date(2026, 10, 5))
        assert not cal.is_ended(far)
        assert cal.round_of(far) == 366 and cal.next_operating_day(far) == far + timedelta(days=1)
        assert cal.next_operating_time(datetime(2027, 10, 6, 19, tzinfo=KST), time(9)) == (
            datetime(2027, 10, 7, 9, tzinfo=KST)
        )
        assert cal.days_through(date(2026, 10, 8)) == (
            date(2026, 10, 6),
            date(2026, 10, 7),
            date(2026, 10, 8),
        )
        with pytest.raises(ValueError):
            _ = cal.operating_days

    def test_days_through_is_clipped_to_the_period(self) -> None:
        assert self.cal.days_through(date(2027, 1, 1)) == self.cal.operating_days
        assert self.cal.days_through(date(2026, 10, 1)) == ()
        assert self.cal.is_ended(date(2026, 10, 17)) and not self.cal.is_ended(date(2026, 10, 16))

    def test_rounds(self) -> None:
        assert self.cal.round_of(date(2026, 10, 6)) == 1
        assert self.cal.round_of(date(2026, 10, 15)) == 10
        assert self.cal.round_of(date(2026, 10, 16)) is None
        assert self.cal.round_of(date(2026, 10, 17)) is None

    @pytest.mark.parametrize(
        ("t", "open_"),
        [
            (time(8, 59, 59), False),
            (time(9, 0), True),
            (time(17, 59, 59), True),
            (time(18, 0), False),
        ],
    )
    def test_market_hours(self, t: time, open_: bool) -> None:
        assert self.cal.is_market_open(datetime.combine(date(2026, 10, 10), t, KST)) is open_

    def test_weekend_is_operating(self) -> None:
        assert date(2026, 10, 10).weekday() == 5
        assert self.cal.is_operating_day(date(2026, 10, 10))

    def test_timezone_conversion(self) -> None:
        utc = datetime(2026, 10, 6, 0, 30, tzinfo=UTC)  # 09:30 KST
        assert self.cal.is_market_open(utc)
        with pytest.raises(ValueError):
            self.cal.is_market_open(datetime(2026, 10, 6, 10, 0))

    def test_certification_cutoff(self) -> None:
        d = date(2026, 10, 7)
        f = self.cal.certification_target_date
        assert f(datetime.combine(d, time(23, 59, 59), KST), time(23, 59)) == d
        assert f(datetime.combine(d, time(22, 0, 30), KST), time(22, 0)) == d
        assert f(datetime.combine(d, time(22, 1), KST), time(22, 0)) == d + timedelta(days=1)


class TestParams:
    def test_defaults_match_spec(self) -> None:
        assert (P.coin_p_up, P.coin_up_exp, P.coin_down_exp, P.coin_cap, P.coin_floor) == (
            0.30,
            2,
            2,
            0.8,
            -0.4,
        )
        assert P.stock_sensitivity == 0.30 and P.daily_buy_limit_ratio == 0.40
        assert (P.coin_calm_rounds, P.coin_calm_cap, P.coin_calm_floor) == (3, 0.30, -0.10)

    def test_reward_is_quarter_of_seed(self) -> None:
        assert P.reward_cash == 250_000 == INITIAL_CASH // 4

    def test_roundtrip(self) -> None:
        assert EventParams.from_dict(P.to_dict()) == P
        assert P.to_dict()["certification_cutoff"] == "23:59"

    def test_params_saved_before_v04_still_load(self) -> None:
        """v0.3까지 저장된 파라미터(reward_coin_quantity 있음, 안정기 없음)도 그대로 읽힌다."""
        old = {k: v for k, v in P.to_dict().items() if not k.startswith(("coin_calm", "reward"))}
        loaded = EventParams.from_dict({**old, "reward_coin_quantity": 2})
        assert loaded == P

    @pytest.mark.parametrize(
        "bad",
        [
            {"coin_p_up": 1.0},
            {"coin_floor": -1.0},
            {"daily_buy_limit_ratio": 0},
            {"stock_min_price": 0},
            {"reward_cash": -1},
            {"reward_cash": REWARD_CASH_MAX + 1},
            {"coin_calm_rounds": -1},
            {"coin_calm_rounds": CALM_ROUNDS_MAX + 1},
            {"coin_calm_cap": 0},
            {"coin_calm_cap": 10.5},
            {"coin_calm_floor": 0},
            {"coin_calm_floor": -1.0},
            {"coin_calm_cap": float("nan")},
        ],
    )
    def test_validation(self, bad: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            replace(P, **bad)


class TestNewsPool:
    """news_pool: 종목별 호재 5·악재 5, 공통 예비 호재 3·악재 3. 패러디 제약을 지킨다."""

    def test_pool_shape(self) -> None:
        from study_invest.news_pool import COMMON_POOLS, STOCK_POOLS, articles_for

        assert set(STOCK_POOLS) == {i.code for i in STOCKS}
        for code, kinds in STOCK_POOLS.items():
            assert {k: len(v) for k, v in kinds.items()} == {"good": 5, "bad": 5}, code
        assert {k: len(v) for k, v in COMMON_POOLS.items()} == {"good": 3, "bad": 3}
        candidates = articles_for("SKLOW", "SK로우닉스", "good")
        assert len(candidates) == 8
        assert all("{name}" not in a.headline + a.subtitle + a.body for a in candidates)
        assert all("SK로우닉스" in a.headline for a in candidates)

    def test_pool_constraints(self) -> None:
        import re

        from study_invest.news_pool import BYLINES, COMMON_POOLS, STOCK_POOLS

        banned = ("삼성", "하이닉스", "LG전자", "미래에셋", "현대")
        seen: set[str] = set()
        every = [a for kinds in STOCK_POOLS.values() for pool in kinds.values() for a in pool]
        every += [a for pool in COMMON_POOLS.values() for a in pool]
        for a in every:
            assert a.headline not in seen, a.headline  # 제목 중복 없음
            seen.add(a.headline)
            assert len(a.headline) <= 120 and len(a.subtitle) <= 120 and len(a.body) <= 600
            assert a.byline in BYLINES
            text = a.headline + a.subtitle + a.body
            assert not any(b in text for b in banned), a.headline
            assert not re.search(r"\d+\s*%", text), a.headline  # 변동률 숫자는 쓰지 않는다
        # 공통 풀: 업종이 드러나는 소재 금지, 종목명 바로 뒤 조사 금지(받침에 따라 달라짐)
        industry = ("서비스 장애", "접속", "앱", "출석", "반도체", "스마트폰", "자동차", "가전")
        for a in [a for pool in COMMON_POOLS.values() for a in pool]:
            text = a.headline + a.subtitle + a.body
            assert not any(w in text for w in industry), a.headline
            assert not re.search(r"\{name\}[이가은는을를의과와]", text), a.headline
