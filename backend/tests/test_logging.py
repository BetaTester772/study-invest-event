"""서버 로깅: 요청 로그, 요청 ID, 처리하지 못한 예외, 핵심 동작 로그."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from conftest import ADMIN_KEY, email_code, register_with
from fastapi.testclient import TestClient

from study_invest.config import Settings
from study_invest.logging_setup import ContextFilter, JsonFormatter, configure_logging


class ListHandler(logging.Handler):
    """컨텍스트 필터·JSON 포맷터를 거친 로그를 dict로 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.addFilter(ContextFilter())
        self.setFormatter(JsonFormatter())
        self.lines: list[dict[str, object]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def logs() -> Iterator[ListHandler]:
    handler = ListHandler()
    logger = logging.getLogger("study_invest")
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


def find(logs: ListHandler, text: str) -> dict[str, object]:
    return next(line for line in logs.lines if text in str(line["message"]))


def test_request_log_has_status_duration_and_request_id(
    client: TestClient, logs: ListHandler
) -> None:
    r = client.get("/api/event")
    line = find(logs, "GET /api/event")
    assert line["status"] == 200
    assert line["method"] == "GET"
    assert isinstance(line["duration_ms"], float)
    assert line["request_id"] == r.headers["x-request-id"]


def test_query_string_is_not_logged(client: TestClient, logs: ListHandler) -> None:
    client.get("/api/ranking?token=secret-value")
    assert all("secret-value" not in json.dumps(line) for line in logs.lines)


def test_safe_incoming_request_id_is_kept_and_unsafe_replaced(
    client: TestClient,
) -> None:
    ok = client.get("/api/event", headers={"X-Request-ID": "abc-123"})
    assert ok.headers["x-request-id"] == "abc-123"
    bad = client.get("/api/event", headers={"X-Request-ID": "x y\tz"})
    assert bad.headers["x-request-id"] != "x y\tz"


def test_domain_error_logs_code(client: TestClient, logs: ListHandler) -> None:
    r = client.get("/api/me")
    assert r.status_code == 401
    assert "UNAUTHORIZED" in str(find(logs, "domain error")["message"])
    assert find(logs, "GET /api/me")["status"] == 401


def test_admin_requests_are_flagged(client: TestClient, logs: ListHandler) -> None:
    client.get("/api/admin/params", headers={"X-Admin-Key": ADMIN_KEY})
    assert find(logs, "GET /api/admin/params").get("admin") is True


def test_unhandled_exception_logged_with_traceback_and_request_id() -> None:
    from fastapi import FastAPI

    from study_invest.api.access_log import REQUEST_ID_SCOPE_KEY, AccessLogMiddleware

    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    handler = ListHandler()
    logger = logging.getLogger("study_invest")
    logger.addHandler(handler)
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/boom")
    finally:
        logger.removeHandler(handler)
    assert r.status_code == 500
    err = find(handler, "unhandled error")
    assert err["level"] == "ERROR"
    assert "kaboom" in str(err["exc"])
    assert REQUEST_ID_SCOPE_KEY  # 앱 핸들러가 이 키로 요청 ID를 응답에 싣는다


def test_app_returns_request_id_on_500(client: TestClient) -> None:
    app = client.app

    @app.get("/api/_boom")  # type: ignore[attr-defined]
    def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert detail["code"] == "INTERNAL_ERROR"
    assert detail["request_id"] == r.headers["x-request-id"]


def test_register_and_login_are_logged(client: TestClient, logs: ListHandler) -> None:
    email = "log@skku.edu"
    code = email_code(client, email)
    r = register_with(client, email, "로거", code=code)
    assert r.status_code == 201, r.text
    line = find(logs, "register:")
    assert line["participant_id"] == r.json()["participant"]["id"]
    assert email not in json.dumps(logs.lines, ensure_ascii=False)


def test_log_level_and_format_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDY_INVEST_LOG_LEVEL", "debug")
    monkeypatch.setenv("STUDY_INVEST_LOG_FORMAT", "json")
    s = Settings.from_env()
    assert (s.log_level, s.log_format) == ("DEBUG", "json")
    monkeypatch.setenv("STUDY_INVEST_LOG_FORMAT", "xml")
    with pytest.raises(ValueError, match="LOG_FORMAT"):
        Settings.from_env()


def test_configure_logging_is_idempotent_and_validates() -> None:
    logger = logging.getLogger("study_invest")
    configure_logging("WARNING", "text")
    configure_logging("INFO", "json")
    marked = [h for h in logger.handlers if getattr(h, "_study_invest_handler", False)]
    assert len(marked) == 1
    assert logger.level == logging.INFO
    with pytest.raises(ValueError):
        configure_logging("LOUD")
