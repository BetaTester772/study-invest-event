"""로깅 설정과 요청 컨텍스트.

`study_invest` 로거에만 핸들러를 붙인다(루트·uvicorn 로거는 건드리지 않는다). 요청마다
요청 ID·참가자 ID를 contextvar에 담아 모든 로그 줄에 붙인다.
"""

from __future__ import annotations

import contextvars
import json
import logging
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


def configure_logging(level: str = "INFO", fmt: Literal["text", "json"] = "text") -> None:
    """앱 로거를 설정한다. 여러 번 불러도 핸들러는 하나만 남는다."""
    resolved = logging.getLevelName(level.upper())
    if not isinstance(resolved, int):
        raise ValueError(f"STUDY_INVEST_LOG_LEVEL이 올바르지 않습니다: {level!r}")
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        if getattr(h, _HANDLER_MARK, False):
            logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _HANDLER_MARK, True)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    logger.addHandler(handler)
    logger.setLevel(resolved)
