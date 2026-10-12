# Plugin compatibility audit

Audit date: 2026-10-12. This covers the repository's 14 original plugins: 12 retained and two removed. It separates reusable instructions from host integrations. Every retained plugin's live workflow in Claude Code and Codex is **NOT CHECKED** in this audit. Reading a skill, validating a manifest, or passing a script test does not prove that a host activates and follows it.

## What the host documentation establishes

Both hosts use skills with `name` and `description` in `SKILL.md`. Claude supports legacy commands and additional metadata; Codex's documented import converts slash commands to skills. The development entry points therefore live in `skills/` and read their companion procedures directly. See [Claude skills](https://code.claude.com/docs/en/skills), [Codex skills](https://learn.chatgpt.com/docs/build-skills), and [Codex import](https://learn.chatgpt.com/docs/import).

OpenAI's public plugin submission guide says to convert reusable commands and agent procedures into skills, use package-relative helpers, and remove Claude-only settings. Those are submission rules, not proof that an existing local plugin has been installed or tested. This repository retains `.claude-plugin` packaging for Claude installations and imports; it does not claim acceptance into OpenAI's public directory. See [submit a Claude plugin](https://developers.openai.com/plugins/guides/submit-claude-plugin#review-what-openai-supports).

Hooks require separate treatment. Claude documents `hooks/hooks.json` as the default location and `tool_response` as the `PostToolUse` result. Codex supports manually installed plugin hooks after trust review, including compatibility environment variables, but that does not establish equivalent tool matchers or payloads. See [Claude plugin layout](https://code.claude.com/docs/en/plugins-reference#standard-layout), [Claude hooks](https://code.claude.com/docs/en/hooks#posttooluse), and [Codex plugin hooks](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks).

## Retained plugins

"Shared workflow" means the source supplies a procedure that ordinary file, shell, and question tools can execute. It describes a source contract, not verified runtime compatibility. Host-specific agent metadata remains an adapter; shared workflows read the procedure without relying on that metadata.

| Plugin | Claude Code source contract | Codex source contract | Required checks and limits |
| --- | --- | --- | --- |
| `agent-dispatch` | CLI launcher and install discovery for Claude | Separate CLI launcher and install discovery for Codex | Requires Bash, Git, `gh`, an authenticated selected CLI, scheduler configuration, and `issue-to-pr`. Fake-CLI contract tests cover dispatch logic, not real permission inheritance or scheduled delivery. |
| `claude-md-slim` | Edit `CLAUDE.md` and path-scoped `.claude/rules` | Can edit the same Claude files with ordinary filesystem tools | Intentionally targets Claude's instruction format. It does not slim `AGENTS.md` or prove Codex loads `.claude/rules`. Audit and extraction scripts can check content preservation. See [Claude memory](https://code.claude.com/docs/en/memory). |
| `codex-collaboration` | Claude leads and dispatches to an authenticated Codex integration or CLI | A Codex-only session does not satisfy the two-model workflow | Retain as an explicit integration. Companion availability, current model resolution, authentication, cancellation, and independent review require live checks. Do not substitute a same-model review and claim cross-model agreement. |
| `humanizer` | Read the selected language rules and edit prose | The same rules are accessible through native file tools | Host tool names or tool restrictions do not establish a shared permission policy. Test EN, RU, short, mixed-language, and embedded-mode prompts on both hosts. The advisory scanner cannot prove prose quality. |
| `implementation-prd` | Shared spec procedure with a Bash scaffold | Same procedure and scaffold through native tools | Resolve helpers from the installed skill. Check scaffold output, refusal to overwrite, data-model selection, and a complete spec bundle. Generated spec quality needs a real prompt on each host. |
| `issue-to-pr` | Shared gated workflow with host companion adapters | Shared workflow with native Codex companions and optional CLI adapters | Requires Bash, Git, `gh`, repository gates, and explicit merge authority. Shell contract tests and mocked behavioral-eval runner tests do not prove a real issue reaches a reviewable PR in both hosts. Live merge is a separate authorized action. |
| `learning-guide` | Analyze and render through skills and Node helpers | Same files and Node helpers through native tools | Resolve renderer resources from the installed skill. Validator and renderer tests cover output contracts. Browser checks cover rendered interactions; source-to-guide synthesis still needs live host prompts. |
| `python-dev` | Native entry skill; optional Claude reviewer adapter | Same entry skill; native bounded delegation or a disclosed sequential review | Legacy command has one skill replacement. Companion links and fallback paths have a static check. Python project tests validate generated code, not skill activation. |
| `tg-essentials` | Shared Telegram account, alerts, and announcement procedures | Same procedures through native file and shell tools | Account scripts require the configured Telethon session; announcements require destination and deployment evidence. Unit tests use controlled inputs. Authentication, real Telegram reads, sends, topic routing, and delivery are separate live checks. |
| `tg-voice` | Automatic transcription targets a Claude Telegram download hook | The local transcription helper can be invoked manually; setup and automatic hook equivalence are unverified | Requires Python, `faster-whisper`, a cached model, and actual voice media. Check hook discovery, `PostToolUse` input shape, matcher, and injected transcript in a real host. A JSON fixture cannot prove a live MCP tool response shape. |
| `typescript-dev` | Native entry skill; optional Claude reviewer adapter | Same entry skill; native bounded delegation or a disclosed sequential review | Legacy command has one skill replacement. Companion links and fallback paths have a static check. TypeScript project tests validate generated code, not skill activation. |
| `unity-dev` | Shared development and direct test-running skills; optional Claude agent adapters | Shared skills with native tools and optional bounded delegation | Test parameters come from the request, not host placeholders. Requires Bash and the matching Unity editor. Script checks cannot prove EditMode, PlayMode, builds, licensing, or target-device behavior. |

## Removed plugins

| Plugin | Reason for removal | Existing feature |
| --- | --- | --- |
| `agent-teams` | The plugin copied native feature documentation and carried stale defaults, controls, and cleanup instructions. Maintain the feature through its official guide rather than a second setup recipe. | Claude still has experimental agent teams; removal of this plugin does not remove that feature. See [agent teams](https://code.claude.com/docs/en/agent-teams). |
| `lsp-setup` | The plugin repeated a Claude-specific marketplace and settings recipe, including a fixed registry of servers. It supplies no general Codex code-intelligence workflow. | Claude documents code-intelligence plugin configuration and installation directly. See [plugin installation](https://code.claude.com/docs/en/discover-plugins) and [LSP manifest reference](https://code.claude.com/docs/en/plugins-reference#lspservers). |

## How to collect behavioral evidence

For each shared workflow, invoke a realistic prompt on each host against the same packaged version. Record host version, skill activation, required resources, observable output, and checks run. Include a rerun and an ambiguous or negative prompt. For workflows with external effects, use a controlled destination and verify interruption and retry behavior before claiming delivery or cleanup.

For host adapters, test the actual integration: two authenticated models for `codex-collaboration`, real scheduled CLI launches for `agent-dispatch`, and a downloaded voice note for `tg-voice`. A missing optional adapter should leave its coverage marked `NOT CHECKED` while unrelated work continues. Required capabilities still block the workflow that needs them.

This audit did not start paid model sessions, modify account authentication, install dependencies, register schedulers, send Telegram messages, or launch Unity. Those operations need their own execution evidence and task authorization.

## Offline verification

The local checks passed on 2026-10-12: 165 issue-to-pr contract tests, 90 dispatch tests, 65 learning-guide checks, 43 Telegram account tests, 20 announcement tests, nine eval-adapter tests, eight catalog checks, two development workflow checks, and six voice hook fixtures. Shellcheck passed for the workflow scripts. The voice fixtures replace Whisper and cached models; they verify payload handling and context output, not audio quality or live tool delivery.

Scaffold overwrite protection, guide rerender consistency, and instruction extraction checks also passed. These results cover local contracts. They leave the live host acceptance requirements above unchanged.
