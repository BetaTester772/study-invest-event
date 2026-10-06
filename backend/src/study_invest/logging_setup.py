"""로깅 설정과 요청 컨텍스트.

`study_invest` 로거에만 핸들러를 붙인다(루트·uvicorn 로거는 건드리지 않는다). 요청마다
요청 ID·참가자 ID를 contextvar에 담아 모든 로그 줄에 붙인다.
"""

from __future__ import annotations

import atexit
import contextlib
import contextvars
import copy
import json
import logging
import logging.handlers
import queue as queue_module
import sys
from datetime import UTC, datetime
from typing import Literal

LOGGER_NAME = "study_invest"

request_ctx: contextvars.ContextVar[dict[str, object] | None] = contextvars.ContextVar(
    "study_invest_request_ctx", default=None
)
"""현재 요청의 가변 컨텍스트(request_id, participant_id, session_id, admin).
스레드풀에서도 같은 dict를 본다."""


def bind(**values: object) -> None:
    """현재 요청 컨텍스트에 값을 더한다. 요청 밖이면 아무 일도 하지 않는다."""
    ctx = request_ctx.get()
    if ctx is not None:
        ctx.update(values)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = request_ctx.get() or {}
        record.request_id = ctx.get("request_id", "-")
        record.participant_id = ctx.get("participant_id")
        record.session_id = ctx.get("session_id")
        record.admin = bool(ctx.get("admin"))
        return True


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        extra = []
        participant_id = getattr(record, "participant_id", None)
        if participant_id is not None:
            extra.append(f"participant={participant_id}")
        session_id = getattr(record, "session_id", None)
        if session_id is not None:
            extra.append(f"session={session_id}")
        if getattr(record, "admin", False):
            extra.append("admin")
        text = f"{text} ({', '.join(extra)})" if extra else text
        detail = getattr(record, "detail", None)
        if isinstance(detail, dict) and detail:
            text += " | " + json.dumps(detail, ensure_ascii=False, default=str)
        return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        participant_id = getattr(record, "participant_id", None)
        if participant_id is not None:
            data["participant_id"] = participant_id
        session_id = getattr(record, "session_id", None)
        if session_id is not None:
            data["session_id"] = session_id
        if getattr(record, "admin", False):
            data["admin"] = True
        detail = getattr(record, "detail", None)
        if isinstance(detail, dict) and detail:
            data["detail"] = detail
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            data.update(fields)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


_HANDLER_MARK = "_study_invest_handler"
QUEUE_SIZE = 10_000
"""대기 로그 상한. 출력이 이보다 오래 막히면 새 로그를 버리고(요청은 계속 처리) 개수를 센다."""


class NonBlockingQueueHandler(logging.handlers.QueueHandler):
    """로그를 큐에 넣기만 한다(호출한 스레드·이벤트 루프는 출력을 기다리지 않는다).

    - 컨텍스트 필터(요청 ID 등)는 호출한 스레드에서 돌아야 하므로 이 핸들러에 붙인다.
    - 큐가 가득 차면 버리고, 다시 들어갈 수 있을 때 버린 개수를 한 줄로 남긴다.
    """

    def __init__(self, queue: queue_module.Queue[logging.LogRecord]) -> None:
        super().__init__(queue)
        self.dropped = 0
        self.listener: DrainingListener | None = None

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # 기본 구현은 exc_info를 지워 JSON 포맷터가 트레이스백을 못 쓴다. 인자만 미리 합치고
        # 나머지(exc_info, detail, fields)는 그대로 둔다. 서식은 출력 스레드에서 처리한다.
        record = copy.copy(record)
        record.msg = record.getMessage()
        record.args = None
        return record

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue_module.Full:
            self.dropped += 1
            return
        if self.dropped:
            dropped, self.dropped = self.dropped, 0
            notice = logging.LogRecord(
                LOGGER_NAME,
                logging.WARNING,
                __file__,
                0,
                f"log queue full: dropped {dropped}",
                None,
                None,
            )
            with contextlib.suppress(queue_module.Full):
                self.queue.put_nowait(notice)


class DrainingListener(logging.handlers.QueueListener):
    """종료 신호를 큐가 가득 차 있어도 넣을 수 있게 한다(기본 구현은 가득 차면 예외로 실패)."""

    def enqueue_sentinel(self) -> None:
        self.queue.put(self._sentinel, timeout=5)  # type: ignore[attr-defined]


def shutdown_logging() -> None:
    """대기 중인 로그를 모두 내보내고 출력 스레드를 멈춘다(종료·재설정 때)."""
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        if getattr(h, _HANDLER_MARK, False):
            logger.removeHandler(h)
            listener = getattr(h, "listener", None)
            if listener is not None:
                listener.stop()  # 큐를 비운 뒤 멈춘다


def configure_logging(level: str = "INFO", fmt: Literal["text", "json"] = "text") -> None:
    """앱 로거를 설정한다. 여러 번 불러도 핸들러는 하나만 남는다.

    출력(stderr)은 별도 스레드가 맡는다. 파이프가 막혀도 요청 처리는 멈추지 않는다.
    """
    resolved = logging.getLevelName(level.upper())
    if not isinstance(resolved, int):
        raise ValueError(f"STUDY_INVEST_LOG_LEVEL이 올바르지 않습니다: {level!r}")
    shutdown_logging()
    logger = logging.getLogger(LOGGER_NAME)
    sink = logging.StreamHandler(sys.stderr)
    sink.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    q: queue_module.Queue[logging.LogRecord] = queue_module.Queue(QUEUE_SIZE)
    handler = NonBlockingQueueHandler(q)
    setattr(handler, _HANDLER_MARK, True)
    handler.addFilter(ContextFilter())
    handler.listener = DrainingListener(q, sink, respect_handler_level=False)
    handler.listener.start()
    logger.addHandler(handler)
    logger.setLevel(resolved)


atexit.register(shutdown_logging)
