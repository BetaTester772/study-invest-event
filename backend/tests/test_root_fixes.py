"""리뷰 지적 사항의 근본 수정 회귀 테스트."""

from __future__ import annotations

import unicodedata
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
from conftest import PNG, Clock, StubRandom, open_day, order, register, settle_day
from fastapi.testclient import TestClient
from sqlalchemy import select

from study_invest.config import Settings
from study_invest.event_calendar import EventCalendar
from study_invest.models import Participant
from study_invest.params import EventParams
from study_invest.services import certification

D1, D2, D3 = date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)


def reg(client: TestClient, identity: str, nickname: str) -> Any:
    return client.post(
        "/api/auth/register",
        json={"identity": identity, "nickname": nickname, "password": "password123"},
    )


class TestOrderQuantityBounds:
    """저장할 수 없는 값은 422, 저장 가능한 잘못된 값은 거부 주문으로 기록."""

    def test_out_of_storage_range_is_422(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        open_day(client, clock, D1)
        for qty in (2**63, 10**30, -(2**63) - 1):
            r = client.post(
                "/api/me/orders", json={"code": "LB", "side": "buy", "quantity": qty}, headers=h
            )
            assert r.status_code == 422, qty
        r = client.post(
            "/api/me/orders", json={"code": "X" * 17, "side": "buy", "quantity": 1}, headers=h
        )
        assert r.status_code == 422

    def test_storable_invalid_quantity_is_recorded(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        open_day(client, clock, D1)
        for qty in (2**62, 0, -5):
            o = order(client, h, "LB", "buy", qty)
            assert (o["status"], o["reject_reason"]) == ("rejected", "INVALID_QUANTITY")
        assert len(client.get("/api/me/orders", headers=h).json()) == 3


class TestManualPricePreviousPrice:
    def test_change_rate_uses_price_published_just_before(
        self, client: TestClient, clock: Clock, rng: StubRandom, admin: dict[str, str]
    ) -> None:
        h = register(client)
        open_day(client, clock, D1)
        # D1에 이틀 뒤(D3) LB 가격을 미리 지정
        r = client.put(
            f"/api/admin/prices/{D3}/LB",
            json={"price": 20_000, "reason": "사전 지정"},
            headers=admin,
        )
        assert r.json()["change_rate"] == pytest.approx(20_000 / 14_000 - 1)  # 잠정
        order(client, h, "SAMSU", "buy", 5)  # D1 쏠림 → D2에서 LB 상승
        settle_day(client, clock, D1)
        open_day(client, clock, D2)
        lb_d2 = next(i["price"] for i in client.get("/api/instruments").json() if i["code"] == "LB")
        assert lb_d2 != 14_000
        settle_day(client, clock, D2)
        open_day(client, clock, D3)
        lb = next(i for i in client.get("/api/instruments").json() if i["code"] == "LB")
        assert (lb["price"], lb["previous_price"]) == (20_000, lb_d2)
        assert lb["change_rate"] == pytest.approx(20_000 / lb_d2 - 1)


class TestInputNormalization:
    def test_nickname_is_stripped_before_length_check(self, client: TestClient) -> None:
        assert reg(client, "a@corp", " a ").status_code == 422
        r = reg(client, "b@corp", "  ab  ")
        assert r.status_code == 201 and r.json()["participant"]["nickname"] == "ab"

    def test_decomposed_hangul_nickname_is_same_nickname(self, client: TestClient) -> None:
        assert reg(client, "a@corp", "공부왕").status_code == 201
        nfd = unicodedata.normalize("NFD", "공부왕")
        assert nfd != "공부왕"
        r = reg(client, "b@corp", nfd)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "NICKNAME_TAKEN"

    def test_identity_normalized_before_length_check(self, client: TestClient) -> None:
        # "ß" 100자는 casefold 후 200자 → 컬럼(128) 초과. 500이 아니라 422.
        assert reg(client, "ß" * 100, "long").status_code == 422
        assert reg(client, "ß" * 64, "okay").status_code == 201  # 128자

    def test_fullwidth_identity_is_same_identity(self, client: TestClient) -> None:
        assert reg(client, "alice@corp", "alice").status_code == 201
        r = reg(client, "ＡＬＩＣＥ＠ｃｏｒｐ", "alice2")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "IDENTITY_TAKEN"
        login = client.post(
            "/api/auth/login",
            json={"identity": " ＡＬＩＣＥ＠ｃｏｒｐ ", "password": "password123"},
        )
        assert login.status_code == 200


class TestAdminKeyHeader:
    def test_non_ascii_key_is_401_not_500(self, client: TestClient) -> None:
        r = client.get("/api/admin/params", headers=[(b"x-admin-key", b"caf\xe9")])
        assert r.status_code == 401


class TestUploadFilesFollowTransaction:
    def _submit(self, client: TestClient, tmp_path: Path) -> tuple[Any, Participant, Path]:
        register(client)
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        s = state.session_factory()
        me = s.scalars(select(Participant)).one()
        from conftest import kst

        cert = certification.submit(
            s, me, PNG, kst(D1, time(12)), EventCalendar(), EventParams(), tmp_path, 10_000_000
        )
        assert cert.image_path is not None
        return s, me, tmp_path / cert.image_path

    def test_rollback_removes_file(self, client: TestClient, tmp_path: Path) -> None:
        s, _, path = self._submit(client, tmp_path)
        assert path.exists()
        s.rollback()
        s.close()
        assert not path.exists()

    def test_close_without_commit_removes_file(self, client: TestClient, tmp_path: Path) -> None:
        s, _, path = self._submit(client, tmp_path)
        s.close()
        assert not path.exists()

    def test_commit_keeps_file(self, client: TestClient, tmp_path: Path) -> None:
        s, _, path = self._submit(client, tmp_path)
        s.commit()
        s.close()
        assert path.exists()

    def test_purge_removes_all_stored_images_but_nothing_else(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        s, _, path = self._submit(client, tmp_path)
        s.commit()
        stray = tmp_path / ("a" * 32 + ".jpg")  # DB에 없는 사진(커밋 전 프로세스 종료 등)
        stray.write_bytes(b"x")
        other = tmp_path / "README.txt"
        other.write_text("keep")
        from conftest import kst

        removed = certification.purge_images(s, tmp_path, kst(date(2026, 10, 20)), EventCalendar())
        s.commit()
        assert removed == 2 and not path.exists() and not stray.exists() and other.exists()


class TestPriceParamsOnTenWonGrid:
    @pytest.mark.parametrize(
        "field_value", [("stock_min_price", 1005), ("coin_price_cap", 5_000_005)]
    )
    def test_rejected(
        self, client: TestClient, admin: dict[str, str], field_value: tuple[str, int]
    ) -> None:
        params = client.get("/api/admin/params", headers=admin).json()
        field, value = field_value
        r = client.put("/api/admin/params", json=dict(params, **{field: value}), headers=admin)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_PARAMS"


class TestCertificationStatus:
    def status(self, client: TestClient, h: dict[str, str]) -> Any:
        r = client.get("/api/me/certification-status", headers=h)
        assert r.status_code == 200
        return r.json()

    def test_status_matches_submit_rules(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        h = register(client)
        clock.set(date(2026, 10, 5), time(12))
        st = self.status(client, h)
        assert (st["can_submit"], st["reason"]) == (False, "OUTSIDE_EVENT")

        clock.set(D1, time(12))
        st = self.status(client, h)
        assert (st["can_submit"], st["target_date"], st["existing"]) == (True, D1.isoformat(), None)

        cert = client.post(
            "/api/me/certifications", headers=h, files={"file": ("a.png", PNG, "image/png")}
        ).json()
        client.post(
            f"/api/admin/certifications/{cert['id']}/review",
            json={"approve": False, "reason": "흐림"},
            headers=admin,
        )
        st = self.status(client, h)
        assert (st["can_submit"], st["reason"]) == (False, "ALREADY_CERTIFIED")
        assert st["existing"]["status"] == "rejected"  # 반려돼도 같은 날은 다시 못 낸다
        again = client.post(
            "/api/me/certifications", headers=h, files={"file": ("b.png", PNG, "image/png")}
        )
        assert again.json()["detail"]["code"] == st["reason"]  # 화면과 제출이 같은 판단

        clock.set(D1, time(23, 59, 59))
        assert self.status(client, h)["can_submit"] is False
        clock.set(D2, time(0, 0))  # 다음 날짜
        assert self.status(client, h)["can_submit"] is True

    def test_disqualified(self, client: TestClient, admin: dict[str, str], clock: Clock) -> None:
        h = register(client)
        pid = client.get("/api/me", headers=h).json()["id"]
        client.patch(
            f"/api/admin/participants/{pid}", json={"status": "disqualified"}, headers=admin
        )
        clock.set(D1, time(12))
        st = self.status(client, h)
        assert (st["can_submit"], st["reason"]) == (False, "DISQUALIFIED")


def test_settings_default_pool_design() -> None:
    s = Settings()
    assert (s.api_pool.size, s.api_pool.max_overflow, s.batch_pool.size) == (20, 0, 2)
    assert s.batch_pool.url == s.database_url and s.migration_url == s.database_url
