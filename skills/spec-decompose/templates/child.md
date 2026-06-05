---
spec_id: <project>.<section_slug>
type: section_spec
project: <project>
parent: <project>.master
decomposition_axis: capability   # 부모와 같은 axis (web이면 ui_section)
source:
  path: master.md
  anchor: <section-slug>          # master의 ## 헤더 슬러그 (spec_doctor STALE 검사에 사용)
  source_hash: <sha256:...>       # 분해 시점 master 섹션 해시 (spec_doctor가 채움/비교)
status: draft                     # draft | hand_edited | approved
depth: 1
complexity_score: <0-12>          # advisory only (MVP는 인간 split/no-split)
open_amendments: []               # []여야 approved/handoff 가능
handoff_to_writing_plans:         # readiness=ready인 leaf만 필수
  scope: <이 섹션이 구현할 범위>
  non_goals: []
  dependencies: []                # [<다른 spec_id>] | none
  acceptance_criteria: []         # outcome-level (관측가능 결과). 이 child가 canonical 소유자.
  verification: []                # 테스트/시각/상호작용 acceptance
  open_questions: []
  readiness: not_ready            # ready | not_ready | out_of_scope
---

# <섹션명> 기획서 (child spec)

> 이 spec은 `master.md`에 종속된다. 본 문서가 master와 충돌하면,
> 승인된 amendment가 명시하지 않는 한 master가 우선한다.

## 무엇 (What)
<이 섹션이 무엇인지. 구현 "어떻게"가 아니라 "무엇/왜". 구현계획은 writing-plans 소유.>

## 왜 (Why)
<economic-prior / 근거.>

## 요구사항 (Requirements)
<각 요구에 origin/confidence 태그. LLM 확장은 confidence: proposed 기본.>
- [direct] <master에 명시된 것>  · origin: master#<anchor>
- [proposed] <LLM이 추가 제안 — 자동 요구사항 승격 금지>
