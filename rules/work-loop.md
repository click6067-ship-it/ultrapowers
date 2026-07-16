# 🔁 작업 루프 + 시스템 빠른 참조

**Phase 0(정의)** → research → plan → 브랜치 구현 → 테스트 → **codex review**(핵심/엔진/데이터 코드) → vcheck(UI) → PR → CI → ship.
크로스리뷰·서브에이전트·MCP는 **과적 금지** — 복잡·핵심 작업에 선택적으로.

## 한 문장 브리프 → 완성물 파이프라인 (2026-07-03 명문화 — 단계마다 도구·게이트)
"X 만들고 싶어" 류 새 프로젝트 브리프가 오면 이 체인을 탄다 (2026 SDD 정론과 동형 — spec→plan→tasks→implement):
1. **Intake·기획**: `/kickoff` (2모델 적대, BLOCKER는 사용자에) → 기획서. 레퍼런스·경쟁사 분석은 ②Prior-art에서 **ask-first**(자동발동 금지 — 업계도 자동 삽입 안 함이 검증됨).
2. **정식화**: `/specpack` (2026-07-16 신설) — plan을 규격 문서로: 경량 PRD(Non-Goals·측정가능 지표 필수, 모호 요구만 EARS) + DB 있으면 Mermaid-ERD `data-model.md` + 새 아키텍처면 `design.md` + 비가역 결정마다 ADR. **스테이크 비례 — 필요한 문서만**(전부 강제 = 과문서화 실패). 산출은 그 repo `docs/specs/<slug>/`.
3. **분해**: 큰 기획서면 `/spec-decompose` → child specs. ⚠️ 과분해 재검사: 모델이 강할수록 잘게 쪼개는 게 손해(Anthropic 2026 하니스 교훈) — 독립 모듈일 때만 분해.
4. **구현**: **Opus 세션**(모델 배분 규칙), superpowers writing-plans→TDD. 장기 작업은 progress 파일+증분 커밋(하니스 패턴), `/goal`은 루프 편의로. 병렬 필요 시 `claude agents`(Agent View)로 'Needs input' 트리아지.
5. **검증·ship**: verify.sh·테스트 → codex review → vcheck(+디자인이면 sloplint, 방향-설정 디자인이면 `/crit` 제안) → PR → ship.
6. **Compound**(작업 끝 1분): 이번에 배운 것·실수 1-2줄을 CLAUDE.md/rules/메모리에 — "실수마다 규칙화"가 프론티어 공통 습관(Hashimoto·Boris·Klaassen). 다음 단위가 쉬워져야 이번 단위가 끝난 것.

## 모델 배분 (2026-07-03 maintainer 지시 — 토큰 통제)
- **시스템 정비·개선·최신화(메타, ~/main·~/.claude 작업) = Fable** (`/model fable`).
- **실제 프로젝트 작업(코딩·구현) = Opus** (`/model opus`). 세션 시작 시 작업 성격에 맞는 모델인지 확인하고, 아니면 사용자에게 `/model` 전환을 제안.
- 서브에이전트 티어링은 별도(researcher=sonnet·verifier=sonnet·redteam=opus·Explore=haiku — frontmatter가 정본).

## 완료선언 규칙 (증거 없으면 완료 아님)
- **완료 증거는 transcript에 실물로** — 실제 명령·출력·exit code. 성공 *주장*은 증거가 아니다.
- **저스테이크·가역 작업은 "진행할까요?" 없이 끝까지 실행** (2026-07-16 로그 실측: 12세션에서 "묻지 말고 알아서" 재지시). 질문은 *모호성 해소용만* — Karpathy 1룰과 양립: 무엇을 할지 모호하면 묻고, 하기로 정해진 걸 진행할지는 묻지 않는다. 백그라운드 서브에이전트 대기 중에도 병행 작업.
- **카피·수치 클레임은 실측된 것만** ("5초 만에"류 — 라이브 동작으로 검증 안 된 문구는 UI에 못 쓴다. 실측 12세션 교정: "이 문구는 라이브 실행일 때만 진실").
- **`/goal`은 루프 편의 장치일 뿐** — evaluator는 transcript만 보므로(파일·명령 실행 안 함) 완료 *검증* 장치가 아니다. 최종 게이트는 항상 결정론 체크(테스트·`doctor.py`·`guardrail_test.py`·lint).
- 적대 리뷰어 주의: "갭을 찾으라는 리뷰어는 멀쩡한 작업에서도 갭을 찾는다"(공식 문서) — correctness·명시 요구사항에 영향 있는 지적만 반영, 나머지는 optional.

## 🤖 시스템 빠른 참조
- **백본 = superpowers** (유일 — gstack 제거됨, 2026-05-27 평가): 규율 학파 — brainstorm→plan→TDD→verification, 자동발동. **기본은 superpowers로 일한다.**
- **커스텀 스킬**: `/vcheck`(시각검증)·`/demo`(데모)·`/kickoff`(Claude↔Codex 적대 기획회의)·`/specpack`(PRD·ERD·design·ADR 규격 문서팩, 2026-07-16)·`/recall`·`/remember`·`/techreport`·`/spec-decompose`(마스터 기획서→child spec 분해)·`/qualityloop`(블라인드 2-judge 채점루프)·`/autopilot`(야간 자율 외곽 하네스, 기본 OFF)·`hallmark`(안티슬롭 디자인)·`/crit`(Codex 크로스모델 디자인·카피 비평, 2026-07-16)·`/ship`(verify→커밋→푸시→배포→vcheck 마무리 체인, 2026-07-16 — "푸시하고 배포까지" 47세션 반복 실측으로 신설)·`/serve`(dev서버 기동+localhost 4계열 진단, 2026-07-16 — 16세션 반복 실측).
- **커스텀 서브에이전트**: `redteam`(opus·인세션 비평)·`researcher`(sonnet·웹조사)·`verifier`(sonnet·단일주장 적대검증)·`judge`(rubric 채점 — qualityloop Judge B)·`Explore`(haiku 오버라이드 — 탐색 비용 방어).
- **저장 워크플로**: `council-research`(fan-out 리서치→주장 적대검증→인용종합)·`plan-panel`(다각도 blind plan→적대채점→종합)·`repo-audit`(shard→리뷰→검증). 전부 verify cap(25)+sonnet 티어링 내장.
- **Codex** 크로스리뷰: codex 플러그인(`/codex:review`·`/codex:rescue`) + 직접 `codex exec`(kickoff). 핵심/엔진/데이터 코드.
- **MCP**: context7=최신문서("use context7"), firecrawl=웹크롤·검색, vercel=배포. 셋 다 minimal 유지(공급망 공격면). 배포·시각검증은 vercel 플러그인·git/gh·`/vcheck`.
- **Agent Teams**(experimental, 플래그 활성): 워커끼리 발견 공유·반박이 필요할 때만 — 결과만 필요하면 서브에이전트가 저렴. 파일럿 게이트: kickoff 대비 실측 우위(unique finding ≥1 · FP 비악화 · ≤2×토큰) 확인 전까지 기본 채택 아님. 파일럿 프로토콜: 파일럿 1회 = 같은 brief를 kickoff vs Agent Teams로 A/B, 기록 필드 = {unique_useful_finding, false_positive, tokens, elapsed}, CPX root-cause·경쟁가설 디버깅에만. 기본 자동발동 금지.
- **도구 큐레이션 규율**: 월 1회 `/insights`로 미사용·반복 패턴 점검. 3개월 미발동 도구 = 삭제 후보("만들었으니 유지" 금지). 스킬 description은 트리거 키워드-first("when, not what") — 발동은 키워드 매칭에 가깝다(실측).
- 상세: `~/main/system/SYSTEM.md` (단일 정본 문서).
