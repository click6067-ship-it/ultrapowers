<!-- v1 역사 기록. 현재 정본은 ../SKILL.md다. -->

# race — blind alternative competition

Race는 속도용 병렬화가 아니라 **평가 오염을 줄이는 고비용 대안 비교**다.
차이가 작은 구현안은 race하지 말고 writer 1명으로 만든다.

## 불변식

- Root coordinator만 장수 task·terminal·worktree를 만든다.
- 후보는 기본 2개, 최대 3개이며 유효 후보 2개 미만이면 winner 없이 중단한다.
- 후보마다 pinned base SHA의 별도 top-level worktree, HOME/XDG/cache/memory/session을 쓴다.
- Worktree는 checkout 격리일 뿐 보안 격리가 아니다. 필요하면 OS principal/VM을 추가한다.
- 후보마다 writer는 1명이며 Race 후보는 child agent를 만들 수 없다.
- Candidate는 sibling worktree/HOME/message와 alias mapping을 보지 못한다.
- Brief·rubric·base·budget·tool policy·config는 시작 전에 hash로 봉인한다.
- Candidate artifact는 commit barrier 뒤 한 번만 제출한다. Repair/synthesis는 새 후보다.
- Fresh read-only judge 2개가 다른 judge 점수를 보기 전 모든 익명 후보를 각각 채점한다.
- Merge·cleanup은 사용자 결정 전 금지다.

## 1. Race gate

다음을 모두 만족해야 한다: 서로 다른 falsifiable hypothesis, 공통 acceptance와 deterministic test,
후보별 비용·시간 cap, 고정 base SHA, 후보 2개+judge 2개 자원.
프롬프트 표현만 다르거나 테스트 없이 말로만 비교하면 race를 취소한다.

## 2. 봉인과 DAG

`brief.md`에는 원문과 동일 질문을, `rubric.md`에는 D1~D5·test·blocker·budget·권한을 기록한다.

```bash
BASE_SHA="$(git rev-parse HEAD)"
python3 ~/main/system/orca-council.py init \
  --mode race --slug <slug> \
  --brief <absolute-brief.md> --rubric <absolute-rubric.md> \
  --base-sha "$BASE_SHA" --candidates 2
```

1 byte라도 바뀌면 새 run이다. 후보별 다음 tuple을 manifest에 남긴다:
`slot | worktree ID/path | base | branch | HOME/XDG | memory | session | credential scope |
OS boundary | terminal | write lease | budget`.

후보 terminal을 시작할 때 각 후보의 실행환경 주장을 JSON으로 제출한다. 경로와 session은 후보마다
달라야 한다. Orca API로 live 확인할 수 없는 HOME·OS boundary는 `self-attested`로 기록하며 보안 격리
검증 완료로 부풀리지 않는다. `worktree-only`는 코드 checkout 격리일 뿐 보안 격리가 아니다.

```json
{
  "home": "/tmp/race/candidate-1/home",
  "xdg_config_home": "/tmp/race/candidate-1/xdg",
  "memory_root": "/tmp/race/candidate-1/memory",
  "session_id": "candidate-1-unique-session",
  "credential_scope": "none",
  "os_boundary": "worktree-only"
}
```

```bash
python3 ~/main/system/orca-council.py orca-bootstrap \
  --run <run_id> --coordinator-handle <term_coord> \
  --candidate-handle candidate-1=<term_1> \
  --candidate-handle candidate-2=<term_2> \
  --candidate-isolation candidate-1=<candidate-1-isolation.json> \
  --candidate-isolation candidate-2=<candidate-2-isolation.json>
```

부트스트랩은 live terminal/worktree 목록을 조회하여 후보별 worktree ID가 서로 다른지, coordinator와
겹치지 않는지, 같은 repo의 sealed base SHA에서 시작했는지 검증한다. HOME/XDG/memory/session은
서로 다른 자기증명 값인지 검증한다. 통과한 뒤에만 root/child task를 만들고 exact task/dispatch ID를
저장한다. 후보는 공통 brief/rubric에서 구현·테스트·고정 commit을 만들고 다른 후보를 보지 않는다.

## 3. Barrier와 익명 bundle

Worker_done 뒤 다음을 먼저 실행한다.

```bash
python3 ~/main/system/orca-council.py orca-reconcile --run <run_id>
```

Task·dispatch·assignee·completed가 일치한 후보만 받는다. 제출물은 고정 commit SHA,
clean status, artifact/patch, 실제 test exit code, cost/time, limitation/blocker를 포함한다.
`submit`은 random A/B/C mapping으로 불변 봉인한다. Race의 child trace는 반드시 비어 있다.

모든 후보가 봉인된 뒤:

```bash
python3 ~/main/system/orca-council.py judge-bundle --run <run_id>
```

Bundle에서 proposer·model·worktree path·angle·순서를 제거한다.

## 4. 두 fresh judge

```bash
python3 ~/main/system/orca-council.py orca-judges \
  --run <run_id> --coordinator-handle <term_coord> \
  --judge-handle judge-1=<term_judge_1> \
  --judge-handle judge-2=<term_judge_2>
```

각 judge는 `judgeId`를 포함한 JSON을 peer 공개 전에 봉인한다. Worker_done 뒤:

```bash
python3 ~/main/system/orca-council.py orca-reconcile --run <run_id>
python3 ~/main/system/orca-council.py score \
  --run <run_id> --judgment <judge-1.json> --judgment <judge-2.json>
```

규칙은 D1×3 + D2×3 + D3×2 + D4 + D5다. 근거 없는 점수는 무효다.
어느 judge에서든 D1/D2가 0이거나 blocker가 있으면 승리 불가다.
두 judge의 1위가 다르거나 평균 마진이 8 미만이면 DRAW다. 최종 judge는 사용자다.

## 5. 사용자 gate와 finalizer

사용자는 `A/B/C`, `DRAW`, `STOP`을 결정한다. 계산 결과를 뒤집으면 이유를 기록한다.

```bash
python3 ~/main/system/orca-council.py decide \
  --run <run_id> --choice <A|B|C|DRAW|STOP> [--reason <text>]
```

결정 뒤 clean finalizer가 다음 순서로 실행한다:
winner hash 재검증 → clean integration tree 적용 → test → fetch/divergence 판정 →
scoped commit/push/PR → clean 확인 → loser terminal stop/archive/worktree remove → orphan 0.
무조건 pull하지 않는다.

## 실패와 canary

- Lease 80%: 새 작업 금지. 100%·hash mismatch·partial/late result: winner 없이 중단.
- Infra retry는 동일 input으로 1회만 한다. Duplicate/stale worker_done은 상태를 두 번 바꾸지 않는다.
- Canary: input 1-byte mutation, sibling-HOME sentinel, unauthorized dispatch, judge prompt injection,
  recursive budget bomb, finalizer hash mutation, coordinator crash-resume, 종료 후 orphan 0.
