"""요청 로그 미들웨어 (순수 ASGI, I/O 없음 → async).

요청마다 요청 ID를 정해 로그 컨텍스트에 넣고(X-Request-ID 응답 헤더로도 돌려준다), 끝나면
메서드·경로·상태·처리 시간을 한 줄로 남긴다. 쿼리 문자열은 남기지 않는다(토큰이 실릴 수 있다).
처리하지 못한 예외는 여기서 트레이스백과 함께 기록한 뒤 그대로 다시 던진다.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..logging_setup import request_ctx

log = logging.getLogger("study_invest.access")

REQUEST_ID_SCOPE_KEY = "study_invest.request_id"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _request_id(headers: dict[bytes, bytes]) -> str:
    """프록시가 넘긴 X-Request-ID가 안전한 형태면 그대로 쓰고, 아니면 새로 만든다."""
    given = headers.get(b"x-request-id", b"").decode("latin-1")
    return given if _VALID_ID.match(given) else uuid.uuid4().hex[:16]


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _request_id(dict(scope["headers"]))
        scope[REQUEST_ID_SCOPE_KEY] = rid
        ctx: dict[str, object] = {"request_id": rid}
        token = request_ctx.set(ctx)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("unhandled error: %s %s", scope["method"], scope["path"])
            raise
        finally:
            ms = (time.perf_counter() - started) * 1000
            path = scope["path"]
            if status >= 500:
                level = logging.ERROR
            elif status >= 400:
                level = logging.WARNING if status in (401, 403, 429) else logging.INFO
            else:
                # SPA 정적 파일 등 API 밖 요청은 DEBUG로 낮춰 소음을 줄인다.
                level = logging.INFO if path.startswith("/api/") else logging.DEBUG
            client = scope.get("client")
            log.log(
                level,
                "%s %s -> %d (%.1fms)",
                scope["method"],
                path,
                status,
                ms,
                extra={
                    "fields": {
                        "method": scope["method"],
                        "path": path,
                        "status": status,
                        "duration_ms": round(ms, 1),
                        "client": client[0] if client else None,
                    }
                },
            )
            request_ctx.reset(token)
