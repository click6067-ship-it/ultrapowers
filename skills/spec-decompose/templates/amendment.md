---
amendment_id: <project>.<section_slug>.amend.<date>.<NNN>
target_spec: <project>.<section_slug>
source_spec: <project>.master
source_anchor: <section-slug>
old_source_hash: <sha256:...>
new_source_hash: <sha256:...>
conflict_class: elaboration       # contradiction | elaboration | proposal | implementation_feedback
status: pending_review            # pending_review | accepted | superseded
created_at: <ISO8601>
---
# Amendment: master <anchor> 변경

## Source Change
<master의 해당 섹션이 무엇이 바뀌었나.>

## Impact
<기존 child에 미치는 영향.>

## Proposed Append
<append할 내용 (덮어쓰기 아님).>

## Conflicts
<기존 child 요구와 충돌하는 점 — conflict_class 근거. blocked_by_conflict면 해소액션 1개 필요:
master 갱신 / amendment 수용 / child 요구를 proposed로 강등 / child 텍스트 삭제.>
