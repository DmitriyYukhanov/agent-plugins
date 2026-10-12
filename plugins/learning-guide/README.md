# learning-guide

Generate single-file, interactive HTML learning guides for any artifact.

## Host compatibility

Use the shared skills in Claude Code or Codex. Resolve bundled files from the installed skill directory and use the current host's tools. Optional Claude agent adapters have a direct or sequential skill fallback. See the [compatibility audit](../../docs/plugin-compatibility.md) for runtime coverage and requirements.

Codex installation:

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add learning-guide@dmitriy-claude-plugins
```

## Installation

```bash
/plugin install learning-guide@dmitriy-claude-plugins
```

## Quickstart

1. In Claude Code, say: *"Create a learning guide for `<path>`."*
2. The `analyze` skill drafts `tour-spec.json` and hands off to `render`.
3. Open `index.html` in any browser.

## Skills

- **`learning-guide:learning-guide`** — entry-point; explains the flow.
- **`learning-guide:analyze`** — reads input → writes `tour-spec.json`.
- **`learning-guide:render`** — renders `tour-spec.json` → `index.html`.

## Requirements

Node.js on PATH. The renderer is zero-dependency — no `npm install`.

## Verifying

Locate the installed `skills/render/SKILL.md` using the host's skill metadata or file tools, then resolve `../..` from its directory to get the absolute plugin root. Replace `<absolute-plugin-root>` in these commands with that path and verify each script exists.

- `node "<absolute-plugin-root>/scripts/tests/run-all.cjs"` runs unit tests for the schema validator, markdown processor, and renderer without extra packages.
- `node "<absolute-plugin-root>/scripts/verify.cjs"` runs smoke renders across the sample archetypes.
- `node "<absolute-plugin-root>/scripts/browser-verify.cjs"` runs optional browser checks in Chromium. It requires Playwright (`npm i -D playwright && npx playwright install chromium`), which is not a runtime dependency.

## Customization

Drop overrides in `<output-dir>/.learning-guide/`:
- `template.html` (set `renderer.template_compatibility_version` in spec)
- `i18n/<locale>.json` (shallow-merged over plugin defaults)
- `extra-styles.css` (appended after defaults)
- `archetype-<name>.md` (custom analyzer templates)
- `policy.json` — `{ "project_root": "<relative-path>" }` widens embedded-source resolution.
