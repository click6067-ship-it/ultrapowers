#!/usr/bin/env bash
# netcheck.sh — WSL 네트워크 회귀 게이트 (결정론, Claude 토큰 0)
#
# 목적: 네트워크 관련 변경(.wslconfig·방화벽·보안SW 설치/제거·WSL 업데이트) 후
#       "고침이 뭘 새로 부쉈는지"를 즉시 드러낸다. 두더지잡기 방지 장치 —
#       역대 두더지 전수 매트릭스(메모리 localhost-root-causes)의 기계 검증판.
# 검사: ①WSL 루프백 ②Windows 브라우저길(curl.exe localhost/127.0.0.1)
#       ③DNS×10 ④TLS 스트림+1MB ⑤portproxy 잔재 ⑥경로 MTU  (+모드·설정 리포트)
# 결과: ~/main/logs/netcheck.log append. 전부 PASS → 침묵·exit 0 / FAIL → stderr 1줄·exit 1.
# ⚠️ 반드시 실제 netns에서 실행(사용자 터미널·cron·sandbox-off Bash) —
#    Claude 샌드박스 Bash는 별도 netns라 전 항목 가짜 FAIL 난다.
set -u

CC="${COMMAND_CENTER:-$HOME/main}"
LOG="$CC/logs/netcheck.log"
mkdir -p "$(dirname "$LOG")"

# 로테이션: 512KB 초과 시 최근 2000줄만 보존 (nightly-health 패턴)
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
    [ -n "$detail" ] && BUF+="$(printf '%s\n' "$detail" | tail -n 10 | sed 's/^/    /')"$'\n'
    FAILED+=("$name")
  fi
}

# Windows interop 바이너리 (cron PATH에 /mnt/c 없을 수 있음 — 절대경로 폴백)
WINCURL=$(command -v curl.exe || { [ -x /mnt/c/Windows/System32/curl.exe ] && echo /mnt/c/Windows/System32/curl.exe; } || true)
WINNETSH=$(command -v netsh.exe || { [ -x /mnt/c/Windows/System32/netsh.exe ] && echo /mnt/c/Windows/System32/netsh.exe; } || true)

# ── 0. 모드·설정 리포트 (판정 아님 — FAIL 시 맥락용) ──
WSLCONF="/mnt/c/Users/click/.wslconfig"
MODE=$(grep -iE '^\s*networkingMode' "$WSLCONF" 2>/dev/null | cut -d= -f2 | tr -d ' \r')
IDLE=$(grep -iE '^\s*vmIdleTimeout' "$WSLCONF" 2>/dev/null | cut -d= -f2 | tr -d ' \r')
record "MODE: networkingMode=${MODE:-NAT(기본)} vmIdleTimeout=${IDLE:-미설정} uptime=$(awk '{printf "%.0fm",$1/60}' /proc/uptime)"

# ── 1. WSL 루프백: 테스트 서버 스핀업 → 127.0.0.1 ──
SRV=""
cleanup_server() {
  [ -n "$SRV" ] || return 0
  kill "$SRV" 2>/dev/null
  wait "$SRV" 2>/dev/null
  SRV=""
}
trap cleanup_server EXIT

PORT=""
for p in 18930 18931 18932 18933; do
  ss -tlnH 2>/dev/null | grep -q ":$p\b" || { PORT=$p; break; }
done
if [ -z "$PORT" ]; then
  check loopback_server 1 "테스트 포트 18930-18933 전부 사용중"
else
  python3 -m http.server "$PORT" --bind 127.0.0.1 --directory /tmp >/dev/null 2>&1 &
  SRV=$!
  curl -s --retry 10 --retry-connrefused --retry-delay 1 --max-time 2 -o /dev/null "http://127.0.0.1:$PORT"
  out=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT" 2>&1)
  [ "$out" = "200" ]; check loopback_wsl $? "WSL내 127.0.0.1:$PORT → $out"

  # ── 2. Windows 브라우저길 (역대 두더지 #4 localhost 차단의 회귀 검증) ──
  if [ -n "$WINCURL" ]; then
    o1=$("$WINCURL" -s -o NUL -w '%{http_code}' --max-time 6 "http://localhost:$PORT" 2>&1)
    [ "$o1" = "200" ]; check win_localhost $? "WIN localhost:$PORT → $o1 (mirrored ::1 블랙홀 or 브라우저 표적 필터 의심)"
    o2=$("$WINCURL" -s -o NUL -w '%{http_code}' --max-time 6 "http://127.0.0.1:$PORT" 2>&1)
    [ "$o2" = "200" ]; check win_127 $? "WIN 127.0.0.1:$PORT → $o2"
  else
    record "win_localhost: SKIP (curl.exe interop 없음)"
  fi
  cleanup_server
fi

# ── 3. DNS ×10 (역대 두더지 #1 — dnsTunneling이 보완 중인지) ──
dnsfail=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  getent hosts api.anthropic.com >/dev/null 2>&1 || dnsfail=$((dnsfail+1))
done
[ "$dnsfail" -eq 0 ]; check dns_x10 $? "10회 중 $dnsfail회 실패 — NAT DNS 간헐실패 재발 신호(dnsTunneling 확인)"

# ── 4. TLS 스트림 + 1MB (역대 두더지 #2 socket-closed 프록시 지표) ──
tlsbad=""
for h in https://github.com https://registry.npmjs.org; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -I "$h" 2>&1)
  case "$code" in 2*|3*) ;; *) tlsbad+="$h→$code " ;; esac
done
dl=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://speed.cloudflare.com/__down?bytes=1000000" 2>&1)
[ "$dl" = "200" ] || tlsbad+="1MB다운로드→$dl "
[ -z "$tlsbad" ]; check tls_stream $? "$tlsbad — socket-closed 계열 재발 신호(다음 카드: wsl --update → MTU 클램프, mirrored 복귀 금지)"

# ── 5. portproxy 잔재 (역대 두더지 실증 원인 — 7/6 :3000 무한행) ──
if [ -n "$WINNETSH" ]; then
  pp=$("$WINNETSH" interface portproxy show all 2>/dev/null | tr -d '\r' | grep -E '^[0-9*]' || true)
  [ -z "$pp" ]; check portproxy_stale $? "잔재 규칙 발견(iphlpsvc가 죽은 타깃으로 포워딩 — elevated delete 필요):"$'\n'"$pp"
else
  record "portproxy_stale: SKIP (netsh.exe interop 없음)"
fi

# ── 6. 경로 MTU (socket-closed 대비 기준선 — 1472 페이로드 = MTU 1500) ──
ping -c1 -M do -s 1472 -W2 1.1.1.1 >/dev/null 2>&1
check mtu_1500 $? "경로 MTU 1500 미통과 — TLS reset 유발 가능(클램프 검토: ip link set eth0 mtu 1400)"

# ── 결과 ──
if [ ${#FAILED[@]} -eq 0 ]; then
  record "RESULT: PASS"
  printf '%s\n' "${BUF%$'\n'}" >> "$LOG"
  exit 0
else
  record "RESULT: FAIL (${FAILED[*]})"
  printf '%s\n' "${BUF%$'\n'}" >> "$LOG"
  echo "netcheck FAIL: ${FAILED[*]} — 상세: $LOG (두더지 매트릭스: 메모리 localhost-root-causes)" >&2
  exit 1
fi

# ── 사용법 ──
# 수동:   bash ~/main/system/netcheck.sh && echo OK   (네트워크 변경 후 즉시)
# 야간:   nightly-health.sh가 있으면 자동 호출 (섹션 통합됨)
