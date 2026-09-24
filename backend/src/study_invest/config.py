"""환경 변수 기반 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql+psycopg://study:study@localhost:5432/study_invest"
    admin_key: str = ""
    """관리자 API 키. 비어 있으면 관리자 API가 모두 거부된다."""
    upload_dir: Path = Path("./uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    scheduler_enabled: bool = False
    """켜면 앱 프로세스 안에서 09:00·18:00 배치를 자동 실행한다."""
    scheduler_interval_seconds: float = 30.0
    auto_create_schema: bool = False
    """켜면 시작 시 create_all로 스키마를 만든다(테스트·로컬 SQLite용). 운영은 Alembic을 쓴다."""
    frontend_dist: Path | None = None
    """빌드된 프론트엔드(dist) 경로. 지정하면 같은 서버에서 정적 파일로 제공한다."""

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        dist = env.get("STUDY_INVEST_FRONTEND_DIST")
        return cls(
            database_url=env.get("STUDY_INVEST_DATABASE_URL", cls.database_url),
            admin_key=env.get("STUDY_INVEST_ADMIN_KEY", ""),
            upload_dir=Path(env.get("STUDY_INVEST_UPLOAD_DIR", str(cls.upload_dir))),
            max_upload_bytes=int(env.get("STUDY_INVEST_MAX_UPLOAD_BYTES", cls.max_upload_bytes)),
            scheduler_enabled=env.get("STUDY_INVEST_SCHEDULER", "0").lower() in {"1", "true", "on"},
            scheduler_interval_seconds=float(env.get("STUDY_INVEST_SCHEDULER_INTERVAL", "30")),
            auto_create_schema=env.get("STUDY_INVEST_AUTO_CREATE_SCHEMA", "0").lower()
            in {"1", "true", "on"},
            frontend_dist=Path(dist) if dist else None,
        )
