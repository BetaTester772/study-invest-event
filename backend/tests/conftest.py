from __future__ import annotations

import os
import random
from collections.abc import Iterator
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from study_invest.api.app import create_app
from study_invest.config import Settings
from study_invest.db import Base
from study_invest.params import KST

ADMIN_KEY = "test-admin-key"
# 기본은 SQLite 메모리 DB. PostgreSQL로 돌리려면:
#   STUDY_INVEST_TEST_DATABASE_URL=postgresql+psycopg://study:study@localhost/study_invest_test
TEST_DB_URL = os.environ.get("STUDY_INVEST_TEST_DATABASE_URL", "sqlite://")

# 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def kst(d: date, t: time = time(10, 0)) -> datetime:
    return datetime.combine(d, t, tzinfo=KST)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def set(self, d: date, t: time = time(10, 0)) -> None:
        self.now = kst(d, t)


class StubRandom(random.Random):
    """정산 코인 추출용 난수를 순서대로 돌려준다. 비면 0.5."""

    def __init__(self) -> None:
        super().__init__(0)
        self.queue: list[float] = []

    def random(self) -> float:
        return self.queue.pop(0) if self.queue else 0.5


@pytest.fixture
def clock() -> Clock:
    return Clock(kst(date(2026, 10, 6), time(8, 0)))


@pytest.fixture
def rng() -> StubRandom:
    return StubRandom()


@pytest.fixture
def client(tmp_path: Path, clock: Clock, rng: StubRandom) -> Iterator[TestClient]:
    settings = Settings(
        database_url=TEST_DB_URL,
        admin_key=ADMIN_KEY,
        upload_dir=tmp_path / "uploads",
        auto_create_schema=True,
        loop_guard="raise",  # 이벤트 루프에서 DB를 부르면 테스트 실패
    )
    app = create_app(settings, clock=clock, rng=rng)
    engine = app.state.study_invest.session_factory.kw["bind"]
    if TEST_DB_URL != "sqlite://":
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
        # 앱 종료(lifespan)가 풀을 닫기 전에 정리한다. 닫힌 뒤에 쓰면 새 연결이 열린 채 남는다.
        if TEST_DB_URL != "sqlite://":
            Base.metadata.drop_all(engine)


@pytest.fixture
def admin() -> dict[str, str]:
    return {"X-Admin-Key": ADMIN_KEY}


def register(client: TestClient, name: str = "alice") -> dict[str, str]:
    r = client.post(
        "/api/auth/register",
        json={"identity": f"{name}@corp", "nickname": name, "password": "password123"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def open_day(client: TestClient, clock: Clock, d: date) -> dict[str, Any]:
    clock.set(d, time(9, 0))
    r = client.post(
        "/api/admin/batch/open", json={"day": d.isoformat()}, headers={"X-Admin-Key": ADMIN_KEY}
    )
    assert r.status_code == 200, r.text
    clock.set(d, time(10, 0))
    body: dict[str, Any] = r.json()
    return body


def settle_day(client: TestClient, clock: Clock, d: date) -> dict[str, Any]:
    clock.set(d, time(18, 0))
    r = client.post(
        "/api/admin/batch/settle", json={"day": d.isoformat()}, headers={"X-Admin-Key": ADMIN_KEY}
    )
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def order(client: TestClient, h: dict[str, str], code: str, side: str, qty: int) -> dict[str, Any]:
    r = client.post("/api/me/orders", json={"code": code, "side": side, "quantity": qty}, headers=h)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body
