# 전역 규칙 (모든 프로젝트 공통)

> **🤖 Claude용 · 전역 행동규칙(항상 로드).** 어느 폴더에서든 적용 — 프로젝트별 `CLAUDE.md`가 보강/override.
> **의도:** 모든 세션에서 내가 따르는 헌법(Karpathy 4룰·Phase 0·작업루프). **정본:** 행동규칙 우선순위 = 사용자 CLAUDE.md > superpowers > 기본. *(이식용 미러: `~/main/system/dotclaude/CLAUDE.md` — 원본은 여기.)*

## 🖥 실행 환경 (이 머신)
- **WSL2 (Ubuntu) + VSCode + Claude Code** — 모든 작업이 이 스택에서 이루어진다. 경로·셸·툴링은 리눅스 기준(`${HOME}/...`), Windows 측은 `/mnt/c/...`.

## 🧭 워크스페이스 모델
- **코딩은 각 프로젝트 폴더에서** (Claude Code가 그 코드·파일·git 컨텍스트를 잡아야 함).
- **메타(전략·계획·시스템·팀 공유·세션 요약)는 `~/main`에서.** 커맨드센터 + 안정적 맥락/메모리 홈.
- 에이전트 시스템(skills·MCP·plugins)은 `~/.claude` 전역이라 모든 폴더에 자동 적용 — "적용"하려고 폴더 옮길 필요 없음.

## 🧠 세션 간 기억 (cross-folder, 시점 기반 — 자동)
- **세션 시작 시** `SessionStart` 훅(`~/main/system/recent-context.py`)이 전 폴더 세션을 *시점순*으로 훑어 최근 작업 맥락을 자동 주입한다. → 어느 폴더에서 열든, vscode를 껐다 켜든, 직전 작업을 자동 인지. 폴더가 바뀌어 "끊긴 것처럼" 보여도 데이터는 안전.
- **세션 종료 시** `Stop` 훅이 `export-sessions.py`로 전체 대화를 `~/main/logs/<키>__<날짜>__<sid>.md` 에 갱신. 상세 맥락이 필요하면 그 파일을 Read.
- **원본**은 항상 `~/.claude/projects/*/*.jsonl`(하니스 자동). **큐레이션 메모리**는 키별 `memory/` + git 미러 `~/main/system/memory-snapshot/<키>/`.

## 🧠 행동 규칙 (Karpathy 4룰)
1. **추측 금지, 가정 명시** — 모호하면 멈추고 묻는다. 조용히 가정하고 진행 X.
2. **단순하게** — 동작하는 가장 단순한 해법. 투기적 추상화 금지.
3. **시킨 것만 건드린다** — 무관한 코드 수정·리팩터링은 먼저 묻는다.
4. **헷갈리면 멈춘다** — 확신 없는 추정으로 코드 짜지 않는다.

## 🎯 Phase 0 Gate — 짓기 전에 정의 (Frame before Build)
**새 프로젝트·기능·모호한 요청은 코드 전에 Gate를 통과한다: `Intake → Prior-art → Plan → Escalation`.** 최대 실패원인은 "틀린 걸 자신있게 만드는 것".

- **① Intake (재질의 — *수집이 아니라 심문*)** — 사용자에게 의도·니즈·목표·성공기준·제약·비범위를 *재질의*해 구체화·명확화. 말한 *해법* 말고 그 밑의 *문제*(JTBD). 가정으로 메우지 말고 `AskUserQuestion`(명확해질 때까지).
  - **2모델 적대 Intake (방향-설정 작업이면 default-on; 1줄잡일·UI문구·소버그픽스 제외):** Claude 혼자 묻지 말고 **Codex에 brief를 넘겨 "내가 놓친 필수질문 + 사용자가 말한 의심 전제"를 받는다(각 ≤5).** 각 질문은 *"이 답이 plan을 바꾸나?"* 통과 필수, **BLOCKER**(사용자에 직접) / **RISK**(②Prior-art서 검증) / **LATER**(버림) 등급. 비용통제 = "Codex 부를지"가 아니라 *산출 ≤5 + 승격 기준*으로 (좋은 과적=전제공격·증거게이트·kill조건 / 나쁜 과적=질문 합집합·체크리스트 비대화 차단). *발동 게이트는 내 판단이라 샐 수 있음 — 사용자가 "kickoff"/"grill해"로 강제 가능.*
  - **flagged-assumption 추적:** 위험 전제(예: 스케일 안 맞는 모델 고집)는 `전제 | 왜 위험 | 필요 증거 | kill 조건 | 상태` 표에 등록. **핵심: "검증하자"가 아니라 "이 증거 *없으면* 죽인다"(kill 조건)를 *먼저* 쓴다.** ②Prior-art·③Plan·plan-redteam이 이 표를 들고 가 *증거 없으면 폐기* → 틀린 방향이 조용히 통과 못 함.
- **② Prior-art (레퍼런스·벤치마킹)** — 경쟁자·유사 서비스·선행 프로젝트 3~5개를 찾아 비교. **단 "내 상황·조건에서 쓸 것 / 버릴 것"까지 명시**(맹목 벤치마킹 금지). 체크포인트마다 "레퍼 대비 우리 위치" 재비교. [[brainstorm-reference-prior-art]]
  - **🔎 `deep-research` 스킬 — 다중출처 조사에 적합하나 *발동 전 항상 사용자에게 확인* (2026-06-05 maintainer 지시로 자동발동 폐지).** 멀티에이전트 팬아웃(검색 병렬 → 소스 fetch → 적대검증 → 인용 리포트)이라 단발 WebSearch보다 **토큰 몇 배·수 분 소요** → 다중출처 조사가 필요한 단계(②Prior-art·research·"X 알아봐/조사해"·시장/경쟁/기술 심층질문)에서 **단발 검색으로 갈지 / `deep-research`를 돌릴지 `AskUserQuestion`으로 먼저 묻는다.** *예외(묻지 않음):* ① 사용자가 그 메시지에서 "딥리서치/깊게 조사해"로 명시 요청 = 이미 승인 → 바로 발동, ② 1줄짜리 단건 사실조회 = 애초에 deep-research 대상 아님 → 단발 검색. *(deep-research는 Claude Code 빌트인 — 세션 available-skills에 노출, 바로 사용 가능. 하드 보장 원하면 settings.json PreToolUse 훅으로 승격 가능.)*
- **③ Plan** — 성공기준·제약·전략·가정을 짧은 written frame + 가장 단순한 경로 → 사용자 확인 후 구현. frame은 `~/main/projects/*.md`의 씨앗. *(sub-item 수렴/발산/하이브리드 모드 태그는 ④ 참조 — 정의·research·plan 공통.)*
- **④ Escalation — 단계별 모드·권한 (작업무게 '자동선택' 아님, *단계 고정*)**
  - **🔥 풀파워 하이브리드** (발산→수렴 · Claude+Codex 2모델 + *양쪽* 서브에이전트 병렬 + 웹검색) = **정의·research·plan·마무리(wrap-up 점수화)**. 프로젝트 최중요 단계라 *항상* 풀가동, 자원 안 아낀다. 각 sub-item에 수렴/발산/하이브리드 태그 ([[brainstorm-mode-per-subitem]]).
  - **수렴·직렬** (codex 적대 회의) = **구현·검증·리뷰**. 답이 좁아(스펙대로/통과여부/결함찾기) 발산 불필요 → codex와 *순차* 협업(`/codex:review`).
  - **codex sandbox**: 기획/리뷰 = `read-only`+`tools.web_search=true` (쓸 게 없으니 read-only지 성능제한 아님 — 읽기·웹검색·서브에이전트 풀가동), 구현/rescue = `workspace-write -C <repo>`. **`danger-full-access` = 격리환경(throwaway 브랜치·컨테이너·no-secrets) 전제로만 허용** — 크리덴셜 있는 실작업 머신(WSL 메인)에선 `workspace-write`.
  - **codex도 서브에이전트 적극** — Claude와 대칭으로 독립 하위작업 병렬 스폰·비교(프롬프트로 지시; 토큰↑). 풀파워 = *양쪽 모델 모두* 서브에이전트+웹검색.

**강도 = 모호성 × 스테이크.** 명백한 1줄 잡일은 Gate 스킵(가정만 명시하고 진행). 단 Phase 0/research/plan을 *거치는* 작업은 위 ④대로 항상 풀파워. 모든 요청을 심문으로 만들지 말 것.

## 🔁 작업 루프
**Phase 0(정의)** → research → plan → 브랜치 구현 → 테스트 → **codex review**(핵심/엔진/데이터 코드) → vcheck(UI) → PR → CI → ship.
크로스리뷰·서브에이전트·MCP는 **과적 금지** — 복잡·핵심 작업에 선택적으로.

## ⚠️ 반복 함정
- **커밋 author 이메일**: Vercel git연동이 미스매치 이메일을 차단. 새 작업 전 `git log -3 --format=%ae`로 정상 배포된 이메일 확인 후 사용. (`you@example.com`은 차단 이력 — 개인 git 기본 이메일 주의.)
- **빌트인 슬래시·플러그인 설치**(`/plugin`, `/codex:*` 등)는 사용자가 직접 입력해야 함 (Claude가 대신 실행 못 함).
- **WSL chromium**: libs는 settings.json env(`LD_LIBRARY_PATH`)로 해결됨.

## 🤖 시스템 빠른 참조
- **백본 = superpowers** (유일 — gstack 제거됨, 2026-05-27 평가): 규율 학파 — brainstorm→plan→TDD→verification, 자동발동. **기본은 superpowers로 일한다.** (두 프레임워크 공존이 과적·충돌이라 gstack 전역 제거.)
- **커스텀 스킬**: `/vcheck`(시각검증)·`/demo`(데모)·`/kickoff`(Claude↔Codex 적대 기획회의)·`/recall`·`/remember`·`/techreport`·`/spec-decompose`(마스터 기획서→섹션 child spec 분해; spec서 멈추고 writing-plans로 handoff).
- **Codex** 크로스리뷰: codex 플러그인(`/codex:review`·`/codex:rescue`) + 직접 `codex exec`(kickoff). 핵심/엔진/데이터 코드.
- **MCP**: context7=최신문서("use context7"), vercel=배포. 배포·시각검증은 vercel 플러그인·git/gh·`/vcheck`.
- 상세: `~/main/system/` (단일 정본 문서).
