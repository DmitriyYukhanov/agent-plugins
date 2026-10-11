# Custom Claude Code plugins and skills

[![Last release](https://img.shields.io/github/release-date/DmitriyYukhanov/claude-plugins?label=last%20release)](https://github.com/DmitriyYukhanov/claude-plugins/releases)
[![Last commit](https://img.shields.io/github/last-commit/DmitriyYukhanov/claude-plugins)](https://github.com/DmitriyYukhanov/claude-plugins/commits/main)
[![License: MIT](https://img.shields.io/github/license/DmitriyYukhanov/claude-plugins)](./LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin%20marketplace-d97757)](https://code.claude.com/docs/en/discover-plugins)

Personal collection of Claude Code plugins and skills for structured, high-quality development workflows. Augments the official Claude plugins marketplace. Claude Code is the target these are built and tested against; Codex installs the same marketplace and picks up the skills.

## Installation

### Claude Code

Add this marketplace:

```bash
/plugin marketplace add DmitriyYukhanov/claude-plugins
```

Then install plugins by name. The `@` suffix is the marketplace name `dmitriy-claude-plugins` (from this repo's `marketplace.json`), not the GitHub path:

```bash
/plugin install agent-dispatch@dmitriy-claude-plugins
/plugin install issue-to-pr@dmitriy-claude-plugins
/plugin install codex-collaboration@dmitriy-claude-plugins
```

You can also run `/plugin` to browse and install interactively.

### Codex CLI

Codex reads this repo's `.claude-plugin/marketplace.json` as-is, so the same marketplace installs there. Needs Codex CLI 0.146 or newer:

```bash
codex plugin marketplace add DmitriyYukhanov/claude-plugins
codex plugin add humanizer@dmitriy-claude-plugins
codex plugin add issue-to-pr@dmitriy-claude-plugins
codex plugin add agent-dispatch@dmitriy-claude-plugins
codex plugin list                  # what each marketplace offers, and what is installed
codex plugin marketplace upgrade   # refresh the snapshots after a release
```

Skills are the part that crosses over, namespaced by plugin: the install above answers to `humanizer:humanizer`. Subagents and slash commands do not. Plugin hooks are untested here: Codex is known to load a hook file the manifest points at, none of these plugins do that, and whether it also finds a `hooks/hooks.json` by convention has not been checked. `${CLAUDE_PLUGIN_ROOT}` stays unexpanded inside a skill body too, so a skill that references it depends on the model resolving the absolute path Codex shows it.

Four plugins here drive Claude Code itself and have nothing to do inside Codex: `agent-teams`, `lsp-setup`, `tg-voice`, and `codex-collaboration`, which exists to call Codex from Claude in the first place.

## Plugins

| Plugin | Category | What it does |
|--------|----------|--------------|
| [agent-dispatch](#agent-dispatch) | workflow | Start headless issue-to-pr runs from GitHub labels on your own machine, Claude Code or Codex |
| [agent-teams](#agent-teams) | productivity | Orchestrate multiple Claude Code instances working in parallel with shared tasks and messaging |
| [claude-md-slim](#claude-md-slim) | development | Shrink an oversized or stale CLAUDE.md into path-scoped rules files, verifying the split lost nothing |
| [codex-collaboration](#codex-collaboration) | workflow | Cross-model Claude + Codex collaboration: drive/validate loops and parallel dual review |
| [humanizer](#humanizer) | writing | Remove AI-writing patterns from English and Russian text, with automatic language detection |
| [implementation-prd](#implementation-prd) | productivity | Turn feature requests into build-ready spec bundles with PRDs, contracts, schemas, and test plans |
| [issue-to-pr](#issue-to-pr) | workflow | Drive a GitHub issue or Project board card through a worktree-isolated, gated pipeline to an approved, merged PR |
| [learning-guide](#learning-guide) | development | Generate single-file, interactive HTML learning guides |
| [lsp-setup](#lsp-setup) | development | Detect project languages and set up LSP servers and Claude Code LSP plugins |
| [python-dev](#python-dev) | development | Python development workflow: architecture, coding guidelines, pytest patterns, and a review agent |
| [tg-essentials](#tg-essentials) | operations | Telegram toolkit: error alerts for any project through a bot, and Telegram as yourself from Telegram Desktop |
| [tg-voice](#tg-voice) | operations | Transcribe Telegram voice messages automatically with local Whisper |
| [typescript-dev](#typescript-dev) | development | TypeScript development workflow: architecture, coding guidelines, testing patterns, and a review agent |
| [unity-dev](#unity-dev) | development | Unity C# workflow: architecture, coding guidelines, tests, CLI builds and runs, and review agents |

## Plugin details

### agent-dispatch

Label an issue `agent` and your own machine picks it up: a tick every few minutes runs
`/issue-to-pr:run N --headless` under your Claude Code or Codex login, and your replies on the
issue or its PR carry the run forward.

- Replies first, then the queue: one run at a time, oldest issue first, only issues you labelled
  and comments you wrote.
- Works on Windows (Task Scheduler), macOS (a LaunchAgent) and Linux (a systemd user timer).
- A hung run is stopped after four hours and marked failed; a logged-out or rate-limited CLI
  pauses dispatching until you clear it.
- `/agent-dispatch:setup` checks the machine, asks for each repo's auto-merge threshold and, after
  one confirmation, sets up the repo list, labels and scheduler entry.

[View documentation](./plugins/agent-dispatch/README.md)

### agent-teams

Set up and orchestrate Claude Code agent teams with:
- Auto-activating skill for agent team setup and coordination
- Teams vs subagents decision guide
- Display modes (in-process and split pane)
- Prompt templates for code review, debugging, and exploration
- Configuration reference with architecture, permissions, and limitations

[View documentation](./plugins/agent-teams/README.md)

### claude-md-slim

Restructure an oversized or stale `CLAUDE.md` so instructions actually get followed:
- Measures the **loaded** size (HTML comments are stripped and free) against the documented 200-line budget
- Ranks sections and marks which to move; flags codebase-derivable content and staleness hints
- Moves subsystem detail into `.claude/rules/*.md` with `paths:` frontmatter, so it loads only when those files are opened
- Documents the `@import` trap: imports load eagerly at launch and save **no** context, only path-scoped rules defer
- Verifies the extraction lost nothing, failing loudly rather than letting a dropped section look like an intentional trim

Complements Anthropic's `claude-md-management` (which audits content quality) by fixing size and structure.

[View documentation](./plugins/claude-md-slim/README.md)

### codex-collaboration

Cross-model collaboration between Claude and Codex with two workflows:

- **collaborative-loop** — Sequential drive/validate/act cycles. Claude analyzes, Codex validates each finding, both models must agree before any action is taken. Iterates until approved or max rounds.
- **cross-review** — Parallel dual review. Both Claude and Codex review independently. Findings confirmed by reviewer agreement, cross-validation, or evidence research are auto-applied each round; only genuinely inconclusive disagreements surface for user decision.

Both workflows run the latest Opus and the latest Codex Astra model at medium effort, unless you ask for a different model or effort. The skills find the Astra model with `codex debug models` on each run, so a new release needs no plugin update.

**Requires** the [Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc). Install it first:
1. `/plugin marketplace add openai/codex-plugin-cc`
2. `/plugin install codex@openai-codex`
3. `/codex:setup` to verify

[View documentation](./plugins/codex-collaboration/README.md)

### humanizer

Auto-routing EN + RU humanizer for Claude Code that removes signs of AI-generated writing:
- Auto-detects language by Cyrillic ratio (≥60 % → RU, ≤10 % → EN, otherwise asks)
- English ruleset — vendored from [blader/humanizer](https://github.com/blader/humanizer), 33 patterns from Wikipedia AI Cleanup
- Russian ruleset — vendored from [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru), 54 patterns with hard bans and triple-pass audit, plus its deterministic 0–100 scanner (optional, needs `pip install razdel pymorphy3`)
- Explicit overrides ("humanize as English" / "обработай как русский") and mixed-text handling
- Optional voice calibration from a writing sample

Distinct from the Claude.ai-only `humanizer.skill` listed below — this is a Claude Code plugin with auto-routing.

[View documentation](./plugins/humanizer/README.md)

### implementation-prd

Implementation-ready spec bundle authoring with:
- Auto-activating skill for turning requests into build-ready spec bundles
- Templates for product, system, and feature PRDs, contracts, schemas, data models, and test plans
- `init-spec-bundle.sh` scaffolding script for standard 4-file bundles
- Quality gates checklist and cross-file alignment rules
- Worked example from a real desktop app project

[View documentation](./plugins/implementation-prd/README.md)

### issue-to-pr

Drive a single GitHub issue from triage to a merge-ready pull request in Claude Code or Codex,
using one shared workflow and the same scripts:

- One flow for a **bare issue** or a **card on a GitHub Projects (v2) board** — Step 0 resolves the input and decides whether board-status sync applies.
- Each run works in its own `../<repo>-worktrees/issue-<N>` git worktree, so concurrent local agents on different issues never clash.
- Hard gates that block forward progress: design hardening (cross-review or a multi-agent fallback), tests green (typecheck + tests, plus visual checks for UI), and a code-review loop that runs until clean, capped by tier at one to three passes.
- Scales the work to the task's **tier** (trivial, standard, complex): research depth, design (an autonomous design panel for complex work), review level, and report length all size to the issue — and it asks **at most one batched question**, deciding everything else itself and surfacing those decisions in the report and PR.
- Takes on more than a single issue: a plain request with no number is drafted into an issue and run; and after a merge, an optional smoke check on the base opens a *draft* revert PR (never an automatic rollback) if the change broke something.
- A careful merge gate: it refuses a head the gates never ran against and a review requesting changes, and passes `--match-head-commit`, so a commit landing after the diff you saw stops the merge rather than shipping unseen.
- Opens the PR and stops; once you approve it in-session it squash-merges, reporting GitHub's own message if the merge is refused, then tears the branch and worktree down. A merge into anything but the default branch is reported as one, since that is the only case where GitHub closes the issue for you.
- The PR auto-links the issue (`Closes #N`), which GitHub closes on a merge into the default branch; board cards advance to *in-progress* at branch cut and *in-review* at PR open, with `Done` left to GitHub's merge-time automation.
- Graceful by default — missing the `project` token scope degrades to link-only, and a failed status write never blocks the PR.
- Optional `.claude/issue-to-pr/config.md` for board URL, base branch, and test commands (auto-detected when unset); companion skills used if installed, with inline fallbacks otherwise (the list is in the plugin's [companions.md](./plugins/issue-to-pr/skills/run/references/companions.md)).
- Headless: with `--headless` the run's question and its merge approval are comments on the issue, and the next run picks up your reply; the PR merges on your `merge` (or `мерж`), and trivial work self-merges (`--auto-merge`) unless the issue already stopped once or the diff touches `human_paths`.

[View documentation](./plugins/issue-to-pr/README.md)

### learning-guide

Generate single-file, interactive HTML learning guides for any artifact:

- **`analyze`** skill — reads input artifact(s) (codebase, planning session, refactor plan, generic doc), writes a `tour-spec.json` describing sections, embedded sources, cross-refs, quizzes, and external link maps. Hands off to render.
- **`render`** skill — runs the bundled zero-dependency Node renderer to produce `index.html` plus launcher scripts. Idempotent for generated artifacts; re-runnable from the shell after hand-edits to the spec.
- **`learning-guide`** entry-point skill — explains the flow and dispatches to the right step.

**Requires** Node.js on PATH. No `npm install` step.

[View documentation](./plugins/learning-guide/README.md)

### lsp-setup

Set up LSP (Language Server Protocol) for Claude Code projects with:
- Auto-detection of project languages from source files and project markers
- Automatic installation of language server binaries and Claude Code LSP plugins
- Environment-aware setup (MINGW, WSL, macOS, Linux) with gotcha handling
- State machine workflow that resumes from any point (install → restart → validate)
- Post-restart validation confirming LSP operations work per language
- Supports all 12 official LSP plugins (C#, Python, TypeScript/JS, Go, Rust, Java, Kotlin, Lua, PHP, Ruby, Swift, C/C++)

[View documentation](./plugins/lsp-setup/README.md)

### python-dev

Python development workflow with:
- `/python-dev` command for end-to-end workflows (discovery → architecture → implementation → review → testing)
- Architecture patterns, protocols, and Mermaid diagrams
- PEP 8-aligned coding guidelines and type-hint best practices
- pytest-based testing patterns, fixtures, mocking, and coverage guidance
- Python-specific review agent that can delegate to general feature review

[View documentation](./plugins/python-dev/README.md)

### tg-essentials

Telegram toolkit, named `tg-alerts` before 2.0.0:
- `tg-alerts` skill: error and alert notifications for any project through a bot. Interactive 7-phase setup (@BotFather bot creation, chat ID discovery, code generation, integration, testing), reference implementations for Python async (FastAPI), Python sync (Django/Flask) and Node.js/TypeScript (Express/NestJS), with deduplication, HTML formatting and fire-and-forget delivery that never crashes the host app
- `tg-account` skill: talks to Telegram as you through the session Telegram Desktop already keeps on disk, so you don't log in or scan a QR code. It finds chats and forum topics, exports history to one text file per day, creates groups, sends, edits and pins posts, posts native checklists and sets the group photo. Posts and checklists can target a forum topic. Every write waits for your yes first

[View documentation](./plugins/tg-essentials/README.md)

### tg-voice

Transcribe Telegram voice messages using local Whisper:
- PostToolUse hook automatically transcribes `.oga` voice messages downloaded via the Telegram channel plugin
- `/voice-to-text-config` skill for guided setup: faster-whisper installation, model download, and end-to-end verification
- Configurable model size via `WHISPER_MODEL` env var (default: `base`)

**Requires:** `faster-whisper` (`pip install faster-whisper`) and the [Telegram channel plugin](https://github.com/anthropics/claude-code).

[View documentation](./plugins/tg-voice/README.md)

### typescript-dev

TypeScript development workflow with:
- `/typescript-dev` command for full-stack TypeScript workflows
- Architecture design for modules, interfaces, and test stubs with Mermaid diagrams
- TypeScript coding guidelines, async patterns, and framework-aware checks
- Testing patterns for unit, integration, and E2E tests (Jest/Vitest style)
- TypeScript-specific review agent that can delegate to general feature review

[View documentation](./plugins/typescript-dev/README.md)

### unity-dev

Unity C# development workflow with:
- `unity-dev` skill orchestrating the full workflow: discovery, architecture, implementation, review, testing
- `unity-run` skill for CLI execution (builds, tests, method execution, asset imports) with Unity installation auto-detection and log monitoring
- `unity-tests-run` skill running Unity Test Framework tests via CLI batchmode
- Architecture design with Mermaid diagrams, C# coding guidelines following Microsoft conventions, EditMode/PlayMode test patterns
- Unity-specific review, simplification, and test-runner agents

[View documentation](./plugins/unity-dev/README.md)

## Claude.ai Skills

Skills for the Claude.ai web interface (not Claude Code). Install via the Skills section in Claude.ai settings.

### humanizer

Rewrites AI-generated text to sound more natural and human. Converted from [blader/humanizer](https://github.com/blader/humanizer) for Claude.ai usage.

**File:** `skills/claude.ai/humanizer.skill`

## License

MIT
