---
spec_id: <project>.master
type: master
project: <project>
status: draft            # draft | ready_for_decomposition | approved
revision: <ISO8601>
content_hash: <sha256>   # spec_doctor가 채움
decomposition_axis: capability   # capability | ui_section | workflow | data_domain | service | cross_cutting
---

# <프로젝트> 마스터 기획서

> 사전조건(이게 있어야 /decompose-spec이 확장): problem · success criteria · non-goals · 분해가능 후보 섹션 ≥2.

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
