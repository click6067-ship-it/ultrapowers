---
paths:
  - "**/*.css"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.vue"
  - "**/*.svelte"
  - "**/*.html"
---
# 🎨 디자인 Anti-Slop 집행 (2026-07-03 — 법에 법원 달기)

**문제**: LLM 디자인은 학습분포 최빈값(Inter·보라 그라데이션·SaaS 카드 템플릿)으로 수렴한다. "디자인 DNA 문서"만으로는 표면만 바뀜 — 실증됨. **프로세스가 프롬프트를 이긴다.**

## 강제 순서 (디자인 작업 = UI 신규/개편이 목적인 작업)
1. **레퍼런스 먼저** — 실제 사이트/작품 2-3개 수집(스크린샷: vcheck.mjs 활용 가능), 각각 "왜 통하는지" 1줄. 사용자가 안 줬으면 물어서 받거나 제안해 승인받는다. **레퍼런스 없이 코드 금지.**
2. **토큰 고정** — 레퍼런스에서 색(4-6개, daltonized 절제 규율 준수)·타이포 3종(과사용 폰트 금지: Inter/Roboto/Arial/Space Grotesk)·spacing 리듬·radius를 뽑아 **스펙 파일(design-tokens)로 고정**. 시그니처 요소 1개 지정.
3. **발산 후 통합 금지** — 방향이 갈리면 2-3개 옵션을 *따로* 만들고 사용자가 고른다(중간 머지 = 평균 회귀 = slop).
4. **코드 → 결정론 채점** — 구현 후 `node ~/.claude/tools/headless/sloplint.mjs <url>` (11규칙, LLM-free). 신호 = 의도적 선택(레퍼런스 근거)인지 기본값 수렴인지 판정. 기본값 수렴이면 재작업.
5. 스크린샷 시각 리뷰(vcheck)는 병행 — 단 sloplint 결과가 우선(LLM 시각판정은 같은 prior로 수렴 위험).

## 자기비판 질문 (frontend-design 플러그인 2-패스 방식 차용)
산출 전: "이 페이지의 어떤 요소가, 같은 주제의 *아무* 페이지에나 낼 법한 기본값처럼 읽히는가?" — 답이 '없다'가 될 때까지.

**구조 레이어 정본 = DESIGNDNA repo** (`~/ghq/github.com/click6067-ship-it/DESIGNDNA`): 방향-설정 디자인은 `DESIGN_DNA-anti-convergence.md`(구조)와 surface(`DESIGN_DNA.md`+`dna.css`)를 *함께* 넘기고 그 게이트(①native artifact 식별 ②구조 도출 ③5안 생성 후 median kill ④anti-reference 선언 ⑤"제품명 바꿔도 재사용 가능하면 실패" 테스트, **최초 structural bet은 사람이 author**)를 따른다. 이 파일 = 그 위의 **기계 집행 레이어**(레퍼런스-first 순서 + sloplint 결정론 채점, 2026-07-03 신설). 문제 기록: 주 키 메모리 `feedback_design_convergence.md`.
