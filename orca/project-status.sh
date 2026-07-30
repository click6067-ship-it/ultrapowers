#!/usr/bin/env bash
# project-status.sh — 프로젝트 상태를 문서 박제 대신 실측으로 출력 (온보딩 ③)
# 사용: project-status.sh [repo경로]   (기본: 현재 폴더의 git root)
# 원칙: 상태표를 md에 쓰면 반나절이면 썩는다(2026-07-30 검증 실증) — 상태는 항상 probe.
set -euo pipefail

REPO=$(git -C "${1:-.}" rev-parse --show-toplevel 2>/dev/null) || {
  echo "git repo가 아님: ${1:-$PWD}" >&2; exit 2; }
NAME=$(basename "$REPO")

echo "# ${NAME} — 실측 상태 ($(date '+%Y-%m-%d %H:%M %Z'))"
echo
BRANCH=$(git -C "$REPO" branch --show-current)
UP=$(git -C "$REPO" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "")
if [ -n "$UP" ]; then
  AHEAD=$(git -C "$REPO" rev-list --count "$UP"..HEAD)
  BEHIND=$(git -C "$REPO" rev-list --count HEAD.."$UP")
  echo "- branch: ${BRANCH} (upstream ${UP}, ahead ${AHEAD} behind ${BEHIND})"
else
  echo "- branch: ${BRANCH} (upstream 없음)"
fi
echo "- HEAD: $(git -C "$REPO" log -1 --format='%h %ci %s' | cut -c1-90)"
DIRTY=$(git -C "$REPO" status --porcelain | wc -l)
echo "- dirty: ${DIRTY}개 항목"

if [ -f "$REPO/DEVLOG.md" ]; then
  LAST_DEV=$(grep -m1 -oE '20[0-9]{2}-[0-9]{2}-[0-9]{2}' "$REPO/DEVLOG.md" || echo "?")
  echo "- DEVLOG.md: 있음 (최근 항목 ${LAST_DEV})"
else
  echo "- DEVLOG.md: 없음"
fi
[ -f "$REPO/CLAUDE.md" ] && echo "- CLAUDE.md: 있음" || echo "- CLAUDE.md: 없음 → /newproject 권함"

TESTS=$(find "$REPO" -maxdepth 2 \( -name '*test*.py' -o -name '*.test.*' -o -name '*_test.go' -o -name '*_test.sh' \) 2>/dev/null | head -5 | wc -l)
echo "- 테스트 파일(깊이2): ${TESTS}개 이상"

PROJ_MD=$(ls /home/click/main/projects/ 2>/dev/null | grep -i -m1 "$NAME" || true)
if [ -n "$PROJ_MD" ]; then
  FM=$(sed -n '2,4p' "/home/click/main/projects/$PROJ_MD" | tr '\n' ' ')
  echo "- ~/main/projects/${PROJ_MD}: ${FM}"
else
  echo "- ~/main/projects/ 등록: 없음"
fi

if [ -f "$REPO/vercel.json" ] || [ -d "$REPO/.vercel" ]; then
  echo "- vercel: 연동 흔적 있음 (배포 상태는 vercel:status로)"
fi
