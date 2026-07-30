---
title: <기능/프로젝트 이름> PRD
status: draft            # draft → ready_for_decomposition → implemented
owner: <작성자>
date: <YYYY-MM-DD>
seed: <kickoff plan.md 경로 또는 "직접 작성">
---

# <이름> — PRD

## 1. 문제 (Problem)
<!-- 누가, 무엇 때문에, 왜 지금 아픈가. 해법 언급 금지 — 문제만. 2-4문장. -->

## 2. 목표 (Goals)
<!-- 이 작업이 성공하면 무엇이 참이 되나. 3개 이하. -->
-

## 3. 비목표 (Non-Goals)
<!-- 의도적으로 안 하는 것. 스코프 폭발 방지의 핵심 — 최소 2개. -->
-

## 4. 사용자와 핵심 시나리오 (Users & Stories)
<!-- 역할별 1-3개. 형식: <역할>는 <상황>에서 <행동>해서 <가치>를 얻는다.
     스토리마다 AC(수용 기준) 1줄: GIVEN <상황> WHEN <행동> THEN <판정 가능한 결과>
     — AC가 "이 스토리 완료"의 판정 기준이자 TDD 테스트의 씨앗. 복잡한 흐름만 유즈케이스(기본/예외 흐름)로 승격. -->
- 스토리:
  - AC:

## 5. 요구사항 (Requirements)
<!-- 자명한 요구는 평문으로. **해석이 갈릴 수 있는 요구만** EARS로 승격:
     WHEN <조건/이벤트> THE SYSTEM SHALL <측정 가능한 동작>
     IF <원치 않는 상황> THEN THE SYSTEM SHALL <방어 동작> -->
### 기능 (FR)
- FR-1:
### 비기능 (NFR — 29148 카테고리: 성능·보안·가용성·사용성·유지보수·이식/상호운용·비용·프라이버시, 해당 시만)
- NFR-1:

## 5b. 인터페이스 · 입출력 (I/O)
<!-- Wiegers "External Interface Requirements" 축약. 인풋: 소스·형식·볼륨 / 아웃풋: 형태·채널·빈도.
     외부 API·타 시스템 연동이 있으면 계약(endpoint·타입)을 여기 또는 별도 파일로. 없으면 "해당 없음". -->
- 인풋:
- 아웃풋:
- 외부 연동:

## 5c. 가정·제약 (Assumptions & Constraints)
<!-- 참이라고 믿고 진행하는 것(가정 — 틀리면 plan이 바뀌는 것 위주) + 주어진 한계(제약 — 스택 지정·예산·환경·마감).
     kickoff flagged-assumption 표가 있으면 여기로 승계. -->
- 가정:
- 제약:

## 6. 성공 지표 (Success Metrics)
<!-- 측정 가능·반증 가능하게. "X가 Y 이하/이상" 형식. 출시 판정 기준 겸용. -->
-

## 7. 마일스톤 (Milestones)
<!-- 최소 버전(MVP)에 뭘 넣고 뭘 미루나. 의도적 연기 1개 이상. -->
- M1 (MVP):
- 연기:

## 8. Open Questions
<!-- 모르는 것. 지어내지 않고 여기 남긴 것들 — 결정적이면 착수 전 해소. -->
-
