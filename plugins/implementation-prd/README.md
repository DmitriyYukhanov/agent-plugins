# implementation-prd

A Claude Code plugin for writing implementation-ready spec bundles that another coding agent can build from directly across frontend, backend, desktop, mobile, SaaS, platform, and feature work.

## Host compatibility

Use the shared skills in Claude Code or Codex. Resolve bundled files from the installed skill directory and use the current host's tools. Optional Claude agent adapters have a direct or sequential skill fallback. See the [compatibility audit](../../docs/plugin-compatibility.md) for runtime coverage and requirements.

Codex installation:

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add implementation-prd@dmitriy-claude-plugins
```

## Installation

```bash
/plugin install implementation-prd@dmitriy-claude-plugins
```

## Features

### Skill: `implementation-prd`

Auto-activating reference knowledge for turning app, service, platform, or complex feature requests into a build-ready spec bundle.

Covers:
- decisive PRDs for apps, services, products, platforms, and large features;
- explicit in-scope / out-of-scope boundaries;
- contracts for APIs, IPC, queues, webhooks, background jobs, and error envelopes;
- SQL schema or data-model artifacts;
- test plans with unit, integration, E2E or end-to-end-equivalent, negative, and exit criteria;
- implementation order, risks, default technical decisions, and Definition of Done.

### Script: `init-spec-bundle.sh`

Scaffolds the standard bundle:
- `<slug>_prd.md`
- `<slug>_contracts.md`
- `<slug>_schema.sql` or `<slug>_data-model.md`
- `<slug>_testplan.md`

Usage:

Locate the installed `skills/implementation-prd/SKILL.md` using the host's skill metadata or file tools, then resolve `../..` from its directory to get the absolute plugin root. Replace `<absolute-plugin-root>` below with that path and verify `scripts/init-spec-bundle.sh` exists. Replace each output placeholder with a quoted absolute destination path.

```bash
bash "<absolute-plugin-root>/scripts/init-spec-bundle.sh" my-feature feature "<absolute-feature-output-dir>" sql

bash "<absolute-plugin-root>/scripts/init-spec-bundle.sh" billing-worker system "<absolute-worker-output-dir>" data-model
```

## Usage

The skill activates automatically when the user asks for a detailed PRD, implementation-ready spec, backend service spec, frontend or mobile app spec, build-ready feature requirements, or a documentation bundle that Claude Code or Codex can implement with minimal follow-up.

Examples:

```text
Write an implementation-ready PRD bundle for a local-first podcast clipping app

Draft a build-ready feature spec for subscription-gated cloud analysis in our desktop product

Turn this rough brief into a PRD + contracts + schema or data model + test plan that Codex can one-shot implement

Write an implementation-ready spec bundle for a multi-tenant billing API and worker pipeline

Create a mobile app spec bundle for offline field inspections with sync and conflict resolution
```

## License

MIT
