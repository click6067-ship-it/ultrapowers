// sloplint — 결정론적 AI-slop 디자인 검사 (LLM-free · 2026-07-03).
// 근거: LLM 채점자는 같은 학습분포를 공유해 slop을 못 알아봄 → DOM/CSS 결정론 검사가 정답
// (developersdigest.tech 16패턴, impeccable.style 46규칙 방법론 참조 — 자체 구현 서브셋 11규칙).
// usage: node sloplint.mjs <url> [--json]
// exit: 0 = clean, 1 = slop 신호 검출, 2 = 실행 실패.
import { chromium } from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const LIBDIR = path.join(os.homedir(), '.claude/tools/headless/chromedeps/usr/lib/x86_64-linux-gnu');
if (fs.existsSync(LIBDIR)) process.env.LD_LIBRARY_PATH = `${LIBDIR}:${process.env.LD_LIBRARY_PATH || ''}`;

const url = process.argv[2];
const asJson = process.argv.includes('--json');
if (!url) { console.error('usage: node sloplint.mjs <url> [--json]'); process.exit(2); }

const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(800);

  const report = await page.evaluate(() => {
    const findings = [];
    const add = (id, hit, detail) => findings.push({ id, hit, detail });
    const els = [...document.querySelectorAll('body *')].filter(e => e.offsetParent !== null || e.tagName === 'BODY');
    const style = (e) => getComputedStyle(e);

    // 1. slop-font: 본문 주 폰트가 과사용 폰트(Inter/Roboto/Arial/Space Grotesk)
    const bodyFont = style(document.body).fontFamily.toLowerCase();
    const slopFonts = ['inter', 'roboto', 'arial', 'space grotesk'];
    const fontHit = slopFonts.find(f => bodyFont.split(',')[0].includes(f));
    add('slop-font', !!fontHit, fontHit ? `body font-family 첫 후보 = ${fontHit} ("${bodyFont.slice(0, 60)}")` : bodyFont.slice(0, 60));

    // 2. purple-gradient: 보라 계열(hue 240~300) 그라데이션 배경
    const grad = els.filter(e => {
      const bg = style(e).backgroundImage;
      if (!bg.includes('gradient')) return false;
      const hues = [...bg.matchAll(/rgba?\((\d+),\s*(\d+),\s*(\d+)/g)].map(m => {
        const [r, g, b] = [+m[1], +m[2], +m[3]].map(v => v / 255);
        const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
        if (mx === mn) return -1;
        let h; const d = mx - mn;
        if (mx === r) h = ((g - b) / d) % 6; else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4;
        return (h * 60 + 360) % 360;
      });
      return hues.some(h => h >= 240 && h <= 300);
    });
    add('purple-gradient', grad.length > 0, `보라(240-300°) 그라데이션 요소 ${grad.length}개`);

    // 3. gradient-text: background-clip:text
    const gt = els.filter(e => (style(e).webkitBackgroundClip || style(e).backgroundClip) === 'text' && style(e).backgroundImage.includes('gradient'));
    add('gradient-text', gt.length > 0, `${gt.length}개`);

    // 4. uniform-radius: 12~20px 동일 radius 카드류 4개+
    const cards = els.filter(e => {
      const s = style(e);
      const r = parseFloat(s.borderRadius);
      return r >= 12 && r <= 20 && (s.boxShadow !== 'none' || s.borderWidth !== '0px' || s.backgroundColor !== 'rgba(0, 0, 0, 0)') && e.clientWidth > 150 && e.clientHeight > 80;
    });
    const radiusCount = {};
    cards.forEach(e => { const r = style(e).borderRadius; radiusCount[r] = (radiusCount[r] || 0) + 1; });
    const maxSame = Math.max(0, ...Object.values(radiusCount));
    add('uniform-radius', maxSame >= 4, `동일 radius 카드 최다 ${maxSame}개 (${JSON.stringify(radiusCount).slice(0, 80)})`);

    // 5. icon-box-grid: 3~4개 균등 자식(아이콘+제목+짧은 텍스트) 그리드
    const grids = els.filter(e => {
      const s = style(e); const kids = [...e.children];
      if (!(s.display === 'grid' || s.display === 'flex') || kids.length < 3 || kids.length > 4) return false;
      const eq = kids.every(k => Math.abs(k.clientWidth - kids[0].clientWidth) < 8);
      const iconish = kids.filter(k => k.querySelector('svg, img[width], [class*="icon"]') && k.querySelector('h1,h2,h3,h4,strong,b')).length;
      return eq && iconish >= 3;
    });
    add('icon-box-grid', grids.length > 0, `${grids.length}개 감지`);

    // 6. badge-above-h1: h1 직전 pill/badge
    const h1 = document.querySelector('h1');
    let badge = false;
    if (h1) {
      const prev = h1.previousElementSibling;
      if (prev && prev.textContent.trim().length < 40) {
        const s = style(prev);
        badge = parseFloat(s.borderRadius) >= 10 && (s.backgroundColor !== 'rgba(0, 0, 0, 0)' || s.borderWidth !== '0px');
      }
    }
    add('badge-above-h1', badge, badge ? `"${h1.previousElementSibling.textContent.trim().slice(0, 30)}"` : '');

    // 7. emoji-headings: 제목/네비의 이모지
    const emojiRe = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
    const emojiHeads = [...document.querySelectorAll('h1,h2,h3,nav a,nav li,aside a')].filter(e => emojiRe.test(e.textContent));
    add('emoji-headings', emojiHeads.length >= 2, `${emojiHeads.length}개 (제목·네비의 이모지)`);

    // 8. allcaps-eyebrow: letter-spacing 있는 올캡 라벨 다수
    const eyebrows = els.filter(e => {
      const s = style(e); const t = e.textContent.trim();
      return t.length > 2 && t.length < 40 && s.textTransform === 'uppercase' && parseFloat(s.letterSpacing) > 0.5;
    });
    add('allcaps-eyebrow', eyebrows.length >= 3, `${eyebrows.length}개`);

    // 9. stats-banner: 큰 숫자+라벨 3~4쌍 로우
    const statRows = els.filter(e => {
      const kids = [...e.children];
      if (kids.length < 3 || kids.length > 4) return false;
      return kids.filter(k => /^[~$+]?\d[\d,.]*[%+kKmMB]?\+?$/.test((k.querySelector('strong,b,span,div,h3,h2')?.textContent || '').trim())).length >= 3;
    });
    add('stats-banner', statRows.length > 0, `${statRows.length}개`);

    // 10. numbered-steps: 원형 1,2,3 스텝
    const stepCircles = els.filter(e => {
      const s = style(e); const t = e.textContent.trim();
      return /^[123]$/.test(t) && parseFloat(s.borderRadius) >= Math.min(e.clientWidth, e.clientHeight) / 2 - 2 && e.clientWidth < 60;
    });
    add('numbered-steps', stepCircles.length >= 3, `${stepCircles.length}개 원형 숫자`);

    // 11. spacing-monotony: 최상위 섹션 수직 패딩 전부 동일
    const sections = [...document.querySelectorAll('main > *, body > * > section, section')].filter(e => e.clientHeight > 200);
    const pads = [...new Set(sections.map(e => style(e).paddingTop))];
    add('spacing-monotony', sections.length >= 4 && pads.length === 1 && parseFloat(pads[0]) > 0, `섹션 ${sections.length}개 패딩 전부 ${pads[0] || '?'}`);

    return findings;
  });

  const hits = report.filter(f => f.hit);
  if (asJson) {
    console.log(JSON.stringify({ url, hits: hits.length, total: report.length, findings: report }, null, 1));
  } else {
    console.log(`sloplint — ${url}`);
    for (const f of report) console.log(` ${f.hit ? '✗' : '✓'} ${f.id}${f.hit ? ` — ${f.detail}` : ''}`);
    console.log(hits.length ? `\n${hits.length}/${report.length} slop 신호 — 레퍼런스-first 재작업 또는 의도적 선택인지 확인` : `\nclean (${report.length} 규칙)`);
  }
  process.exit(hits.length ? 1 : 0);
} catch (e) {
  console.error(`sloplint 실행 실패: ${e.message}`);
  process.exit(2);
} finally {
  await browser.close();
}
