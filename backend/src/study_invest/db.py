"""SQLAlchemy 엔진·세션."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


log = logging.getLogger("study_invest.db")

LoopGuard = Literal["off", "warn", "raise"]


class BlockingCallInEventLoop(RuntimeError):
    """이벤트 루프 스레드에서 동기 DB 호출이 일어났다(서비스 전체가 멈출 수 있음)."""


def make_engine(url: str, pool_size: int = 10, max_overflow: int = 30) -> Engine:
    kwargs: dict[str, object] = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    else:
        # 동기 라우트는 스레드풀에서 돈다. 풀 크기 + overflow를 스레드풀 크기에 맞춘다.
        kwargs.update(pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


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


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    from . import models  # noqa: F401  모델 등록

    Base.metadata.create_all(engine)
