# 🎯 게이트와 루프 — 짓기 전에 정의, 선언 전에 증거

*(2026-07-31 phase0-gate + work-loop 통합 — 내용 무손실, 이력 = system/runbooks/rules-history-2026-07-31.md)*

## Phase 0 (새 방향·열린 기능·되돌리기 비싼 결정)

```text
Intake → Seal → EXPLORE → HARDEN → 사용자 gate
```

- **Intake**: 해법보다 문제(JTBD)·대상 사용자·관측 가능한 성공·제약·비목표 확정. 답이 계획을 바꾸는 질문만 BLOCKER로 되묻는다. 명확한 1줄 잡일은 스킵 — **강도 = 모호성 × 잘못 결정했을 때의 비용.**
- **Seal**: brief·rubric 봉인은 `/kickoff`(orca-council.py)가 소유. 경량 경로는 brief를 대화에 고정. 방향 바꾸는 새 정보 = 기존 run 덮지 말고 새 run.
- **EXPLORE (발산)**: kill condition·premortem 금지 — 조기 자기검열 방지. Council이면 3 lanes(first-principles·reference-first·distant-analogy) × Fable/GPT-Sol 2백본 blind — 동종 subagent 여럿은 다중 백본이 아니다. **모든 draft 봉인 전 종합 금지(전역 barrier)** — 먼저 끝난 안이 기준안이 되어 나머지를 오염시킨다. **Reference-first는 Plan B 전용** (A·C는 봉인 전 미노출; design-antislop의 "레퍼런스 먼저"보다 우선하며, 그 강제 순서는 ADOPT 후 구현 단계부터).
- **HARDEN (봉인 후)**: 주장 분해 → 근거 검증 → kill condition → premortem → refuter → judge 직렬.
- **사용자 gate**: `ADOPT / PIVOT / STOP`. **승인 전 구현·merge·deploy 금지.**

Council·deep research는 자동발동하지 않되, 사용자가 이번 요청에서 풀파워를 명시하면 다시 묻지 않는다.

## 작업 루프

```text
Frame → Explore/Harden → Spec → Build → Verify → Ship → Compound
```

1. **Frame**: 문제·성공·제약·비목표 확정. 고스테이크만 `/kickoff`.
2. **Spec**: `/specpack`으로 이번 결정·테스트에 필요한 문서만. 독립 모듈일 때만 spec-decompose.
3. **Build**: writer 1명이 작은 검증 단위로. 구현 계획·타겟 테스트 = writing-plans. read-only reviewer는 고정 commit을 본다.
4. **Verify**: 실제 test/lint/build/render 출력 없으면 완료가 아니다 — 판정 규칙은 routing의 결정론 게이트(verify.sh).
5. **Ship**: 사용자 승인 후 finalizer가 fetch→divergence 판정→test→push/PR→cleanup.
6. **Compound**: 반복 가능하고 검증된 교훈만 가까운 rule/test/runbook에 짧게. 사고 전문을 상시 context에 넣지 않는다.

## 병렬화 기준

- 서로의 중간 결과 없이 진행되는 읽기·기획·조사 = 병렬 / 공유 mutable 코드·의존 단계 = 직렬
- Plan Council은 백본·방법론·정보밭 분리 / 완료·merge·deploy는 barrier 뒤 수렴 (구현 직렬 규칙 = routing 표)

상세 라우팅 = routing.md · Orca crew = `/orca-trio` · 기획 절차 = `/kickoff`.
