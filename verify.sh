#!/usr/bin/env bash
# verify.sh — 프로젝트 스택 감지 후 테스트·타입체크·린트·빌드를 자동 실행.
# "완료/done 선언 전 증거" 자동화(coding-quality 검증 매트릭스). 설치된 도구만 돌린다.
# 사용: bash ~/main/system/verify.sh [경로]   (기본 = 현재 디렉터리)
set -uo pipefail
cd "${1:-.}" || exit 1
fail=0
checks=0
tests_ran=0
run(){
  local label="$1"
  shift
  checks=$((checks + 1))
  case "$label" in test|pytest|"cargo test"|"go test") tests_ran=$((tests_ran + 1));; esac
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
  if command -v pytest >/dev/null; then
    run "pytest" pytest -q
  else
    # pytest 부재 시 unittest 폴백 (2026-07-30): 이 머신 컨벤션(*_test.py 직접 실행)도 테스트로 집계
    tfiles=$(find . -maxdepth 3 -type f \( -name '*_test.py' -o -name 'test_*.py' \) -not -path './.git/*' -not -path './node_modules/*' | sort | head -40 | tr '\n' ' ')
    if [ -n "${tfiles// /}" ]; then
      run "test" bash -c 'rc=0; for f in '"$tfiles"'; do python3 "$f" >/dev/null 2>&1 || { echo "  FAIL: $f"; rc=1; }; done; exit $rc'
    fi
  fi
fi

# Rust / Go (있으면)
[ -f Cargo.toml ] && command -v cargo >/dev/null && { run "cargo test" cargo test -q; run "clippy" cargo clippy -q; }
[ -f go.mod ]     && command -v go    >/dev/null && { run "go test" go test ./...; run "go vet" go vet ./...; }

# TEST_GAP·TEST_WEAKENED 검사 (2026-07-30, 테스트 소유권 1a+A①): 결정론 경고 계열.
# 경고만 한다(비치명) — "테스트-선행" 자체는 증명 못 하지만, 나쁜 패턴은 결정론으로 잡는다.
TESTPAT='(^|/)tests?/|(^|/)__tests__/|(^|/)spec/|\.test\.|\.spec\.|_test\.|(^|/)test_'
HOOKLOG="$HOME/main/logs/hook-activations.tsv"
warnlog(){ printf '%s\t%s\t%s\n' "$(date +%F_%T)" "$1" "$(pwd)" >> "$HOOKLOG" 2>/dev/null || :; }
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  changed=$( { git diff --name-only HEAD -- 2>/dev/null; git diff --name-only --cached -- 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$' || true)
  if [ -n "$changed" ]; then
    srcish=$(printf '%s\n' "$changed" | grep -E '\.(py|ts|tsx|js|jsx|mjs|go|rs|sh|rb|java|c|cc|cpp|h)$' || true)
    src=$(printf '%s\n' "$srcish" | grep -vE "$TESTPAT" || true)
    tst=$(printf '%s\n' "$srcish" | grep -E "$TESTPAT" || true)
    if [ -n "$src" ] && [ -z "$tst" ]; then
      echo "⚠ TEST_GAP — 소스 변경 $(printf '%s\n' "$src" | wc -l)개, 테스트 변경 0개 (테스트-선행 규율 확인 필요)"
      warnlog TEST_GAP
    fi
    # 테스트 약화 감지 (A①): 테스트 파일에서 삭제>추가, 또는 skip 마커 추가 = writer 권한 밖 (worker-contract)
    if [ -n "$tst" ]; then
      numstat=$(git diff HEAD --numstat -- $(printf '%s\n' "$tst" | tr '\n' ' ') 2>/dev/null || true)
      t_add=$(printf '%s\n' "$numstat" | awk '{a+=$1} END{print a+0}')
      t_del=$(printf '%s\n' "$numstat" | awk '{d+=$2} END{print d+0}')
      if [ "$t_del" -gt "$t_add" ]; then
        echo "⚠ TEST_WEAKENED — 테스트 파일 삭제 ${t_del}줄 > 추가 ${t_add}줄 (테스트 축소는 승인 사항 — worker-contract)"
        warnlog TEST_WEAKENED_SHRINK
      fi
      skips=$(git diff HEAD -- $(printf '%s\n' "$tst" | tr '\n' ' ') 2>/dev/null | grep -cE '^\+.*(@pytest\.mark\.skip|@unittest\.skip|pytest\.xfail|\.skip\(|\.only\(|xit\(|xdescribe\(|t\.Skip\()' || true)
      if [ "${skips:-0}" -gt 0 ]; then
        echo "⚠ TEST_WEAKENED — skip/only 마커 ${skips}건 추가 (테스트 비활성화는 승인 사항)"
        warnlog TEST_WEAKENED_SKIP
      fi
    fi
  fi
fi

if [ "$checks" -eq 0 ]; then
  echo "== NOT_VERIFIED (실행 가능한 check 0개) =="
  exit 2
fi

# NO_TESTS 표시 (redteam#2): lint/build만 돈 PASS는 테스트 0을 숨긴다 — 명시 표기.
if [ "$tests_ran" -eq 0 ]; then
  echo "⚠ NO_TESTS — 테스트 러너 0개 실행 (아래 판정은 lint/타입체크/빌드만의 결과다)"
  warnlog NO_TESTS
  if [ "${VERIFY_REQUIRE_TESTS:-0}" = "1" ]; then
    echo "== NO_TESTS (VERIFY_REQUIRE_TESTS=1 — 테스트 없이는 통과 불가) =="
    exit 3
  fi
fi

if [ "$fail" -eq 0 ]; then
  echo "== PASS ($checks checks) =="
else
  echo "== FAIL ($checks checks; 위 FAIL 처리) =="
fi
exit "$fail"
