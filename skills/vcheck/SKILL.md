---
name: vcheck
description: Headless visual verification of a live URL or local dev server — captures desktop + mobile screenshots, detects horizontal overflow, and reports console/page errors. Use after deploying, after a UI change, or whenever the user asks to verify how a page looks or whether it renders correctly without errors.
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

## Notes

- If chromium fails to launch with a missing-lib error, the persistent libs at `~/.claude/tools/headless/chromedeps` may be gone — re-extract them (debs: libnspr4, libnss3, libasound2t64 via `apt-get download` → `dpkg-deb -x`).
- For a richer interaction check (clicking, scrolling, state changes), write a one-off Playwright script instead.
