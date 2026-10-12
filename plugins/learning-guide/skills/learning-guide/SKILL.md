---
name: learning-guide
description: Use when the user asks to "create a learning guide", "make an interactive tour", "generate onboarding doc", "build a learning module", or any variant of turning an artifact (codebase, planning session, refactor plan, design doc) into an interactive HTML guide. Dispatches to learning-guide:analyze for new tours or learning-guide:render for re-renders after spec edits. Also use when the user is uncertain which step they need.
---

# Learning guide entry point

Discoverability shim. Decides whether the user needs to start fresh (analyze) or re-render an existing spec (render).

## Decision tree

1. **Does a `tour-spec.json` already exist at the target path?**
   - Yes → ask the user: *re-render only* (dispatch `learning-guide:render`), *update spec* (dispatch `learning-guide:analyze` in update mode), or *regenerate from scratch* (dispatch `learning-guide:analyze` after deleting the spec).
   - No → dispatch `learning-guide:analyze`.

2. **Does the user want to manually edit `tour-spec.json` and just re-render?**
   - Confirm Node is on PATH.
   - Locate this installed `SKILL.md` through the current host's skill metadata or file tools. Resolve `../..` from its directory to get the absolute plugin root and verify `scripts/render.cjs` exists. If it is unavailable, report the missing path instead of offering a command that cannot run.
   - Give them `node "<absolute-plugin-root>/scripts/render.cjs" "<absolute-spec-path>"` with both placeholders replaced by the resolved paths. The command needs no host environment variable or skill invocation.

## When NOT to use this skill

- The user already invoked `analyze` or `render` — let those run.
- The user wants help debugging a generated tour — point them at `learning-guide:render`'s references (`renderer-cli.md`, `browser-compatibility.md`).

## Output

Always state which skill you're about to dispatch and why, in one sentence, before invoking it.
