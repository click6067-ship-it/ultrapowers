export const meta = {
  name: 'repo-audit',
  description: '대상 경로 파일을 shard → 병렬 리뷰 → dedupe → 적대 검증으로 감사(버그/보안/품질 sweep). args = 경로(문자열) 또는 {path, focus}.',
  phases: [
    { title: 'Shard', detail: '감사 대상 파일 목록' },
    { title: 'Review', detail: '파일별 병렬 리뷰' },
    { title: 'Verify', detail: '발견 적대 검증' },
  ],
}

const FILES = { type: 'object', properties: { files: { type: 'array', items: { type: 'string' } } }, required: ['files'] }
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: { file: { type: 'string' }, issue: { type: 'string' }, severity: { type: 'string' } },
        required: ['issue'],
      },
    },
  },
  required: ['findings'],
}
const VERDICT = {
  type: 'object',
  properties: { issue: { type: 'string' }, real: { type: 'boolean' }, why: { type: 'string' } },
  required: ['real'],
}

const path = (typeof args === 'string' && args) ? args : (args && args.path) ? args.path : '.'
const focus = (args && args.focus) || 'correctness bugs, security holes, and clear quality issues'

phase('Shard')
const listing = await agent(
  `List source files worth auditing under "${path}" (exclude vendored/generated/node_modules/.git). Return up to 40 paths.`,
  { schema: FILES, label: 'shard', phase: 'Shard' },
)
const files = ((listing && listing.files) || []).slice(0, 40)
log(`${files.length} files to review`)

phase('Review')
const reviewed = await pipeline(
  files,
  (f) => agent(`Review the file "${f}" for: ${focus}. Return concrete findings (file + issue + severity). If clean, return empty findings.`,
    { schema: FINDINGS, label: 'review', phase: 'Review' }),
)
const all = reviewed.filter(Boolean).flatMap((r) => r.findings || [])
const seen = new Set()
const uniq = []
for (const x of all) {
  const k = ((x.file || '') + (x.issue || '')).slice(0, 100).toLowerCase()
  if (k && !seen.has(k)) { seen.add(k); uniq.push(x) }
}
log(`${uniq.length} unique findings to verify`)

phase('Verify')
const verdicts = (await parallel(uniq.map((x) => () =>
  agent(`Adversarially verify this finding — is it REAL? Try to refute it. Default real=false if unsure.\nFile: ${x.file}\nIssue: ${x.issue}`,
    { schema: VERDICT, label: 'verify', phase: 'Verify' }).then((v) => ({ ...x, ...v })),
))).filter(Boolean)
const confirmed = verdicts.filter((v) => v.real)
return { confirmed_count: confirmed.length, total_findings: uniq.length, confirmed }
