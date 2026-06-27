# ultrapowers

A Claude Code + Codex setup for software projects, built on [obra's superpowers](https://github.com/obra/superpowers). Claude plans; a second model from a different lab (Codex / GPT) reviews the plan adversarially *before any code is written*; every planning session is saved as an auditable log; and context carries across sessions and folders.

The loop:

```text
define → research → plan → build → verify → review → ship → report
```

Runs on Claude Code + the Codex CLI. The two-model loop drives heavy usage, so Claude Max and Codex Pro are recommended.

## What's inside

| Component | What it does |
|---|---|
| `CLAUDE.md` | Always-loaded rules for Claude — Karpathy's 4 rules, the Phase 0 Gate, the work loop |
| `AGENTS.md` | The same rules for Codex, so both models share one rulebook |
| `/kickoff` | Two-model adversarial planning review, with **no-echo** scoring |
| council logs | Every kickoff round saved to `council/<date>_<topic>/` — full transcript + the evolving plan |
| phase-fixed modes | Planning & research run divergent (both models + subagents + web search); build, verify & review run convergent |
| cross-session memory | Recent cross-folder context injected at session start; every turn archived to markdown |
| 7 skills | `kickoff` · `recall` · `remember` · `vcheck` · `demo` · `techreport` · `spec-decompose` |
| 4 hooks | session-start context · per-turn archive · session-end summary · techreport auto-push (opt-in) |
| guardrail | a `PreToolUse` hook that blocks **only** catastrophic, irreversible Bash (recursive force-delete of home/root, fs format, raw disk write, fork bomb, force-push to main/master) and lets everything else run — autonomy preserved, deny-by-policy |
| 3 subagents | `researcher` (multi-source web research + crawl) · `verifier` (single-claim adversarial check) · `redteam` (in-session critic) |
| doctor + verify | `doctor.py` health check (auth · hooks · plugins · statusline · runtime versions; runs at install end) · `verify.sh` stack-detect test/typecheck/lint/build matrix |
| statusline | bottom bar — model · context% · dir · git branch · session cost |
| Codex config | safe `~/.codex/config.toml` template (`workspace-write` + `on-request` + web search + context7/firecrawl MCP, key placeholder) |

## How it works

### Phase 0 — define before code

`Intake → Prior-art → Plan`. For ambiguous or high-stakes work, the agent re-questions intent and success criteria, benchmarks prior art, writes a short frame, then implements. An obvious one-line chore skips the gate.

### `/kickoff` — two-model planning review

`/kickoff` is a skill — a documented workflow Claude follows, invoking the Codex CLI as the reviewer. Claude drafts the plan; Codex reviews it adversarially, looping `APPROVED` / `REVISE` (the skill caps it at 4 rounds). A single model reviews its own plan with the biases that wrote it; a second model from a different lab doesn't share all of them.

1. Creates `$COMMAND_CENTER/council/<date>_<topic>/`.
2. **Round 0** — both models write a blind independent frame (neither sees the other), so Codex isn't anchored to Claude's framing.
3. Claude drafts the plan.
4. Codex reviews it in read-only mode with web search, reporting each finding as `[finding] / why it fails / impact / suggested fix`, ending with `VERDICT: APPROVED` or `REVISE`.
5. Repeats until `APPROVED` (the skill's checklist for APPROVED: problem separated from solution · falsifiable success criteria · explicit non-goals · assumptions + evidence · ≥3 premortems · minimal version + a deliberate cut · prior findings resolved) or the round cap.

**no-echo.** On a contested decision the two models can't just agree. Each scores the options on weighted dimensions (evidence grade · real-world survival · counter-argument survival · falsifiability · cost/benefit), cites a basis for every score, and ends with a "what I reversed" section.

### Auditable council logs

Codex runs in the foreground (output streams live), and every round is written to:

```text
$COMMAND_CENTER/council/<date>_<topic>/
  council.md   # full round-by-round transcript: each frame, Codex's findings, every verdict, each revision
  plan.md      # the current plan, overwritten each round
```

`git diff` the folder to replay how a plan evolved.

### Phase-fixed modes

The collaboration mode is set by phase, not guessed per task:

- **Planning · research** — divergent: both models run their own subagents + web search in parallel, then converge.
- **Build · verify · review** — convergent: serial, with Codex cross-review.

### Cross-session memory

A session-start hook injects recent cross-folder context (pointers + links to full logs, not full transcripts); every turn is archived to markdown. Reopen in any folder and recent context reconnects.

## Skills

| Skill | What it does |
|---|---|
| `kickoff` | Two-model adversarial planning review (above) |
| `recall` | Search past work across all folders — conversation archive (`logs/`) + curated memory |
| `remember` | Save one durable fact to curated cross-session memory (typed: user · feedback · project · reference) |
| `vcheck` | Headless visual check of a URL — desktop + mobile screenshots, horizontal-overflow + console-error report |
| `demo` | Scripted product demo recorder — renders frames in a headless browser into `demo.mp4` + `demo.gif` |
| `techreport` | Build a technical report from git history + notes, convert to docx, push to GitHub |
| `spec-decompose` | Split a master spec into per-section child specs (validated by `spec_doctor.py`), then hand off to superpowers `writing-plans` |

```bash
node ~/.claude/tools/headless/vcheck.mjs <url> [outdir]                 # desktop.png + mobile.png + JSON report
node ~/.claude/tools/headless/demo.mjs   <url> [scenario.mjs|-] [outdir] # demo.mp4 + demo.gif
```

## Hooks

| Hook | Runs on | What it does |
|---|---|---|
| `recent-context.py` | SessionStart | Injects recent cross-folder session pointers (slug · time · session id · log path) — pointers, not prompt text |
| `export-sessions.py` | Stop | Converts JSONL transcripts to markdown logs (incremental, with a lock + credential redaction) |
| `session-end-summary.py` | SessionEnd | Writes a one-session summary (first/last prompt, tool-call count, duration, end reason) |
| `techreport-autopush.py` | SessionEnd | Opt-in (off in the default template): when a `.push-pending` marker exists, commits and pushes `reports/` from the command center |

## A typical run

```text
1. Start Claude Code in a project — SessionStart injects recent context pointers.
2. Ambiguous work → Phase 0 frames the problem before code.
3. Planning review → kickoff writes plan.md + council.md, Codex red-teams until APPROVED.
4. Implementation follows the approved plan.
5. vcheck verifies rendered pages when UI is involved.
6. Codex reviews core / engine / data code.
7. Stop exports the session transcript to markdown; SessionEnd writes a summary.
8. techreport generates a report and can push it from the command center.
```

## Install

```bash
git clone <this-repo> ~/ultrapowers

# 1. Runtime — Node 20, Python 3.12
npm i -g @anthropic-ai/claude-code @openai/codex

# 2. Install portable assets into ~/.claude and ~/.codex
bash ~/ultrapowers/install.sh
#    COMMAND_CENTER=~/my-center bash ~/ultrapowers/install.sh   # if your memory/log home isn't ~/main

# 3. Plugins (run inside a Claude session — /plugin can't be invoked by the agent)
#    /plugin install superpowers@claude-plugins-official
#    /plugin install vercel@claude-plugins-official
#    /plugin marketplace add openai/codex-plugin-cc && /plugin install codex@openai-codex

# 4. MCP (kept minimal — 3-6 servers is the sweet spot; GitHub via the gh CLI)
claude mcp add -s user context7 -- npx -y @upstash/context7-mcp
claude mcp add -s user --transport http vercel https://mcp.vercel.com
claude mcp add -s user --env FIRECRAWL_API_KEY=<key> firecrawl -- npx -y firecrawl-mcp   # web crawl; key from firecrawl.dev
#    Codex side: ~/.codex/config.toml is created with context7 + firecrawl — replace the FIRECRAWL_API_KEY placeholder

# 5. Log in: claude (OAuth) · codex login · vercel via /mcp
```

The installer copies `CLAUDE.md → ~/.claude`, `AGENTS.md → ~/.codex`, and `skills/` · `hooks/` · `tools/headless/` · `agents/` · `statusline.py` · `guardrail.py` · `verify.sh` · `doctor.py` into `~/.claude`, plus a safe `~/.codex/config.toml`, with paths substituted. If a `settings.json` already exists it is **merged idempotently** (env · hooks · plugins · statusLine; needs `jq`); otherwise it is created from the template (`permissions.allow: []` — opt-in, see `settings.local.example.json`). It then runs `doctor.py` to verify the install.

## Layout

| Path | What |
|---|---|
| `CLAUDE.md` · `AGENTS.md` | One shared rulebook — for Claude and for Codex |
| `skills/` | The 7 skills (`spec-decompose` also ships `spec_doctor.py` + templates) |
| `hooks/` | The 4 session hooks |
| `tools/headless/` | `vcheck` · `demo` (Playwright + ffmpeg; Chromium runs `--no-sandbox`, so point them at trusted URLs; WSL needs chromium libs, installed separately) |
| `agents/` | 3 subagents — `researcher` · `verifier` · `redteam` |
| `guardrail.py` · `doctor.py` · `verify.sh` · `statusline.py` | PreToolUse guardrail · health check · verification matrix · status bar |
| `codex.config.template.toml` | safe Codex config (web search + MCP, no danger bypass, key placeholder) |
| `install.sh` | One-shot, location-independent installer (idempotent settings merge + post-install doctor) |
| `settings.template.json` · `settings.local.example.json` | Harness template + example local permission allowlist |

## Built on

[superpowers](https://github.com/obra/superpowers) by obra (Jesse Vincent) supplies the skills methodology and plugin ecosystem. ultrapowers keeps it as the backbone and adds the two-model review, council logs, cross-session memory, headless tools, spec decomposition, and reporting.
