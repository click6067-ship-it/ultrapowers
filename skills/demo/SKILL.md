---
name: demo
description: Record a polished, consistent-motion product demo (MP4 + GIF) of a web page using scripted headless browser automation. Captures retina PNG frames and assembles them at 30fps for crisp, smooth output — far better than hand-recorded screen capture. Use when the user wants a demo video / GIF / screencast for a launch (Reddit, X, GeekNews, etc.).
---

# demo — scripted product demo recorder

Produces a launch-quality MP4 (1280px, crisp) + GIF from a scripted interaction. Consistent motion (the "Telegram-style" feel) because every frame is rendered, not hand-captured.

## How to run

```bash
node ~/.claude/tools/headless/demo.mjs <url> [scenario.mjs|-] [outdir]
```

- No scenario → default smooth top-to-bottom scroll-through of the page.
- Custom interaction → write a scenario file (below).
- Self-injects chromium libs; outputs `demo.mp4` + `demo.gif` to the out dir.

## Writing a scenario (custom interactions)

A scenario is an ES module exporting a default async function `(page, h)`. Helpers in `h`:

- `await h.shoot()` — capture one frame.
- `h.hold(n)` — duplicate the last frame `n` times (a pause; n frames ÷ 30 = seconds).
- `await h.scrollTween(toY, frames)` — eased scroll, capturing each frame.
- `await h.setSlider(value, selector='#ctxSlider')` — set a controlled `<input range>` (fires React onChange).
- `h.page`, `h.ease` — raw Playwright page + easing fn.

Example (drag a slider, then reveal a section):
```js
export default async function (page, h) {
  await h.shoot(); h.hold(8);
  const top = await page.evaluate(() => document.getElementById('ctxSlider').getBoundingClientRect().top + scrollY);
  await h.scrollTween(top - 90, 24); h.hold(8);
  for (let i = 0; i <= 60; i++) { await h.setSlider(Math.round((8192 + 250000 * h.ease(i/60))/1024)*1024); await page.waitForTimeout(6); await h.shoot(); }
  h.hold(30);
}
```

## After running

- **Post MP4, not GIF** (Reddit/X autoplay video natively; sharper + smaller). GIF is the fallback for GitHub READMEs / Discord.
- Offer to open the out folder in Windows: `explorer.exe "$(wslpath -w <outdir>)"`.
- Extract a few frames (`ffmpeg -ss <t> -i demo.mp4 -frames:v 1 f.png`) and Read them to verify the capture looks right before handing off.

## Tips
- Click buttons via `page.evaluate(() => [...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='X').click())` to avoid Playwright auto-scroll jumping the framing.
- Keep total length ~8–12s. Frame densely (30fps) + ease for smoothness.
