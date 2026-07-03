#!/usr/bin/env bash
# sloplint 회귀 테스트 — 픽스처 기반 (qualityloop 1호 라운드에서 신설, 2026-07-03)
set -u
cd "$(dirname "$0")"
fails=0
check() { # desc, expected_exit, actual_exit
  if [ "$2" = "$3" ]; then echo "  [OK] $1 (exit $3)"; else echo "  [FAIL] $1 — expect $2 got $3"; fails=$((fails+1)); fi
}

out=$(node sloplint.mjs "file://$PWD/fixtures/slop.html" 2>&1); rc=$?
check "slop.html → 신호 검출(exit 1)" 1 $rc
hits=$(echo "$out" | grep -c '✗')
[ "$hits" -ge 8 ] && echo "  [OK] slop.html 신호 ${hits}/11 (≥8)" || { echo "  [FAIL] slop.html 신호 ${hits}<8"; fails=$((fails+1)); }

node sloplint.mjs "file://$PWD/fixtures/clean.html" >/dev/null 2>&1; rc=$?
check "clean.html → clean(exit 0)" 0 $rc

# 플래그 순서 무관 (--json <url>) + JSON 유효성
jout=$(node sloplint.mjs --json "file://$PWD/fixtures/clean.html" 2>/dev/null); rc=$?
check "--json <url> 순서 동작" 0 $rc
echo "$jout" | python3 -c "
import json,sys
d=json.load(sys.stdin); assert d['total']==11
ids={f['id'] for f in d['findings']}
want={'slop-font','purple-gradient','gradient-text','uniform-radius','icon-box-grid','badge-above-h1','emoji-headings','allcaps-eyebrow','stats-banner','numbered-steps','spacing-monotony'}
assert ids==want, ids^want
" 2>/dev/null \
  && echo "  [OK] --json 유효(11규칙 id 전수)" || { echo "  [FAIL] --json 규칙 id"; fails=$((fails+1)); }

# 특이도 경계: 강신호 정확히 1개 → exit 0 + 경고 (게이트의 핵심 계약 — judge R3 major)
sout=$(node sloplint.mjs "file://$PWD/fixtures/single-strong.html" 2>&1); rc=$?
check "single-strong.html → 경고+통과(exit 0)" 0 $rc
echo "$sout" | grep -q '강신호 1건' && echo "  [OK] 단일 강신호 경고문 출력" || { echo "  [FAIL] 경고문 없음"; fails=$((fails+1)); }

# 결정론: 같은 페이지 2회 실행 = 동일 결과 (AC1 — judge R3 major)
j1=$(node sloplint.mjs --json "file://$PWD/fixtures/slop.html" 2>/dev/null)
j2=$(node sloplint.mjs --json "file://$PWD/fixtures/slop.html" 2>/dev/null)
[ "$j1" = "$j2" ] && echo "  [OK] 결정론(2회 실행 diff 0)" || { echo "  [FAIL] 2회 실행 결과 상이"; fails=$((fails+1)); }

node sloplint.mjs 2>/dev/null; rc=$?
check "무인자 → usage(exit 2)" 2 $rc

echo; [ $fails -eq 0 ] && echo "PASS (sloplint_test)" || echo "FAIL ${fails}건"
exit $([ $fails -eq 0 ] && echo 0 || echo 1)
