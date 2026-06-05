---
name: kickoff
description: 프로젝트·기능 시작 단계의 Claude↔Codex 적대적 기획 회의(council). Claude가 계획 초안을 쓰면 Codex(GPT)가 코드를 안 본 차가운 상태로 레드팀하고, VERDICT가 APPROVED 될 때까지 수정·재검증을 반복한다. 모든 라운드가 세션에 보이고 $COMMAND_CENTER/council/<날짜>_<주제>/에 기록된다. Phase 0(짓기 전에 정의)을 단일 모델이 아니라 두 모델 회의로 수행할 때 사용. "kickoff", "기획 회의", "Codex랑 계획 검토", "adversarial plan review" 요청 시.
---

# kickoff — Claude × Codex 적대적 기획 회의

**목적.** 새 프로젝트/기능의 *방향을 잡는 단계*에서 Claude 혼자 계획하지 않고, Codex(다른 모델)를 차가운 레드팀으로 들여 **맹점·아첨·과적을 깬다.** 코드 작성 전, 계획서 자체를 두드린다. 이것이 전역 `~/.claude/CLAUDE.md`의 **Phase 0 — Frame before Build**를 2-모델 회의로 구체화한 것.

**전제.** Codex CLI가 로그인돼 있어야 한다(`codex login status`로 확인). 안 되면 사용자에게 `codex login` 요청.

## 원칙 (가시성 = 핵심)
- **모든 라운드를 세션에 출력한다.** Codex는 **포그라운드**로 돌려 출력이 사용자 화면에 그대로 흐르게 (`--background` 쓰지 말 것).
- **기록은 항상 `$COMMAND_CENTER/council/<날짜>_<주제>/`에 남긴다** (어느 폴더서 실행하든 — 카운슬을 main에서 한눈에 보기 위함, 니즈#4). `council.md`=회의 전문 누적, `plan.md`=진화하는 계획. 사용자가 라이브로 보고 `git diff`로 궤적 추적. (코딩 프로젝트 한정 계획이면 최종 plan만 그 repo로도 복사.)
- Codex는 **read-only** 샌드박스로만 (계획을 비평할 뿐 파일을 고치지 않는다). 단 **툴은 풀로 연다** — 아래 참조.
- 🛠 **Codex 100% 성능 = 툴 활성화 (2026-05-29 maintainer, dogfooding 검증).** Codex CLI는 자체 에이전트 루프로 웹검색·셸·파일읽기 툴을 *스스로* 쓴다. 기본값(툴 off)으로 돌리면 "팔다리 잘린" 상태 = 자기 학습지식만으로 답함. **반드시 `-c 'tools.web_search=true'`로 웹검색을 열어** Codex가 실시간 근거(논문·통계·시세·레퍼)를 직접 찾아 비평하게 한다. (R2 지식기반 vs R3 웹검색 비교에서 후자가 압도적으로 풍부·구체적이었음.) read-only 샌드박스라 파일은 못 고치지만 셸로 repo를 *읽어* 근거를 댈 수는 있음(코드리뷰가 아닌 기획회의라 코드 안 보는 게 기본이나, 사실확인이 필요하면 허용).
- **합의는 추천이지 결정이 아니다.** 마지막 결정은 사용자.
- **No-echo (2026-06-01 — echo 편향 적발).** Claude가 Codex(또는 그 역)를 *그대로 수용*하면 회의가 죽는다(="반은 맞고 반은 틀려요" 회피화법의 사촌 — 둘 다 *틀림 회피*가 뿌리). 진짜 이견은 **§1C 수치 점수화**로 판정한다 — wholesale 수용 금지, 종합엔 **"내가 뒤집은 것(disagreements)" 섹션 필수**(caving을 눈에 보이게), advocate한 모델이 승자선언 X.

## 언제 쓰나 — 모드 (v2, 2026-05-31)
**모드 분리** (kickoff은 직렬 적대 핑퐁 — 그 한계는 [§Round 0]):
- **kickoff 단독** — 기능 시작, plan이 있고 주 리스크가 *구현 스코프*일 때.
- **judge-panel 단독**(격리 병렬 발산→수렴) — 감사·wrap-up 채점·"이 프로젝트 정직한가" thesis 스트레스.
- **둘 다** — 피벗·고비용 빌드·외부/시장/연구 주장·안전/금융/법 리스크·첫 frame이 의심스러울 때: **judge-panel 먼저**(blind 공격질문) → **kickoff 나중**(plan hardening).

**Round 0는 *항상* 발동** (maintainer 결정 — "정의·research·plan은 무조건 풀파워, Tier 판정 X"): kickoff을 *연다는 것* 자체가 이미 풀파워 가치가 있는 중요 작업이라는 뜻이다. 그러니 Tier로 깎지 않고 **kickoff을 열면 Round 0부터 무조건** 돈다. (codex는 잡일 과적을 우려해 Tier 게이팅을 권고했으나 — 명백한 1줄 잡일은 *애초에 kickoff·Phase 0 Gate를 스킵*하므로 과적이 아니다. 즉 잡일을 kickoff에 안 올리는 것으로 해소.)

## 절차

### 0. Round 0 — Blind 독립 frame (*항상* · 앵커링 차단)
kickoff 핑퐁은 Codex가 Claude plan을 *먼저 봐서* 그 프레이밍에 갇힐 위험(anchoring)이 있다. 그래서 plan 작성 *전에* 항상: Claude와 Codex가 **user brief만 보고(서로 안 보고)** 각자 1문단 frame을 쓴다 — **문제 · 핵심 접근 · 최대 리스크**. 그 뒤 공개해 3불릿 diff(**수렴 / 이견 / 빠진 옵션**)를 `council.md`에 남기고, 이 diff를 종자로 아래 plan을 쓴다.

**+ 적대 Intake 산출 (재질의를 *수집이 아니라 심문*으로):** 각 모델은 frame에 더해 **(a) 기획자가 놓친 필수질문 + (b) 사용자가 말한 의심 전제**를 낸다 — **각 ≤5, 반드시 *"이 답이 plan을 바꾸나?"* 통과**, 등급 `BLOCKER`(사용자에 직접 질문) / `RISK`(Prior-art서 검증) / `LATER`(버림). 위험 전제는 `council.md`에 **flagged-assumption 표**(`전제 | 왜 위험 | 필요 증거 | kill 조건 | 상태`)로 시드 — **kill 조건을 *먼저* 쓴다**("이 증거 없으면 죽인다"). plan·Round 1~N redteam이 이 표를 들고 가 *증거 없으면 폐기*.
> ⚠️ 필드 증식 = 과적. 위 적대-Intake 산출만 예외 허용 — **`≤5 + plan을 바꾸는 질문만`** 필터가 ceremony化를 막는다(좋은 과적: 전제공격·증거게이트·kill조건 / 나쁜 과적: 질문 합집합·체크리스트 비대화). 그 외 별도 템플릿·artifact 금지 — *1문단 + 3불릿 + (방향작업 시) 적대산출, `council.md`에만*.

### 0B. Frame — 계획 초안 (Claude)
기록 폴더부터 만든다: `CDIR=$COMMAND_CENTER/council/$(date +%F)_<주제슬러그>` → `mkdir -p "$CDIR"`. 사용자 요청에서 다음을 끌어내 `$CDIR/plan.md`에 작성하고 **세션에도 출력**한다:
- **문제·니즈**: 누가/무엇을/왜 지금? (사용자가 말한 *해법* 말고 그 밑의 *문제*)
- **성공 기준**: "됐다"를 어떻게 아는가 (측정 가능)
- **제약·비범위**: 한계 + *안 할 것*
- **전략·가정**: 가장 단순한 경로 + 핵심 가정 명시
- **열린 질문**: 모르는 것

모르는 게 결정적이면 여기서 멈추고 사용자에게 `AskUserQuestion`. (가정으로 메우지 말 것.)

### 1. 회의 라운드 (최대 4회)
각 라운드:

**a) Codex에 차갑게 넘긴다** — 현재 `plan.md` 전문 + 적대적 지시를 프롬프트로:
```bash
# 툴 풀-오픈: web_search 켜고 high effort. Codex가 스스로 검색·셸을 쓰며 비평한다.
codex exec -s read-only -c 'tools.web_search=true' -c 'model_reasoning_effort="high"' "$(cat <<'EOF'
You are an adversarial plan reviewer with WEB SEARCH and shell tools available — USE THEM.
Search the web aggressively for real evidence (papers, stats, prices, prior art) and cite sources inline.
You have NOT seen the codebase — judge only this plan (read repo files only to fact-check a claim).
Break it. Find where it fails in production, where scope is wrong (too big OR too small),
which assumptions are unstated or false, what the simplest version is being missed.
No compliments. Only the problems, each as: [finding] / why it fails / impact / suggested fix.
End with exactly one line: "VERDICT: APPROVED" or "VERDICT: REVISE".

=== PLAN ===
EOF
cat "$CDIR/plan.md")" < /dev/null
```
> ⚠️ **`< /dev/null` 필수**(2026-05-27 dogfooding 발견): 프롬프트를 인자로 주면서 stdin을 안 닫으면 codex가 "Reading additional input from stdin..."로 **무한 대기→타임아웃**(특히 비-tty/백그라운드 실행). 항상 stdin을 명시(`< /dev/null` 또는 `< 파일`)할 것.
> gstack 사용자는 `codex challenge`로 대체 가능(같은 엔진). 2라운드부터는 `codex exec resume <session-id>`로 **같은 Codex 세션을 이어** Codex가 "지적이 실제로 반영됐는지" 검증하게 한다. (1라운드 출력 끝의 session id를 기록해 둔다.)

**b) Codex 응답 전문을 세션에 출력**하고 `$CDIR/council.md`에 `## Round N — Codex` 로 추가.

**c) VERDICT 판정** (`APPROVED` / `REVISE` 두 가지만 — 종결상태를 늘리지 않는다):
- `APPROVED` = **"알려진 *blocking 계획 결함*이 없음"** — *plan이 진실이라는 뜻이 아니다*(두 모델 동의 ≠ 정답; 공유 학습편향이면 같은 오답에 합의할 수 있음). 아래 **hard-gate 7개를 전부 충족할 때만** Codex가 APPROVED 허용:
  1. 문제·니즈가 *해법과 분리* 2. 측정가능(falsifiable) 성공기준 3. 비목표/스코프 경계 명시 4. 핵심 가정 + 증거/테스트 5. **3+ premortem 실패모드** 6. 최소버전 + *의도적 삭제/연기 1개+*(over-scope 차단) 7. 이전 라운드 blocking 발견이 `accepted`/`rejected`/`deferred`로 처리됨.
  - *(외부 사실주장이 있으면 인용 추가 — 조건부. repo 주장은 file:line 또는 "미검증" 표기.)* 하나라도 빠지면 `REVISE`.
- `REVISE` → Claude가 계획을 수정하되, **무엇을/왜 바꿨는지 명시**(세션 출력 + `## Round N — Claude 수정` 로그). `plan.md` 갱신. 다음 라운드로.

라운드 캡(4) 도달 시: 합의 강요 말고 — 남은 핵심 쟁점·미해결 이견을 솔직히 정리해 **사용자 판단을 요청**(검증 불가한 건 가정/리스크로 표기).

### 1C. 쟁점 점수화 판정 (no-echo · 두 모델이 *정면으로 맞붙을* 때)
§1 plan-REVISE 핑퐁은 Codex가 Claude plan을 *공격*하는 비대칭 구조다. 그러나 둘이 *진짜 반대 입장*인 쟁점(예: rich vs strip 아키텍처, 모델 A vs B, defer vs cut)은 추종·"균형 머시"로 뭉개지 말고 **각 입장을 점수화해 수치로 승리판정**한다.

**셋업:** 두 모델에 *명시적 반대 스탠스* 배정(각자 steelman, 균형 수렴 금지). 독립 선행→교차(§0 앵커링 차단 동일). 각자 **상대 ≥1 concede + ≥1 counter 강제**(진짜 engagement 증명; 안 하면 그 라운드 무효).

**쟁점 1개당 — 양측 입장 각각 0~5 채점, 가중합 최대 50, 높은 쪽 승:**

| 차원 | 가중 | 0 | 5 |
|---|---|---|---|
| D1 증거등급 | ×3 | 단언·일화 | 복수 peer-review·독립 replication |
| D2 실거래 생존 (OOS·비용후·재현) | ×3 | OOS/비용후 반증 | 비용후·독립재현 robust |
| D3 반론 생존 | ×2 | 자인/반박됨 | 상대 counter 실패, 코어 무손상 |
| D4 반증가능+kill조건 | ×1 | 반증불가 hand-wave | 명확 falsifiable + 통과 |
| D5 이 스케일 비용/편익 | ×1 | 비용>편익(glamour) | 편익이 복잡도·과적합·빌드비용 압도 |

**판정:** 승자 = 고점. **마진 < 8(≈15%) → 무승부 → "challenger"로 보류**(억지 승자선언 금지, 검증으로 미룸).

**anti-fake-precision 3규칙 (자기적용 — 안 지키면 이 점수가 곧 가짜 샤프지수):**
1. **근거 없는 점수 = 무효** — 각 D 점수 옆에 1줄 근거(출처/사실). 못 대면 그 D = 0.
2. **증거 게이트:** D1·D2 중 하나라도 0이면 D3~5 만점도 *승리 불가*(수사로 증거를 못 이긴다).
3. **점수 = 오라클 아님, caving 차단용 추론-강제 장치** — advocate≠judge, 최종 judge는 사용자.

산출: `council.md`에 쟁점별 양측 점수표 + **"내가 뒤집은 것(disagreements)"** 섹션(어느 모델 입장을 점수로 뒤집었는지 명시).

> 워크드 예(2026-06-01 rich-vs-strip): *Kelly-사이징* Opus(keep) 13 vs Codex(cut) 50 → CUT. *Ledoit-Wolf* Opus 37 vs Codex 38 → 무승부=challenger. 점수가 echo·caving 없이 손-판정을 기계적으로 재현했다 = 점수화의 가치.

### 2. 마무리
- 최종 `$CDIR/plan.md` 확정.
- **개선 궤적 요약**: 첫 계획 vs 최종 — 어떤 Codex 지적이 계획을 바꿨는지 3~5줄.
- 다음 단계 안내: 이제 작업 루프(research → 구현 → 테스트 → `codex review` → ...)로 진입. PLAN을 프로젝트 적절한 위치로 옮기거나 `$COMMAND_CENTER/projects/*.md`에 반영.

## 산출물 (전부 `$COMMAND_CENTER/council/<날짜>_<주제>/` — main에서 한눈에)
- `plan.md` — 회의를 거친 최종 계획 (Phase 0 frame)
- `council.md` — 라운드별 Claude↔Codex 회의 전문 (사용자 정독용)

## 안 하는 것
- Codex를 background로 돌려 회의를 숨기지 않는다 (가시성 위반).
- Codex에 쓰기 권한 주지 않는다 (read-only 고정).
- 캡을 넘겨 무한 핑퐁 하지 않는다 (4라운드).
