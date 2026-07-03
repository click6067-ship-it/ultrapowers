#!/usr/bin/env bash
# autopilot.sh — 자율 오케스트레이션 하네스 (루프 밖 안전 셸).
#
# 계약 정본: ~/main/council/2026-07-03_autonomous-orchestration/autopilot-design.md +
#            autopilot-realloop-design.md (실 연결 계약 v2 · Codex 하드닝 8항목).
# 이 파일의 목표 = 계약의 Invariants·Kill conditions를 **코드로** 강제하고 Acceptance tests를 통과시키는 것.
#
# 스텝 구동 (driver_produce_action) — 3경로, 우선순위 순:
#   (1) AUTOPILOT_STEP_HOOK  : 측정가능 드라이버(테스트/드라이런). CMD/TOKENS/USD 를 emit.
#   (2) --real / AUTOPILOT_REAL=1 : 실 LLM 루프. 매 스텝 = `claude -p` 1회(fresh 헤드리스). 격리 플래그
#        (--bare --no-session-persistence --disable-slash-commands --strict-mcp-config)로 spawn,
#        자식 툴은 --tools/--disallowedTools 로 제한, Bash-ledger-우회는 PATH shim + post-step 스캔으로 차단,
#        usage/total_cost_usd 파싱 → ledger 대조. usage 없으면 exit 4(fail-closed).
#   (3) 둘 다 없음 : return 77 → exit 4 (측정 불가 fail-closed, invariant 1).
#
# 무장식(기본 OFF): --arm(또는 AUTOPILOT_ARMED=1) 없이는 아무 동작도 하지 않는다(inert, 부작용 0).
# 실 LLM 루프도 opt-in: --real 없이는 실 provider 호출 안 함(설치돼 있어도) — 사고성 과금 방지.
# 브랜치 전용: 대상 repo가 main/master면 즉시 거부. remote write 없음(--pr는 이번 빌드 스텁).
#
# 사용:
#   autopilot.sh --arm --repo <path> --branch <name> --objective "..." \
#     [--allowed-paths "a/**,b/**"] [--forbidden "network,secrets"] \
#     [--max-steps 15] [--budget-usd 2] [--per-step-usd 0.5] \
#     [--per-call-tokens 200000] [--wall-clock 90m] [--per-step-secs 1200] \
#     [--no-progress 3] [--verify "./verify.sh"] [--output summary.md] \
#     [--commit] [--pr] [--external-judge] \
#     [--real] [--model sonnet] [--judge-model haiku] \
#     [--claude-bin claude] [--child-settings <abs path to trusted settings.json>]
#
# 종료:
#   0  = inert(미무장) 또는 controlled stop(리밋/진전정지/게이트 — 설계대로 안전 정지)
#   2  = 사용법 오류
#   3  = 무장 거부: 대상 브랜치 main/master (branch guard)
#   4  = 무장 거부: 측정 불가 provider (fail-closed, invariant 1 — usage/cost 없음)
#
# stdout 마지막 줄(테스트/사람용 요약):
#   AUTOPILOT: inert (unarmed)
#   AUTOPILOT: refused reason=<r>
#   AUTOPILOT: stop_reason=<r> steps=<n> run_id=<id>

set -u

# ─────────────────────────────────────────────────────────────────────────────
# 0. 기본값 (보수적 — 측정 불가·모호 시 fail-closed)
# ─────────────────────────────────────────────────────────────────────────────
ARMED=0
REPO=""
BRANCH=""
OBJECTIVE=""
ALLOWED_PATHS=""
FORBIDDEN=""
VERIFY_CMD=""
OUTPUT="summary.md"
DO_COMMIT=0
DO_PR=0
EXTERNAL_JUDGE=0

# 실 LLM 루프 (opt-in — 기본 OFF, 설치돼 있어도 --real 없이는 호출 안 함)
REAL_MODE=0
GEN_MODEL="${AUTOPILOT_MODEL:-sonnet}"        # 생성자 = Sonnet (기계적 반복 루프 = 비용 티어링)
JUDGE_MODEL="${AUTOPILOT_JUDGE_MODEL:-haiku}" # 검증자 기본 = haiku (싸게)
CLAUDE_BIN="${AUTOPILOT_CLAUDE_BIN:-claude}"  # 실 provider 바이너리(테스트서 mock 주입)
CHILD_SETTINGS="${AUTOPILOT_CHILD_SETTINGS:-}" # repo 밖 trusted read-only settings(v2 #5, --settings 주입)

MAX_STEPS="${MAX_STEPS:-15}"
TOTAL_BUDGET_USD="${TOTAL_BUDGET_USD:-2}"
PER_STEP_USD="${PER_STEP_USD:-0.50}"
PER_CALL_TOKENS="${PER_CALL_TOKENS:-200000}"
WALL_CLOCK="${WALL_CLOCK:-90m}"
PER_STEP_SECS="${PER_STEP_SECS:-1200}"      # 단일 스텝 시간 상한(초) — 무한 명령 kill
NO_PROGRESS_LIMIT="${NO_PROGRESS_LIMIT:-3}" # 상태벡터 무변화 N회 → 정지
CPU_SECS="${CPU_SECS:-300}"                 # 스텝 명령 CPU 상한(ulimit -t)
FSIZE_BLOCKS="${FSIZE_BLOCKS:-200000}"      # 스텝 write 파일 크기 상한(ulimit -f, 512B blocks ≈ 100MB)
MAX_ARTIFACT_BYTES="${MAX_ARTIFACT_BYTES:-1048576}"  # commit 게이트: 큰 artifact deny (1MB)

CC="${COMMAND_CENTER:-$HOME/main}"

# ─────────────────────────────────────────────────────────────────────────────
# 1. 인자 파싱
# ─────────────────────────────────────────────────────────────────────────────
usage() { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//' | head -40; }

die_usage() { echo "autopilot: 사용법 오류: $1" >&2; echo "AUTOPILOT: refused reason=usage" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --arm) ARMED=1 ;;
    --repo) REPO="${2:-}"; shift ;;
    --branch) BRANCH="${2:-}"; shift ;;
    --objective) OBJECTIVE="${2:-}"; shift ;;
    --allowed-paths) ALLOWED_PATHS="${2:-}"; shift ;;
    --forbidden) FORBIDDEN="${2:-}"; shift ;;
    --verify) VERIFY_CMD="${2:-}"; shift ;;
    --output) OUTPUT="${2:-}"; shift ;;
    --commit) DO_COMMIT=1 ;;
    --pr) DO_PR=1 ;;
    --external-judge) EXTERNAL_JUDGE=1 ;;
    --real) REAL_MODE=1 ;;
    --model) GEN_MODEL="${2:-}"; shift ;;
    --judge-model) JUDGE_MODEL="${2:-}"; shift ;;
    --claude-bin) CLAUDE_BIN="${2:-}"; shift ;;
    --child-settings) CHILD_SETTINGS="${2:-}"; shift ;;
    --max-steps) MAX_STEPS="${2:-}"; shift ;;
    --budget-usd) TOTAL_BUDGET_USD="${2:-}"; shift ;;
    --per-step-usd) PER_STEP_USD="${2:-}"; shift ;;
    --per-call-tokens) PER_CALL_TOKENS="${2:-}"; shift ;;
    --wall-clock) WALL_CLOCK="${2:-}"; shift ;;
    --per-step-secs) PER_STEP_SECS="${2:-}"; shift ;;
    --no-progress) NO_PROGRESS_LIMIT="${2:-}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die_usage "알 수 없는 인자: $1" ;;
  esac
  shift
done

# ─────────────────────────────────────────────────────────────────────────────
# 2. 무장 게이트 — 미무장(기본)이면 부작용 0으로 즉시 종료 (Acceptance: 미무장→아무 동작 없음)
#    (mkdir·로그·git 조회 등 어떤 side effect 보다 앞. 코드로 보장.)
# ─────────────────────────────────────────────────────────────────────────────
if [ "${AUTOPILOT_ARMED:-0}" = "1" ]; then ARMED=1; fi
if [ "${AUTOPILOT_REAL:-0}" = "1" ]; then REAL_MODE=1; fi
if [ "$ARMED" != "1" ]; then
  echo "AUTOPILOT: inert (unarmed)"
  echo "  자율 실행은 기본 OFF. 무장하려면 --arm (또는 AUTOPILOT_ARMED=1) + 봉투(objective/branch/limits)." >&2
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. 숫자 헬퍼 + duration 파서
# ─────────────────────────────────────────────────────────────────────────────
is_num() { [[ "$1" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; }
fadd() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.6f", a+b}'; }
fgt()  { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a>b)}'; }   # exit 0 (true) iff a>b

parse_duration() { # 90m/1h/5400s/5400 → 초
  local d="$1"
  case "$d" in
    *h) awk -v n="${d%h}" 'BEGIN{printf "%d", n*3600}' ;;
    *m) awk -v n="${d%m}" 'BEGIN{printf "%d", n*60}' ;;
    *s) printf '%d' "${d%s}" ;;
    *)  printf '%d' "$d" ;;
  esac
}

for v in MAX_STEPS PER_CALL_TOKENS PER_STEP_SECS NO_PROGRESS_LIMIT CPU_SECS FSIZE_BLOCKS MAX_ARTIFACT_BYTES; do
  is_num "${!v}" || die_usage "$v 는 숫자여야 함: ${!v}"
done
for v in TOTAL_BUDGET_USD PER_STEP_USD; do
  is_num "${!v}" || die_usage "$v 는 숫자여야 함: ${!v}"
done
WALL_CLOCK_SECS=$(parse_duration "$WALL_CLOCK")
is_num "$WALL_CLOCK_SECS" || die_usage "wall-clock 파싱 실패: $WALL_CLOCK"

# ─────────────────────────────────────────────────────────────────────────────
# 4. repo·브랜치 검증 (무장했으니 이제 side effect 허용)
# ─────────────────────────────────────────────────────────────────────────────
[ -n "$REPO" ] || die_usage "--repo 필수"
[ -d "$REPO" ] || die_usage "--repo 경로 없음: $REPO"
if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die_usage "--repo 는 git 워크트리여야 함: $REPO"
fi
REPO_REAL="$(realpath "$REPO")"
CUR_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)"
BASE_COMMIT="$(git -C "$REPO" rev-parse HEAD 2>/dev/null)"   # judge diff 기준(base..working tree)

RUN_ID="$(date +%Y%m%d-%H%M%S)-$$-${RANDOM}"
RUN_DIR="$CC/logs/autopilot/$RUN_ID"
EVENTS="$CC/logs/autopilot/events.jsonl"
mkdir -p "$RUN_DIR" || { echo "autopilot: 로그 디렉터리 생성 실패" >&2; exit 2; }

# 실 LLM 루프 격리 자산(real mode에서만 실제 채워짐; 아니면 inert)
SHIM_BIN="$RUN_DIR/shim-bin"          # PATH 앞 Bash-ledger-우회 차단 shim (v2 #3)
BYPASS_MARKER="$RUN_DIR/bypass.ledger" # shim이 차단 시 기록 → post-step 감지

# JSON 문자열 이스케이프 (외부 의존 없이 — 안전 하네스는 python hiccup에도 견뎌야 함)
json_escape() {
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}; s=${s//$'\t'/\\t}; s=${s//$'\r'/\\r}
  printf '%s' "$s"
}

STEP=0
emit_event() { # <type> [k v ...]  — append-only events.jsonl (canonical 영속상태, invariant 6)
  local type="$1"; shift
  local line
  line="{\"ts\":$(date +%s),\"run_id\":\"$(json_escape "$RUN_ID")\",\"step\":$STEP,\"type\":\"$(json_escape "$type")\""
  while [ $# -ge 2 ]; do
    local k="$1" val="$2"; shift 2
    if is_num "$val"; then line+=",\"$k\":$val"; else line+=",\"$k\":\"$(json_escape "$val")\""; fi
  done
  line+="}"
  # 로테이션: 1MB 초과 시 최근 5000줄 보존 (guardrail/subagent-log 패턴)
  if [ -f "$EVENTS" ] && [ "$(wc -c < "$EVENTS")" -gt 1048576 ]; then
    tail -n 5000 "$EVENTS" > "$EVENTS.tmp" 2>/dev/null && mv "$EVENTS.tmp" "$EVENTS"
  fi
  printf '%s\n' "$line" >> "$EVENTS"
}

# 브랜치 가드 — main/master면 즉시 거부 (Kill: git이 main/master 건드림 / Invariant 5)
case "$CUR_BRANCH" in
  main|master|HEAD)
    emit_event "refused" reason "branch_guard" branch "$CUR_BRANCH"
    echo "autopilot: 거부 — 대상 repo가 '$CUR_BRANCH'. 로컬 WIP 브랜치에서만 자율 실행 (main/master 금지)." >&2
    echo "AUTOPILOT: refused reason=branch_guard"
    exit 3 ;;
esac
# --branch 지정 시 현재 브랜치와 일치 요구 (엉뚱한 브랜치에서 도는 것 방지)
if [ -n "$BRANCH" ] && [ "$BRANCH" != "$CUR_BRANCH" ]; then
  emit_event "refused" reason "branch_mismatch" want "$BRANCH" have "$CUR_BRANCH"
  echo "autopilot: 거부 — 요청 브랜치 '$BRANCH' != 현재 '$CUR_BRANCH'. 체크아웃 후 재실행." >&2
  echo "AUTOPILOT: refused reason=branch_mismatch"
  exit 3
fi

emit_event "run_start" objective "$OBJECTIVE" repo "$REPO_REAL" branch "$CUR_BRANCH" \
  max_steps "$MAX_STEPS" budget_usd "$TOTAL_BUDGET_USD" per_step_usd "$PER_STEP_USD" \
  per_call_tokens "$PER_CALL_TOKENS" wall_clock_secs "$WALL_CLOCK_SECS" \
  per_step_secs "$PER_STEP_SECS" no_progress "$NO_PROGRESS_LIMIT" commit "$DO_COMMIT" pr "$DO_PR"

# ─────────────────────────────────────────────────────────────────────────────
# 5. 상태벡터 (진전-기반 정지 — dup hash 아님. Invariant 2)
#    HEAD · diffstat · 변경파일 목록 · failing-test signature 를 하나의 해시로.
# ─────────────────────────────────────────────────────────────────────────────
FAIL_SIG=""   # verify 실패 시그니처(있으면 상태에 반영)
state_vector() {
  local head diffstat changed
  head="$(git -C "$REPO" rev-parse HEAD 2>/dev/null)"
  diffstat="$(git -C "$REPO" diff --stat 2>/dev/null; git -C "$REPO" diff --cached --stat 2>/dev/null)"
  changed="$(git -C "$REPO" status --porcelain --untracked-files=all 2>/dev/null | sort)"
  printf '%s\n%s\n%s\n%s' "$head" "$diffstat" "$changed" "$FAIL_SIG" | sha1sum | awk '{print $1}'
}

hooks_fp() { # .git/hooks 는 git이 추적 안 함 → 별도 지문 (Invariant 4: .git/hooks 편집 탐지)
  find "$REPO/.git/hooks" -type f -exec sha1sum {} \; 2>/dev/null | sort
}

# 자식이 다음 스텝 guardrail/격리를 바꾸는 것 차단 (v2 #5). git이 무시(.gitignore)해도 잡히게 filesystem 지문.
# .claude/** · MCP config · agents/skills 변경 → 정지.
claude_config_fp() {
  { find "$REPO/.claude" -type f -exec sha1sum {} \; 2>/dev/null
    for f in "$REPO/.mcp.json" "$REPO/mcp.json" "$REPO/.claude.json"; do
      [ -f "$f" ] && sha1sum "$f" 2>/dev/null
    done
  } | sort
}

# 변경된(추적/미추적) 파일 목록
changed_files() {
  git -C "$REPO" status --porcelain --untracked-files=all 2>/dev/null \
    | sed 's/^...//' | sed 's/.* -> //'
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. 위험 분류 (pre-exec command 게이트). 매칭 시 risk class 문자열 반환, 아니면 빈 문자열.
#    denied ledger 로 집계 → 같은 class 2회면 정지 (Kill conditions).
# ─────────────────────────────────────────────────────────────────────────────
classify_risk() {
  local cmd="$1"
  # remote_write — 기본 remote write 없음. --pr 여도 이번 빌드는 스텁이라 실행 금지.
  if printf '%s' "$cmd" | grep -Eq '\bgit[[:space:]]+push\b|\bgh[[:space:]]+(pr|release|repo)\b|\bgit[[:space:]]+remote[[:space:]]+add\b'; then
    echo "remote_write"; return; fi
  # credential_access — .env/키/시크릿 읽기, env 덤프
  if printf '%s' "$cmd" | grep -Eq '(^|[[:space:]/])\.env($|[./[:space:]])|\.env\.[a-zA-Z]|id_rsa|\.ssh/|\.aws/|\.netrc|\.git-credentials|/credentials\b|\bcredentials\.json|\bsecrets?\b|\.npmrc\b|\bprintenv\b|\benv[[:space:]]*(\||>|$)'; then
    echo "credential_access"; return; fi
  # network_egress — 아웃바운드 네트워크
  if printf '%s' "$cmd" | grep -Eq '\b(curl|wget|nc|ncat|netcat|telnet|ssh|scp|sftp|rsync|ftp)\b|\bgit[[:space:]]+(clone|fetch|pull)\b|\b(npm|pnpm|yarn)[[:space:]]+(install|add|ci)\b|\bpip[0-9]?[[:space:]]+install\b|\bapt(-get)?[[:space:]]+install\b|/dev/tcp/'; then
    echo "network_egress"; return; fi
  # privileged_runtime — 권한 상승·시스템·컨테이너
  if printf '%s' "$cmd" | grep -Eq '\b(sudo|su|doas|chroot|mount|umount|systemctl|service|docker|podman|nsenter|setcap)\b'; then
    echo "privileged_runtime"; return; fi
  # destructive_fs — 파괴적 파일시스템·git 되돌림
  if printf '%s' "$cmd" | grep -Eq '\brm[[:space:]]+-[a-zA-Z]*[rf]|\b(dd|mkfs|shred|truncate)\b|\bchmod[[:space:]]+-R\b|\bgit[[:space:]]+(reset[[:space:]]+--hard|clean[[:space:]]+-[a-zA-Z]*f|checkout[[:space:]]+(--[[:space:]]|\.))'; then
    echo "destructive_fs"; return; fi
  echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# 7. repo 밖 write 탈출 감지 (symlink escape / 절대경로 escape). Kill: symlink로 repo 밖 쓰기.
# ─────────────────────────────────────────────────────────────────────────────
path_inside_repo() {
  local p="$1" rp
  case "$p" in /*) rp="$(realpath -m "$p" 2>/dev/null)" ;; *) rp="$(realpath -m "$REPO_REAL/$p" 2>/dev/null)" ;; esac
  case "$rp" in "$REPO_REAL"|"$REPO_REAL"/*) return 0 ;; *) return 1 ;; esac
}

# 명령의 write 대상(리다이렉션·tee)이 repo 밖으로 나가는가
command_writes_escape() {
  local cmd="$1" t
  # 리다이렉션 대상: > file / >> file
  while read -r t; do
    [ -n "$t" ] || continue
    path_inside_repo "$t" || { echo "$t"; return 0; }
  done < <(printf '%s\n' "$cmd" | grep -oE '>>?[[:space:]]*[^[:space:]|;&<>()]+' | sed -E 's/^>>?[[:space:]]*//')
  # tee 대상
  while read -r t; do
    [ -n "$t" ] || continue
    path_inside_repo "$t" || { echo "$t"; return 0; }
  done < <(printf '%s\n' "$cmd" | grep -oE '\btee[[:space:]]+(-a[[:space:]]+)?[^[:space:]|;&]+' | sed -E 's/^tee[[:space:]]+(-a[[:space:]]+)?//')
  return 1
}

# repo 내 escaping symlink(밖을 가리키는 심링크) 스캔 — pre/post 방어심층
escaping_symlink() {
  local l tgt
  while read -r l; do
    [ -n "$l" ] || continue
    tgt="$(realpath -m "$l" 2>/dev/null)"
    case "$tgt" in "$REPO_REAL"|"$REPO_REAL"/*) ;; *) echo "$l"; return 0 ;; esac
  done < <(find "$REPO_REAL" -path "$REPO_REAL/.git" -prune -o -type l -print 2>/dev/null)
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# 8. diff 게이트 (post-exec). 위험 파일군 편집 감지 → 정지(승인 요구). Invariant 4.
#    반환: "reason|file" (없으면 빈 문자열)
# ─────────────────────────────────────────────────────────────────────────────
VERIFY_BASENAME=""
if [ -n "$VERIFY_CMD" ]; then
  # --verify "./verify.sh && pytest" → 첫 토큰의 basename
  VERIFY_BASENAME="$(printf '%s' "$VERIFY_CMD" | awk '{print $1}' | xargs -r basename 2>/dev/null)"
fi

diff_gate() {
  local f base
  while read -r f; do
    [ -n "$f" ] || continue
    base="$(basename "$f")"
    # verify/CI/test harness 수정 → high-risk (Invariant 3)
    if [ -n "$VERIFY_BASENAME" ] && [ "$base" = "$VERIFY_BASENAME" ]; then echo "verify_modified|$f"; return 0; fi
    case "$base" in verify.sh|verify.bat|pytest.ini|tox.ini|jest.config.js|jest.config.ts|jest.config.cjs)
      echo "verify_modified|$f"; return 0 ;; esac
    # .github/workflows (CI/deploy)
    case "$f" in *.github/workflows/*) echo "diff_gate:ci_workflow|$f"; return 0 ;; esac
    # .claude/** — 자식이 guardrail/hooks/agents/skills/settings/MCP 변경 시도 (v2 #5)
    case "$f" in .claude/*|*/.claude/*) echo "diff_gate:claude_config|$f"; return 0 ;; esac
    # package scripts (postinstall 등) — package.json 의 라이프사이클 스크립트 변경만
    if [ "$base" = "package.json" ]; then
      local pj
      pj="$(git -C "$REPO" diff -- "$f" 2>/dev/null; git -C "$REPO" diff --cached -- "$f" 2>/dev/null)"
      [ -n "$pj" ] || pj="$(cat "$REPO/$f" 2>/dev/null)"   # 미추적 신규 파일
      if printf '%s' "$pj" | grep -Eq '"(pre|post)?install"|"pre(uninstall|pack|publish[a-zA-Z]*)?"|"post(uninstall|pack)"|"prepare"'; then
        echo "diff_gate:package_script|$f"; return 0
      fi
    fi
    # Makefile
    case "$base" in Makefile|makefile|GNUmakefile) echo "diff_gate:makefile|$f"; return 0 ;; esac
    # rc/config
    case "$base" in .npmrc|.yarnrc|.yarnrc.yml|.mcp.json|mcp.json|.babelrc|.bashrc|.zshrc|.profile|.bash_profile)
      echo "diff_gate:rc_config|$f"; return 0 ;; esac
    case "$base" in .*rc|*.rc) echo "diff_gate:rc_config|$f"; return 0 ;; esac
    # credential / .env
    case "$base" in .env|.env.*) echo "diff_gate:env_file|$f"; return 0 ;; esac
    # deploy
    case "$base" in Dockerfile|docker-compose.yml|docker-compose.yaml|vercel.json|netlify.toml|fly.toml|Procfile|.dockerignore)
      echo "diff_gate:deploy|$f"; return 0 ;; esac
    # migration
    case "$f" in */migrations/*|*/migrate/*|migrations/*) echo "diff_gate:migration|$f"; return 0 ;; esac
    case "$base" in *migration*|*.migration.*) echo "diff_gate:migration|$f"; return 0 ;; esac
  done < <(changed_files)
  return 1
}

# allowed_paths 위반 (봉투에 명시된 경우만). 변경파일이 어느 glob에도 안 들어가면 정지.
path_violation() {
  [ -n "$ALLOWED_PATHS" ] || return 1
  local f g matched
  while read -r f; do
    [ -n "$f" ] || continue
    matched=0
    IFS=',' read -ra globs <<< "$ALLOWED_PATHS"
    for g in "${globs[@]}"; do
      g="$(printf '%s' "$g" | xargs)"   # trim
      [ -n "$g" ] || continue
      case "$g" in
        */\*\*) [[ "$f" == "${g%\*\*}"* ]] && matched=1 ;;
        *)      [[ "$f" == $g ]] && matched=1 ;;
      esac
    done
    [ "$matched" = "0" ] && { echo "$f"; return 0; }
  done < <(changed_files)
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# 9. commit 게이트 — secret scan + size 리밋 (Invariant 6). 위반 시 반환 0 + 사유.
# ─────────────────────────────────────────────────────────────────────────────
secret_in_diff() {
  local blob f
  blob="$(git -C "$REPO" diff 2>/dev/null; git -C "$REPO" diff --cached 2>/dev/null)"
  # 미추적 신규 파일 내용도 스캔
  while read -r f; do
    [ -n "$f" ] || continue
    [ -f "$REPO/$f" ] && blob+=$'\n'"$(head -c 200000 "$REPO/$f" 2>/dev/null)"
  done < <(git -C "$REPO" ls-files --others --exclude-standard 2>/dev/null)
  printf '%s' "$blob" | grep -Eiq 'api[_-]?key|secret|password|token|@gmail|-----BEGIN[[:space:]][A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}'
}

oversized_artifact() {
  local f sz
  while read -r f; do
    [ -n "$f" ] || continue
    [ -f "$REPO/$f" ] || continue
    sz="$(wc -c < "$REPO/$f" 2>/dev/null || echo 0)"
    if [ "$sz" -gt "$MAX_ARTIFACT_BYTES" ]; then echo "$f($sz)"; return 0; fi
  done < <(changed_files)
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# 10. 스텝 명령 실행 — setsid(새 세션·프로세스그룹) + 워치독 timeout + 그룹 kill 스윕.
#     background process 금지: 스텝 후 항상 process-group 스윕으로 잔여 child 청소.
# ─────────────────────────────────────────────────────────────────────────────
OUR_PGID="$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')"
STEP_RC=0
STEP_TIMED_OUT=0
run_command() { # <cmd> <limit_secs> <outfile> <errfile>
  local cmd="$1" limit="$2" out="$3" err="$4"
  : > "$out"; : > "$err"
  local tmark="$RUN_DIR/.timedout.$STEP"; rm -f "$tmark"
  # 명령은 새 세션(setsid)에서 repo 안, ulimit(cpu·파일크기) 걸고 eval로. cmd는 env로 넘겨 quoting 회피.
  # stdin=/dev/null, stdout/err=파일 → 부모의 파이프 fd를 자식/손자가 물지 않게(명령치환 hang 방지).
  AP_CMD="$cmd" AP_REPO="$REPO_REAL" setsid bash -c \
    'cd "$AP_REPO" || exit 3; ulimit -t '"$CPU_SECS"' 2>/dev/null; ulimit -f '"$FSIZE_BLOCKS"' 2>/dev/null; eval "$AP_CMD"' \
    >"$out" 2>"$err" </dev/null &
  local child=$!
  local pgid; pgid="$(ps -o pgid= -p "$child" 2>/dev/null | tr -d ' ')"; pgid="${pgid:-$child}"
  # 자기 자신(부모 그룹) kill 방지 — pgid가 우리 그룹이면 그룹 kill 대신 child만
  local group_kill=1
  [ -n "$OUR_PGID" ] && [ "$pgid" = "$OUR_PGID" ] && group_kill=0
  # 워치독: 자체 세션(setsid)+fds 완전분리(</dev/null >/dev/null) → 워치독의 sleep이 부모 파이프를
  # 물지 않음. limit 후 tmark 남기고 스텝 그룹 TERM→KILL. (fds 미분리 시 워치독 sleep이 명령치환 hang.)
  AP_TMARK="$tmark" AP_PGID="$pgid" AP_CHILD="$child" AP_GK="$group_kill" AP_LIMIT="$limit" \
  setsid bash -c '
    sleep "$AP_LIMIT"
    : > "$AP_TMARK"
    if [ "$AP_GK" = "1" ]; then kill -TERM -- -"$AP_PGID" 2>/dev/null; sleep 2; kill -KILL -- -"$AP_PGID" 2>/dev/null
    else kill -TERM "$AP_CHILD" 2>/dev/null; sleep 2; kill -KILL "$AP_CHILD" 2>/dev/null; fi
  ' </dev/null >/dev/null 2>&1 &
  local wd=$!
  local wd_pgid; wd_pgid="$(ps -o pgid= -p "$wd" 2>/dev/null | tr -d ' ')"; wd_pgid="${wd_pgid:-$wd}"
  wait "$child" 2>/dev/null; STEP_RC=$?
  # 워치독 취소: 그룹째 kill (내부 sleep까지) → 잔여 sleep 없음
  if [ "$wd_pgid" != "$OUR_PGID" ]; then kill -- -"$wd_pgid" 2>/dev/null; else kill "$wd" 2>/dev/null; fi
  wait "$wd" 2>/dev/null
  # child sweep — 백그라운드로 남은 그룹 멤버 청소 (background job → sweep kill)
  if [ "$group_kill" = "1" ]; then
    kill -TERM -- -"$pgid" 2>/dev/null; sleep 0.2; kill -KILL -- -"$pgid" 2>/dev/null
  fi
  if [ -f "$tmark" ]; then STEP_TIMED_OUT=1; else STEP_TIMED_OUT=0; fi
  rm -f "$tmark"
}

# ─────────────────────────────────────────────────────────────────────────────
# 11. 드라이버 — 다음 액션 생산 (스텝당 1회). 우선순위:
#     (1) AUTOPILOT_STEP_HOOK  : 측정가능 CMD/TOKENS/USD emit (테스트/드라이런).
#     (2) --real / AUTOPILOT_REAL=1 : 실 LLM 루프(driver_real_step) — claude -p 1회 = 한 스텝.
#     (3) 둘 다 없음 : return 77 (측정 불가 fail-closed, invariant 1) → 루프가 exit 4.
#     반환코드: 0=액션생산 · 77=측정불가(→exit4) · 78=자식 타임아웃(→per_step_timeout) · 기타=driver_error
# ─────────────────────────────────────────────────────────────────────────────
driver_produce_action() { # <step>  → stdout: "CMD: ...\nTOKENS: n\nUSD: n"
  local step="$1"
  if [ -n "${AUTOPILOT_STEP_HOOK:-}" ] && [ -x "${AUTOPILOT_STEP_HOOK}" ]; then
    "$AUTOPILOT_STEP_HOOK" "$step" 2>>"$RUN_DIR/hook.err"
    return $?
  fi
  if [ "$REAL_MODE" = "1" ]; then
    driver_real_step "$step"
    return $?
  fi
  return 77   # 실 provider 미연결 & real mode OFF → 측정 불가 → fail-closed
}

# ─────────────────────────────────────────────────────────────────────────────
# 11a. Bash-ledger-우회 차단 shim (v2 #3 — 최중요). PATH 앞에 놓여 자식 Bash가
#      새 LLM/네트워크/remote/패키지설치/인라인코드exec 를 못 돌리게 물리적으로 차단.
#      차단 시 BYPASS_MARKER 에 기록 → post-step 에서 감지·정지(denied ledger 확장).
#      순수차단(항상거부): claude·codex·anthropic·openai·curl·wget·gh·ssh·scp·sftp·nc·telnet·rsync…
#      부분차단(위험 서브명령만): git(push/clone/fetch/pull/remote)·npm/pnpm/yarn(install/add/ci)·
#      pip(install)·apt(install)·python/node(-e/-c 인라인).
# ─────────────────────────────────────────────────────────────────────────────
setup_shim_bin() {
  mkdir -p "$SHIM_BIN" || return 1
  local n real
  # 순수차단 shim
  for n in claude codex anthropic openai curl wget gh ssh scp sftp ftp nc ncat netcat telnet rsync; do
    { printf '#!/usr/bin/env bash\n'
      printf 'printf "%%s %%s\\n" %q "$*" >> "${AP_BYPASS_MARKER:-%s}"\n' "$n" "$BYPASS_MARKER"
      printf 'echo "autopilot: blocked %q (ledger-bypass/network/remote denied)" >&2\n' "$n"
      printf 'exit 1\n'
    } > "$SHIM_BIN/$n"
    chmod +x "$SHIM_BIN/$n"
  done
  # 부분차단 shim 헬퍼 — <name> <real-path> <blocked-word-regex>
  _subcmd_shim() {
    local name="$1" realp="$2" re="$3"
    { printf '#!/usr/bin/env bash\n'
      printf 'if printf " %%s " "$*" | grep -qE %q; then\n' " ($re) "
      printf '  printf "%%s %%s\\n" %q "$*" >> "${AP_BYPASS_MARKER:-%s}"\n' "$name" "$BYPASS_MARKER"
      printf '  echo "autopilot: blocked %q subcommand (denied)" >&2; exit 1\n' "$name"
      printf 'fi\n'
      if [ -n "$realp" ]; then printf 'exec %q "$@"\n' "$realp"
      else printf 'echo "autopilot: %q not available" >&2; exit 127\n' "$name"; fi
    } > "$SHIM_BIN/$name"
    chmod +x "$SHIM_BIN/$name"
  }
  real="$(command -v git 2>/dev/null)";  _subcmd_shim git    "$real" 'push|clone|fetch|pull|remote'
  real="$(command -v npm 2>/dev/null)";  [ -n "$real" ] && _subcmd_shim npm  "$real" 'install|add|ci|exec|dlx|create'
  real="$(command -v pnpm 2>/dev/null)"; [ -n "$real" ] && _subcmd_shim pnpm "$real" 'install|add|dlx|create'
  real="$(command -v yarn 2>/dev/null)"; [ -n "$real" ] && _subcmd_shim yarn "$real" 'install|add|create'
  real="$(command -v pip 2>/dev/null)";  [ -n "$real" ] && _subcmd_shim pip  "$real" 'install'
  real="$(command -v pip3 2>/dev/null)"; [ -n "$real" ] && _subcmd_shim pip3 "$real" 'install'
  real="$(command -v apt 2>/dev/null)";  [ -n "$real" ] && _subcmd_shim apt  "$real" 'install'
  real="$(command -v apt-get 2>/dev/null)"; [ -n "$real" ] && _subcmd_shim apt-get "$real" 'install'
  real="$(command -v python 2>/dev/null)";  [ -n "$real" ] && _subcmd_shim python  "$real" '-e|-c|--eval'
  real="$(command -v python3 2>/dev/null)"; [ -n "$real" ] && _subcmd_shim python3 "$real" '-e|-c|--eval'
  real="$(command -v node 2>/dev/null)";    [ -n "$real" ] && _subcmd_shim node    "$real" '-e|--eval|-p|--print'
  return 0
}

# post-step: shim 이 차단 흔적을 남겼는가 (이번 스텝에서). 있으면 첫 줄 반환.
bash_bypass_detected() {
  [ -n "$BYPASS_MARKER" ] && [ -s "$BYPASS_MARKER" ] || return 1
  head -1 "$BYPASS_MARKER" 2>/dev/null
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# 11b. 자식 프롬프트 — 봉투 objective + 은행(progress bank, 부모가 파일 읽어 삽입: @참조 금지, v2 #2)
#      + "딱 한 개 액션 하고 멈춰라 + NOTE 1줄".
# ─────────────────────────────────────────────────────────────────────────────
build_child_prompt() { # <step> <bank-text>
  local step="$1" bank="$2"
  cat <<EOF
You are ONE bounded step (#$step) of an autonomous fix loop running on a local WIP git branch.
Everything you do stays in the working tree; a human reviews the diff later.

OBJECTIVE (success = exactly this, nothing more; do not expand scope):
$OBJECTIVE

PROGRESS SO FAR (previous steps' one-line notes; may be empty on step 1):
---
$bank
---

DO THIS STEP:
- Take EXACTLY ONE concrete action toward the objective (one edit / one command), then STOP.
- End your reply with a single final line: NOTE: <what you did and the result, one line>

HARD RULES (a violation aborts the entire run):
- Allowed tools: Read, Edit, Bash. Edit/write only files INSIDE this repo working tree.
- FORBIDDEN — never run any of these (they are physically blocked and will abort the run):
  claude/codex/anthropic/openai clients, curl, wget, gh, ssh/scp/sftp, "git push"/clone/fetch/pull/remote,
  npm/pnpm/yarn/pip/apt install, background jobs ("&"), inline code exec ("python -c"/"node -e"),
  printing credentials or secret env vars.
- No @file references, no slash-commands, no sub-agents, no web/network.
- Do NOT touch: .claude/**, settings, hooks, CI workflows, verify/test-harness scripts, .env, migrations,
  package.json lifecycle scripts, Dockerfiles/deploy config. Editing them aborts the run.
EOF
}

# JSON 파싱(no jq — 하네스는 외부의존 최소). total_cost_usd → 없으면 빈 문자열(측정불가).
parse_claude_cost() { # <jsonfile>
  grep -oE '"total_cost_usd"[[:space:]]*:[[:space:]]*[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?' "$1" 2>/dev/null \
    | head -1 | grep -oE '[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$'
}
parse_claude_tokens() { # <jsonfile> → input+output(+cache) 합 (over-count 허용 = 보수적)
  awk '{ s=$0
      while (match(s, /"(input_tokens|output_tokens|cache_creation_input_tokens|cache_read_input_tokens)"[ ]*:[ ]*[0-9]+/)) {
        f=substr(s,RSTART,RLENGTH); sub(/.*:[ ]*/,"",f); t+=f; s=substr(s,RSTART+RLENGTH) } }
    END{ printf "%d", t+0 }' "$1" 2>/dev/null
}
# JSON "result" 문자열에서 자식이 남긴 NOTE 추출(관측용 은행 기록 — reasoning 은 안 봄).
parse_claude_note() { # <jsonfile>
  local r
  r="$(grep -oE '"result"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' "$1" 2>/dev/null | head -1)"
  r="${r#*:}"; r="${r#*\"}"; r="${r%\"}"
  printf '%s' "$r" | grep -oE 'NOTE:.*' | head -1
}

# ─────────────────────────────────────────────────────────────────────────────
# 11c. 실 스텝 = `claude -p` 1회 (fresh 헤드리스, v2 #5·#6·#7 격리 플래그).
#      run_command 로 감싸 setsid+워치독(PER_STEP_SECS)+그룹kill+ulimit 를 그대로 상속.
#      프롬프트는 arg 로 "$(cat pf)" — 명령치환 결과는 재평가되지 않음(injection-safe).
#      반환: 0(+stdout CMD:/TOKENS:/USD:) · 77(측정불가) · 78(타임아웃).
# ─────────────────────────────────────────────────────────────────────────────
driver_real_step() { # <step>
  local step="$1"
  command -v "$CLAUDE_BIN" >/dev/null 2>&1 || [ -x "$CLAUDE_BIN" ] || return 77
  local bank=""
  [ -f "$RUN_DIR/progress.md" ] && bank="$(cat "$RUN_DIR/progress.md" 2>/dev/null)"
  local pf="$RUN_DIR/prompt.$step.txt"
  build_child_prompt "$step" "$bank" > "$pf"
  : > "$BYPASS_MARKER"   # 이번 스텝 흔적만 감지
  local out="$RUN_DIR/child.$step.json" err="$RUN_DIR/child.$step.err"

  # 격리 env + 하드닝 플래그로 자식 spawn. --max-turns 는 현 claude(2.1.x)에 없음 →
  # PER_STEP_SECS(워치독) + --max-budget-usd(per-step 사전캡) 로 mid-call 폭주 방어.
  local cc
  cc="PATH=$(printf '%q' "$SHIM_BIN"):\"\$PATH\""
  cc+=" AP_BYPASS_MARKER=$(printf '%q' "$BYPASS_MARKER")"
  cc+=" CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS=1"
  cc+=" $(printf '%q' "$CLAUDE_BIN") -p \"\$(cat $(printf '%q' "$pf"))\""
  cc+=" --output-format json --bare --no-session-persistence --disable-slash-commands --strict-mcp-config"
  cc+=" --model $(printf '%q' "$GEN_MODEL")"
  cc+=" --tools Read,Edit,Bash --allowedTools Read,Edit,Bash"
  cc+=" --disallowedTools $(printf '%q' 'mcp__*,Agent,Task,WebFetch,WebSearch,NotebookEdit')"
  cc+=" --permission-mode acceptEdits"
  cc+=" --max-budget-usd $(printf '%q' "$PER_STEP_USD")"
  [ -n "$CHILD_SETTINGS" ] && cc+=" --settings $(printf '%q' "$CHILD_SETTINGS")"

  run_command "$cc" "$PER_STEP_SECS" "$out" "$err"
  if [ "$STEP_TIMED_OUT" = "1" ]; then
    emit_event "child" step "$step" timed_out 1 rc "$STEP_RC"
    return 78
  fi
  local cost tokens note
  cost="$(parse_claude_cost "$out")"
  if [ -z "$cost" ]; then
    emit_event "measure_fail" step "$step" rc "$STEP_RC" detail "no total_cost_usd (usage 없음/auth실패/crash)"
    return 77   # usage 없으면 fail-closed (invariant 1, v2 #8)
  fi
  tokens="$(parse_claude_tokens "$out")"
  note="$(parse_claude_note "$out")"; [ -z "$note" ] && note="(no NOTE returned)"
  printf '## step %s — %s\n' "$step" "$note" >> "$RUN_DIR/progress.md"   # 은행 갱신(관측)
  emit_event "child" step "$step" rc "$STEP_RC" cost_usd "$cost" tokens "${tokens:-0}" approx 1
  # 실 스텝은 자식이 이미 편집을 수행 → 부모가 실행할 CMD 없음(빈 CMD). post-step 게이트가 결과를 검사.
  printf 'CMD:\nTOKENS: %s\nUSD: %s\n' "${tokens:-0}" "$cost"
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# 11d. 검증 격리 judge (v2 — 입력경계). 별도 claude -p 가 objective + git diff 만 봄
#      (생성자 progress.md·reasoning 안 봄; --tools '' 로 툴 없음 = 파일도 못 읽음). real/fake 판정.
#      기본 내부 haiku. --external-judge 시 codex(외부모델) — 미설치면 내부로 폴백(스텁 표시).
#      stdout: 판정 텍스트. 성공직전 게이트에서 'REAL' 아니면 정지.
# ─────────────────────────────────────────────────────────────────────────────
run_judge() {
  local diff jpf jout verdict
  diff="$( { git -C "$REPO" diff "$BASE_COMMIT" 2>/dev/null
             echo '--- untracked new files ---'
             git -C "$REPO" ls-files --others --exclude-standard 2>/dev/null | while read -r f; do
               [ -n "$f" ] || continue; echo "=== NEW: $f ==="; head -c 20000 "$REPO/$f" 2>/dev/null; echo
             done; } | head -c 100000 )"
  jpf="$RUN_DIR/judge.$STEP.txt"
  {
    echo "You are an INDEPENDENT verifier. You see ONLY the objective and a git diff below."
    echo "You do NOT see the author's notes, progress, or reasoning. Judge whether the diff"
    echo "GENUINELY accomplishes the objective, or is fake / stubbed / reward-hacked / incomplete."
    echo
    echo "OBJECTIVE:"; echo "$OBJECTIVE"; echo
    echo "DIFF (base..working tree):"; echo "$diff"; echo
    echo "First line must be exactly one of: VERDICT: REAL | VERDICT: FAKE | VERDICT: INCOMPLETE"
    echo "Then one sentence of justification."
  } > "$jpf"

  if [ "$EXTERNAL_JUDGE" = "1" ] && command -v "${AUTOPILOT_CODEX_BIN:-codex}" >/dev/null 2>&1; then
    # 외부 codex judge (opt-in). 최소 호출 — 계약상 스텁/opt-in 허용.
    "${AUTOPILOT_CODEX_BIN:-codex}" exec --model "${AUTOPILOT_CODEX_MODEL:-gpt-5-codex}" \
      "$(cat "$jpf")" 2>>"$RUN_DIR/judge.$STEP.err" | head -c 4000
    return 0
  fi
  command -v "$CLAUDE_BIN" >/dev/null 2>&1 || [ -x "$CLAUDE_BIN" ] || { printf 'VERDICT: UNKNOWN (judge unavailable)'; return 0; }
  jout="$RUN_DIR/judge.$STEP.json"
  local jc
  jc="$(printf '%q' "$CLAUDE_BIN") -p \"\$(cat $(printf '%q' "$jpf"))\""
  jc+=" --output-format json --bare --no-session-persistence --disable-slash-commands --strict-mcp-config"
  jc+=" --model $(printf '%q' "$JUDGE_MODEL") --tools '' "
  jc+=" --disallowedTools $(printf '%q' 'mcp__*,Agent,Task,WebFetch,WebSearch,Bash,Edit,Write,NotebookEdit')"
  jc+=" --max-budget-usd $(printf '%q' "$PER_STEP_USD")"
  run_command "$jc" "$PER_STEP_SECS" "$jout" "$RUN_DIR/judge.$STEP.err"
  verdict="$(grep -oE '"result"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' "$jout" 2>/dev/null | head -1)"
  verdict="${verdict#*:}"; verdict="${verdict#*\"}"; verdict="${verdict%\"}"
  [ -z "$verdict" ] && verdict="VERDICT: UNKNOWN (no result parsed)"
  printf '%s' "$verdict"
}

# ─────────────────────────────────────────────────────────────────────────────
# 12. 종료 렌더 + 정리
# ─────────────────────────────────────────────────────────────────────────────
STOP_REASON=""
TOTAL_USD="0"
declare -A RISK_COUNT=()
START="$(date +%s)"

# 사람용 요약 → summary.md. (스텝 은행 = progress.md 는 그대로 보존; 여기에 포함만 함.)
render_progress() {
  local elapsed bank=""; elapsed=$(( $(date +%s) - START ))
  [ -f "$RUN_DIR/progress.md" ] && bank="$(cat "$RUN_DIR/progress.md" 2>/dev/null)"
  {
    echo "# autopilot run $RUN_ID"
    echo
    echo "- objective: $OBJECTIVE"
    echo "- repo: $REPO_REAL"
    echo "- branch: $CUR_BRANCH"
    echo "- steps run: $STEP / $MAX_STEPS"
    echo "- stop_reason: ${STOP_REASON:-none}"
    echo "- budget used: \$$(awk -v x="$TOTAL_USD" 'BEGIN{printf "%.4f", x}') / \$$TOTAL_BUDGET_USD (approx — client 추정, v2 #8)"
    echo "- wall: ${elapsed}s / ${WALL_CLOCK_SECS}s"
    echo
    echo "## denied ledger (risk class → 횟수)"
    if [ "${#RISK_COUNT[@]}" -eq 0 ]; then echo "- (없음)"; else
      for k in "${!RISK_COUNT[@]}"; do echo "- $k: ${RISK_COUNT[$k]}"; done
    fi
    echo
    if [ -n "$bank" ]; then echo "## step notes (progress bank)"; echo; echo "$bank"; echo; fi
    echo "_워킹트리 보존됨 — 자동 되돌림 없음. \`git -C $REPO_REAL diff\` 리뷰 후 사람이 커밋/머지._"
  } > "$RUN_DIR/summary.md"
}

finish() {
  emit_event "run_end" stop_reason "${STOP_REASON:-none}" steps "$STEP" \
    total_usd "$(awk -v x="$TOTAL_USD" 'BEGIN{printf "%.6f", x}')"
  render_progress
  echo "AUTOPILOT: stop_reason=${STOP_REASON:-none} steps=$STEP run_id=$RUN_ID"
  exit 0
}

# ─────────────────────────────────────────────────────────────────────────────
# 13. 메인 루프
# ─────────────────────────────────────────────────────────────────────────────
PREV_STATE="$(state_vector)"
PREV_HOOKS_FP="$(hooks_fp)"
PREV_CLAUDE_FP="$(claude_config_fp)"
STALL=0

# 실 LLM 루프면 Bash-ledger-우회 shim 설치(v2 #3). 실패해도 fail-closed(측정 없이 자식 못 돎).
if [ "$REAL_MODE" = "1" ]; then
  setup_shim_bin || { STOP_REASON="shim_setup_failed"; emit_event "kill" reason "$STOP_REASON"; finish; }
  emit_event "real_mode" gen_model "$GEN_MODEL" judge_model "$JUDGE_MODEL" \
    claude_bin "$CLAUDE_BIN" external_judge "$EXTERNAL_JUDGE" shim_bin "$SHIM_BIN"
fi

# 무장 즉시, 루프 진입 전 escaping symlink가 이미 있으면 거부 (repo가 이미 탈출로를 품음)
if esc="$(escaping_symlink)"; [ -n "$esc" ]; then
  STOP_REASON="sandbox_violation:symlink"
  emit_event "kill" reason "$STOP_REASON" detail "$esc" phase "pre_loop"
  finish
fi

while true; do
  STEP=$((STEP + 1))

  # (a) MAX_STEPS 하드리밋
  if [ "$STEP" -gt "$MAX_STEPS" ]; then
    STEP=$((STEP - 1)); STOP_REASON="max_steps"
    emit_event "kill" reason "$STOP_REASON"; finish
  fi

  # (b) WALL_CLOCK 하드리밋
  local_now="$(date +%s)"; elapsed=$((local_now - START)); remaining=$((WALL_CLOCK_SECS - elapsed))
  if [ "$remaining" -le 0 ]; then
    STEP=$((STEP - 1)); STOP_REASON="wall_clock"
    emit_event "kill" reason "$STOP_REASON" elapsed "$elapsed"; finish
  fi

  # (c) 드라이버에서 액션 획득 (hook 또는 실 claude -p). driver 는 $() 서브셸 → 상태는 rc·파일로만 전달.
  action="$(driver_produce_action "$STEP")"; drc=$?
  # 이번 스텝이 실 claude 스텝인가 (hook 아님 & real mode) — post-step 게이트 분기용
  this_real=0
  if [ -z "${AUTOPILOT_STEP_HOOK:-}" ] && [ "$REAL_MODE" = "1" ]; then this_real=1; fi
  # (c-1) 자식 mid-call 타임아웃(driver rc 78) → per_step_timeout (측정 후행 방어, v2 열린질문①)
  if [ "$drc" -eq 78 ]; then
    STEP=$((STEP - 1)); STOP_REASON="per_step_timeout"
    emit_event "kill" reason "$STOP_REASON" phase "driver_child" step "$((STEP + 1))"; finish
  fi
  if [ "$drc" -eq 77 ]; then
    # 측정 불가 provider → fail-closed 거부 (invariant 1)
    STEP=$((STEP - 1)); STOP_REASON="fail_closed:measurement"
    emit_event "refused" reason "$STOP_REASON"
    render_progress
    echo "autopilot: 거부 — 실 LLM provider 미연결(비용 측정 불가) → fail-closed. (이번 빌드는 스텁; AUTOPILOT_STEP_HOOK 로 구동)" >&2
    echo "AUTOPILOT: refused reason=fail_closed_measurement"
    exit 4
  fi
  if [ "$drc" -ne 0 ]; then
    STOP_REASON="driver_error"; emit_event "kill" reason "$STOP_REASON" drc "$drc"; finish
  fi

  cmd="$(printf '%s\n' "$action" | sed -n 's/^CMD:[[:space:]]*//p' | head -1)"
  tokens="$(printf '%s\n' "$action" | sed -n 's/^TOKENS:[[:space:]]*//p' | head -1)"
  usd="$(printf '%s\n' "$action" | sed -n 's/^USD:[[:space:]]*//p' | head -1)"
  is_num "$tokens" || tokens=0
  is_num "$usd" || usd=0

  # (d) PER_CALL_TOKENS 하드리밋
  if [ "$tokens" -gt "$PER_CALL_TOKENS" ] 2>/dev/null; then
    STOP_REASON="per_call_tokens"
    emit_event "kill" reason "$STOP_REASON" tokens "$tokens" cap "$PER_CALL_TOKENS"; finish
  fi

  # (e) 예산 누적 + PER_STEP_USD + TOTAL_BUDGET_USD
  TOTAL_USD="$(fadd "$TOTAL_USD" "$usd")"
  emit_event "call" tokens "$tokens" usd "$usd" total_usd "$TOTAL_USD" cmd "$cmd"
  if fgt "$usd" "$PER_STEP_USD"; then
    STOP_REASON="per_step_usd"
    emit_event "kill" reason "$STOP_REASON" usd "$usd" cap "$PER_STEP_USD"; finish
  fi
  if fgt "$TOTAL_USD" "$TOTAL_BUDGET_USD"; then
    STOP_REASON="total_budget"
    emit_event "kill" reason "$STOP_REASON" total_usd "$TOTAL_USD" cap "$TOTAL_BUDGET_USD"; finish
  fi

  # (f) pre-exec 위험 분류 (command 게이트 → denied ledger)
  if [ -n "$cmd" ]; then
    rclass="$(classify_risk "$cmd")"
    if [ -n "$rclass" ]; then
      RISK_COUNT["$rclass"]=$(( ${RISK_COUNT["$rclass"]:-0} + 1 ))
      emit_event "denied" risk_class "$rclass" count "${RISK_COUNT[$rclass]}" cmd "$cmd"
      if [ "${RISK_COUNT[$rclass]}" -ge 2 ]; then
        STOP_REASON="denied_ledger:$rclass"
        emit_event "kill" reason "$STOP_REASON"; finish
      fi
      # 1회차: 이 액션 실행 거부하고 다음 스텝. 진전 없음 → stall 계산.
      NEW_STATE="$(state_vector)"
      if [ "$NEW_STATE" = "$PREV_STATE" ]; then STALL=$((STALL + 1)); else STALL=0; PREV_STATE="$NEW_STATE"; fi
      if [ "$STALL" -ge "$NO_PROGRESS_LIMIT" ]; then
        STOP_REASON="no_progress"; emit_event "kill" reason "$STOP_REASON" stall "$STALL"; finish
      fi
      continue
    fi
    # (g) pre-exec repo 밖 write escape (symlink/절대경로)
    if esc="$(command_writes_escape "$cmd")"; [ -n "$esc" ]; then
      STOP_REASON="sandbox_violation:symlink"
      emit_event "kill" reason "$STOP_REASON" detail "$esc" cmd "$cmd" phase "pre_exec"; finish
    fi
  fi

  # (h) 스텝 실행 (setsid + 워치독 timeout + 그룹 스윕)
  step_limit="$PER_STEP_SECS"; [ "$remaining" -lt "$step_limit" ] && step_limit="$remaining"
  if [ -n "$cmd" ]; then
    run_command "$cmd" "$step_limit" "$RUN_DIR/step.$STEP.out" "$RUN_DIR/step.$STEP.err"
    emit_event "exec" rc "$STEP_RC" timed_out "$STEP_TIMED_OUT" limit_secs "$step_limit"
    if [ "$STEP_TIMED_OUT" = "1" ]; then
      STOP_REASON="per_step_timeout"
      emit_event "kill" reason "$STOP_REASON" limit_secs "$step_limit" cmd "$cmd"; finish
    fi
  fi

  # (h2) 실 스텝: Bash-ledger-우회 감지 (v2 #3). shim 이 이번 스텝에 새 LLM/네트워크/remote/설치/인라인exec
  #      를 차단하며 흔적을 남겼으면 즉시 정지(denied ledger 확장, 심각 → 1회에 kill).
  if [ "$this_real" = "1" ]; then
    if bp="$(bash_bypass_detected)"; [ -n "$bp" ]; then
      RISK_COUNT["bash_bypass"]=$(( ${RISK_COUNT["bash_bypass"]:-0} + 1 ))
      emit_event "denied" risk_class "bash_bypass" count "${RISK_COUNT[bash_bypass]}" detail "$bp"
      STOP_REASON="denied_ledger:bash_bypass"
      emit_event "kill" reason "$STOP_REASON" detail "$bp"; finish
    fi
  fi

  # (i) post-exec: escaping symlink(스텝 중 생성됐을 수 있음)
  if esc="$(escaping_symlink)"; [ -n "$esc" ]; then
    STOP_REASON="sandbox_violation:symlink"
    emit_event "kill" reason "$STOP_REASON" detail "$esc" phase "post_exec"; finish
  fi

  # (j) post-exec: 브랜치 가드 (에이전트가 main/master로 체크아웃?)
  now_branch="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  case "$now_branch" in main|master)
    STOP_REASON="branch_guard"; emit_event "kill" reason "$STOP_REASON" branch "$now_branch"; finish ;;
  esac

  # (k) .git/hooks 지문 변화 (diff 게이트가 못 보는 비추적 경로)
  NOW_HOOKS_FP="$(hooks_fp)"
  if [ "$NOW_HOOKS_FP" != "$PREV_HOOKS_FP" ]; then
    STOP_REASON="diff_gate:git_hooks"
    emit_event "kill" reason "$STOP_REASON"; finish
  fi

  # (k2) .claude/** · MCP config 지문 변화 (v2 #5 — 자식이 다음 스텝 guardrail/격리를 못 바꾸게).
  #      gitignore 로 diff 게이트가 못 봐도 filesystem 지문으로 잡음.
  NOW_CLAUDE_FP="$(claude_config_fp)"
  if [ "$NOW_CLAUDE_FP" != "$PREV_CLAUDE_FP" ]; then
    STOP_REASON="diff_gate:claude_config"
    emit_event "kill" reason "$STOP_REASON"; finish
  fi

  # (l) diff 게이트: 위험 파일군 편집 / verify 수정
  if dg="$(diff_gate)"; [ -n "$dg" ]; then
    reason="${dg%%|*}"; dfile="${dg#*|}"
    STOP_REASON="$reason"
    emit_event "kill" reason "$reason" file "$dfile"; finish
  fi

  # (m) allowed_paths 위반 (봉투 명시 시)
  if pv="$(path_violation)"; [ -n "$pv" ]; then
    STOP_REASON="path_violation"
    emit_event "kill" reason "$STOP_REASON" file "$pv"; finish
  fi

  # (n) commit 게이트 (opt-in --commit): secret scan + size 리밋
  if [ "$DO_COMMIT" = "1" ]; then
    if secret_in_diff; then
      STOP_REASON="secret_scan"; emit_event "kill" reason "$STOP_REASON"; finish
    fi
    if big="$(oversized_artifact)"; [ -n "$big" ]; then
      STOP_REASON="artifact_size"; emit_event "kill" reason "$STOP_REASON" file "$big"; finish
    fi
    # (게이트 통과 시에만 커밋 — 이번 빌드에선 실제 커밋은 하지 않고 게이트만 증명)
    emit_event "commit_gate_pass"
  fi

  # (o) verify 실행 (옵션). 통과 → 성공 정지. 실패 → 시그니처를 상태벡터에 반영.
  if [ -n "$VERIFY_CMD" ]; then
    run_command "$VERIFY_CMD" "$step_limit" "$RUN_DIR/verify.$STEP.out" "$RUN_DIR/verify.$STEP.err"
    emit_event "verify" rc "$STEP_RC" timed_out "$STEP_TIMED_OUT"
    if [ "$STEP_TIMED_OUT" != "1" ] && [ "$STEP_RC" -eq 0 ]; then
      # (o-2) 검증 격리 judge (real mode): verify(자식이 조작 가능) 통과만으로 성공 선언 금지.
      #       별도 claude 가 diff+objective 만 보고 real/fake 판정 (progress·reasoning 안 봄).
      #       'REAL' 아니면 reward-hacking 의심 → judge_reject 정지.
      if [ "$this_real" = "1" ]; then
        jverdict="$(run_judge)"
        emit_event "judge" verdict "$jverdict" model "$JUDGE_MODEL" external "$EXTERNAL_JUDGE"
        if ! printf '%s' "$jverdict" | grep -qiE 'VERDICT:[[:space:]]*REAL|^[[:space:]]*REAL'; then
          STOP_REASON="judge_reject"
          emit_event "kill" reason "$STOP_REASON" verdict "$jverdict"; finish
        fi
      fi
      STOP_REASON="verify_pass"; emit_event "success" reason "$STOP_REASON"; finish
    fi
    FAIL_SIG="$(tail -n 20 "$RUN_DIR/verify.$STEP.out" "$RUN_DIR/verify.$STEP.err" 2>/dev/null | sha1sum | awk '{print $1}')"
  fi

  # (p) 진전-기반 정지 (상태벡터 무변화 N회)
  NEW_STATE="$(state_vector)"
  if [ "$NEW_STATE" = "$PREV_STATE" ]; then STALL=$((STALL + 1)); else STALL=0; PREV_STATE="$NEW_STATE"; fi
  emit_event "progress" stall "$STALL" state "${NEW_STATE:0:12}"
  if [ "$STALL" -ge "$NO_PROGRESS_LIMIT" ]; then
    STOP_REASON="no_progress"; emit_event "kill" reason "$STOP_REASON" stall "$STALL"; finish
  fi
done
