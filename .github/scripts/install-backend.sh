#!/bin/sh
# backend/uv.lock에 고정된 버전 그대로 현재 파이썬 환경에 백엔드와 개발 도구를 설치한다.
# backend/Dockerfile과 같은 방식: uv는 lock을 해시가 붙은 pip 설치 목록으로 옮기는 데만 쓴다.
# lock이 pyproject.toml과 맞지 않으면(의존성을 바꾸고 uv lock을 빠뜨림) 실패한다.
set -eu
cd "$(dirname "$0")/../../backend"

python -m pip install --quiet "uv>=0.8"
req="${RUNNER_TEMP:-/tmp}/backend-requirements.txt"
uv export --locked --no-emit-project --format requirements-txt --extra dev -o "$req"
python -m pip install --require-hashes --no-deps -r "$req"
python -m pip install --no-deps -e .
python -m pip check
