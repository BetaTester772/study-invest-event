"""환경 변수 설정: 이벤트 기간(STUDY_INVEST_EVENT_START/END)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time
from pathlib import Path

import pytest
from conftest import ADMIN_KEY, TEST_DB_URL, Clock, kst
from fastapi.testclient import TestClient

from study_invest.api.app import create_app
from study_invest.config import Settings
from study_invest.db import Base
from study_invest.params import EVENT_END, EVENT_START


def test_event_dates_default_to_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STUDY_INVEST_EVENT_START", raising=False)
    monkeypatch.setenv("STUDY_INVEST_EVENT_END", "")  # compose가 빈 값으로 넘겨도 기본값
    cal = Settings.from_env().calendar
    assert (cal.start, cal.end) == (EVENT_START, EVENT_END)


def test_event_dates_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDY_INVEST_EVENT_START", "2026-09-24")
    monkeypatch.setenv("STUDY_INVEST_EVENT_END", " 2026-10-04 ")
    cal = Settings.from_env().calendar
    assert (cal.start, cal.end) == (date(2026, 9, 24), date(2026, 10, 4))
    assert cal.total_rounds == 10


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-10-04", "2026-09-24"), ("2026/09/24", "2026-10-04"), ("2026-09-24", "tomorrow")],
)
def test_invalid_event_dates_fail_fast(
    monkeypatch: pytest.MonkeyPatch, start: str, end: str
) -> None:
    monkeypatch.setenv("STUDY_INVEST_EVENT_START", start)
    monkeypatch.setenv("STUDY_INVEST_EVENT_END", end)
    with pytest.raises(ValueError):
        Settings.from_env().calendar  # noqa: B018


@pytest.fixture
def qa_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=TEST_DB_URL,
        admin_key=ADMIN_KEY,
        upload_dir=tmp_path / "uploads",
        auto_create_schema=True,
        loop_guard="raise",
        event_start=date(2026, 9, 24),
        event_end=date(2026, 10, 4),
    )
    app = create_app(settings, clock=Clock(kst(date(2026, 9, 25), time(10, 0))))
    engine = app.state.study_invest.session_factory.kw["bind"]
    if TEST_DB_URL != "sqlite://":
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    if TEST_DB_URL != "sqlite://":
        Base.metadata.drop_all(engine)
    engine.dispose()


def test_app_uses_configured_event_dates(qa_client: TestClient) -> None:
    body = qa_client.get("/api/event").json()
    assert body["start"] == "2026-09-24"
    assert body["end"] == "2026-10-04"
    assert body["total_rounds"] == 10
    assert body["is_operating_day"] is True
