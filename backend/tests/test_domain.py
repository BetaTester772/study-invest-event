"""순수 도메인 로직: 반올림, 가격 산정, 운영 달력, 파라미터."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from fractions import Fraction
from typing import Any

import pytest

from study_invest.event_calendar import EventCalendar
from study_invest.instruments import INSTRUMENTS, STOCKS
from study_invest.money import exact, round_half_up
from study_invest.params import KST, EventParams
from study_invest.pricing import (
    coin_rate,
    draw_coin,
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
        assert coin_rate(0.29, 1.0, P) == ("up", 3.0)
        assert coin_rate(0.0, 0.5, P) == ("up", 3.0 * 0.125)

    def test_down_day_at_or_above_p_up(self) -> None:
        assert coin_rate(0.30, 1.0, P) == ("down", -0.5)
        assert coin_rate(0.99, 0.5, P) == ("down", -0.5 * 0.25)

    def test_zero_width(self) -> None:
        assert coin_rate(0.1, 0.0, P)[1] == 0
        assert coin_rate(0.9, 0.0, P)[1] == 0

    def test_range_spec_coin_2(self) -> None:
        rng = random.Random(1)
        for _ in range(10_000):
            _, r = coin_rate(rng.random(), rng.random(), P)
            assert -0.5 <= r <= 3.0

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
        assert (move.p, move.x, move.direction, move.new_price) == (0.1, 1.0, "up", 1_000_000)


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


class TestCalendar:
    cal = EventCalendar()

    def test_period(self) -> None:
        days = self.cal.operating_days
        assert len(days) == 11 and days[0] == date(2026, 10, 6) and days[-1] == date(2026, 10, 16)
        assert self.cal.total_rounds == 10

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
            3,
            2,
            3.0,
            -0.5,
        )
        assert P.stock_sensitivity == 0.30 and P.daily_buy_limit_ratio == 0.40
        assert P.reward_coin_quantity == 1

    def test_roundtrip(self) -> None:
        assert EventParams.from_dict(P.to_dict()) == P
        assert P.to_dict()["certification_cutoff"] == "23:59"

    @pytest.mark.parametrize(
        "bad",
        [
            {"coin_p_up": 1.0},
            {"coin_floor": -1.0},
            {"daily_buy_limit_ratio": 0},
            {"stock_min_price": 0},
            {"reward_coin_quantity": -1},
        ],
    )
    def test_validation(self, bad: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            replace(P, **bad)
