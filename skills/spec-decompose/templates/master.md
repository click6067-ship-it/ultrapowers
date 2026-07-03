---
spec_id: <project>.master
type: master
project: <project>
status: draft            # draft | ready_for_decomposition | approved
revision: <ISO8601>
content_hash: <sha256>   # 선택 — 스킬 절차 중 수동 기입(spec_doctor는 섹션 해시만 계산·비교, 이 필드는 자동 기입 안 함)
decomposition_axis: capability   # capability | ui_section | workflow | data_domain | service | cross_cutting
---

# <프로젝트> 마스터 기획서

> 사전조건(이게 있어야 spec-decompose 스킬이 확장 — 슬래시커맨드 아님, "기획서 분해해줘"로 발동): problem · success criteria · non-goals · 분해가능 후보 섹션 ≥2.

## Problem / 니즈
<누가·무엇을·왜 지금. 해법 말고 그 밑의 문제(JTBD).>

## Success criteria (falsifiable)
<"됐다"를 측정 가능하게.>

## Non-goals / 비범위
<안 할 것.>

## <섹션 1 — 예: Data layer>
<...>

## <섹션 2 — 예: Research factory>
<...>
