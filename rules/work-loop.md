# 🔁 작업 루프

```text
Frame → Explore → Harden → User gate
→ Spec → Implementation plan → Build
→ Test → Independent review → User ship gate
→ Finalize → Compound
```

1. **Frame:** 문제·성공·제약·비목표를 확정한다.
2. **Explore/Harden:** 고스테이크만 `/kickoff`; 아이디어를 먼저 넓히고 봉인 뒤 반증한다.
3. **Spec:** `/specpack`으로 이번 결정과 테스트에 필요한 문서만 만든다. 독립 모듈일 때만 분해한다.
4. **Build:** writer 1명이 작은 검증 단위로 구현한다. read-only reviewer는 고정 commit을 본다.
5. **Verify:** 실제 test/lint/build/render 출력이 없으면 완료가 아니다. `verify.sh`가 check 0개면 `NOT_VERIFIED`다.
6. **Ship:** 사용자가 승인한 뒤 fetch→divergence 판정→test→integration/push/PR→cleanup 순으로 finalizer가 실행한다.
7. **Compound:** 반복 가능하고 검증된 교훈만 가까운 rule/test/runbook에 짧게 남긴다. 사고 전문을 상시 context에 넣지 않는다.

병렬화 기준:

- 서로의 중간 결과가 없어도 진행되는 읽기·기획·조사는 병렬
- 공유 mutable code와 의존 단계는 직렬
- Plan Council은 다른 백본·방법론·정보밭을 분리
- 구현은 worktree당 writer 1명
- 완료·merge·deploy는 barrier 뒤 수렴

상세 라우팅은 `routing.md`, Phase 0는 `phase0-gate.md`, Orca는 `/orca-trio`, 기획은 `/kickoff`가 소유한다.
