#!/usr/bin/env bash
# nightly-health.sh — 값 싼 결정론 야간 헬스체크 (자율 Layer 3-1, Claude 토큰 0)
#
# 실행: doctor.py · guardrail_test.py · sloplint_test.sh(있으면) · memory-snapshot 미러 drift.
# 결과는 $COMMAND_CENTER/logs/health.log 에 타임스탬프 append (기본 ~/main/logs/health.log).
# 전부 PASS → 침묵(exit 0 · stdout 없음). 하나라도 FAIL → stderr 요약 1줄 + exit 1.
# 등록은 사용자가 crontab -e 로 직접 — 자동 등록 없음 (파일 끝 예시줄 참조).
set -u

CC="${COMMAND_CENTER:-$HOME/main}"
LOG="$CC/logs/health.log"
mkdir -p "$(dirname "$LOG")"

# cron 환경엔 nvm PATH가 없다 — node 미발견 시 최신 nvm node bin을 보강 (sloplint용)
if ! command -v node >/dev/null 2>&1; then
  NVM_BIN=$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)
  [ -n "${NVM_BIN:-}" ] && PATH="$PATH:$NVM_BIN"
fi

# 로테이션: 512KB 초과 시 최근 2000줄만 보존 (guardrail.py 패턴)
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 512000 ]; then
  tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

TS() { date '+%Y-%m-%d %H:%M:%S'; }
FAILED=()
BUF=""

record() { BUF+="[$(TS)] $1"$'\n'; }

check() { # <name> <rc(0=pass)> [detail-on-fail]
  local name="$1" rc="$2" detail="${3:-}"
  if [ "$rc" -eq 0 ]; then
    record "$name: PASS"
  else
    record "$name: FAIL (rc=$rc)"
    [ -n "$detail" ] && BUF+="$(printf '%s\n' "$detail" | tail -n 15 | sed 's/^/    /')"$'\n'
    FAILED+=("$name")
  fi
}

# 1. doctor.py — 항상 exit 0이므로 출력으로 판정("PASS 이상 없음" 없으면 FAIL)
out=$(python3 "$CC/system/doctor.py" 2>&1); rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "PASS 이상 없음"; then
  check doctor 0
else
  check doctor 1 "$out"
fi

# 2. guardrail_test.py — exit code로 판정
out=$(python3 "$CC/system/guardrail_test.py" 2>&1); check guardrail_test $? "$out"

# 3. sloplint_test.sh — 있으면 실행, 없으면 SKIP(실패 아님)
SLOP="$HOME/.claude/tools/headless/sloplint_test.sh"
if [ -f "$SLOP" ]; then
  out=$(bash "$SLOP" 2>&1); check sloplint_test $? "$out"
else
  record "sloplint_test: SKIP (없음)"
fi

# 4. memory-snapshot 미러 drift — 미커밋 변경 = drift (doctor의 mirror durability와 상보)
out=$(git -C "$CC" status --porcelain -- system/memory-snapshot 2>&1); rc=$?
if [ $rc -ne 0 ]; then
  check mirror_drift 1 "$out"
elif [ -n "$out" ]; then
  check mirror_drift 1 "미커밋 변경 $(printf '%s\n' "$out" | wc -l)건:"$'\n'"$out"
else
  check mirror_drift 0
fi

# 5. netcheck — WSL 네트워크 회귀 게이트 (두더지 매트릭스 기계검증, 2026-07-07). 없으면 SKIP.
NETCHECK="$CC/system/netcheck.sh"
if [ -f "$NETCHECK" ]; then
  out=$(bash "$NETCHECK" 2>&1); check netcheck $? "$out"
else
  record "netcheck: SKIP (없음)"
fi

# 6. 트렌드-레이더 (2026-07-03 엔지니어 벤치마크 채택) — 신 Claude Code 버전 감지.
#    "한 번 caught up" → "계속 caught up". FAIL 아님(정상): 버전 바뀌면 heads-up만.
VSTATE="$CC/system/.cc-version-seen"
CUR_VER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$CUR_VER" ]; then
  SEEN=$(cat "$VSTATE" 2>/dev/null || echo "")
  if [ "$CUR_VER" != "$SEEN" ] && [ -n "$SEEN" ]; then
    record "TREND: Claude Code $SEEN → $CUR_VER (신기능 확인: code.claude.com/docs/en/whats-new)"
    NEW_VER_MSG="ℹ️ Claude Code 신버전 $CUR_VER (was $SEEN) — whats-new 확인 권장"
  fi
  printf '%s' "$CUR_VER" > "$VSTATE" 2>/dev/null || true
fi

# 결과: 전부 PASS → 로그만 남기고 침묵(단 신버전이면 heads-up) / 하나라도 FAIL → stderr 요약 + exit 1
if [ ${#FAILED[@]} -eq 0 ]; then
  record "RESULT: PASS"
  printf '%s\n' "${BUF%$'\n'}" >> "$LOG"
  [ -n "${NEW_VER_MSG:-}" ] && echo "$NEW_VER_MSG" >&2   # 건강하지만 신버전 heads-up(exit는 0 유지)
  exit 0
else
  record "RESULT: FAIL (${FAILED[*]})"
  printf '%s\n' "${BUF%$'\n'}" >> "$LOG"
  echo "nightly-health FAIL: ${FAILED[*]} — 상세: $LOG" >&2
  exit 1
fi

# ── crontab 등록 예시 (사용자가 crontab -e 로 직접 — 자동 등록 금지) ──
# 매일 새벽 3시: 0 3 * * * /home/click/main/system/nightly-health.sh
