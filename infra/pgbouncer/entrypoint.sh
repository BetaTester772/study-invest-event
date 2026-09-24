#!/bin/sh
# PgBouncer 설정을 환경 변수로 만들어 실행한다. 연결 예산은 docs/dev/db-pools.md 참고.
set -eu

: "${DB_HOST:=db}"
: "${DB_PORT:=5432}"
: "${DB_NAME:=study_invest}"
: "${DB_USER:?DB_USER is required}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"
: "${PGADMIN_DB_USER:=pgadmin}"
: "${PGADMIN_DB_PASSWORD:?PGADMIN_DB_PASSWORD is required}"
: "${API_POOL_SIZE:=20}"
: "${API_RESERVE_POOL:=5}"
: "${BATCH_POOL_SIZE:=2}"
: "${PGADMIN_POOL_SIZE:=5}"
: "${LISTEN_PORT:=6432}"
: "${CONFIG_DIR:=/tmp/pgbouncer}"

mkdir -p "$CONFIG_DIR"
umask 077

# userlist: "사용자" "비밀번호" (큰따옴표는 두 번 써서 이스케이프)
quote() { printf '"%s"' "$(printf '%s' "$1" | sed 's/"/""/g')"; }
{
  printf '%s %s\n' "$(quote "$DB_USER")" "$(quote "$DB_PASSWORD")"
  printf '%s %s\n' "$(quote "$PGADMIN_DB_USER")" "$(quote "$PGADMIN_DB_PASSWORD")"
} > "$CONFIG_DIR/userlist.txt"

API_MAX=$((API_POOL_SIZE + API_RESERVE_POOL))

# 연결 예산 검사: 풀 합계가 PostgreSQL max_connections를 넘으면 시작하지 않는다(운영 중 고갈 방지).
: "${PG_MAX_CONNECTIONS:=50}"
: "${PG_SUPERUSER_RESERVED:=3}"
: "${MIGRATION_CONNECTIONS:=1}"
BUDGET=$((API_MAX + BATCH_POOL_SIZE + PGADMIN_POOL_SIZE + MIGRATION_CONNECTIONS + PG_SUPERUSER_RESERVED))
if [ "$BUDGET" -gt "$PG_MAX_CONNECTIONS" ]; then
  echo "connection budget exceeded: api $API_MAX + batch $BATCH_POOL_SIZE + pgadmin $PGADMIN_POOL_SIZE" \
       "+ migration $MIGRATION_CONNECTIONS + superuser $PG_SUPERUSER_RESERVED = $BUDGET > max_connections $PG_MAX_CONNECTIONS" >&2
  exit 1
fi
echo "connection budget: $BUDGET / $PG_MAX_CONNECTIONS (api $API_MAX, batch $BATCH_POOL_SIZE, pgadmin $PGADMIN_POOL_SIZE)"
server="host=$DB_HOST port=$DB_PORT dbname=$DB_NAME"

cat > "$CONFIG_DIR/pgbouncer.ini" <<INI
[databases]
; ── 앱 풀 (사용자 $DB_USER) ─────────────────────────────────────────────
; 별칭을 실제 DB 이름($DB_NAME)과 다르게 둔다. pgAdmin이 실제 DB 이름으로 접속하면 아래 와일드카드
; (pgAdmin 풀)로 가므로, 앱 풀의 연결 상한(max_db_connections)을 절대 나눠 쓰지 않는다.
; api: HTTP 요청. 앱 쪽 SQLAlchemy 풀(STUDY_INVEST_API_POOL_SIZE)과 같은 크기.
study_invest_api   = $server pool_mode=transaction pool_size=$API_POOL_SIZE reserve_pool=$API_RESERVE_POOL max_db_connections=$API_MAX
; batch: 09:00 공시·18:00 정산 전용. api가 가득 차도 배치는 막히지 않는다.
study_invest_batch = $server pool_mode=transaction pool_size=$BATCH_POOL_SIZE max_db_connections=$BATCH_POOL_SIZE
; ── pgAdmin 풀 ────────────────────────────────────────────────────────
; pgAdmin은 사용자 $PGADMIN_DB_USER로 어느 DB든 접속한다. (DB, 사용자)마다 풀이 따로 생기므로
; DB별 풀 크기를 pgAdmin 상한과 같게 두고, 모든 DB 합계는 [users]의 max_user_connections로 막는다.
* = host=$DB_HOST port=$DB_PORT pool_size=$PGADMIN_POOL_SIZE

[users]
; pgAdmin 전용 풀: 세션 모드, 서버 연결 최대 $PGADMIN_POOL_SIZE개(모든 DB 합계).
$PGADMIN_DB_USER = pool_mode=session max_user_connections=$PGADMIN_POOL_SIZE

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = $LISTEN_PORT
unix_socket_dir =
auth_type = scram-sha-256
auth_file = $CONFIG_DIR/userlist.txt
admin_users = $DB_USER
stats_users = $DB_USER, $PGADMIN_DB_USER

pool_mode = transaction
default_pool_size = 2
reserve_pool_timeout = 3
max_client_conn = 500
; 서버 연결을 기다리는 클라이언트는 15초 뒤 오류(앱은 503으로 응답)
query_wait_timeout = 15
server_idle_timeout = 600
server_lifetime = 3600
server_reset_query = DISCARD ALL
; 앱은 서버측 prepared statement를 쓰지 않는다(prepare_threshold=None).
max_prepared_statements = 0
ignore_startup_parameters = extra_float_digits,options
log_connections = 0
log_disconnections = 0
INI

exec pgbouncer "$CONFIG_DIR/pgbouncer.ini"
