"""SQLAlchemy 엔진·세션."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from .config import PoolSpec, Settings


class Base(DeclarativeBase):
    pass


log = logging.getLogger("study_invest.db")

LoopGuard = Literal["off", "warn", "raise"]


class BlockingCallInEventLoop(RuntimeError):
    """이벤트 루프 스레드에서 동기 DB 호출이 일어났다(서비스 전체가 멈출 수 있음)."""


def make_engine(pool: PoolSpec) -> Engine:
    """연결 풀 하나 = 엔진 하나. 풀 이름은 application_name으로 남겨 pg_stat_activity·pgAdmin에서
    어느 풀의 연결인지 보이게 한다."""
    kwargs: dict[str, Any] = {}
    if pool.url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if pool.url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(
            pool_size=pool.size,
            max_overflow=pool.max_overflow,
            pool_timeout=pool.timeout,
            pool_recycle=pool.recycle,
            pool_pre_ping=True,
            connect_args={
                "application_name": f"study_invest:{pool.name}",
                # PgBouncer transaction 모드에서는 서버 연결이 트랜잭션마다 바뀌므로 서버측
                # prepared statement를 쓰지 않는다(직접 연결에서도 동작은 같다).
                "prepare_threshold": None,
            },
        )
    engine = create_engine(pool.url, **kwargs)
    if pool.url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def pool_status(engine: Engine) -> dict[str, Any]:
    """풀 사용 현황(관리자 모니터링용)."""
    pool = engine.pool
    if isinstance(pool, QueuePool):
        # QueuePool.overflow()는 아직 열지 않은 연결만큼 음수가 되는 내부 카운터다.
        # 운영자가 읽는 값으로 바꿔 준다: 열린 연결 수, pool_size를 넘겨 연 연결 수.
        return {
            "size": pool.size(),
            "opened": pool.checkedin() + pool.checkedout(),
            "checked_out": pool.checkedout(),
            "idle": pool.checkedin(),
            "overflow": max(0, pool.overflow()),
            "timeout": pool.timeout(),
        }
    return {
        "size": None,
        "opened": None,
        "checked_out": None,
        "idle": None,
        "overflow": None,
        "timeout": None,
    }


def install_event_loop_guard(engine: Engine, mode: LoopGuard) -> None:
    """이벤트 루프 스레드에서 실행되는 SQL을 감지한다.

    동기 DB 호출은 반드시 스레드풀(동기 def 라우트·의존성, asyncio.to_thread)에서 해야 한다.
    `async def` 라우트 안에서 DB를 부르면 그동안 모든 요청이 멈추므로, 테스트는 raise로,
    운영은 warn으로 켜 둔다.
    """
    if mode == "off":
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _guard(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # 이벤트 루프 밖(스레드풀·CLI) → 정상
        message = f"blocking SQL on the event loop thread: {statement[:120]}"
        if mode == "raise":
            raise BlockingCallInEventLoop(message)
        log.warning(message)


# --- 트랜잭션에 묶인 파일 ---------------------------------------------------------

_NEW_FILES = "study_invest.new_files"


def track_new_file(session: Session, path: Path) -> None:
    """이 트랜잭션에서 만든 파일로 등록한다. 트랜잭션이 커밋되지 않고 끝나면(롤백·예외·커밋 없이
    close) 파일을 지운다. 파일을 쓰기 **전에** 호출한다(쓰는 도중 실패해도 지워지게)."""
    session.info.setdefault(_NEW_FILES, []).append(path)


@event.listens_for(Session, "after_commit")
def _keep_new_files(session: Session) -> None:
    session.info.pop(_NEW_FILES, None)


@event.listens_for(Session, "after_transaction_end")
def _discard_uncommitted_files(session: Session, transaction: Any) -> None:
    if transaction.parent is not None:  # 세이브포인트 등 하위 트랜잭션은 무시
        return
    for path in session.info.pop(_NEW_FILES, []):
        path.unlink(missing_ok=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    from . import models  # noqa: F401  모델 등록

    Base.metadata.create_all(engine)


@dataclass
class DatabasePools:
    """애플리케이션이 쓰는 연결 풀 묶음.

    - api: HTTP 요청(스레드풀) 전용
    - batch: 09:00 공시·18:00 정산·수동 가격 전용. api 풀이 가득 차도 배치는 막히지 않는다.
    pgAdmin용 풀은 앱 밖(PgBouncer `study_invest_admin`)에 있다. docs/dev/db-pools.md 참고.
    """

    api: Engine
    batch: Engine

    @classmethod
    def create(cls, settings: Settings) -> DatabasePools:
        api = make_engine(settings.api_pool)
        batch_spec = settings.batch_pool
        if (
            batch_spec.url in {"sqlite://", "sqlite:///:memory:"}
            and batch_spec.url == settings.api_pool.url
        ):
            batch = api  # 메모리 SQLite(테스트)는 연결 하나를 공유해야 같은 DB를 본다
        else:
            batch = make_engine(batch_spec)
        for engine in {id(api): api, id(batch): batch}.values():
            install_event_loop_guard(engine, settings.loop_guard)
        return cls(api=api, batch=batch)

    def status(self) -> dict[str, dict[str, Any]]:
        return {"api": pool_status(self.api), "batch": pool_status(self.batch)}

    def dispose(self) -> None:
        self.api.dispose()
        if self.batch is not self.api:
            self.batch.dispose()
