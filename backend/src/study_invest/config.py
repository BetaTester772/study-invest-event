"""환경 변수 기반 설정."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal, cast

from .clock import ScaledClock, system_now
from .event_calendar import EventCalendar
from .params import EVENT_END, EVENT_START, KST


@dataclass(frozen=True)
class PoolSpec:
    """애플리케이션 쪽 연결 풀 하나(SQLAlchemy QueuePool)의 설정.

    원칙: 같은 이름의 PgBouncer 풀 크기와 같게 둔다. 그러면 대기열은 앱 프로세스 안에만 생기고
    (timeout 초과 시 503), PgBouncer 쪽에서는 앱 트래픽이 줄 서지 않는다. docs/dev/db-pools.md 참고.
    """

    name: str
    url: str
    size: int
    max_overflow: int = 0
    timeout: float = 10.0
    """풀에서 연결을 기다리는 최대 초. 넘으면 요청은 503으로 끝난다."""
    recycle: int = 1800
    """이 초보다 오래된 연결은 다시 연다(PgBouncer·방화벽 유휴 끊김 대비)."""


def _env_date(env: Mapping[str, str], name: str, default: date) -> date:
    """YYYY-MM-DD 환경 변수. 비어 있거나 없으면 기본값."""
    value = env.get(name, "").strip()
    return date.fromisoformat(value) if value else default


def _env_datetime(env: Mapping[str, str], name: str) -> datetime | None:
    """ISO 8601 일시 환경 변수. 시간대가 없으면 KST로 본다. 비어 있거나 없으면 None."""
    value = env.get(name, "").strip()
    if not value:
        return None
    at = datetime.fromisoformat(value)
    return at.replace(tzinfo=KST) if at.tzinfo is None else at


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    """실수 환경 변수. 비어 있거나 없으면 기본값."""
    value = env.get(name, "").strip()
    return float(value) if value else default


DEFAULT_DATABASE_URL = "postgresql+psycopg://study:study@localhost:5432/study_invest"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    """API 요청용 풀이 붙는 URL(운영: PgBouncer `study_invest` 풀)."""
    batch_database_url: str | None = None
    """배치(공시·정산) 전용 풀 URL(운영: PgBouncer `study_invest_batch`). 없으면 database_url."""
    migration_database_url: str | None = None
    """Alembic 마이그레이션용 직접 연결(PgBouncer 우회). 없으면 database_url."""
    admin_key: str = ""
    """관리자 API 키. 비어 있으면 관리자 API가 모두 거부된다."""
    upload_dir: Path = Path("./uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_json_bytes: int = 1024 * 1024
    """업로드 외 요청 본문 한도."""
    scheduler_enabled: bool = False
    """켜면 앱 프로세스 안에서 09:00·18:00 배치를 자동 실행한다."""
    scheduler_interval_seconds: float = 30.0
    auto_create_schema: bool = False
    """켜면 시작 시 create_all로 스키마를 만든다(테스트·로컬 SQLite용). 운영은 Alembic을 쓴다."""
    threadpool_size: int = 40
    """동기 라우트·의존성을 실행하는 스레드풀 크기(anyio 기본 40)."""
    api_pool_size: int = 20
    api_pool_timeout: float = 10.0
    batch_pool_size: int = 2
    loop_guard: Literal["off", "warn", "raise"] = "warn"
    """이벤트 루프 스레드에서 SQL이 실행되면 경고(warn)하거나 실패(raise)한다."""
    cpu_workers: int = 1
    """시뮬레이터 등 CPU 작업용 프로세스 수. 0이면 스레드로 실행한다."""
    frontend_dist: Path | None = None
    """빌드된 프론트엔드(dist) 경로. 지정하면 같은 서버에서 정적 파일로 제공한다."""
    event_start: date = EVENT_START
    event_end: date = EVENT_END
    """이벤트 기간(양 끝 포함). 기본값은 규격서 기간이며, 테스트·QA 서버에서만 바꾼다."""
    time_scale: float = 1.0
    """앱 시계 배속. 24면 실제 1시간이 이벤트 하루다. 테스트·QA 서버에서만 바꾼다."""
    time_origin: datetime | None = None
    """앱 시계가 이벤트 첫날 00:00(KST)을 가리키는 실제 시각. time_scale이 1이 아니면 필수."""
    qa_unlimited: bool = False
    """켜면 이벤트 종료일(event_end)을 무시하고 시작일 이후 끝없이 운영한다(QA 무제한 모드).
    공시·정산·회차가 계속 이어져 가격 추세를 길게 볼 수 있다. 테스트·QA 서버에서만 켠다."""
    qa_tools: bool = False
    """켜면 관리자 화면에 시각과 무관하게 가격을 바로 변동시키는 QA 버튼이 생긴다.
    테스트·QA 서버에서만 켠다. 운영에서 켜면 이벤트 진행이 시계를 앞질러 되돌릴 수 없다."""

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        dist = env.get("STUDY_INVEST_FRONTEND_DIST")
        return cls(
            database_url=env.get("STUDY_INVEST_DATABASE_URL", cls.database_url),
            batch_database_url=env.get("STUDY_INVEST_BATCH_DATABASE_URL") or None,
            migration_database_url=env.get("STUDY_INVEST_MIGRATION_DATABASE_URL") or None,
            admin_key=env.get("STUDY_INVEST_ADMIN_KEY", ""),
            upload_dir=Path(env.get("STUDY_INVEST_UPLOAD_DIR", str(cls.upload_dir))),
            max_upload_bytes=int(env.get("STUDY_INVEST_MAX_UPLOAD_BYTES", cls.max_upload_bytes)),
            max_json_bytes=int(env.get("STUDY_INVEST_MAX_JSON_BYTES", cls.max_json_bytes)),
            scheduler_enabled=env.get("STUDY_INVEST_SCHEDULER", "0").lower() in {"1", "true", "on"},
            scheduler_interval_seconds=float(env.get("STUDY_INVEST_SCHEDULER_INTERVAL", "30")),
            auto_create_schema=env.get("STUDY_INVEST_AUTO_CREATE_SCHEMA", "0").lower()
            in {"1", "true", "on"},
            threadpool_size=int(env.get("STUDY_INVEST_THREADPOOL_SIZE", cls.threadpool_size)),
            api_pool_size=int(env.get("STUDY_INVEST_API_POOL_SIZE", cls.api_pool_size)),
            api_pool_timeout=float(env.get("STUDY_INVEST_API_POOL_TIMEOUT", cls.api_pool_timeout)),
            batch_pool_size=int(env.get("STUDY_INVEST_BATCH_POOL_SIZE", cls.batch_pool_size)),
            loop_guard=cast(
                Literal["off", "warn", "raise"], env.get("STUDY_INVEST_LOOP_GUARD", cls.loop_guard)
            ),
            cpu_workers=int(env.get("STUDY_INVEST_CPU_WORKERS", cls.cpu_workers)),
            frontend_dist=Path(dist) if dist else None,
            event_start=_env_date(env, "STUDY_INVEST_EVENT_START", cls.event_start),
            event_end=_env_date(env, "STUDY_INVEST_EVENT_END", cls.event_end),
            time_scale=_env_float(env, "STUDY_INVEST_TIME_SCALE", cls.time_scale),
            time_origin=_env_datetime(env, "STUDY_INVEST_TIME_ORIGIN"),
            qa_unlimited=env.get("STUDY_INVEST_QA_UNLIMITED", "0").lower() in {"1", "true", "on"},
            qa_tools=env.get("STUDY_INVEST_QA_TOOLS", "0").lower() in {"1", "true", "on"},
        )

    @property
    def calendar(self) -> EventCalendar:
        return EventCalendar(self.event_start, None if self.qa_unlimited else self.event_end)

    def make_clock(self) -> Callable[[], datetime]:
        """앱 시계. time_origin이 없으면 실제 KST 시각, 있으면 그때부터 time_scale배로 흐른다."""
        if not (math.isfinite(self.time_scale) and self.time_scale > 0):
            raise ValueError("STUDY_INVEST_TIME_SCALE은 0보다 큰 수여야 합니다.")
        if self.time_origin is None:
            if self.time_scale != 1:
                raise ValueError(
                    "STUDY_INVEST_TIME_SCALE을 바꾸려면 STUDY_INVEST_TIME_ORIGIN도 지정하세요."
                )
            return system_now
        return ScaledClock(
            origin=self.time_origin,
            virtual_origin=datetime.combine(self.event_start, time(0), KST),
            scale=self.time_scale,
        )

    @property
    def api_pool(self) -> PoolSpec:
        return PoolSpec("api", self.database_url, self.api_pool_size, timeout=self.api_pool_timeout)

    @property
    def batch_pool(self) -> PoolSpec:
        # 배치는 요청 폭주와 분리된 전용 풀을 쓴다. 18:00 정산이 API 대기열 뒤에 서지 않는다.
        return PoolSpec(
            "batch",
            self.batch_database_url or self.database_url,
            self.batch_pool_size,
            timeout=60.0,
        )

    @property
    def migration_url(self) -> str:
        return self.migration_database_url or self.database_url
