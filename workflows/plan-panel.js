export const meta = {
  name: 'plan-panel',
  description: 'Single-backbone lightweight panel for medium-stakes planning. It is not the multi-backbone kickoff Council. args=task.',
  phases: [
    { title: 'Explore', detail: '제약 없이 독립 아이디어 발산' },
    { title: 'Harden', detail: 'barrier 뒤 주장·근거·kill condition 생성과 반증' },
    { title: 'Synthesize', detail: '비옹호자 spec seed' },
  ],
}

const DRAFT = {
  type: 'object',
  properties: {
    problem: { type: 'string' },
    hypothesis: { type: 'string' },
    approaches: { type: 'array', items: { type: 'string' } },
    usefulSurprises: { type: 'array', items: { type: 'string' } },
    nonGoals: { type: 'array', items: { type: 'string' } },
    unknowns: { type: 'array', items: { type: 'string' } },
  },
  required: ['problem', 'hypothesis', 'approaches', 'usefulSurprises', 'nonGoals', 'unknowns'],
}

const HARDENED = {
  type: 'object',
  properties: {
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          candidateId: { type: 'string' },
          text: { type: 'string' },
          evidenceStatus: { type: 'string' },
          killCondition: { type: 'string' },
          verdict: { type: 'string' },
          why: { type: 'string' },
        },
        required: ['id', 'candidateId', 'text', 'evidenceStatus', 'killCondition', 'verdict', 'why'],
      },
    },
    disagreements: { type: 'array', items: { type: 'string' } },
    premortem: { type: 'array', items: { type: 'string' } },
    deliberateCuts: { type: 'array', items: { type: 'string' } },
  },
  required: ['claims', 'disagreements', 'premortem', 'deliberateCuts'],
}

const SPEC_SEED = {
  type: 'object',
  properties: {
    problem: { type: 'string' },
    chosen: { type: 'array', items: { type: 'string' } },
    rejected: { type: 'array', items: { type: 'string' } },
    deferred: { type: 'array', items: { type: 'string' } },
    disagreements: { type: 'array', items: { type: 'string' } },
    nonGoals: { type: 'array', items: { type: 'string' } },
    metrics: { type: 'array', items: { type: 'string' } },
    userGateQuestions: { type: 'array', items: { type: 'string' } },
  },
  required: ['problem', 'chosen', 'rejected', 'deferred', 'disagreements', 'nonGoals', 'metrics', 'userGateQuestions'],
}

const task = typeof args === 'string' && args ? args : args && args.task
if (!task) throw new Error('plan-panel: args로 task를 넘겨야 함')

const lenses = [
  '사용자의 실제 문제와 최소 메커니즘',
  '전혀 다른 사용자 여정과 가치 제안',
  '기능을 늘리지 않고 문제를 없애는 삭제·운영 대안',
]

phase('Explore')
const drafts = (await parallel(lenses.map((lens, index) => () =>
  agent(
    `Independent P${index + 1}; never inspect siblings.\nOriginal task: ${task}\nLens: ${lens}\n` +
    'Explore before evaluating. Generate genuinely different approaches and useful surprises. ' +
    'Do not add kill conditions, premortems, scores, or criticism yet. Do not edit files.',
    { schema: DRAFT, label: `explore:P${index + 1}`, phase: 'Explore' },
  ).then((draft) => ({ candidateId: `P${index + 1}`, lens, draft }))
))).filter(Boolean)

if (drafts.length < 2) throw new Error('plan-panel: 유효 독립 후보 2개 미만 — 종합 금지')
const anonymous = drafts

phase('Harden')
const hardened = await agent(
  `Fresh adversarial analyst. Original task: ${task}\n` +
  'The exploration barrier has passed. Convert proposals into falsifiable claims, attach evidence status ' +
  'and kill conditions, then try to refute them. Add 3+ premortems and deliberate cuts. ' +
  'Preserve unresolved disagreements and do not force a scalar winner.\n' +
  `Anonymous candidates: ${JSON.stringify(anonymous)}`,
  { schema: HARDENED, label: 'fresh-hardener', phase: 'Harden' },
)

phase('Synthesize')
return agent(
  `Fresh non-advocate synthesizer. Original task: ${task}\n` +
  'Use only claims that survived hardening. Never hide disagreement or turn unknown into consensus. ' +
  'Produce a small spec seed, not code, and leave ADOPT/PIVOT/STOP to the user.\n' +
  `Candidates: ${JSON.stringify(anonymous)}\nHardening: ${JSON.stringify(hardened)}`,
  { schema: SPEC_SEED, label: 'non-advocate-synthesis', phase: 'Synthesize' },
)
