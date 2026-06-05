// demo — 일관된 모션의 제품 데모 녹화(MP4+GIF). 레티나 PNG 프레임 → ffmpeg 합성.
// usage: node demo.mjs <url> [scenario.mjs] [outdir]
//   scenario.mjs: `export default async function(page, h){ ... }` (h = {shoot, hold, scrollTween, setSlider, ease, page})
//   없으면 기본 = 위→아래 부드러운 스크롤 통과.
import { chromium } from 'playwright';
import ffmpegPath from 'ffmpeg-static';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const LIBDIR = path.join(os.homedir(), '.claude/tools/headless/chromedeps/usr/lib/x86_64-linux-gnu');
if (fs.existsSync(LIBDIR)) process.env.LD_LIBRARY_PATH = `${LIBDIR}:${process.env.LD_LIBRARY_PATH || ''}`;

const url = process.argv[2];
const scenarioPath = process.argv[3] && process.argv[3] !== '-' ? process.argv[3] : null;
const OUT = process.argv[4] || path.join(os.tmpdir(), 'demo-' + Date.now());
if (!url) { console.error('usage: node demo.mjs <url> [scenario.mjs|-] [outdir]'); process.exit(1); }

const W = 1100, H = 760, FPS = 30;
const FR = path.join(OUT, 'frames');
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(FR, { recursive: true });
const ease = (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);

const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
await page.waitForTimeout(1400);

let idx = 0, last = null;
const h = {
  page, ease,
  async shoot() { const f = path.join(FR, `f${String(idx).padStart(4, '0')}.png`); await page.screenshot({ path: f }); last = f; idx++; },
  hold(n) { for (let i = 0; i < n; i++) { const f = path.join(FR, `f${String(idx).padStart(4, '0')}.png`); fs.copyFileSync(last, f); idx++; } },
  async scrollTween(toY, frames = 24) {
    const fromY = await page.evaluate(() => window.scrollY);
    for (let i = 1; i <= frames; i++) { await page.evaluate((y) => window.scrollTo(0, y), Math.round(fromY + (toY - fromY) * ease(i / frames))); await h.shoot(); }
  },
  // 컨트롤된 <input> 슬라이더 값 변경(React onChange 트리거). selector 기본 #ctxSlider.
  async setSlider(value, selector = '#ctxSlider') {
    await page.evaluate(([sel, v]) => { const el = document.querySelector(sel); if (!el) return; const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; s.call(el, String(v)); el.dispatchEvent(new Event('input', { bubbles: true })); }, [selector, value]);
  },
};

async function defaultScenario(page, h) {
  await h.shoot(); h.hold(10);
  const max = await page.evaluate(() => document.body.scrollHeight - window.innerHeight);
  await h.scrollTween(Math.max(0, max), 90);
  h.hold(20);
}

let scenario = defaultScenario;
if (scenarioPath) { const mod = await import(pathToFileURL(path.resolve(scenarioPath)).href); scenario = mod.default; }
await scenario(page, h);
await browser.close();

const inPat = path.join(FR, 'f%04d.png');
execFileSync(ffmpegPath, ['-y', '-framerate', String(FPS), '-i', inPat, '-c:v', 'libx264', '-crf', '18', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-vf', 'scale=1280:-2', '-movflags', '+faststart', path.join(OUT, 'demo.mp4')], { stdio: 'ignore' });
execFileSync(ffmpegPath, ['-y', '-framerate', String(FPS), '-i', inPat, '-vf', 'fps=20,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=160[p];[s1][p]paletteuse=dither=floyd_steinberg', path.join(OUT, 'demo.gif')], { stdio: 'ignore' });
const sz = (f) => (fs.statSync(path.join(OUT, f)).size / 1048576).toFixed(2) + 'MB';
console.log(`DONE: ${idx} frames (${(idx / FPS).toFixed(1)}s) · ${path.join(OUT, 'demo.mp4')} (${sz('demo.mp4')}) · demo.gif (${sz('demo.gif')})`);
