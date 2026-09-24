#!/bin/sh
# pgAdmin 전용 DB 역할. PgBouncer의 pgAdmin 풀(세션 모드, 연결 상한)로만 접속한다.
# 데이터 읽기·쓰기와 모니터링은 되지만 스키마(DDL)는 소유자(POSTGRES_USER)만 바꾼다.
# postgres 이미지는 데이터 디렉터리가 비어 있을 때(첫 기동)만 이 스크립트를 실행한다.
set -eu
: "${PGADMIN_DB_USER:=pgadmin}"
: "${PGADMIN_DB_PASSWORD:?PGADMIN_DB_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v role="$PGADMIN_DB_USER" -v pw="$PGADMIN_DB_PASSWORD" -v db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"role" LOGIN PASSWORD :'pw' CONNECTION LIMIT 5;
GRANT CONNECT ON DATABASE :"db" TO :"role";
GRANT pg_read_all_data, pg_write_all_data, pg_monitor TO :"role";
SQL
