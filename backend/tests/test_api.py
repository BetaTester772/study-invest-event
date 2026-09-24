"""API 통합 흐름: 등록 → 공시 → 주문 → 정산 → 인증·보상 → 랭킹."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from conftest import PNG, Clock, StubRandom, open_day, order, register, settle_day
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

    def test_one_account_per_identity(self, client: TestClient) -> None:
        register(client)
        r = client.post(
            "/api/auth/register",
            json={"identity": "  ALICE@corp ", "nickname": "other", "password": "password123"},
        )
        assert r.status_code == 409 and r.json()["detail"]["code"] == "IDENTITY_TAKEN"
        r = client.post(
            "/api/auth/register",
            json={"identity": "bob@corp", "nickname": "alice", "password": "password123"},
        )
        assert r.json()["detail"]["code"] == "NICKNAME_TAKEN"

    def test_login_logout(self, client: TestClient) -> None:
        register(client)
        bad = client.post("/api/auth/login", json={"identity": "alice@corp", "password": "nope"})
        assert bad.status_code == 401
        r = client.post(
            "/api/auth/login", json={"identity": "Alice@corp", "password": "password123"}
        )
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        assert client.get("/api/me", headers=h).status_code == 200
        assert client.post("/api/auth/logout", headers=h).status_code == 204
        assert client.get("/api/me", headers=h).status_code == 401

    def test_mid_event_join_same_seed(self, client: TestClient, clock: Clock) -> None:
        clock.set(date(2026, 10, 12))
        h = register(client, "late")
        assert client.get("/api/me/portfolio", headers=h).json()["cash"] == 1_000_000

    def test_closed_after_event(self, client: TestClient, clock: Clock) -> None:
        clock.set(date(2026, 10, 17))
        r = client.post(
            "/api/auth/register",
            json={"identity": "x", "nickname": "xx", "password": "password123"},
        )
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


class TestSettlement:
    def test_prices_move_inverse_to_crowding(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        h = register(client)
        open_day(client, clock, D1)
        assert client.get("/api/instruments").json()[0]["day"] == D1.isoformat()
        order(client, h, "SAMSU", "buy", 5)  # 375,000원
        order(client, h, "SAMSU", "sell", 5)  # 매도는 집계하지 않는다
        rng.queue = [0.1, 0.5]  # 코인 상승일, X=0.5 → +37.5%
        result = settle_day(client, clock, D1)
        # B′ = 5,375,000 / 5,000,000 ×3, 총 20,375,000 → r_SAMSU ≈ 1.055
        assert result["detail"]["round"] == 1
        new = result["detail"]["new_prices"]
        assert new["SAMSU"] == 73_760  # 75,000 × (1 − 0.3·0.0552) → 73,760
        assert new["LB"] > 14_000 and new["BYUNG"] == 343_750
        # 공시 전에는 D1 가격이 보인다
        assert prices(client)["SAMSU"] == 75_000
        open_day(client, clock, D2)
        p = client.get("/api/instruments").json()
        samsu = next(i for i in p if i["code"] == "SAMSU")
        assert samsu["price"] == 73_760 and samsu["previous_price"] == 75_000
        assert samsu["change_rate"] < 0
        hist = client.get("/api/instruments/BYUNG/history").json()
        assert [x["price"] for x in hist] == [250_000, 343_750]
        assert hist[1]["source"] == "settlement"
        logs = client.get("/api/admin/settlements", headers=admin).json()
        assert logs[0]["coin"]["p"] == 0.1 and logs[0]["coin"]["direction"] == "up"
        assert logs[0]["stocks"][0]["buy_amount"] == 375_000

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
        assert result["detail"]["rewards_paid"][0]["quantity"] == 1
        pf = client.get("/api/me/portfolio", headers=h).json()
        (coin,) = pf["holdings"]
        assert (coin["code"], coin["quantity"], coin["cost"]) == ("BYUNG", 1, 0)
        assert coin["profit_rate"] is None
        mine = client.get("/api/me/certifications", headers=h).json()
        assert mine[0]["reward_quantity"] == 1 and mine[0]["rewarded_at"]
        ranking = client.get("/api/ranking", headers=h).json()["entries"]
        assert ranking[0]["certified_days"] == 1 and ranking[0]["is_me"] is True
        # 두 번째 공시에서 중복 지급하지 않는다
        settle_day(client, clock, D2)
        assert open_day(client, clock, D3)["detail"]["rewards_paid"] == []

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
        order(client, a, "SKLOW", "buy", 2)  # 크게 몰림 → 하락
        order(client, b, "SAMSU", "buy", 1)  # 기준선 아래 → 상승
        rng.queue = [0.9, 0.0]  # 코인 0%
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        entries = client.get("/api/ranking").json()["entries"]
        assert [e["nickname"] for e in entries] == ["bob", "carol", "alice"]
        assert entries[0]["total_assets"] > 1_000_000 > entries[2]["total_assets"]
        assert [e["rank"] for e in entries] == [1, 2, 3]

    def test_tied_rank(self, client: TestClient) -> None:
        register(client, "alice"), register(client, "bob")
        assert [e["rank"] for e in client.get("/api/ranking").json()["entries"]] == [1, 1]

    def test_admin_requires_key(self, client: TestClient) -> None:
        assert client.get("/api/admin/params").status_code == 401
        assert client.get("/api/admin/params", headers={"X-Admin-Key": "wrong"}).status_code == 401

    def test_params_validation_and_audit(self, client: TestClient, admin: dict[str, str]) -> None:
        params = client.get("/api/admin/params", headers=admin).json()
        assert params["reward_coin_quantity"] == 1
        bad = dict(params, coin_p_up=1.5)
        assert client.put("/api/admin/params", json=bad, headers=admin).status_code == 422
        ok = dict(params, reward_coin_quantity=2)
        assert (
            client.put("/api/admin/params", json=ok, headers=admin).json()["reward_coin_quantity"]
            == 2
        )
        audit = client.get("/api/admin/audit", headers=admin).json()
        assert audit[0]["action"] == "params.update"
        assert audit[0]["detail"]["changed"] == {"reward_coin_quantity": [1, 2]}

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
        assert info["certification"]["reward_coin_quantity"] == 1
