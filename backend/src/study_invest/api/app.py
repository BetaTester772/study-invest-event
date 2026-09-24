"""FastAPI 앱 팩토리."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import multiprocessing
import random
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import anyio.to_thread
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import Settings
from ..db import create_schema, install_event_loop_guard, make_engine, make_session_factory
from ..event_calendar import EventCalendar
from ..params import KST
from ..services.common import DomainError
from ..services.market import run_due
from . import routes_admin, routes_me, routes_public
from .deps import AppState

log = logging.getLogger("study_invest")


def _now() -> datetime:
    return datetime.now(KST)


async def _scheduler(state: AppState) -> None:
    """09:00 공시·18:00 정산을 주기적으로 확인해 실행한다(여러 번 실행해도 안전).

    배치는 동기 DB 작업이므로 asyncio.to_thread로 넘기고, 이벤트 루프는 대기만 한다.
    """
    while True:
        try:
            results = await asyncio.to_thread(
                run_due, state.session_factory, state.clock(), state.calendar, state.rng
            )
            for r in results:
                log.info("batch: %s", r)
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(state.settings.scheduler_interval_seconds)


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    rng: random.Random | None = None,
    calendar: EventCalendar | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url, settings.db_pool_size, settings.db_max_overflow)
    install_event_loop_guard(engine, settings.loop_guard)
    if settings.auto_create_schema:
        create_schema(engine)
    state = AppState(
        settings=settings,
        session_factory=make_session_factory(engine),
        calendar=calendar or EventCalendar(),
        clock=clock or _now,
        rng=rng or random.SystemRandom(),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # 동기 라우트·의존성이 쓰는 스레드풀 크기(DB 풀 크기와 맞춘다).
        anyio.to_thread.current_default_thread_limiter().total_tokens = settings.threadpool_size
        if settings.cpu_workers > 0:
            # fork는 스레드가 있는 프로세스에서 교착 위험이 있어 spawn을 쓴다.
            state.cpu_executor = ProcessPoolExecutor(
                max_workers=settings.cpu_workers, mp_context=multiprocessing.get_context("spawn")
            )
        task = asyncio.create_task(_scheduler(state)) if settings.scheduler_enabled else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if state.cpu_executor is not None:
                state.cpu_executor.shutdown(wait=False, cancel_futures=True)
                state.cpu_executor = None
            engine.dispose()

    app = FastAPI(title="공부장려 모의투자 이벤트", version="0.1.0", lifespan=lifespan)
    app.state.study_invest = state

    @app.exception_handler(DomainError)  # I/O 없음 → async
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"detail": {"code": exc.code, "message": exc.message}}
        )

    app.include_router(routes_public.router)
    app.include_router(routes_me.router)
    app.include_router(routes_admin.router)

    if settings.frontend_dist is not None:
        _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """빌드된 SPA 제공. /api 외 경로는 파일이 없으면 index.html로 돌려준다."""
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:  # 파일 존재 확인(디스크 I/O) → 동기 def
        if path.startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        if not index.is_file():
            raise StarletteHTTPException(status_code=404)
        return FileResponse(index)
