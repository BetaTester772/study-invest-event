"""환경 변수 설정: 이벤트 기간(STUDY_INVEST_EVENT_START/END), 앱 시계 배속(STUDY_INVEST_TIME_*)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import ADMIN_KEY, TEST_DB_URL, Clock, kst
from fastapi.testclient import TestClient

from study_invest.api import app as app_module
from study_invest.api.app import create_app
from study_invest.clock import ScaledClock, system_now
from study_invest.config import Settings
from study_invest.db import Base
from study_invest.params import EVENT_END, EVENT_START, KST


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


# --- 앱 시계 배속(STUDY_INVEST_TIME_SCALE/ORIGIN) ------------------------------------------

QA_START = date(2026, 9, 24)
ORIGIN = datetime(2026, 10, 1, 15, 0, tzinfo=KST)


class FakeReal:
    """ScaledClock의 실제 시각 소스."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.parametrize(
    ("real_elapsed", "virtual"),
    [
        (timedelta(0), kst(QA_START, time(0))),
        (timedelta(minutes=22, seconds=30), kst(QA_START, time(9, 0))),  # 공시
        (timedelta(minutes=45), kst(QA_START, time(18, 0))),  # 정산
        (timedelta(hours=1), kst(QA_START + timedelta(days=1), time(0))),  # 다음 운영일
        (-timedelta(minutes=30), kst(QA_START - timedelta(days=1), time(12, 0))),  # 시작 전
    ],
)
def test_scaled_clock_runs_one_day_per_hour(real_elapsed: timedelta, virtual: datetime) -> None:
    real = FakeReal(ORIGIN + real_elapsed)
    clock = ScaledClock(ORIGIN, kst(QA_START, time(0)), 24, source=real)
    assert clock() == virtual


def test_time_settings_default_to_real_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STUDY_INVEST_TIME_SCALE", raising=False)
    monkeypatch.setenv("STUDY_INVEST_TIME_ORIGIN", "")  # compose가 빈 값으로 넘겨도 기본값
    settings = Settings.from_env()
    assert (settings.time_scale, settings.time_origin) == (1.0, None)
    assert settings.make_clock() is system_now


@pytest.mark.parametrize(
    "origin", ["2026-10-01T15:00", "2026-10-01T15:00:00+09:00", "2026-10-01T06:00:00Z"]
)
def test_time_settings_from_env(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    monkeypatch.setenv("STUDY_INVEST_EVENT_START", "2026-09-24")
    monkeypatch.setenv("STUDY_INVEST_TIME_SCALE", " 24 ")
    monkeypatch.setenv("STUDY_INVEST_TIME_ORIGIN", origin)  # 시간대가 없으면 KST
    settings = Settings.from_env()
    assert settings.time_scale == 24
    assert settings.time_origin == ORIGIN
    clock = settings.make_clock()
    assert isinstance(clock, ScaledClock)
    assert clock.virtual_origin == kst(QA_START, time(0))


@pytest.mark.parametrize(
    ("scale", "origin"),
    [
        ("24", ""),  # 배속만 주고 기준 시각이 없음
        ("0", "2026-10-01T15:00"),
        ("-24", "2026-10-01T15:00"),
        ("nan", "2026-10-01T15:00"),
        ("inf", "2026-10-01T15:00"),
        ("fast", "2026-10-01T15:00"),
        ("24", "2026/10/01 15:00"),
    ],
)
def test_invalid_time_settings_fail_fast(
    monkeypatch: pytest.MonkeyPatch, scale: str, origin: str
) -> None:
    monkeypatch.setenv("STUDY_INVEST_TIME_SCALE", scale)
    monkeypatch.setenv("STUDY_INVEST_TIME_ORIGIN", origin)
    with pytest.raises(ValueError):
        Settings.from_env().make_clock()


def test_app_follows_scaled_clock(tmp_path: Path) -> None:
    # 실제 25분 전에 첫날 00:00이 시작 → 앱 시계는 첫날 10:00 무렵(장중)
    settings = Settings(
        database_url=TEST_DB_URL,
        admin_key=ADMIN_KEY,
        upload_dir=tmp_path / "uploads",
        auto_create_schema=True,
        loop_guard="raise",
        event_start=QA_START,
        event_end=date(2026, 10, 4),
        time_scale=24,
        time_origin=system_now() - timedelta(minutes=25),
    )
    app = create_app(settings)
    engine = app.state.study_invest.session_factory.kw["bind"]
    if TEST_DB_URL != "sqlite://":
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    try:
        with TestClient(app) as c:
            body = c.get("/api/event").json()
            now = datetime.fromisoformat(body["now"])
            assert body["today"] == "2026-09-24"
            assert time(9, 50) <= now.astimezone(KST).time() <= time(10, 30)
            # 첫날 공시 → 장 열림
            r = c.post("/api/admin/batch/run-due", headers={"X-Admin-Key": ADMIN_KEY})
            assert r.status_code == 200, r.text
            assert c.get("/api/event").json()["market"]["is_open"] is True
    finally:
        if TEST_DB_URL != "sqlite://":
            Base.metadata.drop_all(engine)
        engine.dispose()


def test_scheduler_waits_real_seconds_under_scaled_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(app_module, "run_due", lambda *_: [])
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    state = SimpleNamespace(
        batch_session_factory=None,
        clock=Clock(kst(QA_START, time(8, 59))),  # 공시까지 앱 시계 60초
        calendar=None,
        rng=None,
        time_scale=24,
        settings=SimpleNamespace(scheduler_interval_seconds=30.0),
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app_module._scheduler(state))  # type: ignore[arg-type]
    assert slept == [pytest.approx(60 / 24 + app_module.BATCH_WAKE_DELAY)]
