# 공부장려 모의투자 이벤트

공부 인증을 게임 재화(병더리움 코인)와 연결한 2주 모의투자 이벤트 시스템.

- 시스템 규격서: [docs/spec/README.md](docs/spec/README.md) (v0.3)
- API 계약: [docs/dev/api.md](docs/dev/api.md)
- 구현 해석·가정: [docs/dev/implementation-notes.md](docs/dev/implementation-notes.md)
- 원본 규격서(docx): [docs/source/](docs/source/)

## 구성

| 디렉터리 | 내용 |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + PostgreSQL. 가격 산정·정산 배치·인증 검수·시뮬레이터(F-13) |
| `frontend/` | React + TypeScript + Vite. 공용 컴포넌트 라이브러리(`src/components/ui`) 위에 페이지 구성 |
| `docker-compose.yml` | PostgreSQL · 백엔드 · 프론트엔드(nginx) |

## Docker Compose로 실행

```bash
cp .env.example .env        # STUDY_INVEST_ADMIN_KEY, POSTGRES_PASSWORD 변경
docker compose up --build
```

- 웹: http://localhost:8080 (관리자 화면은 `/admin`, `.env`의 관리자 키로 접속)
- API: http://localhost:8080/api (백엔드 직접 접근은 http://localhost:8000, 문서는 `/docs`)
- 백엔드 컨테이너는 시작할 때 `alembic upgrade head`를 실행하고, `STUDY_INVEST_SCHEDULER=1`이면 09:00 공시·18:00 정산을 자동으로 돌린다.

## 로컬 개발

### 백엔드

```bash
cd backend
uv venv && uv pip install -e ".[dev]"      # 또는 python -m venv .venv && pip install -e ".[dev]"
docker compose up -d db                     # 저장소 루트에서. 또는 로컬 PostgreSQL
export STUDY_INVEST_DATABASE_URL=postgresql+psycopg://study:change-me@localhost:5432/study_invest
export STUDY_INVEST_ADMIN_KEY=dev-key
alembic upgrade head
uvicorn --factory study_invest.api.app:create_app --reload
```

검사:

```bash
ruff check src tests && ruff format --check src tests
mypy                                        # strict, src + tests
pytest                                      # 기본은 SQLite 메모리 DB
STUDY_INVEST_TEST_DATABASE_URL=postgresql+psycopg://study:study@localhost/study_invest_test pytest
```

운영 CLI:

```bash
study-invest run-due                         # 밀린 09:00/18:00 배치 실행 (cron 1분 간격 가능)
study-invest open --day 2026-10-06           # 수동 공시
study-invest settle --day 2026-10-06         # 수동 정산
study-invest simulate --paths 100000 --seed 42 [--use-price-cap] [--defaults]
study-invest purge-images                    # 이벤트 종료 후 인증 사진 삭제
```

환경 변수:

| 변수 | 기본값 | 설명 |
|---|---|---|
| `STUDY_INVEST_DATABASE_URL` | `postgresql+psycopg://study:study@localhost:5432/study_invest` | SQLAlchemy URL |
| `STUDY_INVEST_ADMIN_KEY` | (없음) | 관리자 API 키. 비어 있으면 관리자 API 차단 |
| `STUDY_INVEST_UPLOAD_DIR` | `./uploads` | 인증 사진 저장 경로 |
| `STUDY_INVEST_MAX_UPLOAD_BYTES` | `10485760` | 인증 사진 최대 크기 |
| `STUDY_INVEST_SCHEDULER` | `0` | `1`이면 앱 안에서 배치 자동 실행 |
| `STUDY_INVEST_SCHEDULER_INTERVAL` | `30` | 스케줄러 확인 주기(초) |
| `STUDY_INVEST_AUTO_CREATE_SCHEMA` | `0` | `1`이면 시작 시 `create_all`(마이그레이션 대신, 테스트용) |
| `STUDY_INVEST_THREADPOOL_SIZE` | `40` | 동기 라우트 스레드풀 크기 |
| `STUDY_INVEST_DB_POOL_SIZE` / `_DB_MAX_OVERFLOW` | `10` / `30` | DB 연결 풀(합이 스레드풀 이상) |
| `STUDY_INVEST_CPU_WORKERS` | `1` | 시뮬레이터용 프로세스 수(0이면 스레드) |
| `STUDY_INVEST_LOOP_GUARD` | `warn` | 이벤트 루프에서 SQL 실행 시 `warn`/`raise`/`off` |
| `STUDY_INVEST_FRONTEND_DIST` | (없음) | 빌드된 프론트엔드를 백엔드가 직접 제공할 때 경로 |

### 프론트엔드

[frontend/README.md](frontend/README.md) 참고. 개발 서버(`npm run dev`)는 `/api`를 `http://localhost:8000`으로 프록시한다.
