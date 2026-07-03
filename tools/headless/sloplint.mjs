// sloplint — 결정론적 AI-slop 디자인 검사 (LLM-free · 2026-07-03).
// 근거: LLM 채점자는 같은 학습분포를 공유해 slop을 못 알아봄 → DOM/CSS 결정론 검사가 정답
// (developersdigest.tech 16패턴, impeccable.style 46규칙 방법론 참조 — 자체 구현 서브셋 11규칙).
// usage: node sloplint.mjs <url> [--json]   (신뢰하는 URL 전용 — 자기 사이트/로컬 CI 게이트 용도)
// exit 정책: 0 = clean 또는 약신호/단일 강신호(경고만 — 특이도 보호: 정상 사이트도 강신호 1개는 흔함),
//           1 = 강신호 ≥2 (slop 수렴 패턴), 2 = 실행 실패(인프라 — slop으로 오인 금지).
import { chromium } from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const LIBDIR = path.join(os.homedir(), '.claude/tools/headless/chromedeps/usr/lib/x86_64-linux-gnu');
if (fs.existsSync(LIBDIR)) process.env.LD_LIBRARY_PATH = `${LIBDIR}:${process.env.LD_LIBRARY_PATH || ''}`;

const args = process.argv.slice(2);
const url = args.find((a) => !a.startsWith('--'));  // 플래그 순서 무관 (--json <url> 도 동작)
const asJson = args.includes('--json');
if (!url) { console.error('usage: node sloplint.mjs <url> [--json]'); process.exit(2); }
if (!/^(https?|file):\/\//.test(url)) { console.error(`지원 스킴: http(s)://, file:// — got "${url}"`); process.exit(2); }

// 브라우저 sandbox 유지가 기본 — 실패 시에만 --no-sandbox 폴백(WSL2 등 제약 환경, 고지 출력).
// launch 이중 실패까지 exit 2 보장(메인 try 안) — 인프라 실패가 CI에서 slop(1)으로 오인되면 안 됨 (judge 2인 수렴 지적).
let browser = null;
let exitCode = 2;
try {
  try {
    browser = await chromium.launch({ args: ['--disable-dev-shm-usage'] });
  } catch {
    console.error('(sandbox 실행 실패 — --no-sandbox 폴백. 신뢰하는 URL에만 사용할 것)');
    browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  }
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.emulateMedia({ reducedMotion: 'reduce' });  // 결정론성: 모션 최소화
  // networkidle 금지(Playwright 공식 비권장 — 애널리틱스 폴링 사이트에서 영구 미도달 → CI가 인프라 이유로 깨짐)
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (resp && resp.status() >= 400) { console.error(`HTTP ${resp.status()} — 에러 페이지는 채점 대상 아님`); exitCode = 2; process.exitCode = 2; throw new Error(`HTTP ${resp.status()}`); }
  await page.evaluate(() => document.fonts ? document.fonts.ready : null).catch(() => {});
  // 결정론성: 애니메이션/트랜지션 동결 — 같은 페이지 = 같은 계산값
  await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important}' }).catch(() => {});
  await page.waitForTimeout(1200);

  const report = await page.evaluate(() => {
    const findings = [];
    const add = (id, hit, detail) => findings.push({ id, hit, detail });
    // 가시성 판정: rect 기반 — offsetParent는 position:fixed 요소(고정 헤더 등)를 누락시킴
    // html/body 자체 포함 — full-page gradient를 body/html에 주는 사이트의 purple-gradient 미탐 방지(2026-07-03 Codex A7)
    const els = [document.documentElement, document.body, ...document.querySelectorAll('body *')].filter(e => {
      if (e === document.documentElement || e === document.body) return true;
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    const style = (e) => getComputedStyle(e);

    // 1. slop-font: 본문 주 폰트가 과사용 폰트 — weak 신호(참고 전용, 게이트 미반영:
    //    정상 사이트도 광범위 사용이라 게이트에 넣으면 특이도 붕괴. 강신호 게이트와 별개로 리포트만)
    const bodyFont = style(document.body).fontFamily.toLowerCase();
    const slopFonts = ['inter', 'roboto', 'arial', 'space grotesk'];
    const fontHit = slopFonts.find(f => bodyFont.split(',')[0].includes(f));
    findings.push({ id: 'slop-font', hit: !!fontHit, weak: true, detail: fontHit ? `body font-family 첫 후보 = ${fontHit} ("${bodyFont.slice(0, 60)}")` : bodyFont.slice(0, 60) });

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
      // oklch 직렬화 대응(Tailwind v4 등 — hex/hsl은 Chromium이 rgb로 정규화함을 실측 확인, oklch는 별도): 보라 ≈ hue 270~330(근사)
      const okHues = [...bg.matchAll(/oklch\([^)]*?\s([\d.]+)(deg)?\s*[)\/]/g)].map(m => +m[1]);
      return hues.some(h => h >= 240 && h <= 300) || okHues.some(h => h >= 270 && h <= 330);
    });
    add('purple-gradient', grad.length > 0, `보라(240-300°) 그라데이션 요소 ${grad.length}개`);

    // 3. gradient-text: background-clip:text
    const sel = (e) => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '');
    const gt = els.filter(e => (style(e).webkitBackgroundClip || style(e).backgroundClip) === 'text' && style(e).backgroundImage.includes('gradient'));
    add('gradient-text', gt.length > 0, `${gt.length}개${gt[0] ? ` (예: ${sel(gt[0])} "${gt[0].textContent.trim().slice(0, 20)}")` : ''}`);

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
    add('icon-box-grid', grids.length > 0, `${grids.length}개 감지${grids[0] ? ` (예: ${sel(grids[0])})` : ''}`);

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
    add('stats-banner', statRows.length > 0, `${statRows.length}개${statRows[0] ? ` (예: ${sel(statRows[0])} "${statRows[0].textContent.trim().slice(0, 25)}")` : ''}`);

    // 10. numbered-steps: 원형 숫자 스텝 (1~5, "01", "Step 1" 표기 포함)
    const stepCircles = els.filter(e => {
      const s = style(e); const t = e.textContent.trim();
      return /^(0?[1-5]|step\s*[1-5])$/i.test(t) && parseFloat(s.borderRadius) >= Math.min(e.clientWidth, e.clientHeight) / 2 - 2 && e.clientWidth < 80;
    });
    add('numbered-steps', stepCircles.length >= 3, `${stepCircles.length}개 원형 숫자`);

    // 11. spacing-monotony: 섹션 수직 패딩 지배값 비율 (완전 동일 요구는 1px 차이로 미탐 — 80% 지배로 완화)
    const sections = [...document.querySelectorAll('main > *, body > * > section, section')].filter(e => e.clientHeight > 200);
    const padCount = {};
    sections.forEach(e => { const p = style(e).paddingTop; padCount[p] = (padCount[p] || 0) + 1; });
    const domPad = Object.entries(padCount).sort((a, b) => b[1] - a[1])[0];
    const monotone = sections.length >= 4 && domPad && domPad[1] / sections.length >= 0.8 && parseFloat(domPad[0]) > 0;
    add('spacing-monotony', monotone, monotone ? `섹션 ${sections.length}개 중 ${domPad[1]}개 패딩 ${domPad[0]}` : `섹션 ${sections.length}개`);

    return findings;
  });

  const hits = report.filter(f => f.hit);
  const strong = hits.filter(f => !f.weak);
  // 게이트: 강신호 ≥2 = fail. 1개는 경고(정상 프로 사이트도 강신호 1개는 흔함 — 단일 hard-fail은 특이도 붕괴, judge 2인 수렴 지적).
  exitCode = strong.length >= 2 ? 1 : 0;
  if (asJson) {
    console.log(JSON.stringify({ url, hits: hits.length, strong: strong.length, gate: exitCode ? 'fail' : 'pass', total: report.length, findings: report }, null, 1));
  } else {
    console.log(`sloplint — ${url}`);
    for (const f of report) console.log(` ${f.hit ? '✗' : '✓'} ${f.id}${f.weak && f.hit ? ' (약신호)' : ''}${f.hit ? ` — ${f.detail}` : ''}`);
    if (exitCode) console.log(`\n${hits.length}/${report.length} slop 신호 (강 ${strong.length}) — 레퍼런스-first 재작업 또는 의도적 선택인지 확인`);
    else if (strong.length === 1) console.log(`\n강신호 1건 — 게이트 통과(경고): 의도적 선택인지 확인 권장`);
    else if (hits.length) console.log(`\n약신호만 ${hits.length}건 — 게이트 통과, 참고만`);
    else console.log(`\nclean (${report.length} 규칙)`);
  }
} catch (e) {
  console.error(`sloplint 실행 실패: ${e.message}`);
  exitCode = 2;
} finally {
  if (browser) await browser.close();
}
process.exit(exitCode);
