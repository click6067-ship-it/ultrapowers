#!/usr/bin/env bash
# orca-docs.sh — Orca 공식 문서를 '복사하지 않고' 항상 최신으로 읽는 도구
#
# 왜 이게 필요한가 (2026-07-29):
#   Orca CLI 를 며칠간 더듬어 쓰면서 공식 규약을 여러 개 어겼다. 워크트리를 매번
#   새로 만들었고(문서는 명시적으로 금지), worker_done·terminal wait 같은 기본
#   기능을 마커 폴링으로 재발명했다. 원인은 단순하다 — 공식 문서를 안 읽었다.
#
#   그런데 문서를 md 로 복사해두면 CLI 업데이트마다 낡는다. 낡은 문서는 없는 것보다
#   나쁘다(맞다고 믿게 만든다). 다행히 Orca 는 문서를 CLI 에 '번들'한다:
#     orca skills list / skills get <name>   버전 일치 공식 가이드
#     orca agent-context --json              206개 명령의 정확한 스키마
#   즉 정본은 이미 로컬에 있고 CLI 와 함께 갱신된다. 저장할 게 아니라 '가져오면' 된다.
#
#   이 스크립트는 CLI 지문이 바뀌면 캐시를 자동 폐기한다. 그래서 구조적으로 낡지 않는다.
#
# 사용:
#   orca-docs.sh list              사용 가능한 공식 가이드 목록
#   orca-docs.sh guide orca-cli    가이드 전문 (필요시 자동 갱신)
#   orca-docs.sh cmd "worktree create"   그 명령의 정확한 플래그만
#   orca-docs.sh check             캐시 상태
#   orca-docs.sh refresh           강제 갱신
set -uo pipefail

CACHE="${ORCA_DOCS_CACHE:-$HOME/.cache/orca-docs}"

# 실행 파일 선택 — 공식 가이드의 'Start Here' 순서를 그대로 따른다.
#   ⚠️ 리눅스에서 Orca 관리 터미널 밖의 bare `orca` 는 보통 GNOME 스크린리더
#      (/usr/bin/orca)다. 그걸 실행하면 사용자 머신에서 음성이 나온다.
orca_exe() {
  if [ -n "${ORCA_CLI_COMMAND:-}" ]; then printf '%s' "$ORCA_CLI_COMMAND"; return 0; fi
  if [ -n "${ORCA_DEV_REPO_ROOT:-}" ] && command -v orca-dev >/dev/null 2>&1; then
    printf 'orca-dev'; return 0
  fi
  case "$(uname -s)" in
    Linux) command -v orca-ide >/dev/null 2>&1 && { printf 'orca-ide'; return 0; } ;;
  esac
  command -v orca >/dev/null 2>&1 && { printf 'orca'; return 0; }
  return 1
}

# CLI 지문. 바뀌면 캐시를 버린다.
#   `--version` 은 빈 값을 뱉으므로(실측) 명령 수·스키마 버전·스킬 목록을 쓴다.
#   이 셋은 CLI 가 바뀌면 같이 바뀌고, 두 번의 빠른 호출로 얻는다.
fingerprint() {
  local e; e=$(orca_exe) || return 1
  { timeout 30 "$e" agent-context 2>/dev/null
    timeout 30 "$e" skills list 2>/dev/null | sed 's/:.*//'
  } | sha256sum | cut -c1-16
}

need_refresh() {
  local cur; cur=$(fingerprint) || return 1
  [ -n "$cur" ] || return 1
  [ -r "$CACHE/.fingerprint" ] || return 0
  [ "$cur" != "$(cat "$CACHE/.fingerprint" 2>/dev/null)" ]
}

do_refresh() {
  local e; e=$(orca_exe) || { echo "orca CLI 없음" >&2; return 1; }
  mkdir -p "$CACHE" || return 1
  local names n
  names=$(timeout 30 "$e" skills list 2>/dev/null | sed -n 's/^\([a-z0-9-]*\):.*/\1/p')
  [ -n "$names" ] || { echo "skills list 실패 — Orca 실행 중인지 확인" >&2; return 1; }
  while IFS= read -r n; do
    [ -n "$n" ] || continue
    # ⚠️ < /dev/null 필수. 없으면 skills get 이 heredoc stdin 을 먹어서 두 번째
    #    이름부터 사라진다(실측: 8개 중 1개만 캐시됨). 루프 안에서 stdin 을 읽을 수
    #    있는 명령을 부를 때의 고전적 함정 — orca terminal send 에서도 같은 걸 겪었다.
    timeout 60 "$e" skills get "$n" < /dev/null > "$CACHE/$n.md" 2>/dev/null \
      || rm -f "$CACHE/$n.md"
  done <<EOF
$names
EOF
  timeout 60 "$e" agent-context --json < /dev/null > "$CACHE/agent-context.json" 2>/dev/null \
    || rm -f "$CACHE/agent-context.json"
  fingerprint > "$CACHE/.fingerprint"
  printf '갱신됨: %s (가이드 %s개)\n' "$CACHE" "$(ls "$CACHE"/*.md 2>/dev/null | wc -l)"
}

ensure() { need_refresh && do_refresh >/dev/null 2>&1; return 0; }

cmd_schema() {   # $1=명령 이름 일부 ("worktree create")
  [ -r "$CACHE/agent-context.json" ] || { echo "캐시 없음 — refresh 먼저" >&2; return 1; }
  # 실제 스키마(실측): command, path[], summary, usage, flags[](문자열), examples[], notes[]
  python3 - "$1" "$CACHE/agent-context.json" <<'PY'
import json,sys,difflib
q=sys.argv[1].strip().lower()
_d=json.load(open(sys.argv[2]))
cmds=(_d.get('result') or _d).get('commands') or []   # result 래퍼가 없는 형태도 있다(실측)
def nm(c): return c.get('command') or ' '.join(c.get('path') or [])
hits=[c for c in cmds if q in nm(c).lower()]
if not hits:
    print(f'"{q}" 에 맞는 명령 없음. 가까운 것:')
    for m in difflib.get_close_matches(q,[nm(c) for c in cmds],n=8,cutoff=0.3): print('  ',m)
    sys.exit(1)
for c in hits[:5]:
    print(f"### orca {nm(c)}")
    if c.get('summary'): print(f"  {c['summary']}")
    if c.get('usage'):   print(f"  usage: {c['usage']}")
    fl=c.get('flags') or []
    if fl: print("  flags: " + ' '.join('--'+f for f in fl))
    pa=c.get('positionalArgs') or []
    if pa: print("  args : " + ' '.join(str(p) for p in pa))
    for e in (c.get('examples') or [])[:4]: print(f"  예) {e}")
    for n in (c.get('notes') or [])[:4]:    print(f"  ※ {n}")
    print()
PY
}

# ── OpenClaw 도 문서를 로컬에 번들한다 (2026-07-29 발견) ──────────────────────
# Orca 에서 worker_done 을 재발명한 뒤, OpenClaw 에서 command-dispatch 를 또 재발명했다.
# 원인이 같다: 설치본 문서를 안 읽었다. 두 번 같은 실수를 했으니 둘 다 도구로 막는다.
# ⚠️ OpenClaw 는 미니PC 에만 설치돼 있다. 랩탑에서는 '없음' 이라고 정직히 말한다.
oc_docs_dir() {
  local p
  for p in "${OPENCLAW_DOCS:-}" \
           "$HOME/.npm-global/lib/node_modules/openclaw/docs" \
           "/usr/lib/node_modules/openclaw/docs" \
           "/usr/local/lib/node_modules/openclaw/docs"; do
    [ -n "$p" ] && [ -d "$p" ] && { printf '%s' "$p"; return 0; }
  done
  # npm 이 있으면 물어본다(느려서 마지막)
  p=$(npm root -g 2>/dev/null)/openclaw/docs
  [ -d "$p" ] && { printf '%s' "$p"; return 0; }
  return 1
}

case "${1:-}" in
  oc-find)
    d=$(oc_docs_dir) || { echo "OpenClaw 설치본 문서를 찾지 못했습니다 (이 머신에 없을 수 있음)" >&2; exit 1; }
    [ -n "${2:-}" ] || { echo "사용: $0 oc-find <패턴>" >&2; exit 1; }
    printf '문서: %s\n\n' "$d"
    grep -rn --include='*.md' -i -- "$2" "$d" 2>/dev/null \
      | sed "s|^$d/||" | head -"${3:-40}"
    ;;
  oc-doc)
    d=$(oc_docs_dir) || { echo "OpenClaw 설치본 문서 없음" >&2; exit 1; }
    [ -n "${2:-}" ] || { echo "사용: $0 oc-doc tools/skills.md" >&2; exit 1; }
    [ -r "$d/$2" ] || { echo "없음: $d/$2" >&2; exit 1; }
    cat "$d/$2"
    ;;
  oc-list)
    d=$(oc_docs_dir) || { echo "OpenClaw 설치본 문서 없음" >&2; exit 1; }
    printf '문서 루트: %s\n' "$d"
    (cd "$d" && find . -name '*.md' | sed 's|^\./||' | sort) | head -"${2:-60}"
    ;;
  list)
    ensure
    ls "$CACHE"/*.md 2>/dev/null | xargs -r -n1 basename | sed 's/\.md$//' | sed 's/^/  /'
    ;;
  guide)
    [ -n "${2:-}" ] || { echo "사용: $0 guide <이름>  (목록: $0 list)" >&2; exit 1; }
    ensure
    [ -r "$CACHE/$2.md" ] || { echo "가이드 '$2' 없음 — '$0 list' 확인" >&2; exit 1; }
    cat "$CACHE/$2.md"
    ;;
  cmd)
    [ -n "${2:-}" ] || { echo "사용: $0 cmd \"worktree create\"" >&2; exit 1; }
    ensure; cmd_schema "$2"
    ;;
  refresh) do_refresh ;;
  check)
    printf '실행파일 : %s\n' "$(orca_exe || echo '없음')"
    printf '캐시     : %s\n' "$CACHE"
    printf '가이드   : %s개\n' "$(ls "$CACHE"/*.md 2>/dev/null | wc -l)"
    printf '지문     : 저장=%s 현재=%s\n' \
      "$(cat "$CACHE/.fingerprint" 2>/dev/null || echo 없음)" "$(fingerprint || echo 조회실패)"
    if need_refresh; then echo '상태     : 갱신 필요'; else echo '상태     : 최신'; fi
    ;;
  *)
    cat <<EOF
orca-docs.sh — Orca 공식 문서를 복사하지 않고 최신으로 읽는다

Orca:
  list                     공식 가이드 목록
  guide <이름>             가이드 전문 (orca-cli / orchestration / computer-use …)
  cmd "worktree create"    그 명령의 정확한 플래그
  check                    캐시 상태
  refresh                  강제 갱신

OpenClaw (설치본 문서 직접 조회 — 미니PC 에만 있음):
  oc-list [n]              문서 파일 목록
  oc-find <패턴> [n]       전 문서 grep  (예: oc-find command-dispatch)
  oc-doc tools/skills.md   문서 전문

정본은 CLI/패키지에 번들된 문서다.
md 로 복사하지 않는 이유: 업데이트마다 낡고, 낡은 문서는 없는 것보다 나쁘다.
2026-07-29: 이걸 안 읽어서 Orca 의 worker_done 과 OpenClaw 의 command-dispatch 를
연달아 재발명했다. 짜기 전에 여기부터 본다.
EOF
    exit 1 ;;
esac
