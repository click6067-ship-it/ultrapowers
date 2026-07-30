export const meta = {
  name: 'council-research',
  description: '다각도 fan-out 리서치 → 각 주장 적대 검증(refute 시도) → 생존 주장만 인용 종합. deep-research의 council판. loop-engineering: verifier(적대검증) + stop-rule(검증 생존) 내장. args = 리서치 질문(문자열).',
  phases: [
    { title: 'Fan-out', detail: '여러 렌즈로 병렬 웹리서치' },
    { title: 'Verify', detail: '각 주장 적대 검증 — refute 시도' },
    { title: 'Synthesize', detail: '생존 주장만 인용 종합' },
  ],
}

const FINDINGS = {
  type: 'object',
  properties: {
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: { claim: { type: 'string' }, source: { type: 'string' } },
        required: ['claim', 'source'],
      },
    },
  },
  required: ['claims'],
}
const VERDICT = {
  type: 'object',
  properties: {
    claim: { type: 'string' },
    holds: { type: 'boolean' },
    evidence: { type: 'string' },
    // 2026-07-29 감사: 'holds + non-empty string'만 보면 같은 upstream을 되풀이한 출처도
    // '독립 evidence lineage 생존'으로 통과했다. root를 구조로 받아 결정론적으로 센다.
    evidence_roots: {
      type: 'array',
      items: { type: 'string' },
      description: 'URL of the UNDERLYING study/measurement/repository/first-party event for each independent line of support — NOT the news article or blog repeating it.',
    },
  },
  required: ['claim', 'holds', 'evidence', 'evidence_roots'],
}

// host+path로 canonicalize — www·쿼리·프래그먼트·trailing slash 차이로 같은 원증거가
// 서로 다른 root로 세어지는 것을 막는다.
const rootOf = (u) => String(u).trim().toLowerCase()
  .replace(/^[a-z]+:\/\//, '').replace(/^www\./, '')
  .split(/[?#]/)[0].replace(/\/+$/, '')

const question = (typeof args === 'string' && args) ? args
  : (args && args.question) ? args.question
  : null
if (!question) throw new Error('council-research: args로 리서치 질문(문자열)을 넘겨야 함 — 무입력 fan-out 방지')

phase('Fan-out')
const ANGLES = [
  '공식 문서·표준·원천 데이터; upstream citation',
  '독립 실측·재현·benchmark; 원질문과 다른 query family',
  '비판·실패·migration-away·issue tracker; negative evidence 우선',
  '다른 언어권·인접 분야·비주류 커뮤니티의 대안',
]
const found = (await parallel(ANGLES.map((a) => () =>
  agent(
    `Research this question through ONE lens: "${a}".\nQuestion: ${question}\n` +
    `Fan out several targeted web searches; prefer recent + durable sources over hype. ` +
    `Return claims with source URLs. No raw page dumps.`,
    { schema: FINDINGS, label: `research:${a}`, phase: 'Fan-out', model: 'sonnet' },  // 리서치 수집 fan-out 티어링(researcher=sonnet 정책) — synthesize는 부모 모델 유지
  ),
))).filter(Boolean)

const seen = new Set()
const claims = []
for (const f of found) {
  for (const c of (f.claims || [])) {
    const k = (c.claim || '').slice(0, 80).toLowerCase().trim()
    if (k && !seen.has(k)) { seen.add(k); claims.push(c) }
  }
}
const TOPN = 25  // stop-rule: 검증 fan-out 비용 상한(좁은 질문에 35+에이전트 폭주 방지)
const toVerify = claims.slice(0, TOPN)
log(`${claims.length} unique claims, verifying top ${toVerify.length}`)

phase('Verify')
const verdicts = (await parallel(toVerify.map((c) => () =>
  agent(
    `Adversarially verify this claim — TRY TO REFUTE it with independent evidence lineages. ` +
    `Trace each page to the underlying study, measurement, repository, or first-party event. ` +
    `Same-class sources can be independent; different-class pages repeating one upstream source count as one. ` +
    `Default holds=false if you cannot confirm. Include verifying source URLs in "evidence", and put ` +
    `one URL per INDEPENDENT underlying root in "evidence_roots" (two pages repeating one upstream = one root).\n` +
    `Claim: ${c.claim}\nGiven source: ${c.source || '(none)'}`,
    { schema: VERDICT, label: 'verify', phase: 'Verify', model: 'sonnet' },  // 최대 fan-out 구간 비용 티어링
  ).then((v) => ({ ...v, source: c.source || '' })),  // 원 출처 URL 보존 — 무인용 종합 방지
))).filter(Boolean)
const survived = verdicts
  .map((v) => {
    const roots = [...new Set((v.evidence_roots || []).map(rootOf).filter(Boolean))]
    return { ...v, roots, independent: roots.length >= 2 }
  })
  .filter((v) => v.holds && v.evidence && v.source && v.roots.length >= 1)
const corroborated = survived.filter((v) => v.independent).length
log(`${survived.length}/${verdicts.length} claims survived — ${corroborated} corroborated by ≥2 independent evidence roots, ${survived.length - corroborated} single-root`)

if (!survived.length) {
  // 생존 0건이면 종합 금지 — 환각 리포트를 '검증 통과'로 반환하지 않는다
  log('생존 주장 0건 — 종합 스킵')
  return { report: null, note: 'no claims survived adversarial verification', claims_found: claims.length, verified: verdicts.length }
}

phase('Synthesize')
const report = await agent(
  `Write a cited report answering the question, using ONLY these verified claims. ` +
  `Mark residual uncertainty explicitly. End with a "Sources" list built from the claim sources/evidence URLs. ` +
  `Your final text IS the report artifact returned to the caller — no greetings or meta commentary.\n` +
  `Question: ${question}\nVerified claims:\n` +
  survived.map((v) => `- ${v.claim} [evidence: ${v.evidence || ''}] [source: ${v.source}] [roots: ${v.roots.length}${v.independent ? '' : ' — SINGLE-ROOT, 단정 금지'}]`).join('\n'),
  { label: 'synthesize', phase: 'Synthesize' },
)
return report
