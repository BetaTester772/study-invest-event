"""비동기 원칙 회귀 테스트.

- I/O가 없는 함수만 `async def`로 둔다. DB·파일을 쓰는 라우트·의존성은 동기 `def`(스레드풀).
- 이벤트 루프 스레드에서 SQL이 실행되면 conftest의 loop_guard="raise"가
  모든 API 테스트를 실패시킨다.
- 여기서는 async로 선언된 라우트·의존성이 허용 목록 밖으로 늘어나지 않는지 확인한다.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from study_invest.api import routes_admin, routes_me, routes_public
from study_invest.services import certification

ASYNC_ROUTES = {"health", "simulate", "simulate_options"}
"""health·simulate_options: I/O 없음. simulate: CPU 작업을 프로세스 풀에 맡기고 await만 한다."""
ASYNC_DEPENDENCIES = {
    "get_state",
    "get_now",
    "bearer_token",
    "current_participant",
    "require_admin",
}
"""모두 요청 헤더·앱 상태만 읽는다(DB 없음)."""


def _walk(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _walk(dep)


def _routes() -> list[APIRoute]:
    routers = (routes_public.router, routes_me.router, routes_admin.router)
    routes = [r for router in routers for r in router.routes if isinstance(r, APIRoute)]
    assert len(routes) >= 29  # 라우터를 못 찾으면 테스트가 헛돌지 않게
    return routes


def test_only_allowlisted_routes_are_async() -> None:
    async_routes = {
        r.endpoint.__name__ for r in _routes() if inspect.iscoroutinefunction(r.endpoint)
    }
    assert async_routes == ASYNC_ROUTES


def test_only_io_free_dependencies_are_async() -> None:
    async_deps = {
        call.__name__
        for route in _routes()
        for call in _walk(route.dependant)
        if inspect.iscoroutinefunction(call)
    }
    assert async_deps == ASYNC_DEPENDENCIES


def test_upload_runs_off_the_event_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import PNG, register

    seen: list[bool] = []
    original = certification.submit

    def spy(*args: Any, **kwargs: Any) -> Any:
        try:
            asyncio.get_running_loop()
            seen.append(True)
        except RuntimeError:
            seen.append(False)
        return original(*args, **kwargs)

    monkeypatch.setattr(certification, "submit", spy)
    h = register(client)  # clock 픽스처: 2026-10-06 08:00 (당일 인증 가능)
    r = client.post(
        "/api/me/certifications", headers=h, files={"file": ("a.png", PNG, "image/png")}
    )
    assert r.status_code == 201, r.text
    assert seen == [False]  # 스레드풀에서 실행됨(이벤트 루프 아님)


def test_health_stays_responsive_during_simulation(
    client: TestClient, admin: dict[str, str]
) -> None:
    """시뮬레이션(CPU)은 별도 프로세스에서 돌아 이벤트 루프·스레드풀을 막지 않는다."""
    result: dict[str, Any] = {}

    def run() -> None:
        result["sim"] = client.post(
            "/api/admin/simulate", json={"paths": 30_000, "seed": 1}, headers=admin
        )

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.3)
    latencies = []
    while t.is_alive():
        start = time.perf_counter()
        assert client.get("/api/health").status_code == 200
        latencies.append(time.perf_counter() - start)
        time.sleep(0.05)
    t.join()
    assert result["sim"].status_code == 200
    assert latencies, "simulation finished too quickly to measure"
    assert max(latencies) < 0.5
