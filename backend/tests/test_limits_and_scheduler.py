"""요청 본문 크기 제한, 스케줄러 기상 시각, 정산 실패 시 이월."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time

import pytest
from conftest import PNG, Clock, open_day, register
from fastapi.testclient import TestClient

from study_invest.event_calendar import seconds_until_next_batch
from study_invest.params import KST
from study_invest.services import market

D1, D2 = date(2026, 10, 6), date(2026, 10, 7)


class TestBodyLimit:
    def test_declared_oversize_upload_rejected_before_reading(self, client: TestClient) -> None:
        # 로그인 전 요청도 본문을 받기 전에 거부(이전: 50MB를 다 받은 뒤 401)
        big = b"\xff\xd8\xff" + b"0" * (11 * 1024 * 1024)
        r = client.post("/api/me/certifications", files={"file": ("a.jpg", big, "image/jpeg")})
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"

    def test_streamed_oversize_body_rejected(self, client: TestClient) -> None:
        h = register(client)

        def chunks() -> Iterator[bytes]:  # Content-Length 없음(chunked)
            for _ in range(3):
                yield b"x" * (512 * 1024)

        r = client.post(
            "/api/me/orders",
            content=chunks(),
            headers={**h, "content-type": "application/json"},
        )
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"

    def test_json_limit_and_normal_upload_ok(self, client: TestClient, clock: Clock) -> None:
        h = register(client)
        r = client.post(
            "/api/auth/login",
            content=b"{" + b" " * (1024 * 1024 + 1) + b"}",
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 413
        clock.set(D1, time(12, 0))
        r = client.post(
            "/api/me/certifications", headers=h, files={"file": ("a.png", PNG, "image/png")}
        )
        assert r.status_code == 201


class TestSchedulerWakeup:
    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (time(8, 59, 30), 30),
            (time(9, 0), 9 * 3600),  # 정각이면 다음(18:00)까지
            (time(17, 0), 3600),
            (time(23, 0), 10 * 3600),  # 다음 날 09:00
        ],
    )
    def test_seconds_until_next_batch(self, now: time, expected: float) -> None:
        assert seconds_until_next_batch(datetime.combine(D1, now, KST)) == expected

    def test_accepts_other_timezones(self) -> None:
        utc = datetime.combine(D1, time(23, 59, 50), KST).astimezone(UTC)
        assert seconds_until_next_batch(utc) == pytest.approx(9 * 3600 + 10)


class TestSettlementFailureCarryOver:
    def test_open_carries_over_when_prev_settlement_keeps_failing(
        self,
        client: TestClient,
        clock: Clock,
        admin: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        open_day(client, clock, D1)

        def broken(*_: object, **__: object) -> None:
            raise RuntimeError("settlement bug")

        monkeypatch.setattr(market, "settle_stocks", broken)
        clock.set(D1, time(18, 1))
        out = client.post("/api/admin/batch/run-due", headers=admin).json()
        assert [(r["action"], r["detail"].get("error")) for r in out] == [
            ("settle", "RuntimeError")
        ]
        clock.set(D2, time(9, 0))
        out = client.post("/api/admin/batch/run-due", headers=admin).json()
        # 전일 정산은 또 실패하지만 오늘은 전일 가격으로 공시된다
        assert [r["action"] for r in out] == ["settle", "open"]
        assert set(out[1]["detail"]["sources"].values()) == {"carry_over"}
        clock.set(D2, time(9, 1))
        assert client.post("/api/admin/batch/run-due", headers=admin).json() == []
        assert client.get("/api/event").json()["market"]["is_open"] is True
