# 🧭 태스크 라우팅

비싼 하니스는 능력 과시가 아니라 **잘못된 결정을 줄일 때만** 쓴다.

| 상황 | 경로 |
|---|---|
| 명확·가역·작은 작업 | 바로 실행 → 관련 test |
| 모호하지만 저스테이크 | 짧은 Intake → 단일 plan |
| 새 프로젝트·고비용 방향결정 | `/kickoff` Plan Council 제안; 사용자가 명시했으면 즉시 실행 |
| 중간 스테이크 기능·모듈 설계 | `plan-panel` 단일 백본 패널 — kickoff와 상호배타 (2026-07-30 확정) |
| 병렬 다중 에이전트 협업 | `orca-trio` 실터미널 crew 단일 표준 — Agent Teams 은퇴 (2026-07-30 확정) |
| 다출처 사실 조사 | 단발 검색 또는 `council-research`; 비용 큰 fan-out은 제안-first |
| 실제 대안의 동작 비교 | `/race`; 후보별 격리와 같은 rubric |
| 구현 | worktree당 writer 1 + TDD |
| 핵심/엔진/데이터 리뷰 | fresh read-only Codex reviewer |
| UI | render 확인 + vcheck; 방향 디자인이면 crit |
| 마무리 — 솔로·단일 repo | verify → 사용자 ship gate → `/ship` |
| 마무리 — 크루·worktree | verify → 사용자 ship gate → `/orca-trio` finalization 계약(fetch→divergence 판정→orphan 0) |

도구 소유권:

- `/kickoff`: 방향과 Plan Council
- `/specpack`: 승인된 방향의 최소 충분 스펙 문서
- `spec-decompose`: 독립 모듈일 때만 스펙 트리
- `writing-plans`: 구현 단계와 테스트 순서
- Orca orchestration: 장수 task/dispatch/dependency/gate (orca-council은 별도 경로가 아니라 kickoff의 실행 인프라 — 2026-07-30)
- subagent: 한 worker 내부의 짧고 bounded한 read-only 조사
- `/qualityloop`: 완성물 최종 게이트·비코드 산출물·rubric 블라인드 채점 한정; 일상 코드 diff 리뷰는 stop-review 소유 — 상호배타 (2026-07-30 확정)

결정론 게이트는 항상 적용한다.

- 완료 선언 전 실제 test/`system/verify.sh`
- 파괴 명령은 guardrail
- 네트워크 변경은 `system/netcheck.sh`
- merge·deploy·외부 발행은 사용자 승인
- 결과가 없는 workflow run은 PASS가 아니라 `NOT_VERIFIED`

상황별 긴 실행법은 해당 skill/runbook을 조건부로 읽는다. 이 파일에서 모델 목록·스킬 전체 목록·사고 복구 절차를 반복하지 않는다.
