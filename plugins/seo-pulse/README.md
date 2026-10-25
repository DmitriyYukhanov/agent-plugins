# SEO pulse

Use Search Console evidence to choose one SEO change per site, wait and measure.
The weekly routine maintains a pinned report issue and `seo-signal` issues. It
does not edit sites or open PRs.

```text
/plugin install seo-pulse@dmitriy-claude-plugins
```

For Codex, use the app's plugin installer or
`codex plugin add seo-pulse@dmitriy-claude-plugins` where that CLI is available.
The shared skill uses the current host's tools. The bundled MCP config is a
Claude Code adapter; configure MCP separately when your host needs it.

Read the [skill](skills/seo-pulse/SKILL.md) and
[setup guide](skills/seo-pulse/references/setup.md). Copy the project config and
opt-in CI template from the skill's assets. Python 3.11+ is required for weekly
runs; `uvx` runs the pinned upstream MCP adapter for interactive access.

The first read-only assessment can verify project scope and existing experiments
before installing config or creating a report issue. Product workspaces use their
owned landing and documentation pages; marketplace rankings and sales need
separate analytics. Follow each page's source repository when proposing a change.

Weekly reports use deterministic analytics and issue publishing without a paid
model call. Real GSC grants, host installation and first unattended delivery
require separate verification; local tests use a fake API transport.
