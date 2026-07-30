#!/usr/bin/env bash
# verify.sh — 프로젝트 스택 감지 후 테스트·타입체크·린트·빌드를 자동 실행.
# "완료/done 선언 전 증거" 자동화(coding-quality 검증 매트릭스). 설치된 도구만 돌린다.
# 사용: bash ~/main/system/verify.sh [경로]   (기본 = 현재 디렉터리)
set -uo pipefail
cd "${1:-.}" || exit 1
fail=0
checks=0
run(){
  local label="$1"
  shift
  checks=$((checks + 1))
  echo "▶ $label"
  if "$@" 2>&1 | tail -3; then
    echo "  ok"
  else
    echo "  FAIL"
    fail=1
  fi
}

echo "== verify: $(pwd) =="

# Node / TypeScript
if [ -f package.json ]; then
  [ -f tsconfig.json ] && [ -x node_modules/.bin/tsc ] && run "tsc 타입체크" ./node_modules/.bin/tsc --noEmit
  grep -q '"lint"' package.json  && run "lint"  npm run -s lint
  grep -q '"test"' package.json  && run "test"  npm test --silent
  grep -q '"build"' package.json && run "build" npm run -s build
fi

# Python
if find . -maxdepth 2 -type f -name '*.py' -print -quit | grep -q . || [ -f pyproject.toml ] || [ -f requirements.txt ]; then
  command -v python3 >/dev/null && run "python compile" python3 -m compileall -q .
  command -v ruff   >/dev/null && run "ruff"   ruff check .
  command -v pyright>/dev/null && run "pyright" pyright
  command -v mypy   >/dev/null && run "mypy"   mypy .
  command -v pytest >/dev/null && run "pytest" pytest -q
fi

# Rust / Go (있으면)
[ -f Cargo.toml ] && command -v cargo >/dev/null && { run "cargo test" cargo test -q; run "clippy" cargo clippy -q; }
[ -f go.mod ]     && command -v go    >/dev/null && { run "go test" go test ./...; run "go vet" go vet ./...; }

if [ "$checks" -eq 0 ]; then
  echo "== NOT_VERIFIED (실행 가능한 check 0개) =="
  exit 2
fi

if [ "$fail" -eq 0 ]; then
  echo "== PASS ($checks checks) =="
else
  echo "== FAIL ($checks checks; 위 FAIL 처리) =="
fi
exit "$fail"
