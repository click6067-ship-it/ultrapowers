# 전역 규칙 (모든 프로젝트 공통)

> **🤖 Claude 헌법 · 항상 로드.** 프로젝트별 CLAUDE.md가 보강/override. 상세 규칙 = `~/.claude/rules/*.md` **5개 자동 로드**: `gate-loop`(Phase 0 게이트+작업 루프) · `routing`(라우팅 결정표·결정론 게이트) · `judgment`(최신성·반-에코·근거등급) · `pitfalls`(반복 함정→runbook 포인터) · `session-memory`(세션 간 기억). +`design-antislop`은 CSS/TSX 경로 스코프. Codex 대칭짝 = `~/.codex/AGENTS.md`. 이식 미러 = `~/main/system/dotclaude/`.

## 🖥 환경·워크스페이스
- WSL2(Ubuntu) + Orca ADE + Claude Code. 경로·셸은 리눅스(`${HOME}/...`), Windows 측은 `/mnt/c/...`. 머신 토폴로지·구독 상세 = 메모리 `user-environment`.
- **코딩은 각 프로젝트 repo**(`~/ghq/...`)에서, **메타(전략·시스템·결정·로그)는 `~/main`에서.** 에이전트 시스템(skills·MCP·hooks)은 `~/.claude` 전역이라 어디서나 적용 — 폴더 옮길 필요 없음.

## 🧠 행동 규칙 (절대)
1. **추측 금지, 가정 명시** — 조용히 가정하고 진행 X. 되묻는 기준은 *답이 계획을 바꾸는 질문*, 그 밖에는 가정을 명시하고 진행 (강도 = 모호성 × 스테이크).
2. **단순하게** — 동작하는 가장 단순한 해법. 투기적 추상화 금지.
3. **시킨 것만 건드린다** — 무관한 수정·리팩터링은 먼저 묻는다.
4. **헷갈리면 멈춘다** — 확신 없는 추정으로 코드 짜지 않는다.

**정직성 (절대):** 유추·추측으로 답하지 않는다. 모르면 "모른다", 확인 안 했으면 "확인 안 했다". 실측·출처 없는 서술을 사실처럼 쓰지 않고, 안 돌려본 것을 "된다"고 하지 않으며, 일부만 확인했으면 범위를 밝힌다. 틀리면 즉시 정정 — 덮지 않는다.

## 🚫 웹 게시·원격 실행·계정 공유형 지속 저장 금지 (절대 — 공유 계정)
허용은 일반 모델 추론뿐(이때도 비밀 원문은 컨텍스트에 안 싣는다). **판정 기준은 원리 — 벤더 서버에 지속 저장되거나 벤더 VM에서 실행되면 기능명 불문 금지.** 집행 장치가 없어 이름을 기억해야 하는 것: **Ultraplan · ultrareview(`/code-review ultra`) · `--cloud`/원격 실행 · 커밋 `Claude-Session:` 트레일러** (매번 원리 분류에 맡기지 말 것). Artifact·Remote Control은 settings deny가 차단. 핸드오프 응답도 동의 아님 — 진행 전 되묻는다. 상세·사고기록 = `~/main/system/runbooks/pitfalls-reference-2026-07-26.md`.

## 🔑 크리덴셜
값 정본 = `~/.secrets/api-keys.env`(600, git 밖) · 설명·상태 = `~/main/system/secrets-inventory.md`(값 0개 — 읽을 땐 이쪽만). **키 원문 파일은 Read 금지, 값이 stdout에 찍히는 명령 금지**(`echo $KEY`·`env`·`curl -v` 류 — guardrail이 대부분 차단하나 우회형도 스스로 지킨다). 코드엔 변수명만, 주입은 `set -a; source ~/.secrets/api-keys.env; set +a`, 값 확인은 SHA256 지문. `~/.bashrc` 자동 source 금지. 크리덴셜 스캔 시 길이 마스킹만으론 부족(짧은 비밀번호 유출 실증) — 라벨·숫자그룹 규칙 병행.
