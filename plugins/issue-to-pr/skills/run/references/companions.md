# Capabilities and optional companions

Use the tools and skills exposed by the current host, not another agent's installed-plugin list.
Read a companion before invoking it; use it only when its runtime requirements are met. A missing
tool changes the mechanism, never the required check. Use the preferred companion when it is
available and its runtime requirements are met; otherwise report the reason for the fallback once. If the check cannot
actually be performed, report it as blocked, never passed.

## Host tools

- Questions: the host's question tool, otherwise chat. An unanswered asynchronous question is
  still open; count user checkpoints, not tool calls.
- Delegation: native subagents (Claude Code's `Agent`, Codex's collaboration tools). Research and
  review are read-only, one implementation writer, and everything they need is passed explicitly
  rather than inherited from a hook. Without delegation the same checks run sequentially, disclosed.

## Companions

| Capability | Preferred (if installed) | Inline fallback |
|---|---|---|
| Written plan (Step 4) | `superpowers:writing-plans` | Write a short ordered plan (files to touch, test-first steps, gates) before coding. |
| Design critique (Step 2, complex) | `codex-collaboration:cross-review` when its Claude-to-Codex runtime is available | Have an independent reviewer critique the design against the code, then revise; without delegation, self-critique and disclose it. |
| Humanizing human-facing text | `humanizer:humanizer` | Self-edit the text to drop AI-tell phrasing. |
| Lazy design and build (Steps 2–4) | `ponytail:ponytail`, preserving the active level or using `full` when unset | Design and build against the same ladder by hand: does this need to exist, does the stdlib or the platform already do it, can it be one line. |
| Grilling the design (Step 3, `--grill` only) | `mattpocock-skills:grilling` over the design you just built | Discuss the design and open `asked` items in the same checkpoint, continuing until the user confirms the design. |
| Second-model review (Step 6, `complex` or after an escalation) | `codex:rescue --fresh --wait` asked for a read-only review, no edits — without that ask its forwarder runs Codex with `--write`, and `--fresh` skips its resume-thread question. Hand it the issue and the files from `git diff --name-only <BASE>` plus `git ls-files --others --exclude-standard`: nothing is committed yet. It reports findings with `path:line`, impact and evidence, and the parent applies them like any reviewer's, one pass the ratchet counts. Empty output or a background-job notice is a blocked review, not a clean one: take the fallback. Hash the tree before and after the call with `{ git diff <BASE>; git ls-files --others --exclude-standard; git ls-files --others --exclude-standard \| git hash-object --stdin-paths; } \| git hash-object --stdin`; a different hash means Codex edited the tree, a hard stop. | The independent adversarial reviewers, which share the writer's model family: report that no second model read the diff. |
| Deletion lens (Step 6) | `ponytail:ponytail-review` over the run's diff | Re-read the diff hunting only for what to delete: reinvented stdlib, one-caller abstractions, config nobody sets, flags nobody passes. |
| Second opinion (Step 3 ladder, `--headless` only) | `codex:rescue --fresh --wait` asked for a read-only answer, no edits, handed the issue, the options and the repo precedent, asked which option and why; empty output or a background-job notice is no second opinion | Two rungs only; the ledger says no second model weighed in. |

Step 6's four checks get no row. In Claude Code they are `code-review`, `/security-review`,
`simplify` and `run` (the skill that builds the change and drives it); there is no `verify`
command to call. Before Step 7's commit, include `git diff <BASE>` and untracked files in the
security check: `/security-review` reads the committed range and can miss working-tree changes.
Perform that check inline when needed and report its scope. Elsewhere, perform the check directly:
a read-only reviewer over the diff, its
callers and its tests; the trust boundaries, authorization and secret exposure of the changed
flow; the surviving code made simpler without behaviour change; the built change driven past its
happy path.

The `codex-collaboration` and `codex` plugins orchestrate Codex from Claude Code; installing them
in Codex does not supply a second model. Use the inline fallbacks for their rows there. The Codex
review bot on the PR (Step 7) is not the second-model review either. Deep research is optional
user-supplied context, never a prerequisite or a command the pipeline assumes it can start.
