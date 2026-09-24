#!/bin/sh
# 바뀐 파일로 CI가 검사할 영역(backend / frontend / stack)을 정해 $GITHUB_OUTPUT에 쓴다.
#
# 입력(환경 변수)
#   EVENT  github.event_name
#   BASE   비교 기준 커밋(PR: base 브랜치, push: 푸시 전 커밋). 없거나 0000…이면 전체 검사.
#   HEAD   검사할 커밋
# 규칙
#   - 수동 실행, 기준 커밋을 알 수 없음(새 브랜치 첫 푸시·강제 푸시로 사라진 커밋) → 전체 검사
#   - .github/ 아래(CI 정의 자체)가 바뀌면 → 전체 검사
set -eu

out="${GITHUB_OUTPUT:-/dev/stdout}"
all=false

if [ "${EVENT:-}" = "workflow_dispatch" ] || [ -z "${BASE:-}" ] \
  || [ "$BASE" = "0000000000000000000000000000000000000000" ] \
  || ! git cat-file -e "${BASE}^{commit}" 2>/dev/null; then
  all=true
  files=""
else
  # 세 점(...): 기준과의 공통 조상 이후 HEAD 쪽에서 바뀐 파일(PR의 "Files changed"와 같음)
  files=$(git diff --name-only "${BASE}...${HEAD}")
fi

if printf '%s\n' "$files" | grep -q '^\.github/'; then
  all=true
fi

changed() { # 인자: 확장 정규식. 하나라도 맞으면 true
  if [ "$all" = true ] || printf '%s\n' "$files" | grep -Eq "$1"; then echo true; else echo false; fi
}

backend=$(changed '^(backend|infra)/')
frontend=$(changed '^frontend/')
stack=$(changed '^(backend|frontend|infra)/|^docker-compose\.yml$|^\.env\.example$')

{
  echo "backend=$backend"
  echo "frontend=$frontend"
  echo "stack=$stack"
} >> "$out"

echo "all=$all backend=$backend frontend=$frontend stack=$stack"
printf '%s\n' "$files" | sed -n '1,50p'
