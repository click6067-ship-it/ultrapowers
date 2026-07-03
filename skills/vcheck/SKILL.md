---
name: vcheck
description: Use when the user says vcheck/시각 검증/화면 확인/렌더 확인/디자인 확인/스크린샷 찍어봐, or after deploying or changing UI. Headless visual verification of a live URL or local dev server — desktop+mobile screenshots, horizontal-overflow detection, console/page errors, and deterministic AI-slop design checks (sloplint).
---

# vcheck — headless visual check

Verify a web page renders correctly across desktop + mobile, with no layout overflow or JS errors.

## How to run

```bash
node ~/.claude/tools/headless/vcheck.mjs <url> [outdir]
```

- `<url>` — live site, preview URL, or local dev server (e.g. `http://localhost:3000`).
- The script self-injects the chromium system libs (`~/.claude/tools/headless/chromedeps`), so no `LD_LIBRARY_PATH` export is needed.
- It prints a JSON report and writes `desktop.png` + `mobile.png` to the out dir.

## What you do after running

1. Read the JSON: flag `horizontalOverflow: true` (left/right clipping) and any `consoleErrors`.
2. **Read the two screenshot PNGs** with the Read tool to visually inspect layout, spacing, and content — don't just trust the JSON.
3. Report findings concisely: render OK? overflow? errors? + anything visually off.

## Slop check (디자인 검증일 때 — 결정론적, LLM-free)

```bash
node ~/.claude/tools/headless/sloplint.mjs <url> [--json]
```
- 11개 결정론 규칙으로 AI-slop 텔 검사(Inter 폰트·보라 그라데이션·gradient text·동일 radius 카드·아이콘 3-4박스·badge-above-h1·이모지 제목·올캡 eyebrow·통계 배너·원형 숫자 스텝·패딩 단조). exit 1 = 신호 검출.
- **왜 결정론인가**: LLM 채점자는 같은 학습분포를 공유해 slop을 slop으로 못 알아본다(2026 정론) — 스크린샷 시각판정과 *병행*하되 이 결과가 우선.
- 신호 검출 시: 각 항목이 **의도적 선택**(레퍼런스 근거 있음)인지 **기본값 수렴**인지 판정해 보고. 기본값 수렴이면 `~/.claude/rules/design-antislop.md`의 레퍼런스-first 프로세스로 재작업 제안.
- 실측 기준선: fitllm.run = 6/11 (2026-07-03) — 개선 전후 비교용.

## Notes

- If chromium fails to launch with a missing-lib error, the persistent libs at `~/.claude/tools/headless/chromedeps` may be gone — re-extract them (debs: libnspr4, libnss3, libasound2t64 via `apt-get download` → `dpkg-deb -x`).
- For a richer interaction check (clicking, scrolling, state changes), write a one-off Playwright script instead.
