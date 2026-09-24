"""연결 풀 격리 (docs/dev/db-pools.md).

- api 풀이 가득 차면 요청은 오래 기다리지 않고 503, 배치 풀은 영향을 받지 않는다.
- (PgBouncer 경유 시) pgAdmin 풀은 서버 연결 5개로 제한되고, 가득 차도 앱 풀은 영향이 없다.

PostgreSQL 전용. pgAdmin 풀 테스트는 PgBouncer 주소가 있을 때만 돈다:
    STUDY_INVEST_TEST_PGADMIN_URL=postgresql://pgadmin:pgadmin@127.0.0.1:6432/postgres
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import psycopg
import pytest
from conftest import ADMIN_KEY, TEST_DB_URL, Clock
from fastapi.testclient import TestClient

from study_invest.api.app import create_app
from study_invest.config import Settings
from study_invest.db import Base
from study_invest.params import KST

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL.startswith("postgresql"), reason="PostgreSQL 전용(풀 크기가 의미 있음)"
)
PGADMIN_URL = os.environ.get("STUDY_INVEST_TEST_PGADMIN_URL")
ADMIN = {"X-Admin-Key": ADMIN_KEY}


@pytest.fixture
def tiny_pool_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=TEST_DB_URL,
        admin_key=ADMIN_KEY,
        upload_dir=tmp_path,
        auto_create_schema=True,
        loop_guard="raise",
        api_pool_size=1,
        api_pool_timeout=0.5,
        batch_pool_size=1,
    )
    clock = Clock(datetime(2026, 10, 6, 9, 30, tzinfo=KST))
    app = create_app(settings, clock=clock)
    pools = app.state.study_invest.pools
    Base.metadata.drop_all(pools.api)
    Base.metadata.create_all(pools.api)
    with TestClient(app) as client:
        yield client
    Base.metadata.drop_all(pools.api)


def test_api_pool_exhaustion_returns_503_and_batch_still_runs(
    tiny_pool_client: TestClient,
) -> None:
    pools = tiny_pool_client.app.state.study_invest.pools  # type: ignore[attr-defined]
    held = pools.api.connect()  # api 풀의 유일한 연결을 붙잡아 둔다
    try:
        start = time.perf_counter()
        r = tiny_pool_client.get("/api/instruments")
        elapsed = time.perf_counter() - start
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "DB_BUSY"
        assert r.headers["retry-after"] == "2"
        assert elapsed < 3  # pool_timeout(0.5초) 뒤 바로 응답

        # 배치 풀은 별도 → 09:00 공시는 그대로 진행
        r = tiny_pool_client.post(
            "/api/admin/batch/open", json={"day": date(2026, 10, 6).isoformat()}, headers=ADMIN
        )
        assert r.status_code == 200, r.text
        status = tiny_pool_client.get("/api/admin/db-pools", headers=ADMIN)
    finally:
        held.close()
    # 풀 현황 API는 DB를 쓰지 않으므로 api 풀이 가득 차도 응답한다
    assert status.status_code == 200
    assert status.json()["api"]["checked_out"] == 1
    # 연결을 돌려주면 api 풀도 정상
    assert tiny_pool_client.get("/api/instruments").status_code == 200


@pytest.mark.skipif(not PGADMIN_URL, reason="PgBouncer pgAdmin 풀 주소가 필요")
def test_pgadmin_pool_is_capped_and_isolated() -> None:
    assert PGADMIN_URL is not None
    started: list[float] = []
    finished: list[float] = []
    t0 = time.perf_counter()

    def admin_query() -> None:
        with psycopg.connect(PGADMIN_URL) as conn:
            started.append(time.perf_counter() - t0)
            conn.execute("SELECT pg_sleep(1)")
            finished.append(time.perf_counter() - t0)

    threads = [threading.Thread(target=admin_query) for _ in range(6)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    # pgAdmin 풀이 가득 찬 동안에도 앱(api) 풀은 즉시 응답
    app_url = TEST_DB_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(app_url) as conn:
        q0 = time.perf_counter()
        conn.execute("SELECT 1")
        assert time.perf_counter() - q0 < 0.5
    for t in threads:
        t.join(timeout=30)
    finished.sort()
    # 서버 연결 5개 상한 → 6번째 질의는 앞선 질의가 끝난 뒤에야 끝난다(≥ 2초)
    assert len(finished) == 6
    assert finished[4] < 1.9 <= finished[5]
