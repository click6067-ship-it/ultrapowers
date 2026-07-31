---
name: newproject
description: Use when the user says 새 프로젝트/newproject/프로젝트 시작/이 repo 부트스트랩/프로젝트 셋업, or a ghq repo has no CLAUDE.md and needs onboarding. Bootstraps a new project so any future session immediately knows context and direction — lightweight Intake, project CLAUDE.md, $COMMAND_CENTER/projects registration, and kickoff routing for high stakes. 2026-07-30 온보딩 자동화 ①.
---

# /newproject — 프로젝트 부트스트랩

새 repo에서 1회 실행해, 이후 모든 세션이 길 잃지 않고 시스템을 바로 쓰게 만든다.
산출물은 셋: **프로젝트 CLAUDE.md · $COMMAND_CENTER/projects/<name>.md 등록 · (고스테이크면)
kickoff 제안**. 문서는 Intake 답변만큼만 — 긴 문서 양산 금지.

## 절차

1. **위치 확인**: cwd가 git repo 루트인지(`git rev-parse --show-toplevel`), ghq
   컨벤션(`~/ghq/github.com/<owner>/<repo>`)인지. $COMMAND_CENTER에서는 실행하지 않는다
   (메타 허브는 자체 CLAUDE.md 소유).
2. **현황 실측**: `bash $COMMAND_CENTER/system/project-status.sh` 실행 — 이미 CLAUDE.md가
   있으면 덮지 말고 사용자에게 보강할지 묻는다.
3. **경량 Intake** (답이 계획을 바꾸는 질문만, AskUserQuestion 1회 이내):
   - 이 프로젝트가 푸는 문제(JTBD) 한 문장 / 대상 사용자
   - 관측 가능한 성공 기준 1~2개 / 비목표 1~2개
   - 스테이크: 새 방향·되돌리기 비싼 결정인가? → **높으면 CLAUDE.md 생성 후
     `/kickoff`를 제안하고 멈춘다** (Phase 0 gate 소유권 존중)
4. **프로젝트 CLAUDE.md 생성** — 아래 골격, 전체 30줄 이내:
   ```markdown
   # <name> — 프로젝트 컨텍스트
   > 🤖 이 repo 전용. 전역 규칙 상속. 생성: YYYY-MM-DD (/newproject)

   ## 무엇 (3줄 이내)
   - 문제/대상: <Intake 답>
   - 성공: <관측 가능 기준>
   - 비목표: <명시>

   ## 현 단계
   - <기획|구현|운영> — 상세·최신 상태는 문서 박제 금지:
     `bash $COMMAND_CENTER/system/project-status.sh` 로 실측

   ## 이 repo에서의 라우팅 (전역 routing.md 발췌)
   - 구현: writer 1 + TDD / 리뷰: 반대백본 read-only (orca-trio)
   - 기획 고스테이크: /kickoff · 중간: plan-panel
   - 마무리: verify → 사용자 ship gate → /ship

   ## 금지
   - <프로젝트 고유 금지사항 — 없으면 "전역 규칙 외 없음">
   ```
5. **테스트 러너 스캐폴드** (2026-07-30 — 하한 게이트의 바닥): 스택에 맞는 최소
   테스트 1개를 **실패 상태로** 만든다(예: `tests/test_smoke.py`에 핵심 동작 1개를
   미구현 전제로 단언, node면 `package.json`에 `"test"` 스크립트 + 실패 스펙 1개).
   이유: verify.sh의 PASS는 테스트 0이면 lint/build만의 통과다(`NO_TESTS` 표시) —
   테스트 0으로 출발한 프로젝트는 테스트 소유권 장치 전체(TEST_GAP·타겟 테스트)가
   무효가 된다. 첫 실패 테스트가 곧 첫 Target Test다. 사용자가 명시로 거절하면 생략.
6. **$COMMAND_CENTER/projects/<name>.md 등록** — frontmatter(`status: active` +
   결정 기한 있으면 `decide_by`) + 3줄 요약. doctor·SessionStart 브리핑이
   이 파일을 읽는다.
7. **확인**: 새 세션 관점 검증 —
   `echo '{"cwd":"<repo>"}' | python3 $COMMAND_CENTER/system/recent-context.py | tail -6`
   에 프로젝트 브리핑이 뜨는지 실측. 커밋은 사용자 승인 후(프로젝트 repo 규칙에
   따름).

## 하지 않는 것

- PRD/설계 문서 생성 (그건 /specpack — 승인된 방향이 있을 때)
- 상태 수치를 CLAUDE.md에 박제 (probe 원칙)
- $COMMAND_CENTER CLAUDE.md·전역 규칙 수정
