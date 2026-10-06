"""오류 로그용 상세 정보 수집. 응답에는 쓰이지 않고 서버 로그에만 남는다.

개인정보 원칙: 요청 본문·쿼리 문자열·SQL 바인딩 값은 남기지 않는다(비밀번호·학번·메일이 섞인다).
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import Request

_PACKAGE_MARK = "study_invest"
_STATEMENT_LIMIT = 300


def origin(exc: BaseException) -> str:
    """예외가 처음 던져진 곳(우리 코드 중 가장 안쪽 프레임): `services/auth.py:311 in login`."""
    frames = [
        f
        for f in traceback.extract_tb(exc.__traceback__)
        if f"/{_PACKAGE_MARK}/" in f.filename.replace("\\", "/")
    ]
    if not frames:
        return "unknown"
    f = frames[-1]
    short = f.filename.replace("\\", "/").split(f"/{_PACKAGE_MARK}/", 1)[-1]
    return f"{short}:{f.lineno} in {f.name}"


def request_info(request: Request) -> dict[str, Any]:
    """라우트 템플릿·경로 변수·본문 크기·사용자 에이전트(앞부분)."""
    route = request.scope.get("route")
    info: dict[str, Any] = {
        "route": getattr(route, "path", None),
        "path_params": request.path_params or None,
        "content_length": request.headers.get("content-length"),
        "user_agent": (request.headers.get("user-agent") or "")[:120] or None,
    }
    return {k: v for k, v in info.items() if v is not None}


def db_error_info(exc: Exception) -> dict[str, Any]:
    """SQLAlchemy 오류의 원인: 드라이버 예외 종류, SQLSTATE, 제약 이름, SQL(바인딩 제외)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    statement = getattr(exc, "statement", None)
    info: dict[str, Any] = {
        "error_type": type(orig).__name__ if orig is not None else type(exc).__name__,
        "sqlstate": getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None),
        "constraint": getattr(diag, "constraint_name", None),
        "table": getattr(diag, "table_name", None),
        "detail": getattr(diag, "message_detail", None),
        "statement": " ".join(str(statement).split())[:_STATEMENT_LIMIT] if statement else None,
        "origin": origin(exc),
    }
    return {k: v for k, v in info.items() if v is not None}
