"""API 통합 흐름: 등록 → 공시 → 주문 → 정산 → 인증·보상 → 랭킹."""

from __future__ import annotations

import dataclasses
from datetime import date, time
from typing import Any

import pytest
from conftest import (
    PNG,
    Clock,
    StubRandom,
    email_code,
    open_day,
    order,
    register,
    register_with,
    settle_day,
    stock_draws,
)
from fastapi.testclient import TestClient

D1, D2, D3 = date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)
LAST = date(2026, 10, 16)


def prices(client: TestClient) -> dict[str, int]:
    return {i["code"]: i["price"] for i in client.get("/api/instruments").json()}


class TestRegistration:
    def test_register_gives_seed(self, client: TestClient) -> None:
        h = register(client)
        me = client.get("/api/me", headers=h).json()
        assert me["nickname"] == "alice" and me["status"] == "normal"
        pf = client.get("/api/me/portfolio", headers=h).json()
        assert pf["cash"] == 1_000_000 and pf["total_assets"] == 1_000_000 and pf["holdings"] == []

    def test_one_account_per_school_id(self, client: TestClient) -> None:
        register(client)  # alice@g.skku.edu
        # skku.edu와 g.skku.edu의 같은 ID는 같은 사람 → 코드 요청부터 거부
        for email in ("alice@skku.edu", "  ALICE@g.skku.edu "):
            r = client.post("/api/auth/email-code", json={"email": email})
            assert r.status_code == 409 and r.json()["detail"]["code"] == "EMAIL_TAKEN"
        r = register_with(client, "bob@skku.edu", "alice")
        assert r.json()["detail"]["code"] == "NICKNAME_TAKEN"

    def test_login_logout(self, client: TestClient) -> None:
        register(client)
        bad = client.post(
            "/api/auth/login", json={"identity": "alice@g.skku.edu", "password": "nope"}
        )
        assert bad.status_code == 401
        # 두 도메인 어느 쪽으로도 로그인
        for identity in ("Alice@g.skku.edu", "alice@skku.edu"):
            r = client.post(
                "/api/auth/login", json={"identity": identity, "password": "tiger-moon-river-42"}
            )
            assert r.status_code == 200, identity
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        me = client.get("/api/me", headers=h).json()
        # 본인 응답에도 메일은 가려서만 준다
        assert (me["masked_email"], me["verified"], me["email_verified"]) == (
            "a***@g.skku.edu",
            True,
            True,
        )
        assert "alice@g.skku.edu" not in str(me)
        assert client.post("/api/auth/logout", headers=h).status_code == 204
        assert client.get("/api/me", headers=h).status_code == 401

    def test_mid_event_join_same_seed(self, client: TestClient, clock: Clock) -> None:
        clock.set(date(2026, 10, 12))
        h = register(client, "late")
        assert client.get("/api/me/portfolio", headers=h).json()["cash"] == 1_000_000

    def test_closed_after_event(self, client: TestClient, clock: Clock) -> None:
        code = email_code(client, "x@g.skku.edu")
        clock.set(date(2026, 10, 17))
        r = client.post("/api/auth/email-code", json={"email": "y@g.skku.edu"})
        assert r.json()["detail"]["code"] == "REGISTRATION_CLOSED"
        r = register_with(client, "x@g.skku.edu", "xx", code)
        assert r.json()["detail"]["code"] == "REGISTRATION_CLOSED"


class TestTrading:
    def test_rejected_before_open_batch(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        clock.set(D1, time(9, 30))
        assert order(client, h, "SAMSU", "buy", 1)["reject_reason"] == "MARKET_NOT_OPENED"

    def test_market_hours(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        open_day(client, clock, D1)
        clock.set(D1, time(8, 59))
        assert order(client, h, "SAMSU", "buy", 1)["reject_reason"] == "MARKET_CLOSED"
        clock.set(D1, time(18, 0))
        assert order(client, h, "SAMSU", "buy", 1)["reject_reason"] == "MARKET_CLOSED"
        clock.set(D1, time(17, 59))
        assert order(client, h, "SAMSU", "buy", 1)["status"] == "filled"

    def test_buy_sell_and_average_price(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        open_day(client, clock, D1)
        o = order(client, h, "SAMSU", "buy", 3)
        assert (o["status"], o["price"], o["amount"]) == ("filled", 75_000, 225_000)
        order(client, h, "SAMSU", "sell", 1)
        pf = client.get("/api/me/portfolio", headers=h).json()
        assert pf["cash"] == 1_000_000 - 225_000 + 75_000
        (hold,) = pf["holdings"]
        assert (hold["quantity"], hold["avg_price"], hold["cost"]) == (2, 75_000, 150_000)
        assert pf["total_assets"] == 1_000_000

    def test_insufficient_cash_and_holdings(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        open_day(client, clock, D1)
        assert order(client, h, "SKLOW", "buy", 6)["reject_reason"] == "INSUFFICIENT_CASH"
        assert order(client, h, "LB", "sell", 1)["reject_reason"] == "INSUFFICIENT_HOLDINGS"
        assert order(client, h, "LB", "buy", 0)["reject_reason"] == "INVALID_QUANTITY"
        assert order(client, h, "NOPE", "buy", 1)["reject_reason"] == "UNKNOWN_INSTRUMENT"
        r = client.post(
            "/api/me/orders", json={"code": "LB", "side": "buy", "quantity": 1.5}, headers=h
        )
        assert r.status_code == 422

    def test_daily_buy_limit_40_percent(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        open_day(client, clock, D1)
        assert order(client, h, "SAMSU", "buy", 5)["status"] == "filled"  # 375,000
        rejected = order(client, h, "SAMSU", "buy", 1)  # 450,000 > 400,000
        assert rejected["reject_reason"] == "DAILY_BUY_LIMIT"
        assert "매수 상한" in rejected["reject_message"]
        assert order(client, h, "LB", "buy", 28)["status"] == "filled"  # 392,000, 종목별
        pf = client.get("/api/me/portfolio", headers=h).json()
        assert pf["buy_limit"]["limit_amount"] == 400_000
        assert pf["buy_limit"]["remaining"]["SAMSU"] == 25_000
        # 매도 후 재매수도 당일 누적 매수금액으로 센다
        order(client, h, "SAMSU", "sell", 5)
        assert order(client, h, "SAMSU", "buy", 1)["reject_reason"] == "DAILY_BUY_LIMIT"
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        assert order(client, h, "SAMSU", "buy", 1)["status"] == "filled"  # 다음 날 초기화

    def test_disqualified_cannot_trade(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        h = register(client)
        pid = client.get("/api/me", headers=h).json()["id"]
        client.patch(
            f"/api/admin/participants/{pid}", json={"status": "disqualified"}, headers=admin
        )
        open_day(client, clock, D1)
        assert order(client, h, "LB", "buy", 1)["reject_reason"] == "DISQUALIFIED"
        assert client.get("/api/ranking").json()["entries"] == []


class TestAdminPositions:
    def test_buys_sells_and_holdings(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        h = register(client)
        open_day(client, clock, D1)
        order(client, h, "SAMSU", "buy", 3)
        order(client, h, "SAMSU", "sell", 1)
        order(client, h, "LB", "buy", 2)
        rows = client.get("/api/admin/positions", headers=admin).json()
        by = {r["code"]: r for r in rows}
        assert set(by) == {"SAMSU", "LB"}
        s = by["SAMSU"]
        assert (s["quantity"], s["bought_quantity"], s["sold_quantity"]) == (2, 3, 1)
        assert s["bought_amount"] == 3 * s["price"] and s["value"] == 2 * s["price"]
        assert by["LB"]["nickname"] == "alice" and by["LB"]["quantity"] == 2
        assert client.get("/api/admin/positions").status_code == 401


class TestSettlement:
    def test_prices_follow_net_buy_probabilistically(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        h = register(client)
        open_day(client, clock, D1)
        assert client.get("/api/instruments").json()[0]["day"] == D1.isoformat()
        order(client, h, "SAMSU", "buy", 5)  # 375,000원
        order(client, h, "SAMSU", "sell", 2)  # 150,000원 → 순매수 225,000원
        # 코인 상승일, X=1 → 1회차는 안정기라 +30%(평소면 +80%).
        # SAMSU u=0.51: 순매수가 있어 상승 확률이 0.5보다 조금 높으므로(≈0.513) 상승, X=1.
        # 나머지는 (0.5, 0.5): 순매수 0 → 상승 확률 0.5 → 하락, 폭 상한 20% × 0.5 = -10%.
        rng.queue = [0.1, 1.0, *stock_draws(SAMSU=(0.51, 1.0), SKLOW=(0.5, 0.5))]
        result = settle_day(client, clock, D1)
        assert result["detail"]["round"] == 1
        new = result["detail"]["new_prices"]
        # z = 225,000 / 5,225,000 = 9/209, 폭 상한 = 5% + 15% × 200/209 ≈ 19.35%
        assert new["SAMSU"] == 89_520  # 75,000 × 1.19354… = 89,515.6 → 89,520
        assert new["SKLOW"] == 153_000 and new["LB"] == 14_000 and new["BYUNG"] == 325_000
        # 공시 전에는 D1 가격이 보인다
        assert prices(client)["SAMSU"] == 75_000
        open_day(client, clock, D2)
        p = client.get("/api/instruments").json()
        samsu = next(i for i in p if i["code"] == "SAMSU")
        assert samsu["price"] == 89_520 and samsu["previous_price"] == 75_000
        assert samsu["change_rate"] > 0
        hist = client.get("/api/instruments/BYUNG/history").json()
        assert [x["price"] for x in hist] == [250_000, 325_000]
        assert hist[1]["source"] == "settlement"
        logs = client.get("/api/admin/settlements", headers=admin).json()
        assert logs[0]["coin"]["p"] == 0.1 and logs[0]["coin"]["direction"] == "up"
        assert logs[0]["coin"]["calm"] is True
        row = logs[0]["stocks"][0]
        assert (row["code"], row["buy_amount"], row["sell_amount"], row["net_amount"]) == (
            "SAMSU",
            375_000,
            150_000,
            225_000,
        )
        assert row["signal"] == pytest.approx(9 / 209)
        assert row["p_up"] == pytest.approx(0.5 + 0.3 * 9 / 209)
        assert row["move_limit"] == pytest.approx(0.05 + 0.15 * 200 / 209)
        assert (row["u"], row["x"], row["direction"]) == (0.51, 1.0, "up")
        assert row["rate"] == row["move_limit"] and row["total_rate"] == row["rate"]
        assert row["concentration"] is None and row["noise_factor"] is None
        assert logs[0]["params"]["stock_p_shift"] == 0.3

    def test_net_sell_lowers_up_probability(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        """같은 u=0.49여도 순매도면 상승 확률이 0.5 아래로 내려가 하락한다."""
        h = register(client)
        open_day(client, clock, D1)
        order(client, h, "LB", "buy", 25)  # 350,000원
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        order(client, h, "LB", "sell", 25)
        rng.queue = [0.9, 0.0, *stock_draws(LB=(0.49, 1.0), MIRAE=(0.49, 1.0))]
        settle_day(client, clock, D2)
        logs = client.get("/api/admin/settlements", headers=admin).json()
        by = {x["code"]: x for x in logs[1]["stocks"]}
        assert by["LB"]["net_amount"] < 0 and by["LB"]["p_up"] < 0.49
        assert by["LB"]["direction"] == "down" and by["LB"]["rate"] < 0
        assert by["MIRAE"]["p_up"] == 0.5 and by["MIRAE"]["direction"] == "up"

    def test_stock_params(self, client: TestClient, clock: Clock, admin: dict[str, str]) -> None:
        params = client.get("/api/admin/params", headers=admin).json()
        assert (params["stock_p_shift"], params["stock_move_max"], params["stock_move_min"]) == (
            0.3,
            0.2,
            0.05,
        )
        assert "stock_sensitivity" not in params and "stock_noise_scale" not in params
        r = client.put("/api/admin/params", json=dict(params, stock_p_shift=0), headers=admin)
        assert r.status_code == 200 and r.json()["stock_p_shift"] == 0
        # 이 값을 모르는 이전 화면이 보내지 않아도 저장된 값을 유지한다
        new_keys = ("stock_p_shift", "stock_move_max", "stock_move_min")
        legacy = {k: v for k, v in params.items() if k not in new_keys}
        legacy |= {"stock_sensitivity": 0.3, "stock_noise_scale": 0.1, "stock_rate_jitter": 0.1}
        r = client.put("/api/admin/params", json=dict(legacy, news_probability=0.6), headers=admin)
        assert r.status_code == 200 and r.json()["stock_p_shift"] == 0
        assert r.json()["news_probability"] == 0.6
        for key, bad in (("stock_p_shift", 0.6), ("stock_move_max", 0), ("stock_move_min", 0.4)):
            assert (
                client.put(
                    "/api/admin/params", json=dict(params, **{key: bad}), headers=admin
                ).status_code
                == 422
            )
        # δ = 0이면 순매수가 있어도 상승 확률은 반반이다
        h = register(client)
        open_day(client, clock, D1)
        order(client, h, "SAMSU", "buy", 5)
        settle_day(client, clock, D1)
        logs = client.get("/api/admin/settlements", headers=admin).json()
        samsu = next(x for x in logs[0]["stocks"] if x["code"] == "SAMSU")
        assert samsu["net_amount"] == 375_000 and samsu["p_up"] == 0.5
        assert samsu["move_limit"] < 0.2  # 폭은 그래도 줄어든다

    def test_coin_is_calm_for_first_three_rounds(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        """초반 3회차(10/7~10/9 시작가)는 -10%~+30%, 4회차부터 평소 -40%~+80%."""
        days = [D1, D2, D3, date(2026, 10, 9)]
        for d in days:
            open_day(client, clock, d)
            rng.queue = [0.1, 1.0]  # 매번 최대 상승
            settle_day(client, clock, d)
        hist = client.get("/api/instruments/BYUNG/history").json()
        assert [x["price"] for x in hist] == [250_000, 325_000, 422_500, 549_250]  # +30% × 3
        logs = client.get("/api/admin/settlements", headers=admin).json()
        assert [(x["round"], x["coin"]["calm"], x["coin"]["rate"]) for x in logs] == [
            (1, True, 0.3),
            (2, True, 0.3),
            (3, True, 0.3),
            (4, False, 0.8),
        ]
        assert logs[3]["coin"]["new_price"] == int(549_250 * 1.8)  # 10/10 시작가, +80%

    def test_calm_rounds_follow_params(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        params = client.get("/api/admin/params", headers=admin).json()
        client.put("/api/admin/params", json=dict(params, coin_calm_rounds=0), headers=admin)
        open_day(client, clock, D1)
        rng.queue = [0.5, 1.0]  # 하락일, X=1
        assert settle_day(client, clock, D1)["detail"]["new_prices"]["BYUNG"] == 150_000  # -40%

    def test_settle_guards(self, client: TestClient, clock: Clock, admin: dict[str, str]) -> None:
        open_day(client, clock, D1)
        clock.set(D1, time(17, 0))
        r = client.post("/api/admin/batch/settle", json={"day": D1.isoformat()}, headers=admin)
        assert r.json()["detail"]["code"] == "TOO_EARLY"
        settle_day(client, clock, D1)
        r = client.post("/api/admin/batch/settle", json={"day": D1.isoformat()}, headers=admin)
        assert r.json()["detail"]["code"] == "ALREADY_SETTLED"

    def test_last_day_has_no_round(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        clock.set(LAST, time(18, 0))
        r = client.post("/api/admin/batch/settle", json={"day": LAST.isoformat()}, headers=admin)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "NO_ROUND"

    def test_failed_settlement_carries_over(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        open_day(client, clock, D1)
        # 정산 없이 다음 날 공시 → 전일 가격 유지
        result = open_day(client, clock, D2)
        assert set(result["detail"]["sources"].values()) == {"carry_over"}
        assert prices(client)["SAMSU"] == 75_000
        clock.set(D2, time(18, 0))
        r = client.post("/api/admin/batch/settle", json={"day": D1.isoformat()}, headers=admin)
        assert r.json()["detail"]["code"] == "NEXT_DAY_OPENED"

    def test_manual_price_overrides_settlement(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        open_day(client, clock, D1)
        r = client.put(
            f"/api/admin/prices/{D2}/LB", json={"price": 20_000, "reason": "테스트"}, headers=admin
        )
        assert r.status_code == 200 and r.json()["source"] == "manual"
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        assert prices(client)["LB"] == 20_000
        r = client.put(
            f"/api/admin/prices/{D2}/LB", json={"price": 1, "reason": "x"}, headers=admin
        )
        assert r.json()["detail"]["code"] == "DAY_ALREADY_OPENED"

    def test_run_due_is_idempotent(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        clock.set(D1, time(8, 0))
        assert client.post("/api/admin/batch/run-due", headers=admin).json() == []
        clock.set(D1, time(9, 0))
        assert [
            r["action"] for r in client.post("/api/admin/batch/run-due", headers=admin).json()
        ] == ["open"]
        assert client.post("/api/admin/batch/run-due", headers=admin).json() == []
        clock.set(D1, time(18, 1))
        assert [
            r["action"] for r in client.post("/api/admin/batch/run-due", headers=admin).json()
        ] == ["settle"]
        # 다음 날 공시 누락 후 18시: 공시 + 정산을 한 번에
        clock.set(D2, time(18, 5))
        assert [
            r["action"] for r in client.post("/api/admin/batch/run-due", headers=admin).json()
        ] == ["open", "settle"]
        event = client.get("/api/event").json()
        assert event["market"]["day_settled"] is True and event["market"]["is_open"] is False


class TestNews:
    """호재·악재: 전날 정산에서 뽑아 같은 정산에서 곱한다 → 반영된 시작가와 함께 09:00에 발표."""

    def test_random_news_is_drawn_and_applied_in_the_previous_settlement(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        open_day(client, clock, D1)
        assert client.get("/api/news").json() == []
        # 코인(p, X) → 주식 (u, X) 4쌍 → 뉴스(발생, 종목, 종류, 크기, 제목) 순서로 난수를 쓴다.
        # 주식은 X = 0이라 확률 변동이 0%다.
        rng.queue = [0.9, 0.0, *stock_draws(), 0.1, 0.3, 0.2, 0.5, 0.0]
        result = settle_day(client, clock, D1)
        applied = result["detail"]["news"]
        assert [(n["day"], n["code"], n["kind"], n["rate"], n["source"]) for n in applied] == [
            (D2.isoformat(), "SKLOW", "good", 0.15, "random")
        ]
        assert "SK로우닉스" in applied[0]["headline"]
        # 같은 정산에서 바로 곱해진다: 확률 변동 0% × 1.15
        new = result["detail"]["new_prices"]
        assert new["SKLOW"] == 195_500 and new["SAMSU"] == 75_000
        # 공시 전에는 참가자에게 보이지 않는다(관리자 목록에는 반영 완료로 보인다)
        assert client.get("/api/news").json() == []
        assert all(i["news"] is None for i in client.get("/api/instruments").json())
        listed = client.get("/api/admin/news", headers=admin).json()
        assert [(n["code"], n["source"], n["applied"]) for n in listed] == [
            ("SKLOW", "random", True)
        ]
        open_day(client, clock, D2)
        items = client.get("/api/news").json()
        assert [(n["day"], n["code"], n["kind"], n["rate"], n["name"]) for n in items] == [
            (D2.isoformat(), "SKLOW", "good", 0.15, "SK로우닉스")
        ]
        ins = {i["code"]: i for i in client.get("/api/instruments").json()}
        assert ins["SKLOW"]["news"]["headline"] == applied[0]["headline"]
        assert ins["SKLOW"]["price"] == 195_500 and ins["SKLOW"]["change_rate"] == 0.15
        assert ins["SAMSU"]["news"] is None
        # 무작위 뉴스는 종목별 기사 풀에서 제목·부제·본문·바이라인을 모두 채운다
        article = items[0]
        assert article["subtitle"] and article["body"] and article["byline"]
        assert "SK로우닉스" in article["body"] and "{name}" not in article["body"]
        logs = client.get("/api/admin/settlements", headers=admin).json()
        row = next(x for x in logs[0]["stocks"] if x["code"] == "SKLOW")
        assert (row["rate"], row["news_rate"], row["total_rate"]) == (0, 0.15, 0.15)
        other = next(x for x in logs[0]["stocks"] if x["code"] == "SAMSU")
        assert other["news_rate"] is None and other["total_rate"] == 0

    def test_manual_news_overrides_random_and_locks_once_priced(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        open_day(client, clock, D1)
        r = client.put(
            f"/api/admin/news/{D2}/LB",
            json={"kind": "bad", "rate": 0.2, "headline": "  LB,  공장 화재 "},
            headers=admin,
        )
        assert r.status_code == 200, r.text
        assert (r.json()["source"], r.json()["applied"], r.json()["headline"]) == (
            "manual",
            False,
            "LB, 공장 화재",
        )
        assert (r.json()["subtitle"], r.json()["body"], r.json()["byline"]) == (None, None, None)
        # 무작위 뉴스가 나올 난수여도 D2에 이미 뉴스가 있어 만들지 않고 관리자 뉴스를 곱한다
        rng.queue = [0.9, 0.0, *stock_draws(), 0.1, 0.3, 0.2, 0.5, 0.0]
        result = settle_day(client, clock, D1)
        assert [(n["code"], n["source"]) for n in result["detail"]["news"]] == [("LB", "manual")]
        assert result["detail"]["new_prices"]["LB"] == 11_200  # 14,000 × 0.8
        assert [
            (n["code"], n["applied"]) for n in client.get("/api/admin/news", headers=admin).json()
        ] == [("LB", True)]
        # D2 시작가가 정해졌으므로 공시 전이어도 바꾸거나 지울 수 없다
        r = client.put(
            f"/api/admin/news/{D2}/LB",
            json={"kind": "good", "rate": 0.1, "headline": "x"},
            headers=admin,
        )
        assert r.json()["detail"]["code"] == "PRICE_ALREADY_FIXED"
        r = client.delete(f"/api/admin/news/{D2}/LB", headers=admin)
        assert r.json()["detail"]["code"] == "PRICE_ALREADY_FIXED"
        open_day(client, clock, D2)
        assert client.get("/api/news").json()[0]["kind"] == "bad"
        assert prices(client)["LB"] == 11_200
        # 아직 정산 전인 다음 날(D3) 뉴스는 몇 번이고 덮어쓸 수 있다
        for rate, headline in ((0.1, "LB 반등"), (0.25, "정정: LB 급반등")):
            r = client.put(
                f"/api/admin/news/{D3}/LB",
                json={"kind": "good", "rate": rate, "headline": headline},
                headers=admin,
            )
            assert r.status_code == 200 and r.json()["rate"] == rate
        rng.queue = [0.9, 0.0, *stock_draws()]
        assert settle_day(client, clock, D2)["detail"]["new_prices"]["LB"] == 14_000  # ×1.25
        audit = client.get("/api/admin/audit", headers=admin).json()
        assert {a["action"] for a in audit} >= {"news.manual", "market.settle"}

    def test_random_news_avoids_repeating_an_article(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        """같은 종목에 같은 pick 값이 와도 이미 나온 제목은 피한다."""
        headlines = []
        for d in (D1, D2, D3):
            open_day(client, clock, d)
            # 매번 SKLOW 호재, pick=0
            rng.queue = [0.9, 0.0, *stock_draws(), 0.1, 0.3, 0.2, 0.5, 0.0]
            headlines.append(settle_day(client, clock, d)["detail"]["news"][0]["headline"])
        assert len(set(headlines)) == 3
        listed = client.get("/api/admin/news", headers=admin).json()
        assert all(n["code"] == "SKLOW" and n["body"] for n in listed)

    def test_manual_news_validation_and_delete(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        def put(day: date, code: str, **body: Any) -> Any:
            return client.put(
                f"/api/admin/news/{day}/{code}",
                json={"kind": "good", "rate": 0.1, "headline": "x", **body},
                headers=admin,
            )

        assert put(D2, "BYUNG").json()["detail"]["code"] == "NOT_A_STOCK"
        assert put(D2, "NOPE").status_code == 404
        assert put(LAST, "LB").json()["detail"]["code"] == "NO_ROUND"
        assert put(date(2026, 10, 5), "LB").json()["detail"]["code"] == "NOT_OPERATING_DAY"
        assert put(D1, "LB").json()["detail"]["code"] == "NO_PREVIOUS_SETTLEMENT"  # 첫날
        assert put(D2, "LB", rate=0).json()["detail"]["code"] == "INVALID_RATE"
        assert put(D2, "LB", rate=1.5).json()["detail"]["code"] == "INVALID_RATE"
        assert put(D2, "LB", headline="   ").json()["detail"]["code"] == "HEADLINE_REQUIRED"
        assert put(D2, "LB", headline="x" * 121).status_code == 422
        assert put(D2, "LB", kind="meh").status_code == 422
        assert put(D2, "LB", body="x" * 601).status_code == 422  # 스키마 상한
        trimmed = put(D2, "LB", byline=" 명륜  뉴스 ", body="  본문  한 줄 ").json()
        assert (trimmed["body"], trimmed["byline"]) == ("본문 한 줄", "명륜 뉴스")
        assert client.delete(f"/api/admin/news/{D2}/LB", headers=admin).status_code == 204
        assert client.delete(f"/api/admin/news/{D2}/LB", headers=admin).status_code == 404
        assert client.get("/api/admin/news", headers=admin).json() == []


class TestQaAdvancePrice:
    URL = "/api/admin/qa/advance-price"

    def enable(self, client: TestClient) -> None:
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        state.settings = dataclasses.replace(state.settings, qa_tools=True)

    def test_disabled_by_default(self, client: TestClient, admin: dict[str, str]) -> None:
        assert client.get("/api/admin/qa", headers=admin).json() == {"enabled": False}
        r = client.post(self.URL, headers=admin)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "QA_DISABLED"

    def test_requires_admin_key(self, client: TestClient) -> None:
        self.enable(client)
        assert client.post(self.URL).status_code == 401

    def test_first_press_opens_first_day_even_before_event(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        clock.set(date(2026, 10, 1))  # 이벤트 시작 전
        r = client.post(self.URL, headers=admin)
        assert r.status_code == 200 and r.json()["day"] == D1.isoformat()
        assert "round" not in r.json()["detail"] and prices(client)["BYUNG"] == 250_000
        assert client.post(self.URL, headers=admin).json()["detail"]["round"] == 1

    def test_settles_and_opens_next_day_before_the_clock(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        assert client.get("/api/admin/qa", headers=admin).json() == {"enabled": True}
        open_day(client, clock, D1)  # 시계는 D1 10:00 — 18:00·D2 모두 아직 먼 미래
        rng.queue = [0.5, 1.0]  # 병더리움 하락일, X=1 → 안정기 -10%
        r = client.post(self.URL, headers=admin)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["action"] == "advance" and body["day"] == D2.isoformat()
        assert body["detail"]["settled_day"] == D1.isoformat() and body["detail"]["round"] == 1
        assert prices(client)["BYUNG"] == 225_000  # 250,000 × 0.9, 즉시 공시됨
        actions = [a["action"] for a in client.get("/api/admin/audit", headers=admin).json()]
        assert {"market.settle", "market.open", "qa.advance_price"} <= set(actions)

    def test_repeats_round_by_round_until_last_day(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        open_day(client, clock, D1)
        for round_no in range(1, 11):
            r = client.post(self.URL, headers=admin)
            assert r.status_code == 200, r.text
            assert r.json()["detail"]["round"] == round_no
        assert r.json()["day"] == LAST.isoformat()
        r = client.post(self.URL, headers=admin)  # 마지막 날은 반영일이 없다
        assert r.status_code == 409 and r.json()["detail"]["code"] == "NO_ROUND"

    def test_opens_only_when_already_settled(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        open_day(client, clock, D1)
        settle_day(client, clock, D1)  # 정산만 끝나고 다음 날 공시 전
        assert prices(client)["BYUNG"] == 250_000  # 아직 D1 시작가가 공시 중
        r = client.post(self.URL, headers=admin)
        assert r.status_code == 200 and "round" not in r.json()["detail"]
        assert r.json()["day"] == D2.isoformat()
        assert prices(client)["BYUNG"] == 243_750  # 정산 결과(-2.5%)가 공시됨

    def test_normal_batches_still_respect_the_clock(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        open_day(client, clock, D1)
        clock.set(D1, time(17, 0))
        r = client.post("/api/admin/batch/settle", json={"day": D1.isoformat()}, headers=admin)
        assert r.json()["detail"]["code"] == "TOO_EARLY"


class TestQaUnlimited:
    """QA 무제한 모드: 종료일 없이 회차가 끝없이 이어진다."""

    def enable(self, client: TestClient) -> None:
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        state.settings = dataclasses.replace(state.settings, qa_tools=True, qa_unlimited=True)
        state.calendar = state.settings.calendar

    def test_settings_drop_the_end_date(self, client: TestClient) -> None:
        self.enable(client)
        cal = client.app.state.study_invest.calendar  # type: ignore[attr-defined]
        assert cal.start == D1 and cal.end is None and cal.total_rounds is None

    def test_advance_goes_past_the_event_end(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        open_day(client, clock, D1)
        for round_no in range(1, 31):
            r = client.post("/api/admin/qa/advance-price", headers=admin)
            assert r.status_code == 200, r.text
            assert r.json()["detail"]["round"] == round_no
        assert r.json()["day"] == date(2026, 11, 5).isoformat()  # D1 + 30일
        history = client.get("/api/instruments/BYUNG/history").json()
        assert (
            len(history) == 31
            and len(client.get("/api/admin/settlements", headers=admin).json()) == 30
        )

    def test_event_info_has_no_end(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        clock.set(date(2026, 10, 20))
        info = client.get("/api/event").json()
        assert info["end"] is None and info["total_rounds"] is None
        assert info["is_operating_day"] is True and info["market"]["round"] == 15
        assert info["operating_days"][0] == D1.isoformat()
        assert info["operating_days"][-1] == "2026-10-20"  # 오늘까지만
        assert info["coin"]["calm_until"] == "2026-10-09"
        # 시계보다 앞서 공시된 날까지 늘어난다
        clock.set(D1, time(9, 0))
        client.post("/api/admin/batch/open", json={"day": D1.isoformat()}, headers=admin)
        for _ in range(3):
            client.post("/api/admin/qa/advance-price", headers=admin)
        assert (
            client.get("/api/event").json()["operating_days"][-1] == D1.replace(day=9).isoformat()
        )

    def test_scheduler_keeps_running_after_the_event_end(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        self.enable(client)
        day = date(2026, 10, 25)
        clock.set(day, time(18, 5))
        out = client.post("/api/admin/batch/run-due", headers=admin).json()
        assert [(r["action"], r["day"]) for r in out] == [
            ("open", day.isoformat()),
            ("settle", day.isoformat()),
        ]
        assert out[1]["detail"]["round"] == 20

    def test_registration_stays_open(self, client: TestClient, clock: Clock) -> None:
        self.enable(client)
        clock.set(date(2027, 1, 1))
        register(client)


class TestCertification:
    def upload(self, client: TestClient, h: dict[str, str], data: bytes = PNG) -> dict[str, Any]:
        r = client.post(
            "/api/me/certifications", headers=h, files={"file": ("study.png", data, "image/png")}
        )
        body: dict[str, Any] = r.json()
        body["_status"] = r.status_code
        return body

    def test_submit_review_reward_flow(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        h = register(client)
        open_day(client, clock, D1)
        clock.set(D1, time(21, 0))
        cert = self.upload(client, h)
        assert cert["_status"] == 201 and cert["target_date"] == D1.isoformat()
        assert client.get(str(cert["image_url"]), headers=h).content == PNG
        again = self.upload(client, h)
        assert again["detail"]["code"] == "ALREADY_CERTIFIED"

        pending = client.get("/api/admin/certifications?status=pending", headers=admin).json()
        assert [c["nickname"] for c in pending] == ["alice"]
        r = client.post(
            f"/api/admin/certifications/{cert['id']}/review", json={"approve": True}, headers=admin
        )
        assert r.json()["status"] == "approved"

        settle_day(client, clock, D1)
        result = open_day(client, clock, D2)
        assert result["detail"]["rewards_paid"][0]["amount"] == 250_000
        # 현금 25만원(시드의 1/4). 코인은 주지 않는다.
        pf = client.get("/api/me/portfolio", headers=h).json()
        assert (pf["cash"], pf["holdings"], pf["total_assets"]) == (1_250_000, [], 1_250_000)
        # 보상은 손익이 아니라 원금: 수익률 0%
        assert (pf["rewards_received"], pf["principal"], pf["profit"]) == (250_000, 1_250_000, 0)
        assert pf["return_rate"] == 0 and pf["buy_limit"]["limit_amount"] == 500_000
        mine = client.get("/api/me/certifications", headers=h).json()
        assert mine[0]["reward_cash"] == 250_000 and mine[0]["rewarded_at"]
        ranking = client.get("/api/ranking", headers=h).json()["entries"]
        assert ranking[0]["certified_days"] == 1 and ranking[0]["is_me"] is True
        assert (ranking[0]["principal"], ranking[0]["return_rate"]) == (1_250_000, 0)
        (person,) = client.get("/api/admin/participants", headers=admin).json()
        assert (person["principal"], person["return_rate"]) == (1_250_000, 0)
        # 받은 보상은 그날 바로 주문에 쓸 수 있다
        assert order(client, h, "SAMSU", "buy", 6)["status"] == "filled"  # 450,000원
        # 두 번째 공시에서 중복 지급하지 않는다
        settle_day(client, clock, D2)
        assert open_day(client, clock, D3)["detail"]["rewards_paid"] == []
        audit = client.get("/api/admin/audit", headers=admin).json()
        (paid,) = [a for a in audit if a["action"] == "reward.pay"]
        assert paid["detail"]["amount"] == 250_000

    def test_reward_follows_params_and_skips_disqualified(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        a, b = register(client, "alice"), register(client, "bob")
        clock.set(D1, time(12, 0))
        for h, data in ((a, PNG), (b, PNG + b"x")):
            cert = self.upload(client, h, data)
            client.post(
                f"/api/admin/certifications/{cert['id']}/review",
                json={"approve": True},
                headers=admin,
            )
        params = client.get("/api/admin/params", headers=admin).json()
        client.put("/api/admin/params", json=dict(params, reward_cash=100_000), headers=admin)
        bob = client.get("/api/me", headers=b).json()["id"]
        client.patch(
            f"/api/admin/participants/{bob}", json={"status": "disqualified"}, headers=admin
        )
        open_day(client, clock, D1)
        settle_day(client, clock, D1)
        paid = open_day(client, clock, D2)["detail"]["rewards_paid"]
        assert [p["amount"] for p in paid] == [100_000]  # 지급 시점 파라미터, 실격자 제외
        assert client.get("/api/me/portfolio", headers=a).json()["cash"] == 1_100_000
        assert client.get("/api/me/portfolio", headers=b).json()["cash"] == 1_000_000

    def test_cutoff_moves_to_next_day(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        h = register(client)
        params = client.get("/api/admin/params", headers=admin).json()
        params["certification_cutoff"] = "22:00"
        assert client.put("/api/admin/params", json=params, headers=admin).status_code == 200
        clock.set(D1, time(22, 30))
        assert self.upload(client, h)["target_date"] == D2.isoformat()
        assert client.get("/api/event").json()["certification"]["cutoff"] == "22:00"

    def test_outside_event_and_bad_image(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        clock.set(date(2026, 10, 5), time(12, 0))
        assert self.upload(client, h)["detail"]["code"] == "OUTSIDE_EVENT"
        clock.set(D1, time(12, 0))
        bad = self.upload(client, h, b"not an image")
        assert bad["_status"] == 422 and bad["detail"]["code"] == "INVALID_IMAGE"

    def test_duplicate_hash_flagged_and_reject_needs_reason(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        a, b = register(client, "alice"), register(client, "bob")
        clock.set(D1, time(12, 0))
        first = self.upload(client, a)
        second = self.upload(client, b)
        queue = client.get("/api/admin/certifications", headers=admin).json()
        dup = next(c for c in queue if c["id"] == second["id"])
        assert dup["duplicate_of"] == first["id"]
        r = client.post(
            f"/api/admin/certifications/{second['id']}/review",
            json={"approve": False, "reason": " "},
            headers=admin,
        )
        assert r.json()["detail"]["code"] == "REASON_REQUIRED"
        r = client.post(
            f"/api/admin/certifications/{second['id']}/review",
            json={"approve": False, "reason": "사진 재사용"},
            headers=admin,
        )
        assert r.json()["reject_reason"] == "사진 재사용"
        r = client.post(
            f"/api/admin/certifications/{second['id']}/review",
            json={"approve": True},
            headers=admin,
        )
        assert r.json()["detail"]["code"] == "ALREADY_REVIEWED"
        people = client.get("/api/admin/participants", headers=admin).json()
        assert next(p for p in people if p["nickname"] == "bob")["rejected_certifications"] == 1

    def test_other_users_image_is_hidden(self, client: TestClient, clock: Clock) -> None:
        a, b = register(client, "alice"), register(client, "bob")
        clock.set(D1, time(12, 0))
        cert = self.upload(client, a)
        assert client.get(str(cert["image_url"]), headers=b).status_code == 404


class TestRankingAndAdmin:
    def test_ranking_by_total_assets(
        self, client: TestClient, clock: Clock, rng: StubRandom
    ) -> None:
        a, b = register(client, "alice"), register(client, "bob")
        register(client, "carol")
        open_day(client, clock, D1)
        order(client, a, "SKLOW", "buy", 2)
        order(client, b, "SAMSU", "buy", 1)
        # 코인 0%, SAMSU 상승·SKLOW 하락(최대 폭)
        rng.queue = [0.9, 0.0, *stock_draws(SAMSU=(0.0, 1.0), SKLOW=(0.99, 1.0))]
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        entries = client.get("/api/ranking").json()["entries"]
        assert [e["nickname"] for e in entries] == ["bob", "carol", "alice"]
        assert entries[0]["total_assets"] > 1_000_000 > entries[2]["total_assets"]
        assert [e["rank"] for e in entries] == [1, 2, 3]
        # 보상이 없으면 수익률 순서도 총자산 순서와 같다
        assert [e["return_rank"] for e in entries] == [1, 2, 3]

    def test_return_rate_is_on_own_principal(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        """수익률 = (총자산 − 시드 − 받은 보상) / (시드 + 받은 보상). 보상은 손익이 아니다."""
        a, b = register(client, "alice"), register(client, "bob")
        register(client, "carol")  # 거래 없음: 수익률 0%
        clock.set(D1, time(8, 0))
        cert = TestCertification().upload(client, a)
        client.post(
            f"/api/admin/certifications/{cert['id']}/review", json={"approve": True}, headers=admin
        )
        open_day(client, clock, D1)
        order(client, a, "SKLOW", "buy", 2)  # 둘 다 340,000원어치 같은 종목 → 같은 손실
        order(client, b, "SKLOW", "buy", 2)
        rng.queue = [0.9, 0.0, *stock_draws(SKLOW=(0.99, 1.0))]  # 코인 0%, SKLOW 하락
        settle_day(client, clock, D1)
        open_day(client, clock, D2)  # alice는 보상 250,000원을 받는다
        sklow = prices(client)["SKLOW"]
        loss = 2 * (170_000 - sklow)
        assert loss > 0
        entries = {e["nickname"]: e for e in client.get("/api/ranking").json()["entries"]}
        alice, bob, carol = entries["alice"], entries["bob"], entries["carol"]
        assert (alice["principal"], alice["profit"]) == (1_250_000, -loss)
        assert (bob["principal"], bob["profit"]) == (1_000_000, -loss)
        assert alice["return_rate"] == pytest.approx(-loss / 1_250_000)
        assert bob["return_rate"] == pytest.approx(-loss / 1_000_000)
        # 총자산은 보상을 받은 alice가 1위, 수익률은 같은 손실을 더 작은 원금으로 낸 bob이 가장 낮다
        assert (alice["rank"], bob["rank"], carol["rank"]) == (1, 3, 2)
        assert (carol["return_rank"], alice["return_rank"], bob["return_rank"]) == (1, 2, 3)
        # 공개 랭킹은 닉네임과 아래 값만 보여 준다(05 §4, 닉네임만 공개)
        assert set(alice) == {
            "rank",
            "nickname",
            "total_assets",
            "principal",
            "profit",
            "return_rate",
            "return_rank",
            "certified_days",
            "streak",
            "is_me",
        }
        # 내 자산 화면도 같은 수익률
        assert client.get("/api/me/portfolio", headers=a).json()["return_rate"] == pytest.approx(
            alice["return_rate"]
        )

    def test_return_rank_ties_are_shared(
        self, client: TestClient, clock: Clock, rng: StubRandom
    ) -> None:
        a, b = register(client, "alice"), register(client, "bob")
        register(client, "carol")
        open_day(client, clock, D1)
        order(client, a, "SKLOW", "buy", 2)
        order(client, b, "SKLOW", "buy", 2)
        rng.queue = [0.9, 0.0, *stock_draws(SKLOW=(0.99, 1.0))]
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        entries = {e["nickname"]: e for e in client.get("/api/ranking").json()["entries"]}
        # 같은 원금으로 같은 손실을 낸 alice·bob은 수익률 공동 2위
        assert {n: e["return_rank"] for n, e in entries.items()} == {
            "carol": 1,
            "alice": 2,
            "bob": 2,
        }

    def test_tied_rank(self, client: TestClient) -> None:
        register(client, "alice"), register(client, "bob")
        entries = client.get("/api/ranking").json()["entries"]
        assert [e["rank"] for e in entries] == [1, 1]
        assert [e["return_rank"] for e in entries] == [1, 1]

    def test_admin_requires_key(self, client: TestClient) -> None:
        assert client.get("/api/admin/params").status_code == 401
        assert client.get("/api/admin/params", headers={"X-Admin-Key": "wrong"}).status_code == 401

    def test_params_validation_and_audit(self, client: TestClient, admin: dict[str, str]) -> None:
        params = client.get("/api/admin/params", headers=admin).json()
        assert params["reward_cash"] == 250_000
        assert (params["coin_calm_rounds"], params["coin_calm_cap"], params["coin_calm_floor"]) == (
            3,
            0.3,
            -0.1,
        )
        bad = dict(params, coin_p_up=1.5)
        assert client.put("/api/admin/params", json=bad, headers=admin).status_code == 422
        bad = dict(params, coin_calm_floor=0.1)
        assert client.put("/api/admin/params", json=bad, headers=admin).status_code == 422
        ok = dict(params, reward_cash=300_000, coin_calm_rounds=4)
        saved = client.put("/api/admin/params", json=ok, headers=admin).json()
        assert (saved["reward_cash"], saved["coin_calm_rounds"]) == (300_000, 4)
        audit = client.get("/api/admin/audit", headers=admin).json()
        assert audit[0]["action"] == "params.update"
        assert audit[0]["detail"]["changed"] == {
            "coin_calm_rounds": [3, 4],
            "reward_cash": [250_000, 300_000],
        }

    def test_simulate_endpoint(self, client: TestClient, admin: dict[str, str]) -> None:
        r = client.post("/api/admin/simulate", json={"paths": 500, "seed": 3}, headers=admin)
        body = r.json()
        assert body["paths"] == 500 and body["price_cap"] is None
        assert 0.2 < body["daily"]["up_ratio"] < 0.4

    def test_event_info(self, client: TestClient, clock: Clock) -> None:
        clock.set(D1, time(12, 0))
        info = client.get("/api/event").json()
        assert info["total_rounds"] == 10 and len(info["operating_days"]) == 11
        assert info["now"].endswith("+09:00")
        assert info["market"]["round"] == 1 and info["market"]["day_opened"] is False
        assert info["certification"]["reward_cash"] == 250_000
        assert info["coin"] == {
            "cap": 0.8,
            "floor": -0.4,
            "calm_rounds": 3,
            "calm_until": "2026-10-09",  # 3회차(10/8 정산)가 반영되는 날
            "calm_cap": 0.3,
            "calm_floor": -0.1,
        }

    @pytest.mark.parametrize(
        ("calm_rounds", "shown", "until"), [(0, 0, None), (1, 1, "2026-10-07"), (50, 10, LAST)]
    )
    def test_event_coin_calm_info(
        self,
        client: TestClient,
        admin: dict[str, str],
        calm_rounds: int,
        shown: int,
        until: date | str | None,
    ) -> None:
        params = dict(client.get("/api/admin/params", headers=admin).json())
        params["coin_calm_rounds"] = calm_rounds
        assert client.put("/api/admin/params", json=params, headers=admin).status_code == 200
        coin = client.get("/api/event").json()["coin"]
        expected = until.isoformat() if isinstance(until, date) else until
        assert (coin["calm_rounds"], coin["calm_until"]) == (shown, expected)


class TestQaNextStep:
    URL = "/api/admin/qa/next-step"

    def test_steps_through_open_close_next_day(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        assert client.post(self.URL, headers=admin).status_code == 403
        state.settings = dataclasses.replace(state.settings, qa_tools=True)
        clock.set(date(2026, 10, 1))
        rng.queue = [0.5, 1.0]
        steps = []
        for _ in range(4):
            r = client.post(self.URL, headers=admin)
            assert r.status_code == 200, r.text
            event = client.get("/api/event").json()
            steps.append((r.json()["action"], r.json()["day"], event["market"]["is_open"]))
        assert steps == [
            ("open", D1.isoformat(), True),
            ("settle", D1.isoformat(), False),
            ("open", D2.isoformat(), True),
            ("settle", D2.isoformat(), False),
        ]
