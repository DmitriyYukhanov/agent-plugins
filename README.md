# Plugins and skills for AI agents

![Code Stage agent plugins: blue and silver signal streams on a graphite background](./assets/agent-plugins-signal-weave.png)

[![Last release](https://img.shields.io/github/release-date/DmitriyYukhanov/agent-plugins?label=last%20release)](https://github.com/DmitriyYukhanov/agent-plugins/releases)
[![Last commit](https://img.shields.io/github/last-commit/DmitriyYukhanov/agent-plugins)](https://github.com/DmitriyYukhanov/agent-plugins/commits/main)
[![Workflow tests](https://github.com/DmitriyYukhanov/agent-plugins/actions/workflows/issue-to-pr-tests.yml/badge.svg)](https://github.com/DmitriyYukhanov/agent-plugins/actions/workflows/issue-to-pr-tests.yml)
[![License: MIT](https://img.shields.io/github/license/DmitriyYukhanov/agent-plugins)](./LICENSE)

Reusable skills and plugins for software development, writing, and automation.
Shared skills follow one workflow and use the tools available in the current
agent. The collection also includes integrations for particular hosts; their
requirements are listed below.

Claude Code and Codex use the same marketplace. Other agents that support
[Agent Skills](https://agentskills.io/specification) can use individual shared
skills. Compatibility of a file format does not establish that every workflow,
hook, or agent adapter works in every host. See the
[compatibility audit](./docs/plugin-compatibility.md) for evidence and limits.

## Install

### Claude Code

```sh
/plugin marketplace add DmitriyYukhanov/agent-plugins
/plugin install humanizer@dmitriy-claude-plugins
/plugin install issue-to-pr@dmitriy-claude-plugins
/plugin install python-dev@dmitriy-claude-plugins
```

Use `/plugin` to browse the catalog and manage plugins. To enable updates, open
Marketplaces, select this marketplace, and choose Enable auto-update.

### Codex

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add humanizer@dmitriy-claude-plugins
codex plugin add issue-to-pr@dmitriy-claude-plugins
codex plugin add python-dev@dmitriy-claude-plugins
codex plugin marketplace upgrade dmitriy-claude-plugins
```

Use a CLI with `codex plugin` available, or install through the Codex app's
plugin interface. Shared workflows are native skills, including
`python-dev:python-dev` and `typescript-dev:typescript-dev`. Claude-specific agent
files and hooks are optional adapters; they are not prerequisites for shared
skills. Codex's documented CLI refresh is `marketplace upgrade`; this README does
not promise an automatic update schedule.

### Copilot and other agents

Install the skill directory, including its referenced scripts and resources,
through your agent's supported skill installer. GitHub Copilot CLI also
[accepts marketplaces in `.claude-plugin`](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference#marketplacejson).
This collection has not completed runtime acceptance in Copilot. Check the
requirements of each skill before using it.

### Existing installations

The repository address changed from `DmitriyYukhanov/claude-plugins` to
`DmitriyYukhanov/agent-plugins`. The marketplace ID remains
`dmitriy-claude-plugins` to preserve installed plugin keys and settings. Update
the source address in each host configuration; an uninstall is unnecessary.
The [migration guide](./docs/marketplace-migration.md) covers backups, profiles,
refresh commands, and a possible later marketplace ID change.

## Plugins

| Plugin | Purpose | Host scope |
|---|---|---|
| [agent-dispatch](#agent-dispatch) | Dispatch queued GitHub issues on your machine | Claude Code or Codex CLI |
| [claude-md-slim](#claude-md-slim) | Audit and split oversized CLAUDE.md instructions | Shared scripts; targets Claude configuration |
| [codex-collaboration](#codex-collaboration) | Coordinate Claude-led work and Codex validation | Claude Code adapter with Codex companion |
| [humanizer](#humanizer) | Edit English and Russian AI writing | Shared skills |
| [implementation-prd](#implementation-prd) | Write specs, contracts, data models, and test plans | Shared skills |
| [issue-to-pr](#issue-to-pr) | Take GitHub issues to reviewed pull requests | Claude Code or Codex |
| [learning-guide](#learning-guide) | Build interactive HTML learning guides | Shared skills; Node.js required |
| [python-dev](#python-dev) | Develop and test Python projects | Shared skills |
| [seo-pulse](#seo-pulse) | Review Search Console evidence and maintain weekly signal issues | Shared skill; Python and GSC access required |
| [tg-essentials](#tg-essentials) | Manage Telegram chats, alerts, and announcements | Shared skills; account and dependencies required |
| [tg-voice](#tg-voice) | Transcribe Telegram voice notes through a download hook | Claude Code adapter |
| [typescript-dev](#typescript-dev) | Develop and test TypeScript projects | Shared skills |
| [unity-dev](#unity-dev) | Develop and test Unity projects | Shared skills; Unity editor required |

## Plugin details

### agent-dispatch

Run one queued issue at a time under an authorized Claude Code or Codex login.
Includes scheduling, interrupted-run recovery, and owner checks.
[Documentation](./plugins/agent-dispatch/README.md).

### claude-md-slim

Audit loaded instructions and verify a split preserves their content. Its output
uses Claude's CLAUDE.md and path-scoped rules; running the scripts from Codex does
not give Codex those loading semantics.
[Documentation](./plugins/claude-md-slim/README.md).

### codex-collaboration

Run sequential analysis/validation loops or parallel dual reviews through the
Claude Code Codex companion. This is a specific integration, not a generic
review skill. Requires the
[Codex companion for Claude Code](https://github.com/openai/codex-plugin-cc).
[Documentation](./plugins/codex-collaboration/README.md).

### humanizer

Choose the English or Russian editing ruleset automatically, with explicit
language overrides and optional voice calibration. Includes upstream MIT
attribution and an optional Russian text scanner.
[Documentation](./plugins/humanizer/README.md).

### implementation-prd

Produce a PRD, contracts, a storage or data model, and a test plan that agree on
scope and behavior. Includes templates and a scaffold that refuses overwrites.
[Documentation](./plugins/implementation-prd/README.md).

### issue-to-pr

Follow one workflow for bare GitHub issues and Project cards. Worktrees isolate
changes; design review, tests, code review, and explicit merge gates control
progress. Claude Code and Codex have separate behavioral test adapters.
[Documentation](./plugins/issue-to-pr/README.md).

### learning-guide

Analyze an artifact into a tour specification, then render an interactive HTML
guide with navigation, quizzes, and embedded sources. Node.js runs the bundled
renderer; diagrams require access to the documented CDN.
[Documentation](./plugins/learning-guide/README.md).

### python-dev

Use native skills for architecture, implementation, pytest guidance, and review.
Read the review instructions directly when the host cannot load the optional
Claude reviewer adapter.
[Documentation](./plugins/python-dev/README.md).

### seo-pulse

Choose one SEO change from Search Console evidence, check page intent and
internal links, and measure results at two and four weeks. Optional weekly reports
surface signals and sustained declines without editing sites. Includes a GSC MCP
adapter and service-account CI template.
Install with `/plugin install seo-pulse@dmitriy-claude-plugins`.
[Documentation](./plugins/seo-pulse/README.md).

### tg-essentials

Read or manage Telegram chats and forum topics, export history, and prepare
messages through the local Telegram Desktop session. Also includes bot error
alerts and checked deployment announcements. Live account operations need their
own authorization and dependencies.
[Documentation](./plugins/tg-essentials/README.md).

### tg-voice

Transcribe voice notes locally with faster-whisper through a Claude Code download
hook. Codex hook delivery is unverified; use the shared Telegram toolkit for
manual operations instead.
[Documentation](./plugins/tg-voice/README.md).

### typescript-dev

Use native skills for architecture, implementation, testing, and review. The
shared workflow supports host-native delegation or sequential review.
[Documentation](./plugins/typescript-dev/README.md).

### unity-dev

Discover the Unity editor, develop C# components, and run EditMode or PlayMode
tests through shared skill procedures. A real project and editor are required
for runtime validation.
[Documentation](./plugins/unity-dev/README.md).

## Write a shared skill

Keep one workflow. Describe the capabilities it needs, resolve resources from
the installed skill directory, and use the current host's tools. Make platform
integrations explicit. Record contract tests and real host runs separately.
Follow the [authoring guide](./docs/skill-creation.md).

`agent-teams` and `lsp-setup` have been removed from this catalog. The former
repeated native Claude documentation; the latter depended entirely on Claude's
LSP configuration. Existing installations are managed separately from catalog
removal; see the [migration guide](./docs/marketplace-migration.md).

## Claude.ai package

The standalone [humanizer.skill](./skills/claude.ai/humanizer.skill) remains
available for Claude.ai's Skills interface. It is separate from the plugin.

## License

[MIT](./LICENSE). Vendored resources retain their documented licenses.
