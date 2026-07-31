# Plan Council v3 — 실행 runbook

## 1. Intake와 Seal

원본 요청에서 문제와 대상 사용자, 성공을 관측할 방법, 제약과 비목표, 계획을 실제로 바꾸는 BLOCKER/RISK만 확정한다.

코디네이터의 해석을 워커 입력에 섞지 않는다. `brief.md`, `rubric.md`, base SHA, lane card를 봉인하고 hash를 manifest에 기록한다.

## 2. EXPLORE — 6개 blind worker

| Lane | Fable | GPT‑Sol | 사고 규칙 |
|---|---|---|---|
| A First Principles | A-F | A-G | 경쟁제품 금지. 공식 규격·실측·계산만 허용 |
| B Reference-first | B-F | B-G | 유사사례와 실패사례에서 취할 것/버릴 것 |
| C Distant Analogy | C-F | C-G | 대상 도메인 키워드 대신 구조가 같은 먼 분야 탐색 |

각 칸은 fresh session이며 `brief + 자기 lane card + output schema`만 받는다. 서로의 draft, coordinator 선호, 다른 lane 검색어를 받지 않는다.

발산 산출:

- 문제 재정의
- 핵심 가설과 3개 이상 서로 다른 접근
- 예상 사용자 가치
- 의도적 삭제와 비목표
- 모르는 사실
- 사용한 query·URL·source class·community·language

발산에서는 모든 아이디어에 kill condition과 premortem을 강제하지 않는다. 아이디어 생성 단계의 조기 자기검열을 피한다.

## 3. 정보밭 분할

중앙은 답이나 상세 검색어가 아니라 **내용중립 축**을 배정한다.

| Worker | 발견 경로 |
|---|---|
| A-F | 로컬 실측·계산 + 공식 스펙 |
| A-G | 별도 query family의 공식·표준 1차 자료 |
| B-F | vendor docs·제품 changelog·성공 구현 |
| B-G | GitHub issues·postmortem·실사용자/비판 커뮤니티 |
| C-F | 학술·역사적 분야, backward citation |
| C-G | 타 산업 실무·비영어 자료, forward citation |

- 같은 Firecrawl을 둘 다 써도 URL 발견 경로가 다르고, Firecrawl이 서로 다른 URL의 추출기로만 쓰였다면 허용한다.
- 같은 query/ranking 결과를 나눠 읽은 것은 독립 연구가 아니다.
- 제출 뒤 URL, root domain, query token, citation root의 overlap을 계산한다. full v3에서 기준을 넘으면 lane synthesis를 막고 fresh retry 또는 별도 downgraded run으로 보낸다.
- **overlap 임계값 (orca-council.py 코드가 정본, 2026-07-30 문서화):** queries Jaccard > 0.6 / evidence_roots > 0.4 / urls > 0.4 / cross-lane 조합 > 0.6 → 차단. query는 표현이 아니라 정규화된 내용으로 비교한다(norm_query — 07-29 "어순만 바꾼 같은 검색" 우회 수리).
- 감사 입력은 worker 자기보고 research log가 기본이며, **가능하면 `$COMMAND_CENTER/system/council-provenance-extract.py`로 세션 로그(jsonl)에서 실제 검색 호출을 추출해 대조한다**(자기보고↔실로그 불일치 = 그 worker provenance를 low-trust로 표시).
- **출처 독립성은 source class가 아니라 증거 계보(evidence lineage)로 판정한다.** 같은 class의 서로 독립된 실험은 독립일 수 있고, 다른 class라도 같은 보도자료를 재인maintainer면 하나다.

## 4. 전역 blind barrier와 Lane synthesis

**여섯 raw draft가 모두 hash-seal되기 전에는 어떤 worker에게도 sibling 결과를 공개하지 않는다.**
전역 barrier가 닫힌 뒤 세 fresh synthesizer를 병렬 실행한다. 각 synthesizer는 자기 lane의 두 draft만 읽고 다른 lane은 보지 않는다.

산출:

- 공통 결론
- Fable만 발견한 것
- GPT만 발견한 것
- 양립 불가능한 이견
- lane 대표안

평균내지 않는다. 이견의 원인이 사실·가치·제약 중 무엇인지 표시한다.

## 5. Claim Barrier와 HARDEN

세 lane synthesis가 봉인된 뒤 처음으로 함께 연다.

1. **Claim extraction:** 대표안을 주장 단위로 분해하고 `claim/source/status/scope/kill_condition`을 붙인다.
2. **Evidence verification:** 반증 자료를 먼저 찾고, 같은 원증거를 재인용한 출처는 하나로 센다.
3. **Refuter:** 숨은 전제, 실패조건, 삭제 가능한 기능을 공격한다. 1라운드만.
4. **Blind judges:** 라벨을 숨긴 채 rubric으로 독립 채점한다. D1 또는 D2가 0이면 수사 점수로 이길 수 없다. 점수 차가 8 미만이면 DRAW.
   - **judge 백본 = GPT-Sol + Opus (2026-07-30 확정).** 종합·조율을 controller(Fable)가 하므로 Fable judge는 "자기 글 자기 채점"(자기선호 편향, arXiv 2410.21819)이 된다 — judge는 컨트롤러와 다른 모델 2개로. 실행: GPT-Sol = `codex exec -s read-only -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' "$(cat <prompt>)" < /dev/null`, Opus = fresh judge 서브에이전트(model opus).
   - **rubric 가중치(orca-council.py 고정): D1×3 · D2×3 · D3×2 · D4×1 · D5×1 (만점 100).** D1 집행 가능성·정확성, D2 문제 적합은 상수 축이고, D3~D5의 구체 의미는 run별 rubric.md가 특화한다(예: 07-29 run은 D3 단순화 실효·D4 재발 방지 구조·D5 검증 가능성).
5. **Synthesis:** advocate가 아닌 fresh agent가 살아남은 주장과 이견으로 spec seed를 만든다.
6. **Fidelity check (2026-07-30 신설 — 발산 6:수렴 1 병목 보정):** spec seed 봉인 직후, **비컨트롤러 judge(GPT-Sol)**가 seed를 6 draft·3 synthesis와 대조해 **왜곡·누락만** 채점한다(품질 재채점 아님). 왜곡·누락 발견 시 seed를 수정해 재봉인한 뒤에만 user gate로 간다. blind로 지킨 다양성이 단일 종합 지점에서 증발하는 것을 막는 최소 장치.

사용자는 ADOPT/PIVOT/STOP을 결정한다.

## 6. Orca DAG

Orca orchestration이 task/dispatch/worker_done/ask/dependency의 유일한 lifecycle 정본이다.

```text
root
├─ A-F ─┐
├─ A-G ─┤
├─ B-F ─┤
├─ B-G ─┼─ GLOBAL BARRIER (6개 모두 completed)
├─ C-F ─┤       ├─ synth-A (입력은 A-F/A-G만)
└─ C-G ─┘       ├─ synth-B (입력은 B-F/B-G만)
                └─ synth-C (입력은 C-F/C-G만)
                      └─ claim-verify → refuter → judge-G(GPT-Sol) + judge-O(Opus)
                                                   └→ synthesis → fidelity-check(GPT-Sol) → user gate
```

Artifact ledger는 Orca ID와 산출물 hash를 참조할 뿐 task 상태를 복제·수정·복구하지 않는다.
**Orca에서 synth-A/B/C 각각의 `deps`는 여섯 raw worker task ID 전체여야 한다.**
입력 파일은 자기 lane 두 개뿐이지만 ready 조건은 전역 barrier다. ledger의 늦은 submit 거부만으로는
조기 노출을 막을 수 없으므로 DAG 자체가 이를 강제해야 한다.

각 역할은 외부 Run Controller가 캡처한 `task_id/dispatch_id/terminal/model/session/parent/deps`
스냅샷을 ledger에 함께 봉인한다. 이는 **controller-attested** 증거다. 현재 ledger가 Orca 런타임이나
모델 공급자에게 직접 재조회한 “live-verified” 증거는 아니며, 그 검증은 Resource Provisioner의 책임이다.

봉인·다양성 감사·결정론 채점은 `$COMMAND_CENTER/system/orca-council.py`가 담당한다. 사용자에게 보이는 run을
`$COMMAND_CENTER/council` 아래에 둘 때는 모든 명령에 `--state-root $COMMAND_CENTER/council`을 사용한다.
Orca lifecycle은 여전히 별도 정본이며 ledger에는 mutable status를 복사하지 않는다.

## 7. 실패와 예산

- worker 무응답: 같은 백본 fresh session으로 1회 재시도
- 같은 칸 두 번 실패: lane 결손 표시
- 한 백본이 전부 실패: 다중백본 Council이 아니므로 사용자에게 강등 gate
- full v3 정족수는 6개 전부다. 결손이 생기면 같은 run에서 느슨하게 계속하지 않는다.
- 사용자가 비용·가용성 때문에 강등을 승인한 경우에만 별도 brief와 profile로 **새 downgraded run**을 만든다.
- same-backbone 대체를 cross-model 결과로 위장 금지
- **judge 결원 열화 금지 (2026-07-30 A③):** judge 한쪽이 못 뜨면 조용히 1명으로 진행하지 않는다 — orca-council.py가 2명·비컨트롤러 2백본을 하드 강제하며, 스크립트를 우회한 수동 run에서도 단독 judge 결과는 PASS가 아니라 **DEGRADED**로 표기하고 사용자 gate에 결원 사실을 명시한다 (07-29 full run의 단독 GPT judge 열화 재발 방지)
- 발산·반박·judge 라운드는 각각 1회. 새 사실이나 봉인 brief 변경 없이는 무한 토론 금지
- 여섯 fresh session/terminal은 **동시 6개**를 뜻하지 않는다. RAM에 맞춰 2~3개씩 wave로 실행해도
  전역 barrier 전까지 공개만 막으면 된다. 단, 한 run 안에서 session/terminal provenance는 재사maintainer지 않는다.
- 비용·시간·token·재시도·사람 개입시간을 기록한다. Council은 strong single-agent 기준선과 A/B 평가 후 유지한다.
