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
        properties: { file: { type: 'string' }, issue: { type: 'string' }, severity: { type: 'string' }, line: { type: 'number' }, evidence: { type: 'string' }, confidence: { type: 'string' } },
        required: ['file', 'issue'],
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
  (f) => agent(`Review the file "${f}" for: ${focus}. Return concrete findings (file + issue + severity). For each finding include file:line (line number) and the code evidence (the actual snippet or behavior that proves the issue). If clean, return empty findings.`,
    { schema: FINDINGS, label: 'review', phase: 'Review' }),
)
const all = reviewed.filter(Boolean).flatMap((r) => r.findings || [])
const seen = new Set()
const uniq = []
for (const x of all) {
  const k = ((x.file || '') + (x.issue || '')).slice(0, 100).toLowerCase()
  if (k && !seen.has(k)) { seen.add(k); uniq.push(x) }
}
const TOPN = 25  // stop-rule: 검증 fan-out 비용 상한 (council-research 35에이전트 교훈과 동일 — 1ede3a8)
// severity 우선 정렬 후 cap — high/critical이 26번째로 밀려 미검증되는 것 방지 (2026-07-03 Codex A9)
const sevRank = { critical: 0, high: 1, medium: 2, low: 3 }
uniq.sort((a, b) => (sevRank[(a.severity || '').toLowerCase()] ?? 2) - (sevRank[(b.severity || '').toLowerCase()] ?? 2))
const toVerify = uniq.slice(0, TOPN)
log(`${uniq.length} unique findings, verifying top ${toVerify.length}` + (uniq.length > TOPN ? ` (${uniq.length - TOPN}건 미검증 pass-through)` : ''))

phase('Verify')
const verdicts = (await parallel(toVerify.map((x) => () =>
  agent(`Adversarially verify this finding — is it REAL? Try to refute it. Default real=false if unsure.\nFile: ${x.file}${x.line != null ? `\nLine: ${x.line}` : ''}\nIssue: ${x.issue}${x.evidence ? `\nEvidence: ${x.evidence}` : ''}\nRead the file yourself and refute or confirm with a concrete file:line reference.`,
    { schema: VERDICT, label: 'verify', phase: 'Verify', model: 'sonnet' }).then((v) => ({ ...x, ...v })),
))).filter(Boolean)
const confirmed = verdicts.filter((v) => v.real)
return { confirmed_count: confirmed.length, total_findings: uniq.length, unverified_overflow: uniq.slice(TOPN), confirmed }
