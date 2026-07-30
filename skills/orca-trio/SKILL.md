---
name: orca-trio
description: Use when the user says orca trio/오르카 크루/Orca coordinator/agent crew, or asks to create, attach, supervise, recover, or finish coordinated Orca terminals and worktrees. Orca orchestration owns task lifecycle; this skill supplies role, ownership, recovery, and finalization contracts.
---

# orca-trio — Orca coordinator crew

## 라이브 계약 먼저

이 스킬은 역할·소유권 정책만 보유한다. Orca 명령과 플래그의 정본은 설치된
바이너리다. 시작 전에 선택한 동일 실행파일로 다음 두 가이드를 전문 로드한다.

```text
ORCA skills get orca-cli
ORCA skills get orchestration --full
```

하나라도 실패하면 정확한 오류를 보고하고 중단한다. 이 스킬이나 로컬 md에서
기억한 명령으로 대체하지 않는다.

## 핵심 정의

Orca terminal 여러 개가 아니라 다음이 있을 때만 agentic crew다.

- exact task ID, parent, deps, dispatch ID
- 역할별 read/write 범위
- `worker_done`을 task/dispatch/assignee와 대조
- 죽은 worker·중복 완료·재시작을 복구
- 사용자 승인 없는 merge/deploy 금지
- 종료 때 terminal/worktree/untracked orphan 0

## 소유권

```text
Orca orchestration  = task/dispatch/worker_done/ask/gate의 lifecycle 정본
Artifact ledger     = 봉인 brief, 산출 hash, claim, score, 사용자 결정
Git + tests         = 코드와 완료 사실
Coordinator         = DAG·권한·gate; 제품 파일 read-only
Writer              = worktree당 한 명
Reviewer            = 고정 commit read-only 검토
Finalizer           = test→integration→push/PR→cleanup
```

Artifact ledger가 Orca task 상태를 복제하거나 Orca CLI를 대신 호출하지 않는다.

**plan → spec 인계 (2026-07-29 감사):** coordinator는 제품 파일 read-only이고 plan 모드의 writer는 0이다. 따라서 ADOPT 뒤 `/specpack`이 repo에 문서를 쓰려면 **명시적 writer task로 인계**한다 — coordinator가 직접 쓰지 않고, 인계 없이 방치해 아무도 쓰기 소유권을 갖지 않는 상태로 파이프라인을 멈추지도 않는다. coordinator는 결과 hash만 받는다.

## 모드

- **plan:** 제품 파일 writer 0. 고스테이크면 `/kickoff`의 3 lanes × 2 backbones Council.
- **build:** writer 1 + read-only reviewer. 같은 mutable worktree에 writer 둘 금지.
- **race:** 후보마다 worktree/HOME/XDG/memory/session을 분리하고 같은 brief/rubric/base로 경쟁. 후보 child agent 금지.

## 시작 전 라우팅

1. 현재 terminal/worktree의 exact handle과 full worktree ID를 조회한다.
2. 같은 worktree의 기존 crew와 active task를 확인해 중복 생성을 막는다.
3. task가 독립 병렬화되지 않으면 trio를 만들지 않고 duo/단일 세션으로 강등한다.
4. 새 worker의 위치·생성·dispatch 방식은 방금 로드한 라이브 가이드로 결정한다.
5. 이 WSL 호스트에서는 worker 시작만 직렬화한다: terminal 하나 생성 → `tui-idle`
   확인 → 다음 terminal 생성. 모두 ready 뒤 task dispatch는 병렬로 한다. Orca가
   runtime Codex hook bundle을 재생성하는 동안 동시 시작하면 한 terminal이
   `codex-hooks-review-prompt`에 걸릴 수 있다. 이때 effective hook을 검토·신뢰하기
   전에는 dispatch하지 않는다.
6. 장수 조정은 라이브 orchestration lifecycle을 사용하고 exact task/dispatch ID를 검증한다.

## Coordinator 루프

1. brief를 파일로 봉인하고 context boundary 기준으로 DAG를 만든다.
2. 모든 node를 parent/deps와 함께 먼저 등록한다.
3. ready node만 라이브 가이드가 지정한 방식으로 worker에 dispatch한다.
4. 라이브 가이드의 blocking wait로 완료·escalation·decision gate를 기다린다.
5. 완료 메시지는 exact `(task_id, dispatch_id, assignee)`가 맞고 산출물이 실제 존재할 때만 인정한다.
6. 성공 node만 dependent를 해제한다. 실패는 retry/reassign/cancel 정책으로 처리한다.
7. 모든 상태 변경은 Orca에서 하고, artifact ledger에는 ID와 결과 hash만 기록한다.

워커 완료 계약과 복구 체크리스트는 [worker contract](references/worker-contract.md), 종료 절차는 [finalization](references/finalization.md)을 따른다.

## 안 하는 것

- terminal before/after diff를 lifecycle ID로 간주
- 화면의 “완료” 문구만 보고 task 완료 처리
- coordinator가 제품 파일 수정
- 같은 worktree의 병렬 writer
- worktree를 보안 격리라고 표현
- finalizer 없이 merge 후 terminal/worktree를 방치
