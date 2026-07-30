---
name: autopilot
description: Use when the user says /autopilot/오토파일럿/야간 자율 실행/밤새 돌려/autonomous run/자율 루프/브랜치서 자동으로 고쳐놔, or explicitly asks to run a long bounded fix/refactor loop overnight on a WIP branch. Arms the outer safety harness (system/autopilot.sh) with an execution envelope — multi hard-limits (steps/budget/tokens/wall-clock), timeout+process-group kill, progress-based stop, diff/command gates, denied-action ledger, secret/size scan. NEVER auto-invoke; only on explicit user request. Default is OFF/unarmed (does nothing until armed).
---

# /autopilot — 자율 오케스트레이션 (무장식 안전 하네스)

**정체성 (계약 §사용가이드).** "대신 생각하는 장치"가 **아니다.** 성공조건이 이미 정해진 **긴 반복 루프를 밤새·브랜치 안에서 싸게 굴리는 장치.** 방향·철학·아키텍처 결정에는 쓰지 않는다.

**정본 계약:** `~/main/council/2026-07-03_autonomous-orchestration/autopilot-design.md` + `autopilot-realloop-design.md` (실 연결 계약 v2 · Codex 하드닝 8항목).
**하네스 코드:** `~/main/system/autopilot.sh` (모든 Invariant·Kill condition을 **코드로** 강제 — 문서 약속 아님).
**Acceptance 증명:** `~/main/system/autopilot_test.sh` (44 assertion — 26 하네스 + 18 실연결 — 전부 PASS 유지가 안전 계약).

## 🔒 발동 규칙 (중요)
- **자동발동 절대 금지.** 이 스킬은 사용자가 `/autopilot` 또는 명시적 "야간 자율 실행/밤새 돌려/자율 루프"라고 **직접 요청할 때만** 쓴다. session-start·다른 작업 흐름에서 스스로 트리거하지 말 것.
- **기본 = OFF(미무장).** `autopilot.sh`는 `--arm`(또는 `AUTOPILOT_ARMED=1`) 없이는 아무 동작도 하지 않는다(inert, 부작용 0). 이 무장 게이트는 **코드로** 보장된다. 스킬이 무장을 결정하는 게 아니라, 사용자의 명시 요청 → 봉투 확정 → `--arm` 전달.
- **커밋·머지·push는 사람이.** 하네스는 로컬 WIP 브랜치만 건드리고, 자동 되돌림·자동 머지·remote write를 하지 않는다. 리뷰는 사용자.

## 봉투(envelope) — "명령"보다 "봉투"
자율 루프는 딱 정해진 경계 안에서만 돈다. 사용자 요청에서 아래를 채운다(모호하면 **묻는다** — Phase 0 Intake). 봉투는 `/kickoff`로 확정하는 게 이상적(파이프라인 참조).

```
objective:     무엇을 완료하면 성공인가 (좁게. 예: tests/cpx_eval 의 failing test만 통과)
branch:        로컬 WIP 브랜치명 (main/master 금지 — 코드가 거부)
allowed_paths: 편집 허용 glob (예: src/cpx_eval/**, tests/cpx_eval/**)
forbidden:     network, secrets, migrations, public API 변경 …
budget:        $ / turns / wall-clock / LOC diff  (보수적으로)
verify:        성공 판정 명령 (예: ./verify.sh && pytest tests/cpx_eval)
stop:          pass | same failure Nx | forbidden path 접촉 | budget hit
output:        summary.md + remaining_failures.md
```

## 절차 (사용자가 명시 요청했을 때)
1. **Intake.** objective/branch/allowed_paths/forbidden/budget/verify/stop/output을 사용자와 확정. 하나라도 비면 `AskUserQuestion`. best-fit인지 점검(아래 "언제 쓰나").
2. **브랜치 준비.** 대상 repo에서 로컬 WIP 브랜치 체크아웃 확인(`git -C <repo> rev-parse --abbrev-ref HEAD`). main/master면 하네스가 거부(exit 3)하므로 먼저 브랜치를 만든다.
3. **무장 호출.** 봉투를 인자로 매핑해 `autopilot.sh --arm` 실행:
   ```bash
   COMMAND_CENTER="$HOME/main" \
   bash ~/main/system/autopilot.sh --arm --real \
     --repo "<repo 절대경로>" \
     --branch "<wip-branch>" \
     --objective "<objective>" \
     --allowed-paths "<glob,glob>" \
     --forbidden "<network,secrets,migrations>" \
     --max-steps 15 --budget-usd 2 --per-step-usd 0.50 \
     --per-call-tokens 200000 --wall-clock 90m --no-progress 3 \
     --model sonnet --judge-model haiku \
     --verify "<verify 명령>" --output summary.md
   ```
   - **기본값은 보수적**(위가 예시 기본). 사용자가 더 크게 원하면 명시적으로만 올린다.
   - **실 LLM 루프 = `--real`(또는 `AUTOPILOT_REAL=1`)로 opt-in.** 매 스텝 = `claude -p` 1회(fresh 헤드리스, 생성자 sonnet). `--real` 없으면 `AUTOPILOT_STEP_HOOK`(측정가능 드라이버)이나, 둘 다 없으면 **fail-closed(exit 4)로 거부**(비용 측정 불가 = 실행 안 함, invariant 1). **`--real` 없이는 claude 가 설치돼 있어도 절대 호출 안 함**(사고성 과금 방지 — opt-in 게이트, 테스트 23).
   - **⚠ `--bare` 인증:** 자식은 `--bare` 로 spawn → 인증이 **`ANTHROPIC_API_KEY` 또는 `apiKeyHelper`(--child-settings 로 주입)만** 읽는다(OAuth·keychain 안 읽음). WSL 메인(OAuth) 세션에선 `ANTHROPIC_API_KEY` export 또는 `--child-settings <apiKeyHelper 든 settings.json>` 필요. 없으면 자식이 인증 실패 → usage 없음 → **fail-closed(exit 4)** 로 안전 정지.
   - **참고(설계 대비 실제):** 설계가 가정한 `--max-turns` 는 현 claude 2.1.x에 **없음**(2.1.201에서 재확인, 2026-07-06) → 스텝당 폭주 방어는 `--per-step-secs`(워치독 kill) + `--max-budget-usd`(per-step 사전캡)으로 대체(둘 다 실재 플래그).
4. **관찰.** 영속상태는 append-only `~/main/logs/autopilot/events.jsonl`(run_id·step·command·result·budget ledger·verdict), 렌더는 `~/main/logs/autopilot/<run_id>/progress.md`. 정지 사유는 stdout 마지막 줄 `AUTOPILOT: stop_reason=... steps=... run_id=...`.
5. **인계.** 종료 후 사용자에게 `git -C <repo> diff` 리뷰 요청. 워킹트리는 보존됨(자동 되돌림 없음). 커밋/머지는 사용자.

## 코드로 강제되는 것 (스킬이 "약속"하는 게 아님)
- **다중 하드리밋:** MAX_STEPS · TOTAL_BUDGET_USD · PER_STEP_USD · PER_CALL_TOKENS · WALL_CLOCK. 측정 불가 → 실행 거부(fail-closed).
- **timeout + process-group kill:** 모든 명령 = 새 세션(setsid) + 워치독 timeout + `kill -- -PGID` 스윕. background process 금지(스텝 후 잔여 child 청소).
- **진전-기반 정지:** dup-hash 아님. 상태벡터(HEAD·diffstat·변경파일·failing signature) N회 무변화 → 정지.
- **diff 게이트:** `.git/hooks`·`.github/workflows`·package 라이프사이클 스크립트·Makefile·rc/config·`.env`·deploy·migration 편집 감지 → 정지(승인 요구). verify/CI/test harness 수정 = high-risk.
- **command 게이트 + denied ledger:** network_egress·credential_access·remote_write·destructive_fs·privileged_runtime 분류. 같은 risk class 2회 → 정지.
- **repo 밖 write 차단:** symlink/절대경로 escape 감지 → 즉시 정지.
- **브랜치 전용:** main/master → 거부. remote write 없음(`--pr`는 이번 빌드 스텁).
- **commit 게이트:** secret scan(api-key·token·secret·password·@gmail·PRIVATE KEY) + artifact size 리밋.
- **실 루프 격리 (v2 Codex 하드닝 — real mode에서 코드로):**
  - **Bash-ledger-우회 차단(#3):** PATH 앞 shim 이 자식 Bash 의 `claude·codex·anthropic·openai·curl·wget·gh·ssh/scp/sftp·nc·telnet·rsync`(순수차단) 및 `git push/clone/fetch/pull/remote·npm/pnpm/yarn/pip/apt install·python/node -e/-c`(서브명령 차단)을 물리적으로 막고 흔적 기록 → post-step `denied_ledger:bash_bypass` 정지.
  - **fresh·격리 spawn(#5·#6·#7):** `--bare --no-session-persistence --disable-slash-commands --strict-mcp-config` + `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`·`CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS=1`. 자식 툴 = `--tools Read,Edit,Bash` + `--disallowedTools mcp__*,Agent,Task,WebFetch,WebSearch,NotebookEdit`.
  - **@우회 차단(#2):** progress bank 는 **부모가 파일 읽어 프롬프트 본문에 삽입**(자식 `@`참조 금지, 프롬프트에 명시).
  - **config 변조 정지(#5):** `.claude/**`·MCP config 변경을 diff 게이트 + filesystem 지문(gitignore 우회 방지) 양쪽으로 감지 → `diff_gate:claude_config` 정지.
  - **검증 격리 judge:** verify 통과만으로 성공 선언 안 함. 별도 `claude -p`(기본 haiku, `--tools ''` = 툴 없음)가 **objective + git diff 만** 보고 real/fake 판정(생성자 progress·reasoning 안 봄). `REAL` 아니면 `judge_reject` 정지. `--external-judge` = codex(외부모델) opt-in(미설치 폴백).
  - **비용 이중화(#8):** ledger 는 client 추정치라 "approx" 로 명명 + `--max-budget-usd`(per-step 사전 하드캡) 병용. usage 없으면 exit 4.

## 언제 쓰나 (best-fit) / 안 쓰는 게 나은 때
**값한다:** ① 야간 테스트 수리(실패 로그→작은수정→재실행) ② 기계적 리팩터·타입/lint debt ③ 마이그레이션 dry-run(브랜치서 "어디까지 자동되나"+깨지는목록) ④ CPX 실험 배치 관리(variant matrix·재시도·metrics 정규화) ⑤ 재현성 청소(README metric ↔ results JSON 불일치·seed·split drift). — sweet spot: 성공/실패가 커맨드로 판정 · 수정범위 좁음 · 반복多 판단小 · 실패해도 중간산출 유용 · 브랜치 격리 자연스러움.

**안 쓴다:** 문제정의 흔들림(방향·평가철학) · 의학/학술 주장 결정 · 큰 아키텍처 변경 · 비밀·배포·삭제 낌 · 긴급 핫픽스 · 결정론 테스트로 충분한 작은 수정.

## 파이프라인
`kickoff(명령서=봉투 확정) → /autopilot(야간 실행) → qualityloop(블라인드 채점) → repo-audit/review → 수동 merge`. 서브에이전트는 무제한 병렬 아니라 역할 1~2개.

## 검증 (하네스가 안 깨졌는지)
- `bash -n ~/main/system/autopilot.sh` · `bash ~/main/system/autopilot_test.sh`(44 assertion 전부 PASS 필수 — 실 연결 테스트는 mock claude 로 과금 없이 measurement→ledger→limit·격리 경로 검증).
- 미무장 실행 → `AUTOPILOT: inert (unarmed)` + 부작용 0 확인.
