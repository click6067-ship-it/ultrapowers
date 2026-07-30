# Changelog

All versions preserved in git history — nothing is squashed or force-pushed.
Dates are the actual commit timestamps (KST).

## v0.6 — 2026-07-30 · Mixed-backbone Orca crew era

The largest update since launch. The system graduated from "Claude plans,
Codex reviews" to a **real multi-backbone agent crew** run on the Orca ADE:
a read-only coordinator, single-writer workers, and cross-lab reviewers with
full task/dispatch lifecycle provenance.

**New: `orca/` layer** (optional — needs Windows Orca ADE + WSL)
- `sync-orca-codex-home.py` + tests — parser-truth trust sync for Orca's Codex
  runtime home; survived a 5-round adversarial GPT review (4 real defects found
  and fixed: stale trust keys, TOML orphan-key reattachment, header disguises,
  mutation-red gaps). Drift detection is tomllib-semantic: no textual disguise
  can false-green.
- `orca-wsl-bridge.ps1` + `orca-ide-wsl-wrapper.sh` + quoting tests — the
  WSL↔Windows CLI bridge. Fixes PowerShell 5.1's native-argv quote loss
  (inverse CommandLineToArgvW assembly; 501-vector fuzz reviewed) and the
  vendor PATH/Path duplicate-key crash (stablyai/orca#9498 — root cause traced
  to the app's attribution env builder and reported upstream; #11499 also filed).
- `orca_wsl_platform_gate.py` + 21 tests — fail-closed Windows-Orca/WSL
  execution-boundary gate (strict UNC/distro, exact caller).
- `orca-provision.sh` (serial worker startup), `orca-finalize-check.py`
  (deterministic finalization gate, NOT_VERIFIED semantics),
  `orca-metrics.py` (crew-vs-single-agent measurement snapshots),
  `orca-docs.sh` (live bundled-guide loader — docs are never copied to md),
  `orca-council.py` + 17 tests (artifact ledger: sealed briefs/hashes/scores;
  never owns Orca lifecycle), `project-status.sh` (probe-not-bake status).

**New skills (13 → 17)**
- `orca-trio` — coordinator/writer/reviewer crew contracts on live Orca guides
- `race` — isolated-candidate competition with blind judges
- `hallmark` — anti-AI-slop design system
- `newproject` — project onboarding bootstrap (lightweight intake → 30-line
  project CLAUDE.md → command-center registration → kickoff routing)

**New hooks (7 → 11)** — `skill-nudge` (situation→skill suggestions),
`skill-usage-log` (PreToolUse counters for the 30-day usage verdict),
`orca-trio-guard`, `session-end-runner` (serialized SessionEnd pipeline),
plus `redaction.py` with regression tests.

**Rules & constitution** — always-on rules cut ~76% (30,397B → 7,320B; detail
moved to conditional runbooks), new `judgment.md` (recency · anti-echo ·
evidence-grade discipline), `routing.md` codifies the 2026-07-30 decisions:
parallel collaboration unified on orca-trio real-terminal crews (Claude Code
Agent Teams retired), planning review split by stakes (kickoff=high /
plan-panel=medium), qualityloop vs stop-review roles made mutually exclusive.

**Evidence discipline** — `verify.sh` exits 2 `NOT_VERIFIED` when zero checks
ran; guardrail grew to 77 regression cases; doctor gained runtime hook-trust,
WSL named-flag, and mirror-freshness checks.

Field results behind this release (from the private command-center reports):
a mixed Fable-writer × GPT-reviewer trio shipped a real P0 fix with APPROVE;
fire drills measured worker-kill auto-recovery, duplicate/late worker_done
contracts, and caught 2 real defects; a six-worker machinery E2E (Fable 3 +
Opus 3) passed 6/6; an app-restart drill passed 8/8 (orchestration state
fully survives; panes reattach).

## v0.5 — 2026-07-16 (`4f21ebe`)
4 new skills (`specpack` · `crit` · `ship` · `serve`) + 2 new hooks
(`devlog` — per-repo DEVLOG.md session distillation · `uislop-check`) +
`doc2txt.sh` / `netcheck.sh`. Log-mining-driven (64 sessions, 1,483
utterances) situation→skill suggestion table.

## v0.4.x — 2026-07-06 (`30e41b1`)
Harness corrections sync + README fixes.

## v0.4 — 2026-07-03 (`905fdd6` → `a256275`, 6 commits)
Full-system audit day with two-model adversarial hardening:
- `sloplint` — deterministic 11-rule AI-slop design linter (+fixtures)
- rules split into 5 auto-loaded topic files; `qualityloop` skill
- `judge` · `Explore` agents; subagent-log JSONL cost observability
- install.sh made location-independent (COMMAND_CENTER env), public-copy
  private-dependency removal (graceful skip), guardrail bare-force-push block
- workflow verify caps · citation preservation · sonnet tiering

## v0.3 — 2026-06-28 (`5a36f5e` → `4ee6023`)
3 Dynamic Workflows published (`council-research` · `plan-panel` ·
`repo-audit`) with adversarial verification and cost caps.

## v0.2 — 2026-06-28 (`f6cac26` → `d28b3c8`, 5 commits)
Hardening wave: PreToolUse guardrail (shlex + recursion bypass-proofing,
long-flag/expanded-home coverage), `doctor.py`, `verify.sh` matrix, safe
Codex config template, statusline, custom subagents
(researcher/verifier/redteam), idempotent install merge.

## v0.1 — 2026-06-05 (`876ff80`)
Initial public release: a Claude Code + Codex setup on top of obra's
superpowers — two-model adversarial planning (`/kickoff`), auditable council
logs, cross-session memory, core skills and hooks.
