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
        required: ['claim'],
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
  },
  required: ['claim', 'holds'],
}

const question = (typeof args === 'string' && args) ? args
  : (args && args.question) ? args.question
  : 'No question provided (pass args)'

phase('Fan-out')
const ANGLES = ['공식 문서·1차 출처', '최신 동향·릴리스(최근 1달)', '비판·실패·한계', '대안·경쟁 비교']
const found = (await parallel(ANGLES.map((a) => () =>
  agent(
    `Research this question through ONE lens: "${a}".\nQuestion: ${question}\n` +
    `Fan out several targeted web searches; prefer recent + durable sources over hype. ` +
    `Return claims with source URLs. No raw page dumps.`,
    { schema: FINDINGS, label: `research:${a}`, phase: 'Fan-out' },
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
log(`${claims.length} unique claims to verify`)

phase('Verify')
const verdicts = (await parallel(claims.map((c) => () =>
  agent(
    `Adversarially verify this claim — TRY TO REFUTE it with independent sources. ` +
    `Default holds=false if you cannot confirm.\nClaim: ${c.claim}\nGiven source: ${c.source || '(none)'}`,
    { schema: VERDICT, label: 'verify', phase: 'Verify' },
  ),
))).filter(Boolean)
const survived = verdicts.filter((v) => v.holds)
log(`${survived.length}/${verdicts.length} claims survived adversarial verification`)

phase('Synthesize')
const report = await agent(
  `Write a cited report answering the question, using ONLY these verified claims. ` +
  `Mark residual uncertainty explicitly. End with a "Sources" list.\n` +
  `Question: ${question}\nVerified claims:\n` +
  survived.map((v) => `- ${v.claim} [${v.evidence || ''}]`).join('\n'),
  { label: 'synthesize', phase: 'Synthesize' },
)
return report
