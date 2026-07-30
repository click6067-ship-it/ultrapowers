---
name: newproject
description: Use when the user says 새 프로젝트/newproject/프로젝트 시작/이 repo 부트스트랩/프로젝트 셋업, or a ghq repo has no CLAUDE.md and needs onboarding. Bootstraps a new project so any future session immediately knows context and direction — lightweight Intake, project CLAUDE.md, ~/main/projects registration, and kickoff routing for high stakes. 2026-07-30 온보딩 자동화 ①.
---

# /newproject — 프로젝트 부트스트랩

새 repo에서 1회 실행해, 이후 모든 세션이 길 잃지 않고 시스템을 바로 쓰게 만든다.
산출물은 셋: **프로젝트 CLAUDE.md · ~/main/projects/<name>.md 등록 · (고스테이크면)
kickoff 제안**. 문서는 Intake 답변만큼만 — 긴 문서 양산 금지.

## 절차

1. **위치 확인**: cwd가 git repo 루트인지(`git rev-parse --show-toplevel`), ghq
   컨벤션(`~/ghq/github.com/<owner>/<repo>`)인지. ~/main에서는 실행하지 않는다
   (메타 허브는 자체 CLAUDE.md 소유).
2. **현황 실측**: `bash ~/main/system/project-status.sh` 실행 — 이미 CLAUDE.md가
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
     `bash ~/main/system/project-status.sh` 로 실측

   ## 이 repo에서의 라우팅 (전역 routing.md 발췌)
   - 구현: writer 1 + TDD / 리뷰: 반대백본 read-only (orca-trio)
   - 기획 고스테이크: /kickoff · 중간: plan-panel
   - 마무리: verify → 사용자 ship gate → /ship

   ## 금지
   - <프로젝트 고유 금지사항 — 없으면 "전역 규칙 외 없음">
   ```
5. **~/main/projects/<name>.md 등록** — frontmatter(`status: active` +
   결정 기한 있으면 `decide_by`) + 3줄 요약. doctor·SessionStart 브리핑이
   이 파일을 읽는다.
6. **확인**: 새 세션 관점 검증 —
   `echo '{"cwd":"<repo>"}' | python3 ~/main/system/recent-context.py | tail -6`
   에 프로젝트 브리핑이 뜨는지 실측. 커밋은 사용자 승인 후(프로젝트 repo 규칙에
   따름).

## 하지 않는 것

- PRD/설계 문서 생성 (그건 /specpack — 승인된 방향이 있을 때)
- 상태 수치를 CLAUDE.md에 박제 (probe 원칙)
- ~/main CLAUDE.md·전역 규칙 수정
