#!/usr/bin/env bash
# ultrapowers/install.sh — clone 후 한 번으로 ~/.claude에 설치. 위치 독립(스크립트 자기 위치 기준).
# 네 작동 시스템(command-center)은 COMMAND_CENTER env로 지정(기본 ~/main).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # = ultrapowers repo 루트(어디에 clone하든)
DST="$HOME/.claude"
CC="${COMMAND_CENTER:-$HOME/main}"                     # command-center 위치(메모·로그·보고서 홈)
mkdir -p "$DST/skills" "$DST/tools/headless" "$DST/hooks" "$CC/logs" "$CC/reports"

backup() { if [ -e "$1" ]; then cp -a "$1" "$1.bak.$(date +%s)"; fi; return 0; }

echo "▶ 행동규칙 CLAUDE.md"
backup "$DST/CLAUDE.md"; cp "$SRC/CLAUDE.md" "$DST/CLAUDE.md"

echo "▶ Codex 전역 헌법 AGENTS.md (~/.codex/AGENTS.md — 2모델 org의 Codex 절반, CLAUDE.md 대칭짝)"
if [ -f "$SRC/AGENTS.md" ]; then mkdir -p "$HOME/.codex"; backup "$HOME/.codex/AGENTS.md"; cp "$SRC/AGENTS.md" "$HOME/.codex/AGENTS.md"; fi

echo "▶ 커스텀 스킬 전수 설치 (v0.6: 17종 — kickoff·orca-trio·race·newproject·hallmark 포함)"
for sdir in "$SRC"/skills/*/; do
  s="$(basename "$sdir")"
  backup "$DST/skills/$s"; rm -rf "$DST/skills/$s"
  cp -r "$sdir" "$DST/skills/$s"
  find "$DST/skills/$s" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
done

echo "▶ hooks → ~/.claude/hooks/ (위치 독립)"
for h in recent-context.py export-sessions.py session-end-summary.py techreport-autopush.py subagent-log.py devlog.py uislop-check.py skill-nudge.py skill-usage-log.py orca-trio-guard.py session-end-runner.py redaction.py; do
  if [ -f "$SRC/hooks/$h" ]; then cp "$SRC/hooks/$h" "$DST/hooks/$h"; chmod +x "$DST/hooks/$h"; fi
done

echo "▶ 헤드리스 툴 (vcheck·demo·flipcheck)"
cp "$SRC"/tools/headless/{vcheck.mjs,demo.mjs,flipcheck.mjs,package.json,package-lock.json} "$DST/tools/headless/" 2>/dev/null || true
( cd "$DST/tools/headless" && npm ci >/dev/null 2>&1 && echo "  node_modules OK" ) || echo "  ⚠️ 'cd $DST/tools/headless && npm ci' 수동 실행 필요"
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "  ℹ️ WSL 감지 — vcheck/demo의 chromium은 시스템 libs(chromedeps)가 필요(이 레포 미번들). README 'WSL' 참조."
fi

echo "▶ statusline + 커스텀 서브에이전트 (researcher·verifier·redteam)"
[ -f "$SRC/statusline.py" ] && { backup "$DST/statusline.py"; cp "$SRC/statusline.py" "$DST/statusline.py"; }
if ls "$SRC"/agents/*.md >/dev/null 2>&1; then mkdir -p "$DST/agents"; cp "$SRC"/agents/*.md "$DST/agents/"; fi

echo "▶ doctor + guardrail + verify + doc2txt + netcheck + Codex config (안전 기본 — danger 없음, 키 placeholder)"
[ -f "$SRC/doctor.py" ] && cp "$SRC/doctor.py" "$DST/doctor.py"
[ -f "$SRC/guardrail.py" ] && cp "$SRC/guardrail.py" "$DST/guardrail.py"
[ -f "$SRC/verify.sh" ] && cp "$SRC/verify.sh" "$DST/verify.sh"
[ -f "$SRC/doc2txt.sh" ] && { cp "$SRC/doc2txt.sh" "$DST/doc2txt.sh"; chmod +x "$DST/doc2txt.sh"; }
[ -f "$SRC/netcheck.sh" ] && { cp "$SRC/netcheck.sh" "$DST/netcheck.sh"; chmod +x "$DST/netcheck.sh"; }
if ls "$SRC"/workflows/*.js >/dev/null 2>&1; then mkdir -p "$DST/workflows"; cp "$SRC"/workflows/*.js "$DST/workflows/"; fi
if [ -f "$SRC/codex.config.template.toml" ] && [ ! -f "$HOME/.codex/config.toml" ]; then
  mkdir -p "$HOME/.codex"; cp "$SRC/codex.config.template.toml" "$HOME/.codex/config.toml"
  echo "  ~/.codex/config.toml 생성(web_search·MCP, FIRECRAWL_API_KEY=placeholder → 실제 키로 교체)"
fi

echo "▶ settings.json (hook 경로 → ~/.claude/hooks/, command-center → $CC)"
_SUBST=$(mktemp)
sed -e "s#__CLAUDE__#$DST#g" -e "s#__CC__#$CC#g" "$SRC/settings.template.json" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); d.pop("_comment",None); json.dump(d,sys.stdout,ensure_ascii=False,indent=2)' > "$_SUBST"
if [ ! -f "$DST/settings.json" ]; then
  cp "$_SUBST" "$DST/settings.json"
  echo "  신규 생성(경로 치환). permissions.allow=[] — 편의 권한은 settings.local.example.json 참고해 본인 opt-in."
elif command -v jq >/dev/null 2>&1; then
  backup "$DST/settings.json"
  # env 머지: COMMAND_CENTER는 항상 존재 보장(기존 값 우선, 없으면 template=이번 설치의 $CC).
  #           LD_LIBRARY_PATH는 기존 값 보존(없을 때만 template) — 무조건 덮어쓰면 사용자 커스텀 파괴.
  if jq -s '.[0] as $live | .[1] as $tmpl | $live
      | .env = ((.env // {}) + {COMMAND_CENTER: (.env.COMMAND_CENTER // $tmpl.env.COMMAND_CENTER),
                                LD_LIBRARY_PATH: (.env.LD_LIBRARY_PATH // $tmpl.env.LD_LIBRARY_PATH)})
      | .enabledPlugins = ($tmpl.enabledPlugins + ($live.enabledPlugins // {}))
      | .extraKnownMarketplaces = (($tmpl.extraKnownMarketplaces // {}) + ($live.extraKnownMarketplaces // {}))
      | .statusLine = ($live.statusLine // $tmpl.statusLine)
      | .effortLevel = ($live.effortLevel // $tmpl.effortLevel)
      | .theme = ($live.theme // $tmpl.theme)
      | .hooks = (reduce ($tmpl.hooks | to_entries[]) as $e (($live.hooks // {});
          .[$e.key] = (((.[$e.key] // []) + $e.value) | group_by(.matcher)
            | map({matcher: .[0].matcher, hooks: (map(.hooks[]) | unique_by(.command))}))))
    ' "$DST/settings.json" "$_SUBST" > "$DST/settings.json.new"; then
    mv "$DST/settings.json.new" "$DST/settings.json"
    echo "  기존 settings.json 머지(env·hooks·plugins·statusLine, matcher 보존, idempotent). allow·plugin-disable 보존. 백업=.bak.*"
    echo "  env: COMMAND_CENTER 보장(기존 값 우선, 없으면 $CC) · LD_LIBRARY_PATH 기존 값 보존"
  else
    rm -f "$DST/settings.json.new"; cp "$_SUBST" "$DST/settings.deploy-template.json"
    echo "  ⚠️ jq 머지 실패 — 원본 유지(백업=.bak.*), 참고: $DST/settings.deploy-template.json"
  fi
else
  backup "$DST/settings.json"; cp "$_SUBST" "$DST/settings.deploy-template.json"
  echo "  ⚠️ jq 없음 → 자동머지 생략(반쪽머지 방지). 기존 유지(백업=.bak.*), 참고: $DST/settings.deploy-template.json"
fi
rm -f "$_SUBST"

echo "▶ 설치 검증 (doctor — codex auth·hooks·plugins·statusline·버전)"
[ -f "$DST/doctor.py" ] && { COMMAND_CENTER="$CC" python3 "$DST/doctor.py" 2>/dev/null || echo "  (doctor 스킵)"; }

cat <<NEXT

✅ ultrapowers 설치 완료. COMMAND_CENTER=$CC (지속하려면 shell rc에 'export COMMAND_CENTER=$CC')
   남은 수동 단계:
   1) 플러그인(세션 안, 직접):  /plugin install superpowers@claude-plugins-official · vercel@claude-plugins-official · codex@openai-codex
   2) MCP:    claude mcp add -s user context7 -- npx -y @upstash/context7-mcp
              claude mcp add -s user --transport http vercel https://mcp.vercel.com
              claude mcp add -s user --env FIRECRAWL_API_KEY=<키> firecrawl -- npx -y firecrawl-mcp
              # ~/.codex/config.toml 생성됨(context7+firecrawl) — FIRECRAWL_API_KEY placeholder를 실제 키로 교체
   3) 로그인:  claude(OAuth) · codex login(ChatGPT) · vercel /mcp
   ※ 두 모델 워크플로라 Claude Max + Codex Pro 가정.
NEXT

echo "▶ verify.sh (NOT_VERIFIED 계약: 실행 check 0개면 PASS가 아니라 exit 2)"
[ -f "$SRC/verify.sh" ] && { cp "$SRC/verify.sh" "$CC/system/verify.sh" 2>/dev/null || cp "$SRC/verify.sh" "$DST/verify.sh"; }

echo "▶ orca/ (선택 레이어 — Windows Orca ADE + WSL에서만 의미. 자동 설치하지 않음)"
echo "  Orca 사용 시: orca/README 격인 주석과 $SRC/orca/ 스크립트를 COMMAND_CENTER/system/ 에 복사 후"
echo "  orca/orca-docs.sh guide orca-cli 로 설치본 라이브 가이드부터 읽을 것."

echo "✅ install 완료. 다음 수동 단계: (1) ~/.secrets/api-keys.env 생성(chmod 600) (2) Claude Code 로그인 (3) codex 로그인"
