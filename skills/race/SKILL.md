---
name: race
description: Use when the user says race/레이스/경쟁 구현/blind judge, or two or three materially different implementations must compete before an expensive decision. Uses isolated candidates, equal inputs and budgets, anonymous artifacts, two fresh judges, and a user gate before integration. Scope split with qualityloop — race = 복수의 실제 구현을 격리해 경쟁시킬 때(후보/DRAW/STOP); 단일 고정 산출물의 품질 채점·수정 루프는 qualityloop.
---

# race — 실제 대안의 엄격한 경쟁

Race는 아이디어를 많이 내는 Plan Council이 아니다. **서로 다른 가설을 실제 산출물과 동일한 test로 비교**하는 고비용 모드다.

## 불변식

- 후보 2~3개, 같은 sealed brief/rubric/base SHA/budget
- 후보별 별도 worktree/HOME/XDG/memory/session
- worktree는 checkout 격리일 뿐 보안 격리가 아님
- 후보별 writer 1명, child agent 0
- sibling 산출·worktree·message 열람 금지
- candidate commit과 artifact는 barrier 뒤 한 번만 제출
- fresh read-only judge 2명이 익명 bundle을 독립 채점
- D1 또는 D2가 0이면 승리 불가, judge 불일치나 평균 margin `<8`이면 DRAW
- 사용자가 선택하기 전 merge·loser cleanup 금지

## 소유권

- **Resource Provisioner:** worktree·HOME·terminal을 만들고 live base/head/분리 상태를 검증. ⚠️ **`MANUAL_LIMITED` — 이 실행기는 아직 없다**(보고서 §11). 그때까지는 코디네이터가 수동 수행하고 **격리 증거를 첨부**한다; 증거 없으면 race를 PASS로 닫지 않는다.
- **Orca orchestration:** root/child/deps/dispatch/worker_done/retry/gate lifecycle
- **`orca-council.py`:** sealed input·candidate hash·opaque Orca reference·anonymous bundle·score·사용자 결정
- **Finalizer:** 승인 뒤 test→integration→push/PR→cleanup→orphan 0

Artifact ledger가 `orca-bootstrap`, `orca-reconcile`, judge dispatch를 수행하지 않는다.

## 실행 흐름

1. Provisioner가 후보 자원을 만들고 base SHA·서로 다른 worktree/HOME/session을 검증한다.
2. `orca-council.py init --mode race ... --base-sha <sha>`로 brief/rubric을 봉인한다.
3. Orca에 root와 후보 task를 parent/deps로 만들고 `dispatch --inject`한다.
4. 각 Orca ID를 ledger `bind`에 기록한다. 상태는 복사하지 않는다.
5. Orca가 유효한 `worker_done`을 인정하고 실제 commit/test/artifact가 존재할 때 candidate를 `submit`한다.
6. 모든 후보가 봉인되면 `judge-bundle`; Orca가 fresh judge 2개를 dispatch한다.
7. 두 judge JSON을 `score`로 결정론 재계산한다.
8. 사용자가 익명 라벨 `X/Y/Z`, `DRAW`, `STOP`을 결정한다.
9. 승인된 선택만 finalizer가 통합하고 나머지를 정리한다.

정확한 worker contract와 finalizer는 `/orca-trio` references를 따른다. 과거 상세 명령은 [v1 기록](references/v1-legacy.md)에 보존돼 있지만, lifecycle 중복 명령은 사용하지 않는다.

## 실패

- infra retry는 동일 입력으로 1회
- duplicate/late/stale `worker_done`은 상태를 두 번 바꾸지 않음
- 후보 2개 미만, base/hash drift, sibling leak, judge prompt injection이면 winner 없이 중단
- coordinator restart 뒤 Orca task와 Git/artifact hash를 재조회; ledger의 과거 status를 신뢰하지 않음
