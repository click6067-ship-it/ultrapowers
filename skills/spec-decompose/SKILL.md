---
name: spec-decompose
description: Phase 0 마스터 기획서(spec/기획서)를 섹션별 child spec으로 분해하는 범용 spec tree manager. master를 읽고 LLM이 분해안(섹션 트리+복잡도)을 제안→사용자 승인→child spec 스켈레톤 생성. 기획(spec)에서 멈추고 구현계획·태스크는 superpowers writing-plans에 handoff(세 번째 프레임워크 아님). 결정론적 검증·tree 재생성은 spec_doctor.py. "기획서 분해", "decompose spec", "마스터 기획서 쪼개", "스펙 트리", "spec-decompose", "spec-doctor" 요청 시. 이 SKILL.md가 절차 정본.
---

# spec-decompose — 재귀적 기획서 분해 (spec tree manager)

**목적.** Phase 0의 큰 마스터 기획서를 들고만 있지 말고 섹션별 child spec으로 쪼개 심층 정의하되, 쪼개기·연결·마스터변경 추적을 시스템이 떠먹여주게 한다. **기획에서 멈추고** 구현계획은 writing-plans에 넘긴다.

**핵심 포지셔닝 (절대 위반 금지).** 이건 **spec tree manager지 기획 프레임워크가 아니다.** superpowers(brainstorming/writing-plans/kickoff)를 *대체* 안 하고 그 위에 얹혀 **스펙 트리의 구조·연결·변경·승인 상태만** 관리한다. 경계:
- **이 시스템 = spec(기획서) 소유** — "무엇/왜".
- **writing-plans = plan/task 소유** — "어떻게 구현". child spec은 plan prose를 쓰지 않는다.
- 이 경계가 흐려지면 = 예전에 제거한 "두 번째 프레임워크" 재현 = 즉시 롤백.

**정본.** 절차 정본 = 이 SKILL.md (자기완결적, clone-anywhere). 설계 근거·kickoff 회의록은 작성자 노트(`$COMMAND_CENTER/projects/spec-decompose-design.md`, 기본 `$COMMAND_CENTER`)에 있으나 *스킬 동작에 필수 아님* — 없어도 스킬은 돈다.

---

## 권한 서열 (governance of truth)
master > 승인된 amendment > child > writing-plans 출력 > /kickoff(advisory) > 코드.
모든 child 본문 하단 고정: `> 이 spec은 master.md에 종속. 충돌 시 승인된 amendment 없으면 master 우선.`

---

> **호출.** 이건 슬래시커맨드가 아니라 **스킬**이다. 사용자가 "기획서 분해해줘 <master.md>" 또는 "spec-decompose" / "spec-doctor 돌려줘"라고 하면 이 스킬이 발동된다. (스킬은 리터럴 `/decompose-spec` 슬래시를 등록하지 않는다 — 아래 "모드"는 이 스킬 안의 두 동작 흐름을 가리킨다.)

## 모드 1 — 분해 ("기획서 분해 <master.md>")

### 0. 사전조건 게이트
master를 Read. 다음이 **전부** 있어야 진행 (없으면 "master 먼저 완성" 거부, 설익은 분해→amendment storm 차단):
- frontmatter `status: ready_for_decomposition` (아니면 사용자에게 마킹 요청)
- 본문에 problem · success criteria · non-goals · **분해가능 후보 섹션 ≥2**

### 1. PLAN-ONLY (쓰기 0 — 먼저 제안)
master를 읽고 **섹션 트리를 제안만** 한다 (파일 생성 전혀 안 함):
- 섹션 목록 (master의 ## 헤더 우선 참고, 없으면 LLM이 논리적 분해 제안)
- 섹션별 **복잡도 점수**(0-12, advisory) + split/no-split 권고 + 근거 1줄
- 토큰/개수 추정
- **guardrail (하드):** 총 spec ≤ 10 (master 포함) · 첫 패스 재귀 금지 · 패스당 새 spec ≤ 5. 10 초과면 병합 강제 또는 deferred 표시.
세션에 트리를 출력하고 **사용자 승인을 기다린다.** (승인 전 쓰기 절대 금지.)

### 2. 승인 후 — child 스켈레톤 생성
승인된 섹션마다 `templates/child.md` 기반으로 `<specs_dir>/sections/<slug>/spec.md` 생성:
- frontmatter: spec_id·parent·source(path/anchor/source_hash)·complexity_score 채움
  - **source_hash = master 해당 ## 섹션 내용의 sha256[:12]** (spec_doctor와 동일 방식: 헤더 제외 섹션 본문)
- 본문: master 섹션에서 추출한 "무엇/왜" + 요구사항(각 origin/confidence 태그, LLM 확장은 `proposed`)
- **child 본문은 spec prose** — 구현 "어떻게"/태스크/테스트케이스 금지(그건 writing-plans).
- handoff 블록은 틀만 (readiness: not_ready). leaf가 실제 ready 되는 건 사용자가 채운 뒤.

### 3. 마무리
- `spec_doctor.py <specs_dir> --rebuild-tree` 실행 → tree.yaml 생성 + 검증.
- 결과 요약 + "각 child를 채운 뒤 writing-plans로 넘기세요" 안내.

---

## 모드 2 — 검증 ("spec-doctor <specs_dir>")
`python3 <skill_dir>/tools/spec_doctor.py <specs_dir> [--rebuild-tree] [--json]` 실행. (skill_dir = 이 SKILL.md가 있는 디렉토리.)
검사: frontmatter 필수필드 · 중복 spec_id · 고아 parent · 깨진 source.path · **STALE**(master 섹션 해시≠child source_hash) · ready leaf의 handoff 완전성.
**silent recovery 금지** — 깨진 건 조용히 고치지 않고 *리포트*. 결과를 사용자에게 그대로 전달.
(approval/handoff/rebuild 전에 항상 먼저 돌릴 것.)

---

## MVP 경계 (지금 있는 것 / 없는 것)
**있음:** 사전조건 게이트 · plan-only 분해 · 승인 후 child 스켈레톤 · spec_doctor(검증+tree재생성).
**없음(설계는 됐으나 deferred):** 재귀(depth>1) · `/reconcile-spec`(amendment) · 복잡도 자동임계값 · `/kickoff-section` · 훅.
→ MVP는 프라마나로 dogfood해 성공기준(설계 §7) 실측 후 확장. generic 주장은 프라마나(capability)+web(ui_section) 2 axis 통과 전 **미검증.**

## 안 하는 것
- 승인 전 파일 쓰기. · child에 구현 태스크/plan prose 작성. · master 전체를 child마다 컨텍스트로 주입(부모 섹션+요약만). · 자동 재귀. · spec_doctor가 깨진 걸 조용히 복구.
