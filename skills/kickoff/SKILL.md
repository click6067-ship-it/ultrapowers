---
name: kickoff
description: Use when the user says kickoff/킥오프/기획 회의/기획안 비교/계획 레드팀/grill해, or a new high-stakes project or feature needs Phase 0 framing before code. Runs a proposal-first, multi-backbone Plan Council with blind divergence, adversarial hardening, non-advocate synthesis, and a user ADOPT/PIVOT/STOP gate.
---

# kickoff — Multi-backbone Plan Council

## 목적과 발동

코드 전에 문제·가설·비목표·성공기준을 고정하되, 한 모델의 첫 프레이밍에 전체 기획이 끌려가지 않게 한다.

- **기본 경로:** 명확하고 가역적인 작은 작업은 짧은 Intake→Plan 후 바로 실행한다.
- **Council 경로:** 새 프로젝트, 방향이 열린 기능, 되돌리기 비싼 결정, 사용자가 풀파워 기획을 요청한 경우에만 제안 후 실행한다.
- 사용자가 이번 메시지에서 kickoff·깊은 기획·풀파워를 명시하면 이미 승인된 것으로 본다.

## 불변 규칙

1. 원본 brief와 rubric을 SHA-256으로 봉인한다. 질문이 방향을 바꾸면 기존 run을 고치지 않고 새 run을 만든다.
2. Plan A/B/C는 서로의 산출물을 보지 않는 fresh session이다.
3. 각 lane은 **Fable과 GPT‑Sol 두 백본**을 각각 fresh session으로 실행한다. 같은 백본의 하위 agent 둘을 “다중 백본”이라 부르지 않는다.
4. 모든 Plan worker는 read-only다. 제품 파일은 쓰지 않고 자기 산출물만 제출한다.
5. 발산 중에는 kill condition·premortem·상대안 비평을 강제하지 않는다. 그것들은 barrier 뒤 HARDEN 단계에서 붙인다.
6. advocate가 judge가 되지 않는다. 합의되지 않은 이견은 평균내거나 숨기지 않는다.
7. 최종 선택은 사용자만 한다. 승인 전 구현·merge·deploy 금지.

## 파이프라인

```text
Intake → Seal
       → EXPLORE: 3 lanes × 2 backbones, blind parallel
       → lane synthesis: lane별 2안을 비옹호자가 합침
       → Claim Barrier
       → HARDEN: evidence verify → refuter → blind judge
       → non-advocate spec seed
       → user ADOPT / PIVOT / STOP
       → specpack
```

- **Plan A — First Principles:** 경쟁사·유사제품을 보지 않고 제약·불변량·최소 메커니즘에서 출발한다.
- **Plan B — Reference-first:** 유사제품·공식 사례·실패 사례에서 “쓸 것/버릴 것”을 도출한다. Ref-first의 정확한 위치다.
- **Plan C — Distant Analogy:** 문제를 구조로 추상화해 전혀 다른 산업·학문에서 동형 해법을 찾는다.

정확한 DAG, 정보밭 분할, 모델/도구 배치, 실패 강등, 산출 schema는 작업 시작 전에 [Plan Council v3 runbook](references/plan-council-v3.md)을 읽는다.

## 결과물

`orca-council.py` 상태 디렉터리와 사용자가 정한 council 작업 폴더에 최소한 다음을 남긴다.

- 봉인된 `brief.md`, `rubric.md`, `manifest.json`
- 여섯 raw draft와 세 lane synthesis
- source/query overlap 감사
- claim ledger, refutation, judgment
- `sealed/spec-seed.json`, manifest의 immutable user decision

긴 회의 전문보다 **결정을 바꾼 주장·근거·삭제안·미해결 이견**을 우선한다.

## 안 하는 것

- 모든 요청에 Council 자동발동
- 한 Fable 세션의 subagent 셋을 A/B/C 독립 모델로 간주
- 동일 검색 query·상위 URL을 양쪽 백본에 복제
- 발산 전에 레퍼런스·kill condition·평가표를 모든 lane에 주입
- 점수 차가 작거나 근거가 약한데 억지 승자 선정
