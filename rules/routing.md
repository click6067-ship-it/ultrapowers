# 🧭 태스크 라우팅

비싼 하니스는 능력 과시가 아니라 **잘못된 결정을 줄일 때만** 쓴다.

| 상황 | 경로 |
|---|---|
| 명확·가역·작은 작업 | 바로 실행 → 관련 test |
| 모호하지만 저스테이크 | 짧은 Intake → 단일 plan |
| 새 프로젝트·고비용 방향결정 | `/kickoff` Plan Council 제안; 사용자가 명시했으면 즉시 실행 |
| 중간 스테이크 기능·모듈 설계 | `plan-panel` — kickoff와 상호배타 |
| 병렬 다중 에이전트 협업 | `orca-trio` 실터미널 crew 단일 표준 |
| 다출처 사실 조사 | 단발 검색 또는 `council-research`; 비용 큰 fan-out은 제안-first |
| 실제 대안의 동작 비교 | `/race`; 후보별 격리, 같은 rubric |
| 구현 | worktree당 writer 1 + TDD (계획·타겟 테스트 = writing-plans) |
| 핵심/엔진/데이터 리뷰 | fresh read-only 반대백본 reviewer |
| UI | render 확인 + vcheck; 방향 디자인이면 crit |
| 마무리 — 솔로·단일 repo | verify → 사용자 ship gate → `/ship` |
| 마무리 — 크루·worktree | verify → 사용자 ship gate → `/orca-trio` finalization (`orca-finalize-check.py` 7검사 PASS) |

도구 소유권: `/kickoff`=방향·Plan Council(orca-council은 그 실행 인프라) · `/specpack`=최소 충분 스펙 · `spec-decompose`=독립 모듈일 때만 · `writing-plans`=구현 단계·타겟 테스트 · Orca orchestration=장수 lifecycle · subagent=한 worker 내부의 짧고 bounded한 read-only 조사 · `/qualityloop`=완성물 최종 게이트(일상 코드 diff는 stop-review — 상호배타).

**결정론 게이트 (항상):**
- 완료 선언 전 실제 test/`system/verify.sh` — check 0개 = `NOT_VERIFIED`, 결과 없는 run은 PASS가 아니다
- 파괴 명령 = guardrail · 네트워크 변경 = `system/netcheck.sh` · merge·deploy·외부 발행 = 사용자 승인

상황별 긴 실행법은 해당 skill/runbook을 조건부로 읽는다 — 이 파일에서 반복하지 않는다.
