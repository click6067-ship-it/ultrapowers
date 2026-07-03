# 🎯 Phase 0 Gate — 짓기 전에 정의 (Frame before Build)

**새 프로젝트·기능·모호한 요청은 코드 전에 Gate를 통과한다: `Intake → Prior-art → Plan → Escalation`.** 최대 실패원인은 "틀린 걸 자신있게 만드는 것".

- **① Intake (재질의 — *수집이 아니라 심문*)** — 사용자에게 의도·니즈·목표·성공기준·제약·비범위를 *재질의*해 구체화·명확화. 말한 *해법* 말고 그 밑의 *문제*(JTBD). 가정으로 메우지 말고 `AskUserQuestion`(명확해질 때까지).
  - **2모델 적대 Intake (방향-설정 작업이면 default-on; 1줄잡일·UI문구·소버그픽스 제외):** Claude 혼자 묻지 말고 **Codex에 brief를 넘겨 "내가 놓친 필수질문 + 사용자가 말한 의심 전제"를 받는다(각 ≤5).** 각 질문은 *"이 답이 plan을 바꾸나?"* 통과 필수, **BLOCKER**(사용자에 직접) / **RISK**(②Prior-art서 검증) / **LATER**(버림) 등급. 비용통제 = "Codex 부를지"가 아니라 *산출 ≤5 + 승격 기준*으로 (좋은 과적=전제공격·증거게이트·kill조건 / 나쁜 과적=질문 합집합·체크리스트 비대화 차단). *발동 게이트는 내 판단이라 샐 수 있음 — 사용자가 "kickoff"/"grill해"로 강제 가능.*
  - **flagged-assumption 추적:** 위험 전제(예: 스케일 안 맞는 모델 고집)는 `전제 | 왜 위험 | 필요 증거 | kill 조건 | 상태` 표에 등록. **핵심: "검증하자"가 아니라 "이 증거 *없으면* 죽인다"(kill 조건)를 *먼저* 쓴다.** ②Prior-art·③Plan·plan-redteam이 이 표를 들고 가 *증거 없으면 폐기* → 틀린 방향이 조용히 통과 못 함.
- **② Prior-art (레퍼런스·벤치마킹)** — 경쟁자·유사 서비스·선행 프로젝트 3~5개를 찾아 비교. **단 "내 상황·조건에서 쓸 것 / 버릴 것"까지 명시**(맹목 벤치마킹 금지). 체크포인트마다 "레퍼 대비 우리 위치" 재비교. [[brainstorm-reference-prior-art]]
  - **🔎 `deep-research` 스킬 — 다중출처 조사에 적합하나 *발동 전 항상 사용자에게 확인* (2026-06-05 maintainer 지시로 자동발동 폐지).** 멀티에이전트 팬아웃(검색 병렬 → 소스 fetch → 적대검증 → 인용 리포트)이라 단발 WebSearch보다 **토큰 몇 배·수 분 소요** → 다중출처 조사가 필요한 단계(②Prior-art·research·"X 알아봐/조사해"·시장/경쟁/기술 심층질문)에서 **단발 검색으로 갈지 / `deep-research`를 돌릴지 `AskUserQuestion`으로 먼저 묻는다.** *예외(묻지 않음):* ① 사용자가 그 메시지에서 "딥리서치/깊게 조사해"로 명시 요청 = 이미 승인 → 바로 발동, ② 1줄짜리 단건 사실조회 = 애초에 deep-research 대상 아님 → 단발 검색. *(저장 워크플로 `council-research`(적대검증·cap 내장)도 같은 확인 규칙 적용.)*
- **③ Plan** — 성공기준·제약·전략·가정을 짧은 written frame + 가장 단순한 경로 → 사용자 확인 후 구현. frame은 `~/main/projects/*.md`의 씨앗. *(sub-item 수렴/발산/하이브리드 모드 태그는 ④ 참조 — 정의·research·plan 공통.)*
- **④ Escalation — 단계별 모드·권한 (작업무게 '자동선택' 아님, *단계 고정*)**
  - **🔥 풀파워 하이브리드** (발산→수렴 · Claude+Codex 2모델 + *양쪽* 서브에이전트 병렬 + 웹검색) = **정의·research·plan·마무리(wrap-up 점수화)**. 프로젝트 최중요 단계라 *항상* 풀가동, 자원 안 아낀다. 각 sub-item에 수렴/발산/하이브리드 태그 ([[brainstorm-mode-per-subitem]]).
  - **수렴·직렬** (codex 적대 회의) = **구현·검증·리뷰**. 답이 좁아(스펙대로/통과여부/결함찾기) 발산 불필요 → codex와 *순차* 협업(`/codex:review`).
  - **codex sandbox**: 기획/리뷰 = `read-only`+`tools.web_search=true` (쓸 게 없으니 read-only지 성능제한 아님 — 읽기·웹검색·서브에이전트 풀가동), 구현/rescue = `workspace-write -C <repo>`. **`danger-full-access` = 격리환경(throwaway 브랜치·컨테이너·no-secrets) 전제로만 허용** — 크리덴셜 있는 실작업 머신(WSL 메인)에선 `workspace-write`.
  - **codex도 서브에이전트 적극** — Claude와 대칭으로 독립 하위작업 병렬 스폰·비교(프롬프트로 지시; 토큰↑). 풀파워 = *양쪽 모델 모두* 서브에이전트+웹검색.

**강도 = 모호성 × 스테이크.** 명백한 1줄 잡일은 Gate 스킵(가정만 명시하고 진행). 단 Phase 0/research/plan을 *거치는* 작업은 위 ④대로 항상 풀파워. 모든 요청을 심문으로 만들지 말 것.
