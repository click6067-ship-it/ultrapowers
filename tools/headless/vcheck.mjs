// vcheck — 헤드리스 시각 검증. 데스크톱+모바일 스샷, 가로 오버플로, 콘솔에러.
// usage: node vcheck.mjs <url> [outdir]
import { chromium, devices } from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// chromium 시스템 라이브러리(영구 위치)를 자식 프로세스에 상속 → WSL에서 sudo 없이 동작
const LIBDIR = path.join(os.homedir(), '.claude/tools/headless/chromedeps/usr/lib/x86_64-linux-gnu');
if (fs.existsSync(LIBDIR)) process.env.LD_LIBRARY_PATH = `${LIBDIR}:${process.env.LD_LIBRARY_PATH || ''}`;

const url = process.argv[2];
if (!url) { console.error('usage: node vcheck.mjs <url> [outdir]'); process.exit(1); }
const OUT = process.argv[3] || path.join(os.tmpdir(), 'vcheck-' + Date.now());
fs.mkdirSync(OUT, { recursive: true });

async function check(label, opts) {
  const b = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const ctx = await b.newContext(opts);
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
  p.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message.slice(0, 200)));
  const r = { label };
  try {
    await p.goto(url, { waitUntil: 'networkidle', timeout: 40000 });
    await p.waitForTimeout(1600);
    const shot = path.join(OUT, `${label}.png`);
    await p.screenshot({ path: shot });
    const m = await p.evaluate(() => ({ docW: document.documentElement.scrollWidth, winW: window.innerWidth, title: document.title }));
    r.status = 'ok'; r.screenshot = shot; r.title = m.title;
    r.horizontalOverflow = m.docW > m.winW + 1; r.docWidth = m.docW; r.winWidth = m.winW;
  } catch (e) { r.status = 'error'; r.error = e.message.split('\n')[0]; }
  r.consoleErrors = errs;
  await b.close();
  return r;
}

const desktop = await check('desktop', { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const mobile = await check('mobile', { ...devices['iPhone 13'], hasTouch: true });
console.log(JSON.stringify({ url, outDir: OUT, desktop, mobile }, null, 2));
