"""서버 로깅: 요청 로그, 요청 ID, 처리하지 못한 예외, 핵심 동작 로그."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from conftest import ADMIN_KEY, email_code, profile_for, register_with
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


def _detail(logs: ListHandler, text: str) -> dict[str, object]:
    d = find(logs, text)["detail"]
    assert isinstance(d, dict)
    return d


def test_login_failure_logs_reason_without_leaking_identity(
    client: TestClient, logs: ListHandler
) -> None:
    r = client.post("/api/auth/login", json={"identity": "2026123456", "password": "pw-12345678"})
    assert r.status_code == 401
    d = _detail(logs, "domain error: INVALID_CREDENTIALS")
    assert d["origin"].startswith("services/auth.py")  # type: ignore[union-attr]
    ctx = d["context"]
    assert isinstance(ctx, dict)
    assert ctx["why"] == "no_such_account"
    assert ctx["identity"] == "20***(10자)"
    assert d["route"] == "/api/auth/login"
    assert "2026123456" not in json.dumps(logs.lines, ensure_ascii=False)
    assert "pw-12345678" not in json.dumps(logs.lines, ensure_ascii=False)


def test_validation_error_logs_fields_not_values(client: TestClient, logs: ListHandler) -> None:
    r = client.post("/api/auth/login", json={"identity": "x", "password": 12345})
    assert r.status_code == 422
    d = _detail(logs, "validation failed")
    errors = d["errors"]
    assert isinstance(errors, list) and errors
    assert any("password" in e["loc"] for e in errors)
    assert "12345" not in json.dumps(logs.lines)


def test_unknown_route_logs_http_error(client: TestClient, logs: ListHandler) -> None:
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert "http error: 404" in str(find(logs, "http error")["message"])


def test_code_errors_log_attempts_and_reason(client: TestClient, logs: ListHandler) -> None:
    email = "detail@skku.edu"
    email_code(client, email)
    r = register_with(client, email, "디테일", code="000000")
    assert r.status_code == 400
    ctx = _detail(logs, "domain error: INVALID_CODE")["context"]
    assert isinstance(ctx, dict)
    assert ctx["attempts"] == 1
    assert ctx["remaining_attempts"] >= 0
    assert email not in json.dumps(logs.lines, ensure_ascii=False)


def test_session_id_ties_login_to_later_requests_and_logout(
    client: TestClient, logs: ListHandler
) -> None:
    email = "sess@skku.edu"
    r = register_with(client, email, "세션", code=email_code(client, email))
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    sid = find(logs, "register:")["session_id"]
    assert isinstance(sid, str) and len(sid) == 12
    assert token not in json.dumps(logs.lines) and sid not in token

    auth = {"Authorization": f"Bearer {token}"}
    client.get("/api/me", headers=auth)
    assert find(logs, "GET /api/me")["session_id"] == sid
    client.post("/api/auth/logout", headers=auth)
    assert find(logs, "logout")["session_id"] == sid

    # 폐기된 토큰의 요청도 같은 세션 ID로 남고, 참가자는 붙지 않는다.
    stale_count = len(logs.lines)
    assert client.get("/api/me", headers=auth).status_code == 401
    stale = next(ln for ln in logs.lines[stale_count:] if "GET /api/me" in str(ln["message"]))
    assert stale["session_id"] == sid and "participant_id" not in stale

    # 다시 로그인하면 새 세션 ID가 발급된다.
    again = client.post(
        "/api/auth/login",
        json={"identity": profile_for(email)["student_id"], "password": "tiger-moon-river-42"},
    )
    assert again.status_code == 200, again.text
    assert find(logs, "login")["session_id"] != sid
