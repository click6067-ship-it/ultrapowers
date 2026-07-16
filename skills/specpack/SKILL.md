---
name: specpack
description: Use when the user says PRD 써줘/스펙 정식화/기획 규격화/specpack/ERD 그려줘/데이터모델 문서화/요구사항 정리해/개발 전 문서 만들어, or a kickoff-approved plan needs to become formal spec docs before implementation. Produces the standard pre-development doc chain — lightweight PRD (+EARS for ambiguous requirements), Mermaid-ERD data model, design doc, ADR — sized to stakes, then hands off to spec-decompose / writing-plans.
---

# specpack — 개발 착수 전 표준 스펙 문서 체인

**목적.** "모든 작업이 중구난방"을 끊는다: 코드 전에 **무엇을(PRD) · 데이터는(ERD) · 어떻게(design) · 왜 그렇게 정했나(ADR)**를 규격 문서로 고정하고 들어간다. 2026 SDD 정론(GitHub spec-kit·AWS Kiro·SVPG/Cagan)의 공통 구조를 1인 개발자+AI 에이전트 규모로 경량화한 것.

**포지셔닝 (기존 체인과의 관계 — 대체 아님).**
```
/kickoff (적대 기획회의 → plan.md 초안)          ← "방향" 소유
   ↓
specpack (이 스킬 — plan을 규격 문서로 정식화)     ← "문서 규격" 소유
   ↓
spec-decompose (큰 스펙만 — child 분해)           ← "스펙 트리" 소유
   ↓
superpowers writing-plans → TDD 구현              ← "구현 계획·태스크" 소유
```
kickoff 없이 바로 불려도 된다(소규모 기능). 단 문제정의가 흔들리면 Phase 0 Gate(Intake)부터.

## 문서 체인 — 무엇을 언제 만들고 언제 스킵하나 (스테이크 비례가 정론)

> 핵심 원칙(교차 검증된 업계 정론): **"스펙의 엄격함은 모호성을 제거하는 데 필요한 최소 수준으로"**(Addy Osmani). 전부 만드는 게 아니라, 아래 판정대로 **필요한 것만** 만든다. 과문서화도 실패다.

| 문서 | 파일 | 만든다 | 스킵한다 |
|---|---|---|---|
| **PRD** (경량, 1페이지 지향) | `docs/specs/<slug>/prd.md` | 새 프로젝트·새 기능·요구가 모호할 때 | 자명한 1-2단계 잡일, 순수 버그픽스 |
| **데이터 모델/ERD** | `docs/specs/<slug>/data-model.md` | DB/영속 스키마가 새로 생기거나 크게 바뀔 때 | DB 없음, 또는 테이블 1-2개로 자명 |
| **설계문서** | `docs/specs/<slug>/design.md` | 새 아키텍처·외부 API 계약·비가역 기술 선택이 있을 때 | 확립된 패턴 재사용이면 스킵 |
| **ADR** | `docs/adr/NNNN-<slug>.md` | 되돌리기 어려운 결정이 내려진 순간마다 1건 | 가역적·사소한 결정 |

파일 위치는 **해당 프로젝트 repo** 기준(spec-kit `specs/`·Kiro `.kiro/specs/` 관행의 절충 — `docs/` 아래로 모아 타인이 바로 찾게). 메타/전략 결정은 기존 `$COMMAND_CENTER/decisions/log.md` 그대로(그건 ADR의 경량 변형이다).

## 절차

### 0. 입력·스테이크 판정
- kickoff 산출 `plan.md`가 있으면 그걸 씨앗으로. 없고 요구가 모호하면 **Phase 0 Gate(Intake 재질의)부터** — specpack은 정식화 도구지 정의 도구가 아니다.
- 위 표로 **이번에 만들 문서 목록을 판정해 근거와 함께 1줄로 선언**한다 (예: "PRD+ERD 생성, design.md 스킵 — 기존 Next.js 패턴 재사용"). 사용자가 다르게 원하면 조정.

### 1. PRD 작성 — `templates/prd.md` 기반
채우기 규칙:
- **Non-Goals(비목표) 필수** — 2026 PRD 공통 진화점. "안 하는 것"이 스코프 폭발을 막는다.
- **성공 지표는 측정 가능(falsifiable)하게** — "좋아진다" 금지, "X가 Y 이하" 형식.
- **모호한 요구사항만 EARS 문장으로 승격** — `WHEN <조건> THE SYSTEM SHALL <동작>` (Rolls-Royce EARS, Kiro requirements.md 채택 표기). 전체를 EARS로 쓰지 않는다(해석이 하나뿐인 문장은 그대로).
- 모르는 건 지어내지 말고 **Open Questions**에 남긴다 — 결정적이면 사용자에게 질문.

### 2. 데이터 모델 — `templates/data-model.md` 기반 (해당 시)
- **Mermaid `erDiagram`**(Crow's Foot 카디널리티)로 작성 — 텍스트라 git diff·리뷰 가능, GitHub 네이티브 렌더.
- 실제 스키마(prisma/SQL/DDL)가 이미 있으면 **스키마가 정본, 이 문서는 도출물** — 스키마에서 생성하고 문서에 그 사실을 명시(드리프트 방지).
- 엔티티마다 "왜 존재하나" 1줄. 관계마다 카디널리티 근거가 비자명하면 주석.

### 3. 설계문서 — `templates/design.md` 기반 (해당 시)
- Google Design Docs 축약형: 컨텍스트/목표 → 제안 설계(다이어그램·API 계약) → **고려한 대안과 트레이드오프**(최소 1개 — 대안 없는 설계문서는 설계가 아니라 통보) → 리스크.
- 여기서 내려진 비가역 결정은 각각 ADR로도 1건씩 (`templates/adr.md`, Nygard 4필드).

### 4. 마무리·handoff
- PRD frontmatter에 `status: ready_for_decomposition` 마킹 (spec-decompose 사전조건 게이트와 연결).
- 분해가 필요한 크기(섹션 ≥2, 독립 모듈)면 → **spec-decompose**. 아니면 바로 → **superpowers writing-plans**.
- 산출 요약: 만든 문서 목록 + 스킵한 문서와 근거 + Open Questions 수.

## 안 하는 것
- 구현 태스크·테스트케이스 작성 (writing-plans 소유).
- 전 문서 강제 생산 (스테이크 판정 없이 4종 다 만들면 이 스킬을 잘못 쓴 것).
- 지어낸 지표·가짜 정밀도 (모르면 Open Question).
- kickoff/브레인스토밍 대체 (방향이 안 잡힌 브리프는 Phase 0로 반려).
