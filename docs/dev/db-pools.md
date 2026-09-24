# DB 연결 풀 설계

PostgreSQL 연결은 한정된 자원이다. 이 문서는 누가 몇 개의 연결을 쓰는지 **예산**으로 고정하고, 어느 한쪽이 몰려도 다른 쪽이 굶지 않도록 풀을 나눈 이유를 적는다.

## 구조

```text
                      ┌──────────────────────── PgBouncer :6432 ─────────────────────────┐
 FastAPI 프로세스       │                                                                    │      PostgreSQL :5432
 ┌──────────────────┐  │  study_invest_api    transaction  pool 20 (+예약 5)  ──────────────┼──▶  ≤ 25
 │ api 풀 (20)       │──┼─▶                                                                  │
 │  └ HTTP 요청      │  │  study_invest_batch  transaction  pool 2           ──────────────┼──▶  ≤ 2
 │ batch 풀 (2)      │──┼─▶                                                                  │
 │  └ 09:00/18:00   │  │  * (실제 DB 이름)     session      pool 5, 사용자 pgadmin ─────────┼──▶  ≤ 5
 └──────────────────┘  │                         ▲                                        │
                       └─────────────────────────┼────────────────────────────────────────┘
 pgAdmin ────────────────────────────────────────┘
 Alembic 마이그레이션 ─────────────────────────── (PgBouncer 우회, 직접 연결) ─────────────────▶  1
                                                                          superuser 예약 ─▶  3
                                                                          합계 36 ≤ max_connections 50
```

## 풀 목록

| 풀 | 쓰는 곳 | 앱 쪽 | PgBouncer | 모드 | 서버 연결 상한 |
|---|---|---|---|---|---|
| **api** | HTTP 요청(스레드풀의 동기 라우트) | SQLAlchemy `QueuePool` 20, overflow 0, 대기 10초 | `study_invest_api` pool 20 + reserve 5 | transaction | 25 |
| **batch** | 09:00 공시·보상, 18:00 정산, 수동 가격, `run-due` CLI | `QueuePool` 2, 대기 60초 | `study_invest_batch` pool 2 | transaction | 2 |
| **pgAdmin** | pgAdmin(사용자 `pgadmin`) | — | `*`(실제 DB 이름) pool 5, `[users] max_user_connections=5` | session | 5 |
| 마이그레이션 | 컨테이너 시작 시 `alembic upgrade head` | 직접 연결 1 | — | — | 1 |
| superuser 예약 | 비상 접속(`superuser_reserved_connections`) | — | — | — | 3 |

합계 36, PostgreSQL `max_connections=50`. PgBouncer는 시작할 때 이 합계를 `PG_MAX_CONNECTIONS`와 비교해 넘으면 **기동하지 않는다**(`infra/pgbouncer/entrypoint.sh`).

## 설계 원칙

1. **풀마다 상한이 따로 있다.** api가 20개를 다 써도 batch 2개, pgAdmin 5개는 그대로 남는다. 그래서 요청 폭주 중에도 18:00 정산은 제시간에 돌고, 장애 대응용 pgAdmin 접속도 막히지 않는다.
2. **앱 풀 크기 = PgBouncer 풀 크기.** 대기열은 앱 프로세스 안에만 생긴다. api 풀에서 10초(`STUDY_INVEST_API_POOL_TIMEOUT`) 안에 연결을 못 받으면 요청은 **503 `DB_BUSY`**(`Retry-After: 2`)로 끝난다. 무한 대기하며 스레드풀을 막지 않는다. PgBouncer 예약 5개는 앱 프로세스를 늘릴 때(워커·레플리카)의 여유다.
3. **pgAdmin은 앱 풀에 들어올 수 없다.** 앱 풀 별칭(`study_invest_api`, `study_invest_batch`)은 실제 DB 이름과 다르다. pgAdmin이 트리에서 실제 DB(`study_invest`, `postgres`)를 열면 와일드카드 항목(`*`)으로 가고, 사용자 `pgadmin`의 세션 모드 풀(모든 DB 합계 5개)만 쓴다. `pgadmin` 역할은 데이터 읽기·쓰기·모니터링만 되고 스키마 변경은 소유자만 한다.
4. **transaction 모드에 맞는 코드만 쓴다.** 서버 연결이 트랜잭션마다 바뀌므로 세션 상태에 기대지 않는다.
   - 서버측 prepared statement 끔: psycopg `prepare_threshold=None`, PgBouncer `max_prepared_statements=0`
   - 잠금은 트랜잭션 범위만: `SELECT … FOR UPDATE/SHARE`, `pg_advisory_xact_lock`
   - `SET`·`LISTEN`·세션 advisory lock·임시 테이블은 쓰지 않는다
5. **마이그레이션은 PgBouncer를 우회한다**(`STUDY_INVEST_MIGRATION_DATABASE_URL`). DDL 트랜잭션이 풀 연결을 오래 잡지 않게 한다.
6. **어느 풀의 연결인지 보인다.** 앱 연결은 `application_name`이 `study_invest:api` / `study_invest:batch`라서 pgAdmin의 대시보드나 `pg_stat_activity`에서 구분된다.

## 운영

| 확인할 것 | 방법 |
|---|---|
| 앱 풀 사용 현황 | `GET /api/admin/db-pools` (`size` 설정, `opened` 열린 연결, `checked_out` 사용 중, `idle`, `overflow`) |
| PgBouncer 풀 | `psql -h localhost -p 6432 -U study pgbouncer -c 'SHOW POOLS'` (컨테이너 안 또는 포트를 열었을 때) |
| 서버 연결 | pgAdmin → 대시보드, 또는 `SELECT application_name, usename, count(*) FROM pg_stat_activity GROUP BY 1, 2` |

**풀 크기를 바꿀 때**: `.env`의 `API_POOL_SIZE`·`BATCH_POOL_SIZE`는 앱과 PgBouncer에 같이 적용된다. `(API_POOL_SIZE + 5) + BATCH_POOL_SIZE + 5 + 1 + 3 ≤ PG_MAX_CONNECTIONS`를 지켜야 하며, 어기면 PgBouncer가 시작하지 않는다. uvicorn 워커나 레플리카를 N개로 늘리면 앱 쪽 합계가 N배가 되므로 앱 풀을 `API_POOL_SIZE / N`으로 줄이거나 PgBouncer 예약분 안에서 조정한다.

**pgAdmin 역할**은 PostgreSQL 데이터 디렉터리가 처음 만들어질 때(`infra/postgres/initdb/10-pgadmin-role.sh`) 생성된다. 기존 볼륨에 추가하려면 그 스크립트의 SQL을 소유자 계정으로 한 번 실행한다.

## 검증

- `tests/test_pools.py`
  - api 풀을 가득 채우면 0.5초 안에 503이 나오고, 같은 순간 batch 풀로 09:00 공시가 성공한다.
  - (PgBouncer 경유) pgAdmin 질의 6개를 동시에 보내면 5개만 동시에 돌고, 그동안 앱 풀 질의는 즉시 응답한다.
- 전체 테스트를 PgBouncer transaction 풀 경유로 실행해 통과(잠금·세이브포인트·advisory lock 포함):
  `STUDY_INVEST_TEST_DATABASE_URL=postgresql+psycopg://study:study@127.0.0.1:6432/study_invest_api pytest`
