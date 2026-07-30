# 🎯 Phase 0 — 짓기 전에 정의

새 프로젝트·방향이 열린 기능·되돌리기 비싼 결정은 코드 전에 다음을 거친다.

```text
Intake → Seal → EXPLORE → HARDEN → 사용자 gate
```

- **Intake:** 해법보다 문제(JTBD), 대상 사용자, 관측 가능한 성공, 제약, 비목표를 확정한다. 답이 계획을 바꾸는 질문만 `BLOCKER/RISK`로 남긴다. 명확한 1줄 잡일은 건너뛴다.
- **Seal (Council 경로 한정):** 원본 brief와 rubric을 hash로 봉인한다 — 절차는 `/kickoff`가 소유한다. 경량 경로에서는 brief를 대화에 고정하는 것으로 갈음한다. 어느 쪽이든 방향을 바꾸는 새 정보가 나오면 기존 run을 덮어쓰지 않고 새 run을 만든다.
- **EXPLORE:** 아이디어 생성 단계. first-principles·reference-first·distant-analogy를 서로 보지 못하게 발산한다. **모든 draft가 봉인되기 전에는 어떤 종합도 열지 않는다(전역 barrier)** — lane 하나가 먼저 끝나도 조기 종합·sibling 공개는 금지다. 먼저 끝난 안이 사실상 기준안이 되어 나머지를 오염시킨다. 이 단계에는 전면적인 kill condition·premortem·상대안 비평을 넣지 않는다.
- **HARDEN:** 발산물이 봉인된 뒤 주장 분해, 근거 검증, kill condition, premortem, refuter, judge를 직렬 적용한다.
- **사용자 gate:** `ADOPT / PIVOT / STOP`. 승인 전 구현·merge·deploy 금지.

사용자가 kickoff·풀파워 기획을 명시했거나 고비용 방향결정이면 `/kickoff`의 **3 lanes × 실제 Fable/GPT‑Sol 2 backbones**를 쓴다. 한 lead의 동종 subagent 여러 개는 다중 백본으로 세지 않는다.

Prior-art는 universal 선행 단계가 아니다. **Reference-first는 EXPLORE의 Plan B**에만 먼저 들어가며, **Plan A(first-principles)와 Plan C(distant-analogy)**에는 봉인 전 노출하지 않는다. 이 규칙은 `rules/design-antislop.md`의 "레퍼런스 먼저"보다 **우선한다** — design-antislop의 강제 순서는 kickoff EXPLORE lane 산출물에는 적용되지 않고 구현 단계부터 적용된다.

강도는 `모호성 × 잘못 결정했을 때의 비용`에 비례한다. Council·deep research는 자동발동하지 않되, 사용자가 이번 요청에서 깊은 조사·풀파워를 명시하면 다시 묻지 않는다.
