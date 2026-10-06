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
from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..captcha import CaptchaVerifier, make_captcha
from ..config import Settings
from ..db import DatabasePools, create_schema, make_session_factory
from ..event_calendar import EventCalendar, seconds_until_next_batch
from ..logging_setup import configure_logging
from ..mail import Mailer, make_mailer
from ..services.common import DomainError
from ..services.market import run_due
from . import routes_admin, routes_me, routes_public
from .access_log import REQUEST_ID_SCOPE_KEY, AccessLogMiddleware
from .deps import AppState
from .error_log import db_error_info, origin, request_info
from .limits import BodySizeLimitMiddleware

log = logging.getLogger("study_invest")

BATCH_WAKE_DELAY = 0.05
"""배치 정각 직후 깨어나기 위한 여유(초)."""

MULTIPART_OVERHEAD = 64 * 1024
"""multipart 경계·헤더용 여유(바이트)."""


def _unavailable(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "2"},
        content={"detail": {"code": code, "message": message}},
    )


async def _scheduler(state: AppState) -> None:
    """09:00 공시·18:00 정산을 주기적으로 확인해 실행한다(여러 번 실행해도 안전).

    배치는 동기 DB 작업이므로 asyncio.to_thread로 넘기고, 이벤트 루프는 대기만 한다.
    """
    while True:
        try:
            results = await asyncio.to_thread(
                run_due, state.batch_session_factory, state.clock(), state.calendar, state.rng
            )
            for r in results:
                log.info("batch: %s", r)
        except Exception:
            log.exception("scheduler tick failed")
        # 주기적으로 확인하되, 09:00·18:00 정각에는 바로 깨어나 공시·정산 지연을 없앤다.
        # 남은 시간은 앱 시계 기준이므로 배속으로 나눠 실제 대기 시간으로 바꾼다.
        until_batch = seconds_until_next_batch(state.clock()) / state.time_scale + BATCH_WAKE_DELAY
        await asyncio.sleep(min(state.settings.scheduler_interval_seconds, until_batch))


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    rng: random.Random | None = None,
    calendar: EventCalendar | None = None,
    mailer: Mailer | None = None,
    captcha: CaptchaVerifier | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level, settings.log_format)
    pools = DatabasePools.create(settings)
    if settings.auto_create_schema:
        create_schema(pools.api)
    state = AppState(
        settings=settings,
        pools=pools,
        session_factory=make_session_factory(pools.api),
        batch_session_factory=make_session_factory(pools.batch),
        calendar=calendar or settings.calendar,
        clock=clock or settings.make_clock(),
        rng=rng or random.SystemRandom(),
        mailer=mailer or make_mailer(settings),
        captcha=captcha or make_captcha(settings),
        time_scale=settings.time_scale,
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
            pools.dispose()

    app = FastAPI(title="공부장려 모의투자 이벤트", version="0.1.0", lifespan=lifespan)
    app.state.study_invest = state

    @app.exception_handler(PoolTimeoutError)  # I/O 없음 → async
    async def _pool_exhausted(request: Request, exc: PoolTimeoutError) -> JSONResponse:
        # api 풀이 가득 차 pool_timeout 동안 연결을 못 받음 → 무한 대기 대신 즉시 503.
        log.warning(
            "api pool exhausted: %s",
            exc,
            extra={
                "detail": {
                    **request_info(request),
                    "pools": {n: dict(st) for n, st in state.pools.status().items()},
                    "pool_timeout": state.settings.api_pool_timeout,
                }
            },
        )
        return _unavailable(
            "DB_BUSY", "요청이 많아 잠시 처리할 수 없습니다. 잠시 후 다시 시도하세요."
        )

    @app.exception_handler(OperationalError)  # I/O 없음 → async
    async def _db_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
        # DB·PgBouncer 연결 실패, PgBouncer query_wait_timeout 등.
        log.error(
            "database unavailable: %s",
            exc.orig,
            extra={"detail": {**request_info(request), **db_error_info(exc)}},
        )
        return _unavailable(
            "DB_UNAVAILABLE", "데이터베이스에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
        )

    @app.exception_handler(IntegrityError)  # I/O 없음 → async
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # 동시 요청이 같은 유니크 키를 만들려다 충돌한 경우. 세션은 의존성에서 롤백된다.
        log.info(
            "integrity conflict: %s",
            exc.orig,
            extra={"detail": {**request_info(request), **db_error_info(exc)}},
        )
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "CONFLICT",
                    "message": "같은 요청이 동시에 처리되어 충돌했습니다. 다시 시도하세요.",
                }
            },
        )

    @app.exception_handler(DomainError)  # I/O 없음 → async
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        # 요청 한 줄(access)에는 상태만 남으므로 어떤 규칙에 걸렸는지·왜 걸렸는지를 따로 남긴다.
        log.log(
            logging.ERROR
            if exc.status >= 500
            else logging.WARNING
            if exc.status in (401, 403, 429)
            else logging.INFO,
            "domain error: %s (%d) %s",
            exc.code,
            exc.status,
            exc.message,
            extra={
                "detail": {
                    "code": exc.code,
                    "origin": origin(exc),
                    **request_info(request),
                    **({"context": exc.context} if exc.context else {}),
                }
            },
        )
        return JSONResponse(
            status_code=exc.status, content={"detail": {"code": exc.code, "message": exc.message}}
        )

    @app.exception_handler(RequestValidationError)  # I/O 없음 → async
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 어느 필드가 왜 틀렸는지만 남긴다. 입력값(input)은 비밀번호·학번일 수 있어 뺀다.
        fields = [
            {"loc": ".".join(str(p) for p in e["loc"]), "type": e["type"], "msg": e["msg"]}
            for e in exc.errors()
        ]
        log.info(
            "validation failed: %s",
            ", ".join(f"{f['loc']}({f['type']})" for f in fields),
            extra={"detail": {**request_info(request), "errors": fields}},
        )
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(StarletteHTTPException)  # I/O 없음 → async
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        # 404·405·413 등 프레임워크가 내는 오류. 존재하지 않는 경로 탐색 같은 시도도 남는다.
        log.info(
            "http error: %d %s",
            exc.status_code,
            exc.detail,
            extra={"detail": request_info(request)},
        )
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)  # I/O 없음 → async
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 트레이스백은 AccessLogMiddleware가 이미 남겼다. 응답에는 요청 ID만 실어 문의에 쓰게 한다.
        rid = request.scope.get(REQUEST_ID_SCOPE_KEY)
        log.error(
            "unhandled %s at %s",
            type(exc).__name__,
            origin(exc),
            extra={"detail": request_info(request)},
        )
        # 이 응답은 요청 로그 미들웨어 바깥(ServerErrorMiddleware)에서 만들어져 헤더를 직접 단다.
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": str(rid)} if rid else None,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "message": "서버 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
                    "request_id": rid,
                }
            },
        )

    # 본문 크기 제한: 업로드 경로만 사진 한도 + multipart 여유, 나머지(JSON)는 1MiB.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=settings.max_json_bytes,
        path_limits={"/api/me/certifications": settings.max_upload_bytes + MULTIPART_OVERHEAD},
    )
    # 가장 바깥에 둬서 본문 크기 거절(413) 같은 응답도 요청 로그에 남긴다.
    app.add_middleware(AccessLogMiddleware)
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
