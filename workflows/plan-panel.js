export const meta = {
  name: 'plan-panel',
  description: '하나의 task를 여러 각도로 블라인드 plan 초안(병렬) → 각 초안 적대 리뷰·점수 → 최고안 종합(타 초안 장점 이식). 어려운 결정·고비용 빌드 전. args = task(문자열).',
  phases: [
    { title: 'Draft', detail: '각도별 블라인드 초안' },
    { title: 'Review', detail: '적대 리뷰 + 점수' },
    { title: 'Synthesize', detail: '최고안 종합' },
  ],
}

const PLAN = {
  type: 'object',
  properties: {
    approach: { type: 'string' },
    steps: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
    cut: { type: 'string' },
  },
  required: ['approach', 'steps'],
}
const REVIEW = {
  type: 'object',
  properties: {
    score: { type: 'number' },
    failures: { type: 'array', items: { type: 'string' } },
    verdict: { type: 'string' },
  },
  required: ['score'],
}

const task = (typeof args === 'string' && args) ? args : (args && args.task) ? args.task : 'No task (pass args)'

phase('Draft')
const ANGLES = ['MVP·최소기능 우선', '리스크·실패모드 우선', '사용자가치 우선', '가장 단순한 해법']
const drafts = (await parallel(ANGLES.map((a) => () =>
  agent(
    `Draft an implementation plan for the task, from THIS angle only: "${a}".\nTask: ${task}\n` +
    `Give: approach, concrete steps, top risks, and one deliberate cut/defer.`,
    { schema: PLAN, label: `draft:${a}`, phase: 'Draft' },
  ),
))).filter(Boolean)

phase('Review')
const reviewed = (await parallel(drafts.map((d, i) => () =>
  agent(
    `Adversarially review this plan. Find failure modes, wrong scope, unstated assumptions. Score 0-100 (be harsh).\n` +
    `Plan: ${JSON.stringify(d)}`,
    { schema: REVIEW, label: `review:${i}`, phase: 'Review' },
  ).then((r) => ({ draft: d, review: r })),
))).filter(Boolean)
const ranked = reviewed.sort((a, b) => (b.review.score || 0) - (a.review.score || 0))
log(`best score: ${ranked[0] && ranked[0].review.score}`)

phase('Synthesize')
const final = await agent(
  `Synthesize ONE best plan for the task. Base it on the highest-scored draft, graft the strongest ideas from the others, ` +
  `and resolve the failure modes the reviews raised.\nTask: ${task}\nRanked drafts + reviews:\n` +
  ranked.map((r) => `[score ${r.review.score}] ${r.draft.approach} — failures: ${(r.review.failures || []).join('; ')}`).join('\n'),
  { label: 'synthesize', phase: 'Synthesize' },
)
return final
