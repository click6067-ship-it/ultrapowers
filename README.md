# ultrapowers

A Claude Code + Codex agent-system setup, grown from [obra's superpowers](https://github.com/obra/superpowers) into a **multi-backbone agent crew** run on the Orca ADE: a read-only coordinator, single-writer workers, and reviewers from a *different lab* attacking pinned commits — with every task, dispatch, and completion recorded by Orca's orchestration layer, and "done" decided only by real test output plus a user gate.

```text
define → research → plan → build → verify → cross-lab review → ship → report
```

Why cross-lab review? Measured 2026-07-30: in a single day, GPT reviewers overturned Fable-written code **four rounds in a row** with real defects (stale trust keys, TOML orphan-key reattachment, valid-header disguises, missing mutation coverage) that same-model review had waved through. Diversity catches what redundancy cannot.

> Built and hardened in daily operation by **Claude Fable 5** (coordinator / system work), **Claude Opus** (project implementation), and **OpenAI Codex GPT‑5.6‑Sol xhigh** (adversarial review).

## The two-repo model

| Repo | Visibility | Role |
|---|---|---|
| **ultrapowers** (this) | public | The shareable agent system: constitution, rules, 17 skills, 11 hooks, workflows, guardrail/doctor/verify, the Orca coordination layer, templates, installer |
| **command-center** | private | The owner's meta hub: the same system as its deployed source of truth, plus strategy/decisions/session logs/reports/memory |

Fresh machine, two clones, done:

- **Owner (full restore):** clone command-center to `~/main` → `bash ~/main/system/dotclaude/deploy.sh` → manual steps (secrets file, CLI logins). This public repo is the shareable equivalent and second backup of the system half.
- **Everyone else:** clone this repo → `bash install.sh` (installs into `~/.claude` + `~/.codex`; set `COMMAND_CENTER=<dir>` for your logs/reports home, default `~/main`).

## What's inside

| Component | What it does |
|---|---|
| `CLAUDE.md` + `rules/` | Core constitution + auto-loaded topic rules: Phase 0 gate · work loop · session memory · pitfalls · **routing** (task→tool decision table, incl. the 2026-07-30 unification: parallel collaboration = orca-trio real-terminal crews, planning review split by stakes) · **judgment** (recency · anti-echo · evidence grades 🟢🟡⚪) · path-scoped design anti-slop. Always-on rules were cut ~76% — detail lives in conditional runbooks |
| `AGENTS.md` | The same constitution for Codex, so both labs share one rulebook |
| **`orca/`** (optional layer) | Orca-ADE crew suite: WSL↔Windows CLI bridge with quote-exact argv (PowerShell 5.1 CommandLineToArgvW assembly — 501-vector fuzz-reviewed) · parser-truth Codex-runtime policy sync (tomllib-semantic drift detection, no textual disguise can false-green; 26 tests) · fail-closed platform gate (21 tests) · worker provisioner · deterministic finalization checker · crew metrics · artifact-ledger council (17 tests) · live bundled-doc loader. Needs Windows Orca + WSL; everything else works without it |
| 17 skills | `kickoff` · **`orca-trio`** · **`race`** · `qualityloop` · `specpack` · `spec-decompose` · `autopilot` · `vcheck` · `crit` · `ship` · `serve` · `demo` · `recall` · `remember` · `techreport` · **`hallmark`** · **`newproject`** — see Skills below |
| 11 hooks | session-start context **+ pointer-only project brief** · per-turn archive · session-end pipeline (serialized runner) · per-repo devlog · UI-slop nudge · **skill-nudge** · **skill-usage-log** · orca-trio guard · subagent log · techreport autopush (opt-in) · `redaction.py` (+tests) |
| 3 workflows | `council-research` · `plan-panel` · `repo-audit` — parallel multi-agent pipelines with adversarial verification and cost caps |
| guardrail | PreToolUse hook blocking only catastrophic, irreversible Bash — **77 regression cases**, bypass-hardened (shlex + recursion + nested wrappers), deny-by-policy |
| doctor + verify | `doctor.py` health check (hooks integrity · mirror drift · runtime hook trust · Orca bridge canaries · pending-decision watch) · `verify.sh` — **zero executed checks = exit 2 `NOT_VERIFIED`, never PASS** |
| sloplint | deterministic 11-rule AI-slop design linter (an LLM judge shares the training prior and can't see its own slop) |
| 5 subagents | `researcher` · `verifier` · `redteam` · `judge` · `Explore` — model-tiered by cost |
| templates | `settings.template.json` (ships the no-cloud security locks) · safe Codex `config.toml` (secrets by env-var *name* only) · statusline |

## Operating contracts — what makes it a crew, not just terminals

- **Single ownership**: Orca orchestration owns task/dispatch/worker-done lifecycle; git owns code; real test output owns "works"; the user owns decisions. No two systems own the same state.
- **One writer per worktree**; reviewers are read-only against a pinned commit; `APPROVE`/`REVISE` loops end with a *fresh* reviewer.
- **Serial worker startup** (create → tui-idle → next) to avoid hook-bundle races; dispatch runs parallel afterwards.
- **Measured failure semantics** (fire-drilled 2026-07-30): worker kill → dispatch auto-fails and the task auto-returns to ready (recovery = one re-dispatch) · duplicate `worker_done` is delivered twice with **no runtime dedup** (the coordinator deduplicates) · a superseded dispatch's late `worker_done` has zero state authority · an app restart preserves all orchestration state and reattaches terminal panes.
- **Evidence or it didn't happen**: sealed briefs (sha256), exact IDs in reports, `NOT_VERIFIED` over false green.

## Skills

| Skill | What it does |
|---|---|
| `kickoff` | Multi-backbone plan council — blind divergence (3 methodologies × 2 backbones), adversarial hardening, non-advocate synthesis, user ADOPT/PIVOT/STOP gate |
| `orca-trio` | Crew contracts for Orca coordination — roles, ownership, recovery, finalization; commands always loaded from the installed binary's live guides (docs are never copied to md) |
| `race` | Two/three isolated implementations compete — separate worktrees, sealed identical briefs, anonymized artifacts, blind judges, DRAW on thin margins |
| `qualityloop` | Blind independent scoring of a finished deliverable against a rubric; deterministic checks first; loop until pass (max 3 rounds) |
| `newproject` | Project onboarding bootstrap — lightweight intake → 30-line project CLAUDE.md → command-center registration → kickoff routing for high stakes |
| `hallmark` | Anti-AI-slop design system for greenfield pages, audits, redesigns |
| `specpack` | Approved plan → the standard pre-dev doc chain (lightweight PRD · Mermaid-ERD · design doc · ADRs), sized to stakes |
| `spec-decompose` | Master spec → validated per-section child specs (`spec_doctor.py`), then hand off to writing-plans |
| `crit` | Cross-model design & copy critique — Codex (vision) as adversarial nitpicker, findings verified against real code, `sloplint` referees |
| `ship` | The finish chain — verify → author-email + diff-damage check → scoped commit → push → deploy → live visual check → evidence report |
| `serve` | Dev server that is actually reachable — outside-sandbox launch, `127.0.0.1` check, 4-family localhost diagnosis on failure |
| `vcheck` / `demo` | Headless visual verification / scripted MP4+GIF product demos |
| `recall` / `remember` | Search past work across all folders / save one durable fact to curated memory |
| `techreport` | Git history + notes → detailed technical report → docx; upload is a separate explicit approval |
| `autopilot` | Outer safety harness for bounded autonomous runs — hard limits, watchdog kill, diff & command gates, secret scan; unarmed by default |

## A typical crew run (measured example, 2026-07-30)

```text
1. Coordinator probes the system → finds a P0 (the WSL bridge was eating quotes,
   breaking worker_done payloads).
2. task-create → dispatch --inject to a fresh Fable writer terminal (serial startup,
   sealed brief with sha256).
3. Writer fixes the bridge + ships regression tests → scoped commit → worker_done
   with exact task/dispatch IDs.
4. Fresh GPT-5.6-Sol reviewer attacks the pinned commit read-only → 501-vector
   fuzz → APPROVE (or REVISE → same writer fixes → fresh reviewer).
5. Coordinator independently re-runs the gates (tests · doctor · drift) and reports
   with evidence. User gate decides ship.
```

## Install

```bash
git clone https://github.com/click6067-ship-it/ultrapowers ~/ultrapowers

# 1. Runtime — Node 20, Python 3.12
npm i -g @anthropic-ai/claude-code @openai/codex

# 2. Install portable assets into ~/.claude and ~/.codex
bash ~/ultrapowers/install.sh
#    COMMAND_CENTER=~/my-center bash ~/ultrapowers/install.sh   # if your memory/log home isn't ~/main

# 3. Plugins (run inside a Claude session — /plugin can't be invoked by the agent)
#    /plugin install superpowers@claude-plugins-official
#    /plugin install vercel@claude-plugins-official

# 4. MCP (kept minimal — 3-6 servers is the sweet spot; GitHub via the gh CLI)
claude mcp add -s user context7 -- npx -y @upstash/context7-mcp
claude mcp add -s user --transport http vercel https://mcp.vercel.com
claude mcp add -s user --env FIRECRAWL_API_KEY=<key> firecrawl -- npx -y firecrawl-mcp
#    Codex side: ~/.codex/config.toml is created with context7 + firecrawl — key by env NAME only

# 5. Secrets & logins: create ~/.secrets/api-keys.env (chmod 600) · claude (OAuth) · codex login
# 6. (optional) Orca layer: install the Orca ADE, then read the live guides first:
#    bash ~/ultrapowers/orca/orca-docs.sh guide orca-cli
```

The installer copies the rulebooks, all 17 skills, 11 hooks (+tests), headless tools, agents, workflows, statusline, guardrail, doctor and verify into place, creates a safe `~/.codex/config.toml`, **merges idempotently** into an existing `settings.json` (needs `jq`), and runs `doctor.py` to verify itself. WSL note: `vcheck`/`demo` chromium needs system libs installed separately.

## Layout

| Path | What |
|---|---|
| `CLAUDE.md` · `AGENTS.md` · `rules/` | One shared rulebook — for Claude and for Codex |
| `skills/` (17) · `hooks/` (11 + tests) · `agents/` (5) · `workflows/` (3) | The agent surfaces |
| `orca/` | The Orca-ADE crew suite (optional; bridge · policy sync · gate · provisioner · finalizer · metrics · council · doc loader, with their test suites) |
| `tools/headless/` | `vcheck` · `demo` · `sloplint` (Playwright + ffmpeg; Chromium runs `--no-sandbox` — trusted URLs only) |
| `guardrail.py`(+77-case test) · `doctor.py` · `verify.sh` · `autopilot.sh`(+44-case test) · `netcheck.sh` · `doc2txt.sh` · `statusline.py` | Root utilities |
| `settings.template.json` · `settings.local.example.json` · `codex.config.template.toml` | Templates (no-cloud locks included; secrets by env-var name only) |
| `install.sh` · `CHANGELOG.md` | One-shot location-independent installer · full version history v0.1→v0.6 |

## Version history

See **[CHANGELOG.md](CHANGELOG.md)** — every release from v0.1 (2026-06-05) to v0.6 (2026-07-30) with dates, commit hashes, and what changed and why. Git history is never rewritten; prior versions remain checkable.

## Built on

[superpowers](https://github.com/obra/superpowers) by obra (Jesse Vincent) supplies the skills methodology and plugin ecosystem. ultrapowers keeps it as the backbone and adds the multi-backbone crew, cross-lab adversarial review, Orca lifecycle coordination, auditable council logs, cross-session memory, headless tools, and the evidence discipline.
