"""순수 도메인 로직: 반올림, 가격 산정, 운영 달력, 파라미터."""

from __future__ import annotations

import math
import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from fractions import Fraction
from typing import Any

import pytest

from study_invest.event_calendar import EventCalendar
from study_invest.instruments import INSTRUMENTS, STOCKS
from study_invest.money import exact, round_half_up
from study_invest.params import (
    CALM_ROUNDS_MAX,
    INITIAL_CASH,
    KST,
    NEWS_PER_DAY_MAX,
    REWARD_CASH_MAX,
    STOCK_DAILY_LIMIT,
    STOCK_P_SHIFT_MAX,
    EventParams,
)
from study_invest.pricing import (
    StockDraw,
    coin_rate,
    combined_rate,
    draw_coin,
    draw_news,
    draw_stock_randoms,
    flow_signal,
    is_calm_round,
    move_limit,
    next_coin_price,
    next_stock_price,
    settle_stocks,
    up_probability,
)

P = EventParams()
P0 = replace(P, virtual_liquidity=0)
PL = replace(P, stock_move_max=0.20, stock_move_exp=1)
"""계산 예시용: 폭 상한 5%~20%, 선형 폭(X¹). 03-pricing §2.4 예시와 같다."""
PRICES = {i.code: i.initial_price for i in STOCKS}
MAN = 10_000
L = P.virtual_liquidity  # 300만원


def same_draw(u: float, x: float) -> dict[str, StockDraw]:
    """전 종목에 같은 (u, X)."""
    return dict.fromkeys(PRICES, StockDraw(u, x))


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
    """03-pricing §2: 순매수 신호 z로 상승 확률과 폭 상한을 정하고 (u, X)로 뽑는다."""

    def test_flow_signal(self) -> None:
        assert flow_signal(0, L) == 0
        assert flow_signal(L, L) == Fraction(1, 2)
        assert flow_signal(-L, L) == Fraction(-1, 2)
        assert flow_signal(3 * L, L) == Fraction(3, 4)
        # L = 0이면 순매수 부호, 순매수도 0이면 0
        assert (flow_signal(10, 0), flow_signal(-10, 0), flow_signal(0, 0)) == (
            Fraction(1),
            Fraction(-1),
            Fraction(0),
        )

    def test_up_probability_rises_with_net_buy(self) -> None:
        assert up_probability(Fraction(0), P) == Fraction(1, 2)
        assert up_probability(Fraction(1, 2), P) == Fraction(13, 20)  # 0.5 + 0.3 × 0.5
        assert up_probability(Fraction(-1, 2), P) == Fraction(7, 20)
        assert up_probability(Fraction(1), P) == Fraction(4, 5)  # 한계 0.2~0.8
        assert up_probability(Fraction(1, 2), replace(P, stock_p_shift=0)) == Fraction(1, 2)

    def test_move_limit_shrinks_with_net_flow(self) -> None:
        assert move_limit(Fraction(0), PL) == Fraction(1, 5)  # M_max 20%
        assert move_limit(Fraction(1, 2), PL) == Fraction(1, 8)  # 5% + 15% × 0.5
        assert move_limit(Fraction(-1, 2), PL) == Fraction(1, 8)  # 순매도도 같다
        assert move_limit(Fraction(1), PL) == Fraction(1, 20)  # M_min 5%
        limits = [move_limit(flow_signal(n * MAN, L), PL) for n in (0, 100, 500, 2000, 10_000)]
        assert limits == sorted(limits, reverse=True)
        # 최대·최소가 엇갈려 저장돼 있어도 정렬해 쓴다
        swapped = replace(PL, stock_move_max=0.05, stock_move_min=0.20)
        assert move_limit(Fraction(1, 2), swapped) == Fraction(1, 8)

    def test_settlement_example(self) -> None:
        """L=300만. SAMSU 순매수 300만(z=0.5), LB 순매도 300만(z=−0.5), 나머지 0. u=0.6, X=1."""
        moves = settle_stocks(
            PRICES,
            {"SAMSU": 600 * MAN, "LB": 100 * MAN},
            {"SAMSU": 300 * MAN, "LB": 400 * MAN},
            PL,
            same_draw(0.6, 1.0),
        )
        samsu, sklow, lb = moves["SAMSU"], moves["SKLOW"], moves["LB"]
        assert (samsu.buy_amount, samsu.sell_amount, samsu.net_amount) == (
            600 * MAN,
            300 * MAN,
            300 * MAN,
        )
        assert (samsu.signal, samsu.p_up, samsu.u, samsu.x) == (
            Fraction(1, 2),
            Fraction(13, 20),
            0.6,
            1.0,
        )
        assert (samsu.direction, samsu.rate) == ("up", Fraction(1, 8))  # 0.6 < 0.65
        assert samsu.new_price == 84_380  # 75,000 × 1.125 = 84,375 → 10원 사사오입
        assert (sklow.p_up, sklow.direction, sklow.rate) == (
            Fraction(1, 2),
            "down",
            Fraction(-1, 5),
        )
        assert sklow.new_price == 136_000
        assert (lb.net_amount, lb.p_up, lb.direction) == (-300 * MAN, Fraction(7, 20), "down")
        assert lb.rate == Fraction(-1, 8) and lb.new_price == 12_250

    def test_magnitude_scales_with_x(self) -> None:
        moves = settle_stocks(PRICES, {}, {}, PL, same_draw(0.1, 0.5))
        assert all(m.direction == "up" and m.rate == Fraction(1, 10) for m in moves.values())
        moves = settle_stocks(PRICES, {}, {}, PL, same_draw(0.9, 0.0))
        assert all(m.rate == 0 and m.new_price == m.old_price for m in moves.values())

    def test_magnitude_uses_exponent(self) -> None:
        """기본 폭 지수 2: 변동률 = 폭 상한 × X². 순매수 0이면 폭 상한 15%라 X=0.5 → 3.75%."""
        moves = settle_stocks(PRICES, {}, {}, P, same_draw(0.1, 0.5))
        assert all(m.direction == "up" and m.rate == Fraction(3, 80) for m in moves.values())
        moves = settle_stocks(PRICES, {}, {}, P, same_draw(0.9, 1.0))
        assert all(m.rate == Fraction(-3, 20) for m in moves.values())  # X=1이면 지수와 무관
        cubic = settle_stocks(PRICES, {}, {}, replace(PL, stock_move_exp=3), same_draw(0.1, 0.5))
        assert all(m.rate == Fraction(1, 40) for m in cubic.values())  # 20% × 0.125

    def test_default_magnitude_statistics(self) -> None:
        """순매수 0, 기본값: |변동률| 평균 ≈ 15%/3 = 5%, 최대 15%, 10% 초과 ≈ 1 − √(2/3) ≈ 18.4%."""
        rng = random.Random(7)
        mags = [
            abs(float(m.rate))
            for _ in range(5_000)
            for m in settle_stocks(PRICES, {}, {}, P, draw_stock_randoms(PRICES, rng)).values()
        ]
        n = len(mags)
        assert sum(mags) / n == pytest.approx(0.05, abs=0.002)
        assert max(mags) <= 0.15
        assert sum(x > 0.10 for x in mags) / n == pytest.approx(1 - math.sqrt(2 / 3), abs=0.01)

    def test_up_ratio_follows_probability(self) -> None:
        """순매수 L이면 상승 비율 ≈ 0.65, 순매도 L이면 ≈ 0.35. 크기는 ≤ 12.5%."""
        rng = random.Random(2026)
        ups = {"SAMSU": 0, "LB": 0}
        n = 20_000
        for _ in range(n):
            moves = settle_stocks(
                PRICES,
                {"SAMSU": L},
                {"LB": L},
                P,
                draw_stock_randoms(PRICES, rng),
            )
            for code in ups:
                ups[code] += moves[code].direction == "up"
                assert abs(moves[code].rate) <= Fraction(1, 8)
        assert ups["SAMSU"] / n == pytest.approx(0.65, abs=0.015)
        assert ups["LB"] / n == pytest.approx(0.35, abs=0.015)

    def test_draw_order(self) -> None:
        """종목 순서대로 (u, X)를 쓴다."""
        draws = draw_stock_randoms(["A", "B"], Seq([0.1, 0.2, 0.3, 0.4]))
        assert draws == {"A": StockDraw(0.1, 0.2), "B": StockDraw(0.3, 0.4)}

    def test_min_price_floor(self) -> None:
        assert next_stock_price(1_200, Fraction(-3, 10), 1_000) == 1_000
        assert next_stock_price(14_000, Fraction(24, 100), 1_000) == 17_360

    def test_validation(self) -> None:
        draws = same_draw(0.5, 0.5)
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {"BYUNG": 1}, {}, P, draws)
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, {"BYUNG": 1}, P, draws)
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {"LB": -1}, {}, P, draws)
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, {}, P, {"SAMSU": StockDraw(0.5, 0.5)})  # 종목 누락
        for bad in (StockDraw(1.0, 0.5), StockDraw(0.5, 1.5), StockDraw(float("nan"), 0.5)):
            with pytest.raises(ValueError):
                settle_stocks(PRICES, {}, {}, P, dict.fromkeys(PRICES, bad))

    def test_params_defaults_and_range(self) -> None:
        assert (P.stock_p_shift, P.stock_move_max, P.stock_move_min) == (0.30, 0.15, 0.05)
        assert P.stock_move_exp == 2
        EventParams(stock_p_shift=0, stock_move_min=0, stock_move_exp=0.5)
        EventParams(stock_p_shift=STOCK_P_SHIFT_MAX, stock_move_max=STOCK_DAILY_LIMIT)
        bad_values: list[tuple[str, float]] = [
            ("stock_p_shift", -0.01),
            ("stock_p_shift", STOCK_P_SHIFT_MAX + 0.01),
            ("stock_move_max", 0),
            ("stock_move_max", STOCK_DAILY_LIMIT + 0.01),
            ("stock_move_min", -0.01),
            ("stock_move_min", STOCK_DAILY_LIMIT + 0.01),
            ("stock_move_min", float("nan")),
            ("stock_move_exp", 0),
            ("stock_move_exp", 100.5),
            ("stock_move_exp", float("nan")),
        ]
        for field, bad in bad_values:
            with pytest.raises(ValueError):
                replace(P, **{field: bad})  # type: ignore[arg-type]


class Seq(random.Random):
    """정해진 균등난수를 순서대로 돌려준다."""

    def __init__(self, values: list[float]) -> None:
        super().__init__(0)
        self.values = values

    def random(self) -> float:
        return self.values.pop(0)


class TestNews:
    """03-pricing §3: 호재·악재는 확률 변동률에 곱으로 얹힌다."""

    def test_combined_rate(self) -> None:
        assert combined_rate(Fraction(1, 10), None) == Fraction(1, 10)
        assert combined_rate(Fraction(1, 10), Fraction(-1, 5)) == Fraction(-12, 100)

    def test_news_multiplies_after_rate(self) -> None:
        """전 종목 -20%(u=0.99, X=1)인데 SAMSU는 호재 +15%가 곱해져 -8%가 된다."""
        news = {"SAMSU": Fraction(15, 100)}
        moves = settle_stocks(PRICES, {}, {}, PL, same_draw(0.99, 1.0), news=news)
        samsu = moves["SAMSU"]
        assert samsu.rate == Fraction(-1, 5)
        assert samsu.news_rate == Fraction(15, 100)
        assert samsu.total_rate == Fraction(-8, 100)
        assert samsu.new_price == 69_000
        lb = moves["LB"]
        assert lb.news_rate is None and lb.total_rate == lb.rate == Fraction(-1, 5)
        assert lb.new_price == 11_200

    def test_bad_news_can_exceed_daily_limit(self) -> None:
        """뉴스는 ±30%에 묶이지 않는다: 악재 -20% × 확률 변동 -20% → -36%."""
        news = {"SAMSU": Fraction(-1, 5)}
        moves = settle_stocks(PRICES, {}, {}, PL, same_draw(0.99, 1.0), news=news)
        assert moves["SAMSU"].total_rate == Fraction(-36, 100)
        assert moves["SAMSU"].new_price == 48_000

    def test_news_validation(self) -> None:
        draws = same_draw(0.5, 0.5)
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, {}, P, draws, news={"BYUNG": Fraction(1, 10)})
        with pytest.raises(ValueError):
            settle_stocks(PRICES, {}, {}, P, draws, news={"LB": Fraction(-1)})

    def test_draw_news_sequence(self) -> None:
        """기본값은 호재 1건·악재 1건. 뉴스마다 종목 → 크기 → 제목 순으로 균등난수를 쓴다."""
        codes = [i.code for i in STOCKS]
        assert (P.news_good_per_day, P.news_bad_per_day) == (1, 1)
        good_only = replace(P, news_good_per_day=1, news_bad_per_day=0)
        draws = draw_news(codes, good_only, Seq([0.3, 0.5, 0.9]))
        assert [(d.code, d.kind, d.rate, d.headline_pick) for d in draws] == [
            ("SKLOW", "good", 0.1, 0.9)
        ]
        bad_only = replace(P, news_good_per_day=0, news_bad_per_day=1)
        draws = draw_news(codes, bad_only, Seq([0.99, 0.333, 0.0]))
        assert [(d.code, d.kind, d.rate) for d in draws] == [("LB", "bad", 0.08)]
        # 하한·상한이 엇갈려 저장돼 있어도 정렬해 쓴다
        swapped = replace(good_only, news_rate_min=0.2, news_rate_max=0.1)
        assert [x.rate for x in draw_news(codes, swapped, Seq([0.0, 0.0, 0.0]))] == [0.1]
        assert draw_news([], P, Seq([])) == []

    def test_draw_news_default_is_one_good_and_one_bad_on_different_stocks(self) -> None:
        codes = [i.code for i in STOCKS]
        # 호재: 4종목 중 첫째(SAMSU). 악재: 남은 3종목 중 첫째(SKLOW)
        draws = draw_news(codes, P, Seq([0.0, 0.5, 0.0, 0.0, 0.0, 0.9]))
        assert [(d.code, d.kind, d.rate) for d in draws] == [
            ("SAMSU", "good", 0.1),  # 크기 U 0.5 → 5% + 10% × 0.5
            ("SKLOW", "bad", 0.05),  # 크기 U 0.0 → 하한 5%
        ]
        # 난수가 같은 자리를 가리켜도(0.0) 종목은 겹치지 않는다. 어느 난수에서도 건수와 순서는 같다.
        rng = random.Random(7)
        seen_good: set[str] = set()
        seen_bad: set[str] = set()
        for _ in range(500):
            got = draw_news(codes, P, rng)
            assert [d.kind for d in got] == ["good", "bad"]
            assert got[0].code != got[1].code
            assert all(0.05 <= d.rate <= 0.15 for d in got)
            seen_good.add(got[0].code)
            seen_bad.add(got[1].code)
        # 호재·악재 모두 어느 종목에든 갈 수 있다(특정 종목에 쏠리지 않는다)
        assert seen_good == seen_bad == set(codes)

    def test_draw_news_counts(self) -> None:
        codes = [i.code for i in STOCKS]
        three = replace(P, news_good_per_day=2, news_bad_per_day=1)
        got = draw_news(codes, three, random.Random(1))
        assert [d.kind for d in got] == ["good", "good", "bad"]
        assert len({d.code for d in got}) == 3
        # 둘 다 0이면 난수를 쓰지 않고 뉴스도 없다
        off = replace(P, news_good_per_day=0, news_bad_per_day=0)
        assert draw_news(codes, off, Seq([])) == []
        # 4건이면 4종목 모두에 하나씩
        full = replace(P, news_good_per_day=2, news_bad_per_day=2)
        got = draw_news(codes, full, random.Random(2))
        assert sorted(d.code for d in got) == sorted(codes)
        # 종목이 건수보다 적으면 종목 수까지만
        assert len(draw_news(codes[:1], P, random.Random(3))) == 1

    def test_params_range(self) -> None:
        assert (P.news_good_per_day, P.news_bad_per_day) == (1, 1)
        assert (P.news_rate_min, P.news_rate_max) == (0.05, 0.15)
        EventParams(news_good_per_day=0, news_bad_per_day=0, news_rate_min=1, news_rate_max=1)
        EventParams(news_good_per_day=NEWS_PER_DAY_MAX, news_bad_per_day=0)
        EventParams(news_good_per_day=2, news_bad_per_day=2)
        for bad in (
            {"news_good_per_day": -1},
            {"news_bad_per_day": -1},
            {"news_good_per_day": NEWS_PER_DAY_MAX + 1},
            {"news_good_per_day": 3, "news_bad_per_day": 2},  # 합이 종목 수(4)를 넘는다
            {"news_rate_min": 0},
            {"news_rate_max": 1.5},
        ):
            with pytest.raises(ValueError):
                EventParams(**bad)

    def test_stored_params_with_the_removed_keys_still_load(self) -> None:
        """이전 버전이 저장한 news_probability·news_max_per_day는 무시하고 새 기본값을 쓴다."""
        loaded = EventParams.from_dict({"news_probability": 0.5, "news_max_per_day": 3})
        assert (loaded.news_good_per_day, loaded.news_bad_per_day) == (1, 1)


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
        assert P.stock_p_shift == 0.30 and P.daily_buy_limit_ratio == 0.40
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
