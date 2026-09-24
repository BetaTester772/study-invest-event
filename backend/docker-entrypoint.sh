#!/bin/sh
# DB 마이그레이션을 적용한 뒤 명령을 실행한다.
set -e
if [ "${STUDY_INVEST_MIGRATE:-1}" = "1" ]; then
  alembic upgrade head
fi
exec "$@"
