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

echo "▶ 커스텀 스킬 6 (vcheck·demo·kickoff·recall·remember·techreport) + spec-decompose(아래) = 7"
for s in vcheck demo kickoff recall remember techreport; do
  mkdir -p "$DST/skills/$s"; cp "$SRC/skills/$s/SKILL.md" "$DST/skills/$s/SKILL.md"
done

echo "▶ 커스텀 스킬: spec-decompose (SKILL.md + tools + templates)"
if [ -d "$SRC/skills/spec-decompose" ]; then
  backup "$DST/skills/spec-decompose"; rm -rf "$DST/skills/spec-decompose"
  cp -r "$SRC/skills/spec-decompose" "$DST/skills/spec-decompose"
  find "$DST/skills/spec-decompose" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi

echo "▶ hooks → ~/.claude/hooks/ (위치 독립)"
for h in recent-context.py export-sessions.py session-end-summary.py techreport-autopush.py; do
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

echo "▶ doctor + guardrail + verify + Codex config (안전 기본 — danger 없음, 키 placeholder)"
[ -f "$SRC/doctor.py" ] && cp "$SRC/doctor.py" "$DST/doctor.py"
[ -f "$SRC/guardrail.py" ] && cp "$SRC/guardrail.py" "$DST/guardrail.py"
[ -f "$SRC/verify.sh" ] && cp "$SRC/verify.sh" "$DST/verify.sh"
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
else
  backup "$DST/settings.json"
  cp "$_SUBST" "$DST/settings.deploy-template.json"
  echo "  ⚠️ 기존 settings.json 존재 → 덮지 않음(머신별 설정 보존). 병합 참고용: $DST/settings.deploy-template.json (필수키: env·hooks·enabledPlugins)"
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
   3) 로그인:  claude(OAuth) · codex login(ChatGPT) · vercel /mcp
   ※ 두 모델 워크플로라 Claude Max + Codex Pro 가정.
NEXT
