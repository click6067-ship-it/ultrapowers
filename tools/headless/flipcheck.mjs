import { chromium } from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const LIBDIR = path.join(os.homedir(), '.claude/tools/headless/chromedeps/usr/lib/x86_64-linux-gnu');
if (fs.existsSync(LIBDIR)) process.env.LD_LIBRARY_PATH = `${LIBDIR}:${process.env.LD_LIBRARY_PATH || ''}`;

const url = process.argv[2] || 'http://localhost:3000';
const OUT = process.argv[3] || '/tmp/flipcheck';
fs.mkdirSync(OUT, { recursive: true });

const b = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
await p.goto(url, { waitUntil: 'networkidle' });

// go to features section
await p.evaluate(() => document.getElementById('features')?.scrollIntoView({ block: 'center' }));
await p.waitForTimeout(800);

// the flip card = div.group with perspective; pick the first one in the desktop grid
const card = p.locator('div.group.\\[perspective\\:1200px\\]').first();
await card.waitFor({ state: 'visible' });
const box = await card.boundingBox();
console.log('card box', JSON.stringify(box));

// clip region with generous vertical margin so clipping at wrapper edge is visible
const clip = {
  x: Math.max(0, box.x - 20),
  y: Math.max(0, box.y - 60),
  width: box.width + 40,
  height: box.height + 120,
};

// 1) front (no hover) — move mouse away first
await p.mouse.move(10, 10);
await p.waitForTimeout(900);
await p.screenshot({ path: path.join(OUT, '1-front.png'), clip });

// hover to trigger flip (700ms duration)
await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
// 2) mid-flip (~350ms in)
await p.waitForTimeout(330);
await p.screenshot({ path: path.join(OUT, '2-midflip.png'), clip });
// 3) post-flip (settled)
await p.waitForTimeout(700);
await p.screenshot({ path: path.join(OUT, '3-back.png'), clip });

console.log('done ->', OUT);
await b.close();
