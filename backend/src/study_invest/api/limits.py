"""요청 본문 크기 제한 (순수 ASGI 미들웨어, I/O 없음 → async).

Starlette는 multipart 본문을 핸들러 호출 전에 끝까지 받아 임시 파일에 저장한다. 그래서 핸들러
안에서 크기를 검사하면 이미 디스크를 쓴 뒤다(로그인 전 요청도 마찬가지). 여기서는 본문을 받기
전에 Content-Length로 거부하고, Content-Length가 없거나 거짓인 요청은 받는 도중 한도를 넘는
순간 중단한다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DETAIL = {"code": "PAYLOAD_TOO_LARGE", "message": "요청 본문이 너무 큽니다."}


class BodySizeLimitMiddleware:
    def __init__(
        self, app: ASGIApp, default_limit: int, path_limits: Mapping[str, int] | None = None
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.path_limits = dict(path_limits or {})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.path_limits.get(scope["path"], self.default_limit)

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await _reject(send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI 본문 파서는 HTTPException을 그대로 전달하므로 413으로 응답된다.
                    raise HTTPException(status_code=413, detail=DETAIL)
            return message

        await self.app(scope, limited_receive, send)


async def _reject(send: Send) -> None:
    body = json.dumps({"detail": DETAIL}, ensure_ascii=False).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
