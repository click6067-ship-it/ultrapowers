---
name: ship
description: Use when the user says 배포해/배포까지/푸시하고 배포/커밋하고 마무리/ship/실배포 ㄱㄱ/푸시하고 끝내, or a finished change needs the full finish chain. Runs the standardized ship pipeline — verify.sh → author-email check → scoped commit → push → deploy (vercel or push-triggered) → live vcheck screenshot — and reports evidence (commit hash, deploy URL, render check). Replaces the manually-repeated "커밋·푸시·배포·확인해줘" chain (실측: 47개 세션에서 반복).
---

# ship — 커밋→푸시→배포→검증 표준 마무리 체인

**목적.** 로그 실측상 가장 자주 반복된 수동 지시("푸시하고 배포까지", "커밋하고 마무리", "배포 확인")를 한 체인으로. **새 도구가 아니라 기존 게이트들의 고정 순서** — 각 단계는 이미 있는 것(verify.sh·git·vercel·vcheck)이고, ship은 순서·증거·함정 체크를 강제한다.

## 체인 (순서 고정 — 건너뛰면 그 이유를 출력)

### 1. 검증 게이트 (증거 없이 배포 없음)
```bash
bash $COMMAND_CENTER/system/verify.sh   # 스택 감지 → test·typecheck·lint·build
```
FAIL이면 **여기서 멈추고 보고** — "일단 배포"는 없다. (사용자가 명시적으로 "검증 스킵"하면 스킵을 기록하고 진행.)

### 2. 커밋 (함정 체크 내장)
- **author 이메일 확인** (Vercel 미스매치 차단 이력): `git log -3 --format=%ae` — 기존 배포 이메일과 다르면 멈추고 확인. 기본 신원 = `click6067-ship-it <you@example.com>`.
- **`git diff --shortstat` 확인** — `NNN files, 0 insertions(+)`(deletions-only)면 truncate 손상 신호 → 멈춤 (2026-07-07 $COMMAND_CENTER 사고 교훈).
- **의도한 경로만 add** (`git add -A` 금지 — 샌드박스 /dev/null 마스크 함정). 커밋 메시지는 변경 요약으로.

### 3. 푸시
- force-push 금지(guardrail이 어차피 차단). 현재 브랜치 → origin. main/master 직푸시는 이 repo의 기존 관행을 따른다(관행 불명이면 확인).

### 4. 배포 (프로젝트 타입 자동 감지)
| 감지 | 행동 |
|---|---|
| `.vercel/` 또는 vercel 연동 repo | `vercel:deploy` (기본 preview; 사용자가 "프로덕션/실배포/prod" 명시했을 때만 prod) |
| push-트리거 자동배포 (Render·Netlify·GitHub Pages 등) | 푸시가 곧 배포 — 배포 완료를 라이브 URL로 확인 |
| 배포 대상 없음 (라이브러리·스크립트) | 커밋+푸시에서 종료, "배포 대상 없음" 명시 |

### 5. 라이브 검증 (배포했으면 필수)
```bash
node ~/.claude/tools/headless/vcheck.mjs <배포 URL>
```
데스크톱+모바일 스크린샷을 **Read로 직접 보고** 판정 — JSON만 믿지 않기. 콘솔 에러·가로 오버플로 보고. **완료 기준 = 렌더 확인까지** (푸시 성공 ≠ 배포 성공).

### 6. 증거 브리핑 (1블록)
```
✅ ship 완료
- verify: PASS (test N·lint OK)
- commit: <hash> "<메시지>" (author 확인됨)
- deploy: <URL> (preview|prod)
- vcheck: 렌더 OK · 콘솔에러 0 · 오버플로 없음
```

## 안 하는 것
- verify FAIL 상태로 배포 (명시적 스킵 지시 없이는).
- 프로덕션 배포를 사용자 명시 없이 (기본 = preview).
- force-push · `git add -A` · author 미확인 커밋.
- 여러 프로젝트 동시 ship (한 번에 한 repo).
