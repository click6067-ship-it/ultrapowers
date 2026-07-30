<div align="center">

# ⚡ ultrapowers

**A multi-backbone AI agent *crew* — not just one model with a to-do list.**

Claude plans and writes. A model from a *different lab* attacks the pinned commit read-only. Real tests and a human gate decide "done." Every task, dispatch, and completion is recorded by the **Orca ADE** — the part almost nobody is building on yet.

[![runs on Orca ADE](https://img.shields.io/badge/runs%20on-Orca%20ADE-1a9fbf)](https://github.com/stablyai/orca)
[![built with Claude Code + Codex](https://img.shields.io/badge/built%20with-Claude%20Code%20%2B%20Codex-6E56CF)](https://claude.com/claude-code)
[![stars](https://img.shields.io/github/stars/click6067-ship-it/ultrapowers?style=flat)](https://github.com/click6067-ship-it/ultrapowers/stargazers)
[![license](https://img.shields.io/github/license/click6067-ship-it/ultrapowers)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/click6067-ship-it/ultrapowers/pulls)

```text
define → research → plan → build → verify → cross-lab review → ship → report
```

**[Why](#why-this-exists)** · **[Does it work?](#does-cross-lab-review-actually-catch-anything-measured-not-marketing)** · **[Highlights](#highlights)** · **[Architecture](#architecture)** · **[Skills](#skills)** · **[Install](#install)** · **[Changelog](CHANGELOG.md)**

</div>

---

## Why this exists

Most "AI dev setup" repos stop at *Claude plans, another model reviews in the same chat.* That's one model reviewing its own blind spots with a fresh coat of paint.

ultrapowers runs the loop as a **real crew on the [Orca ADE](https://github.com/stablyai/orca)**: a read-only **coordinator**, a single **writer** per worktree, and a **reviewer from a different lab** hammering a *pinned commit* — each in its own terminal, each with real task/dispatch/completion provenance. It grew out of [obra's **superpowers**](https://github.com/obra/superpowers) and keeps that discipline as its backbone.

The Orca foundation is the part you won't find in the usual superpowers / aider / cursor tooling — and it's what turns "spin up more terminals" into an accountable pipeline where lifecycle, ownership, and evidence are first-class.

## Does cross-lab review actually catch anything? (measured, not marketing)

One day, 2026-07-30. A GPT‑5.6‑Sol reviewer attacked Fable-written infrastructure code and sent it back **four rounds in a row** — each time with a *real* defect that same-model review had already passed:

| Round | What the cross-lab reviewer caught |
|---|---|
| 1 | Stale trust key surviving a dedup → silent false-green |
| 2 | TOML orphan-key reattachment when a table shrinks |
| 3 | Valid-but-disguised config headers slipping past a regex |
| 4 | Two defense layers with no mutation-red coverage |

Only round 5 got an `APPROVE`. **Diversity catches what redundancy cannot** — that's the whole thesis, and it's reproducible in the commit history.

## Highlights

- 🐋 **Built on the Orca ADE** — real multi-terminal crew with task/dispatch/`worker_done` lifecycle, not screen-scraped terminals.
- 🧪 **Evidence or it didn't happen** — `verify.sh` exits `NOT_VERIFIED` (never PASS) when zero checks ran; sealed briefs (sha256); exact IDs in every report.
- 🛡️ **77-case guardrail** — a PreToolUse hook that blocks *only* catastrophic, irreversible Bash (recursive home/root deletion, disk format, force-push to main, through nested `sudo/env/time` wrappers) and lets everything else run. Bypass-hardened with shlex + recursion.
- 🎛️ **17 skills, 11 hooks, 3 workflows, 5 subagents** — planning council, isolated `race`, blind `qualityloop`, anti-slop design (`sloplint` — deterministic, because an LLM judge can't see its own slop), onboarding bootstrap, and more.
- 🔁 **Fire-drilled failure semantics** — worker kill auto-recovers, duplicate/late `worker_done` can't corrupt state, app restart preserves everything (8/8 restart drill).
- 🔒 **Secrets by env-var name only** — no keys in configs; no-cloud locks ship in the settings template.

---

# Architecture

## 1. Layers — who owns what

```text
┌─────────────────────────────────────────────────────────────┐
│ L0  USER                                                    │
│     problem definition · risk approval · final call         │
│     (ADOPT / PIVOT / STOP)                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ L1  COORDINATOR   (a role contract — not a fixed model)     │
│     read-only · builds the DAG · assigns scope · barriers   │
│     · cross-checks evidence                                 │
│     ✗ never edits product files                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ task-create → dispatch --inject
┌──────────────────────────▼──────────────────────────────────┐
│ L2  ORCA ORCHESTRATION      ★ source of truth for lifecycle │
│     task · dispatch · worker_done · deps · gates · retries  │
│     (survives an app restart — verified 8/8)                │
└──────────────────────────┬──────────────────────────────────┘
                           │
      ┌────────────────────┼────────────────────┐
      ▼                    ▼                    ▼
┌────────────┐      ┌─────────────┐     ┌────────────────┐
│ L3 WRITER  │      │ L3 REVIEWER │     │ L3 JUDGE       │
│ exactly 1  │      │ read-only   │     │ blind scoring  │
│ per worktree│     │ pinned commit│    │ (race /        │
│            │      │ ★ other lab │     │  qualityloop)  │
└─────┬──────┘      └──────┬──────┘     └────────────────┘
      │                    │
      ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│ L4  SUBAGENTS — short, bounded, read-only lookups inside    │
│     a single worker (never a substitute for cross-lab)      │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ L5  SOURCES OF TRUTH  (overlap guarantees drift)            │
│   git commit ········ what the code is                      │
│   real test output ·· whether it works                      │
│   artifact ledger ··· sealed hashes · claims · scores       │
│   user gate ········· what gets adopted                     │
└─────────────────────────────────────────────────────────────┘
```

## 2. Execution plane — the Windows ↔ WSL boundary

The distinctive part of running on Orca, and the place two real defects were found and fixed.

```text
Windows
├── Orca ADE (the app)                 ← owns terminals, worktrees, lifecycle
│     └─ spawns ──▶ WSL2 terminals
│                    ├─ Coordinator (Claude Code)
│                    ├─ Writer      (Claude Code)
│                    └─ Reviewer    (Codex CLI)
│
└── orca.exe (the CLI binary)
      ▲
      │   CLI call path: WSL ──▶ Windows
      │
   orca-wsl-bridge.ps1   ← PowerShell 5.1
      ▲                     ① repairs the duplicate PATH/Path env key
      │                        (upstream bug — defense in depth)
      │                     ② rebuilds argv by CommandLineToArgvW rules
      │                        (PS 5.1 silently eats embedded quotes)
   orca-ide (bash wrapper)
      ▲                     ships argv as one JSON→Base64 value, intact
      │
   WSL2 Linux (ext4)
      ├── ~/main             ← command center (meta hub)
      ├── ~/ghq/<owner>/…    ← project repos
      └── ~/.claude ~/.codex ← the global agent system
```

**Design call:** the repo stays on ext4 inside WSL. The problem was never "Linux tooling"; it was bridge stability — so the bridge got fixed instead of moving code to a slower filesystem.

## 3. Instruction loading — what a session actually gets

```text
session start
   │
   ├─ always loaded (global)
   │    CLAUDE.md                    the constitution
   │    rules/*.md            (6)    phase0-gate · work-loop
   │                                 session-memory · pitfalls
   │                                 routing · judgment
   │    ↳ trimmed ~76% (30,397B → 7,320B); detail moved to
   │      conditional runbooks read only on symptom match
   │
   ├─ path-scoped
   │    rules/design-antislop.md     only when editing CSS/TSX
   │    <project>/CLAUDE.md          only in that repo
   │
   └─ SessionStart hook (recent-context.py)
        ├─ recent-session pointers  (metadata only — never prompt text)
        └─ project brief (in a project repo)
             CLAUDE.md present? · last 3 DEVLOG headers
             registration status · deadline warning (D-7)
             + "run the probe for live state" (never bake state)
```

Two rules make this safe and cheap: **no free text is ever injected** (pointers only — blocks prompt-injection and context leakage), and **state is probed, never baked into docs** (a baked status table was measured going stale within half a day).

## 4. Hook wiring — the enforcement layer

```text
PreToolUse
 ├─ [Bash]               guardrail.py        blocks catastrophic commands (77 cases)
 ├─ [Agent|Task|Workflow] orca-trio-guard.py  prevents crew misuse
 ├─ [Skill]              skill-usage-log.py  usage counters (async)
 └─ [*]                  Orca bridge hook

PostToolUse
 ├─ [Edit|Write]         uislop-check.py     instant UI-slop feedback
 └─ [*]                  Orca bridge hook

UserPromptSubmit  →  skill-nudge.py (situation → skill) + trio guard
SubagentStop      →  subagent-log.py (cost telemetry: model · tokens · duration)
Stop              →  export-sessions.py (transcript archive, async) + nudge
SessionStart      →  recent-context.py
SessionEnd        →  session-end-runner.py (serialized pipeline)
                      ├─ session summary
                      ├─ devlog  (per-repo DEVLOG.md)
                      └─ memory mirror, scoped commit
```

Protection is **two-layer**: `guardrail.py` (pattern deny) *and* an OS sandbox (bubblewrap, fail-closed). Either one failing still leaves the other.

## 5. Task routing — when to reach for what

```text
                     work arrives
                          │
           ┌──────────────┴──────────────┐
     clear · reversible            ambiguous or expensive
     · small                             │
           │                       judge the stakes
      just do it                         │
      + related tests      ┌──────────────┼──────────────┐
                          low          medium          high
                           │              │              │
                    short intake     plan-panel      /kickoff
                    → single plan  (single backbone) (3 methods × 2
                                                      backbones, blind
                                                      → refute → synth)
                                                            │
                                                     user ADOPT gate
                                                            │
                                                       /specpack
                            ┌───────────────────────────────┘
                            ▼
                 build: one writer per worktree + TDD
                            │
                            ├─ need to compare real alternatives?
                            │  → /race (isolation + blind judges)
                            ▼
                 verify: verify.sh → cross-lab reviewer (pinned commit)
                            │
                            ▼
                 finish: qualityloop → user ship gate → /ship
```

Settled 2026-07-30: parallel collaboration unified on **orca-trio** real-terminal crews (Claude Code Agent Teams retired), planning review split by stakes, and `qualityloop` vs stop-review made mutually exclusive.

## 6. Operating contracts — what makes it a crew, not just terminals

- **Single ownership** — Orca owns lifecycle; git owns code; real test output owns "works"; the user owns decisions. No two systems own the same state.
- **One writer per worktree**; reviewers are read-only against a pinned commit; `APPROVE`/`REVISE` loops end with a *fresh* reviewer.
- **Serial worker startup** (create → tui-idle → next) to avoid hook-bundle races; dispatch runs parallel afterwards.
- **Measured failure semantics** — worker kill → dispatch auto-fails and the task auto-returns to ready (recovery = one re-dispatch) · duplicate `worker_done` is delivered twice with **no runtime dedup** (the coordinator dedupes) · a superseded dispatch's late `worker_done` has zero state authority · an app restart preserves orchestration state and reattaches panes.

## 7. Evidence discipline — the definition of "done"

The real center of gravity of the system.

| Gate | Rule |
|---|---|
| `verify.sh` | zero executed checks is **not** PASS → exit 2 `NOT_VERIFIED` |
| `worker_done` | only a matching `(taskId, current dispatchId)` pair carries state authority; stale sends are mail only |
| reviewer | read-only against a pinned commit; if the target commit moves mid-review, the review fails |
| completion | never declared without real test / doctor / diff output |
| finalization | fetch → divergence check → zero orphans → user gate |
| evidence grades | 🟢 official/measured · 🟡 secondary · ⚪ inference — grade inflation is a violation |

> Built and hardened in daily operation by **Claude Fable 5** (coordinator / system work), **Claude Opus** (project implementation), and **OpenAI Codex GPT‑5.6‑Sol xhigh** (adversarial review).

---

## What's inside

| Component | What it does |
|---|---|
| `CLAUDE.md` + `rules/` | Constitution + auto-loaded topic rules (§3 above), including **judgment** (recency · anti-echo · evidence grades) and **routing** (§5 above) |
| `AGENTS.md` | The same constitution for Codex, so both labs share one rulebook |
| **`orca/`** (optional) | Orca-ADE crew suite: WSL↔Windows CLI bridge with quote-exact argv (501-vector fuzz-reviewed) · parser-truth Codex-runtime policy sync (no TOML disguise can false-green; 26 tests) · fail-closed platform gate (21 tests) · worker provisioner · finalization checker · crew metrics · artifact-ledger council (17 tests) · live bundled-doc loader |
| 17 skills · 11 hooks · 3 workflows · 5 subagents | The agent surfaces (see Skills below and §4 above) |
| doctor + verify | health check (mirror drift · runtime hook trust · Orca bridge canaries · pending-decision watch) · `NOT_VERIFIED` verify semantics |
| templates | `settings.template.json` (no-cloud locks) · safe Codex `config.toml` (secrets by env-var *name* only) · statusline |

## Skills

| Skill | What it does |
|---|---|
| `kickoff` | Multi-backbone plan council — blind divergence (3 methodologies × 2 backbones), adversarial hardening, non-advocate synthesis, user ADOPT/PIVOT/STOP gate |
| `orca-trio` | Crew contracts for Orca coordination — roles, ownership, recovery, finalization; commands loaded from the installed binary's live guides |
| `race` | Two/three isolated implementations compete — separate worktrees, sealed identical briefs, anonymized artifacts, blind judges, DRAW on thin margins |
| `qualityloop` | Blind independent scoring of a finished deliverable against a rubric; deterministic checks first; loop until pass |
| `newproject` | Project onboarding bootstrap — lightweight intake → 30-line project CLAUDE.md → registration → kickoff routing for high stakes |
| `hallmark` | Anti-AI-slop design system for greenfield pages, audits, redesigns |
| `specpack` / `spec-decompose` | Approved plan → PRD · ERD · design · ADRs, sized to stakes / master spec → validated per-section child specs |
| `crit` | Cross-model design & copy critique — findings verified against real code, `sloplint` referees |
| `ship` | verify → author-email + diff-damage check → scoped commit → push → deploy → live visual check → evidence report |
| `serve` | Dev server that's actually reachable — outside-sandbox launch, `127.0.0.1` check, 4-family localhost diagnosis on failure |
| `vcheck` / `demo` · `recall` / `remember` · `techreport` · `autopilot` | Visual verify / demos · search & memory · reports · bounded autonomous harness |

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

# 5. Secrets & logins: create ~/.secrets/api-keys.env (chmod 600) · claude (OAuth) · codex login
# 6. (optional) Orca layer: install the Orca ADE, then read the live guides first:
#    bash ~/ultrapowers/orca/orca-docs.sh guide orca-cli
```

The installer copies the rulebooks, all 17 skills, 11 hooks (+tests), headless tools, agents, workflows, statusline, guardrail, doctor and verify into place, creates a safe `~/.codex/config.toml`, **merges idempotently** into an existing `settings.json` (needs `jq`), and runs `doctor.py` to verify itself. WSL note: `vcheck`/`demo` chromium needs system libs installed separately. The `orca/` layer additionally needs the Orca ADE (Windows) managing WSL2 projects — everything else works without it.

> **Heads up:** this drives *heavy* usage (two labs, adversarial loops). Claude Max and Codex Pro are recommended.

## The two-repo model

```text
       ┌──────────────────────────────────┐
       │  ~/.claude  ~/.codex   (live)    │  ← what actually runs
       └──────────────┬───────────────────┘
                      │ sync (mirror)
                      ▼
    ┌────────────────────────────────────────┐
    │ command-center            (private)    │
    │   dotclaude/ dotcodex/  portable assets│
    │   orca/                 the crew layer │
    │   reports/ decisions/ projects/        │
    └──────────────┬─────────────────────────┘
                   │ publish (manifest allowlist + PII/danger gate)
                   ▼
    ┌────────────────────────────────────────┐
    │ ultrapowers               (public)     │
    │   the safe subset + install.sh         │
    │   + CHANGELOG (v0.1 → v0.6)            │
    └────────────────────────────────────────┘
```

| Repo | Visibility | Role |
|---|---|---|
| **ultrapowers** (this) | public | The shareable agent system — constitution, rules, skills, hooks, workflows, guardrail/doctor/verify, the Orca layer, templates, installer |
| **command-center** | private | The owner's meta hub: the same system as its deployed source of truth, plus strategy/decisions/session logs/reports/memory |

New machine: clone this repo → `install.sh` → three manual steps (secrets file, Claude login, Codex login).

## Version history

See **[CHANGELOG.md](CHANGELOG.md)** — every release from v0.1 (2026-06-05) to v0.6 (2026-07-30) with dates, commit hashes, and what changed and why. Git history is never rewritten.

## Built on

[superpowers](https://github.com/obra/superpowers) by obra (Jesse Vincent) supplies the skills methodology and plugin ecosystem. ultrapowers keeps it as the backbone and adds the multi-backbone crew, cross-lab adversarial review, Orca lifecycle coordination, auditable council logs, cross-session memory, headless tools, and the evidence discipline.

<div align="center">

**Three sentences that define the design**

*Split ownership so nothing is owned twice.*
*Diverge structurally early; converge strictly late.*
*Diversity catches what redundancy cannot.*

*If that resonates, a ⭐ helps others find it.*

</div>
