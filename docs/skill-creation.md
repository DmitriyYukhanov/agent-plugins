# Skill authoring

Use the [Agent Skills specification](https://agentskills.io/specification) for the shared format. Consult the target host's documentation for discovery, installation, permissions, and extensions. For Claude Code packaging, see its [skills documentation](https://docs.anthropic.com/en/docs/claude-code/skills).

Keep skills focused on the task. Link to platform documentation rather than copying it. A valid skill format does not prove that every host can install the plugin or execute its workflow.

## Metadata

The shared frontmatter requires `name` and `description`. Optional base fields are `license`, `compatibility`, `metadata`, and experimental `allowed-tools`.

- Match `name` to the skill directory: 1-64 lowercase letters, digits, or hyphens, without leading, trailing, or consecutive hyphens. Prefer names that make the task clear.
- Keep `description` within 1024 characters. State what the skill does and when to use it; put the main trigger first because host listings may truncate it.
- Add `compatibility` only for actual environment requirements, within 500 characters. Use `metadata` for string-to-string annotations.
- The base `allowed-tools` format is a space-separated string. Support and enforcement vary by host; verify both before treating it as a permission control.

Fields such as `argument-hint`, `disable-model-invocation`, `user-invocable`, `model`, `context`, `agent`, and `hooks` are host extensions. Add one only when needed, document its host, and check that host's current reference. Other hosts may ignore or reject it. Model selection and invocation settings do not establish portability or grant authorization.

## One workflow, available capabilities

- Write one shared workflow in `SKILL.md`. Specify capabilities such as reading files, running commands, searching documentation, or delegating a bounded review. Use the current host's tools to provide them.
- Keep generic skills independent of mandatory vendor CLIs, model names, and agent APIs. A command example may show an available adapter; its name must not become the task's completion criterion.
- If a capability is required and unavailable, report which step is blocked. If an adapter is optional, use a documented equivalent where possible or report the missing coverage and continue unaffected work.
- A skill whose purpose is a particular host integration may require that host's CLI, APIs, or settings. Declare that scope and its prerequisites explicitly; keep host setup in the integration reference rather than duplicating the shared workflow.
- Document installation support separately from workflow requirements. Host hooks, plugin manifests, and agent configuration remain host-specific even when the skill body is shared.

## SKILL.md body

- Keep `SKILL.md` lean and procedural; target under 500 lines.
- Assume the agent is competent. Add task-specific workflow, constraints, and references.
- Give one clear default path first. Do not present a menu of equivalent options unless the choice is genuinely important.
- Order fragile workflows and give each step a checkable completion criterion. State failure branches, stop conditions, and which independent steps may run in parallel.
- For live mutations, read the current state first and keep writes within the user's authorized scope. Require approval for destructive actions that lack authorization. Design retry behavior to avoid duplicate writes or data loss.
- Use progressive disclosure: keep variants, long examples, schemas, and domain detail in referenced files, not in the main body. When loading reference files, read only the relevant section rather than the entire file.
- Link referenced files directly from `SKILL.md`; avoid deep reference chains.
- Use forward slashes in paths and examples, even on Windows.

## Bundled resources and paths

- Put deterministic or repeated logic in `scripts/` instead of large inline code blocks. Validate scripts directly: check argument handling, exit codes, and stdout/stderr contracts.
- Use `references/` for detailed guidance and `assets/` for templates or other static resources. Add them only when the workflow needs them.
- Label host configuration by its target. For example, an `agents/` directory containing OpenAI-format configuration is a host adapter, not a portable subagent definition.
- Do not create extra files like `README.md`, `CHANGELOG.md`, or setup notes inside a skill unless the skill truly needs them at runtime.
- Do not duplicate the same guidance across `SKILL.md` and `references/`.
- Resolve bundled paths relative to the installed `SKILL.md` or script location, using the host's resource mechanism. Quote resolved filesystem paths. Avoid machine-specific absolute paths and mandatory expansion of host variables such as `${CLAUDE_PLUGIN_ROOT}` in shared skills.
- In standalone shell scripts that may be invoked from different directories, derive the plugin root relative to the script location:
  ```bash
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
  ```

## Shell scripts

- Use `set -euo pipefail`, validate required args with `${1:?...}`, write diagnostics to `stderr`, and keep structured output on `stdout`.
- Always double-quote shell variable expansions (`"$VAR"`, `"${1}"`). Never interpolate user-supplied values into `eval`, backticks, or unquoted command positions.
- Never interpolate shell variables directly into inline Python/Ruby/etc. string literals. Pass non-secret data via positional arguments or environment variables; pass secrets via stdin or file descriptors.
- Never hardcode or log API tokens or secrets. Read credentials from environment variables; never echo them to stdout.
- Run `shellcheck` on skill scripts as part of validation.

## Temp files

- Scope temp files under a skill-specific directory and clean them up.
- Use `trap 'rm -rf "$SKILL_TMPDIR"' EXIT` for automatic cleanup on all exit paths. Use a descriptive variable name that does not shadow the POSIX `TMPDIR` variable.
- For scripts that do not need repo-scoped temp files, `mktemp -d` is also acceptable.

## Subagents

- Define the subtask, required capabilities, expected result, and completion criterion. Map these to the current host's delegation tools when available; keep host-specific agent types and model settings in the adapter.
- If delegation is optional, provide a sequential path. If isolation or independent review is required, report a missing delegation capability rather than claiming the requirement was met.
- Apply least-privilege to spawned agents: restrict their tool access and mutation scope to what the subtask requires. Do not let a restricted skill bypass its own controls by delegating to an unrestricted subagent.
- Limit fan-out: avoid spawning one agent per file or item. Batch work into a bounded number of agents to prevent scalability issues.

## Validation

- Start from a few real prompts before writing the skill. Author against realistic triggers, not idealized examples.
- Test negative and ambiguous triggers to verify the skill does not over-trigger or misroute.
- Run deterministic contract checks for metadata, resource references, script interfaces, and packaging. These checks cannot prove that an agent follows the workflow.
- For behavioral evidence, execute realistic prompts on each host whose behavior you claim to support. Verify skill activation and observable outcomes, including a happy path and rerun; test interruption and retry where side effects make them relevant.
- Keep evidence tied to the tested source version and host. Record what ran, what passed or failed, and what was not checked. A claimed skill read or a contract pass alone is insufficient behavioral evidence.
- Report unavailable optional adapter checks explicitly. Their absence must not block unrelated work or releases; a failed required check still blocks the behavior it covers. Do not install vendor tools or start paid sessions merely to fill optional coverage without authorization.
- Check hostile input, credential handling, and mutation safety. Keep compatibility claims within the evidence collected.
