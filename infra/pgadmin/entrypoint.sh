#!/bin/sh
# pgAdmin 서버 등록(servers.json)을 환경 변수로 만든 뒤 원래 엔트리포인트를 실행한다.
# 연결은 PgBouncer의 pgAdmin 전용 풀(사용자 $PGADMIN_DB_USER, 세션 모드, 최대 5연결)로 간다.
set -eu
: "${POSTGRES_DB:=study_invest}"
: "${PGADMIN_DB_USER:=pgadmin}"
cat > /tmp/servers.json <<JSON
{
  "Servers": {
    "1": {
      "Name": "study_invest (pgAdmin 풀)",
      "Group": "공부장려 모의투자",
      "Host": "pgbouncer",
      "Port": 6432,
      "MaintenanceDB": "$POSTGRES_DB",
      "Username": "$PGADMIN_DB_USER",
      "SSLMode": "disable",
      "Comment": "PgBouncer pgAdmin 전용 풀: 세션 모드, 서버 연결 최대 5개. 앱 풀과 분리됨."
    }
  }
}
JSON
export PGADMIN_SERVER_JSON_FILE=/tmp/servers.json
exec /entrypoint.sh "$@"
