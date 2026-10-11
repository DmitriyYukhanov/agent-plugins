# issue-to-pr

A plugin for Claude Code and Codex that drives a GitHub issue from triage to a merge-ready pull
request through a gated pipeline. The input can be a **bare issue**, a **card on a
GitHub Projects (v2) board**, or a **plain request with no issue yet**; the skill drafts
one first. The PR always links the issue so it auto-closes on merge; board cards advance
as work progresses.

## Installation

Claude Code:

```bash
/plugin marketplace add DmitriyYukhanov/claude-plugins
/plugin install issue-to-pr@dmitriy-claude-plugins
```

Codex (user-wide, across local projects):

```bash
codex plugin marketplace add DmitriyYukhanov/claude-plugins
codex plugin add issue-to-pr@dmitriy-claude-plugins
```

Skip marketplace registration if already configured. After a release, run
`codex plugin marketplace upgrade dmitriy-claude-plugins`, then the same `codex plugin add`
command to install the update. Start a new task to pick up the installed skills.

Git, authenticated `gh` and Bash are required; `skills/setup` §1 checks them and, on Windows,
finds Git for Windows' own `bash.exe`. Per-project settings remain optional.

## Features

### Skill: `run`

Invoked by the model or by you (`/issue-to-pr:run [issue-number | "free text"]
[--tier trivial|standard|complex] [--grill]
[--headless] [--auto-merge trivial|standard|complex|none]`).
The pipeline runs triage, research, design, implementation, review, PR, approval-gated merge,
and cleanup. Hard gates block forward progress; everything between them scales to the task.

**Headless.** `--headless` is for a run nobody is watching: its one question and its "ready to
merge" become comments on the issue, labels (`agent:*`) carry the state, and the next
`--headless` run picks up your reply where the last one stopped. It merges when you reply `merge`
(or `мерж`) to its latest report; a clean PR at or under `--auto-merge` (default `trivial`)
merges on its own, unless the issue already stopped once or the diff touches `human_paths`.

- **Isolated per task.** Each run cuts its branch inside a dedicated
  `../<repo>-worktrees/issue-<N>` git worktree, so several local agents can drive different
  issues in the same clone without clashing.
- **Scaled by tier.** Trivial, standard or complex (`--tier` overrides). Research depth,
  design machinery (an autonomous design panel for complex work), review level and passes,
  and report length all size to it.
- **Autonomous, one checkpoint max.** Three moments: one batched question mid-run (only if
  something needs your preference), the merge gate, and hard stops. `--grill` spends that first
  moment on `grilling` instead, which works the design in rounds of numbered decisions until
  nothing is left silently assumed. Every other decision it makes itself, logs, and surfaces in
  the report and PR body.
- **Gates.** Design hardening (cross-review or a multi-agent fallback), tests green
  (typecheck + tests, plus visual checks for UI work), and a code-review loop that runs
  until clean within the tier's pass cap. Review depth escalates when a pass confirms two or
  more bugs. If a later pass finds a positive bug count at least as high as the previous one,
  the run simplifies the affected code before patching and weighs deletion for each open fix.
  Every confirmed fix, including bot findings, starts with a failing regression test. The
  report and PR body name any fix without one and explain why.
  Once the diff settles, a last pass builds the change and drives it at its own surface.
- **Review bots.** After the PR opens, the run waits up to 20 minutes for CodeRabbit and, on
  standard and complex runs, asks Codex for a review with `@codex review`. It works out who is
  reviewing from what shows up on the PR, so a repo without bots costs about four minutes. Each
  thread a bot opens is checked like any other review finding: fixed, re-gated and answered with
  the commit, or answered with the reason it was rejected. A CodeRabbit rate limit goes into the
  summary; asking it again is your call.
- **Commit contents.** Each commit passes an index audit against an explicit file list. The
  report and PR body show file groups, counts, indexed sizes and reasons for flagged files.
  Unexplained flagged files are unstaged before the run stops; working files stay on disk.
- **Beyond a single issue.** A plain request with no number is drafted into an issue and run.
- **A careful merge gate.** Merge happens only on your explicit in-session approval, never on
  the turn the PR opens. The merge script refuses a head the gates never ran against, a review
  requesting changes, an unresolved review thread from anyone and a CodeRabbit review still in
  progress, and passes `--match-head-commit`, so a commit landing after the diff you
  were shown stops the merge rather than shipping unseen. If GitHub refuses the merge, its own
  message is reported and the run says what to do next.
- **Cleanup and a safety net.** Once the PR is merged it deletes the branch, tears down the
  worktree, and clears the run's files; a merge into anything but the default branch is reported
  as one, since GitHub only closes the issue on the default. An optional smoke check runs on the
  updated base; if it fails, the skill opens a *draft* revert PR, never an automatic rollback.
- **Board sync, gracefully.** Cards advance to *in-progress* at branch cut and *in-review*
  at PR open; `Done` is left to GitHub's merge-time automation. A missing `project` token
  scope degrades to link-only and never blocks the PR.

### Skill: `setup`

Run once before your first task. It checks the shell, Git and GitHub access (`repo`, plus
`project` for board mode), then reports the current host's available capabilities and fallbacks.
It diagnoses setup without changing it. Optional companion installation instructions are
provided on request, for the host you are actually using.

### Configuration (optional)

`.claude/issue-to-pr/config.md` (YAML frontmatter) sets the board URL, base branch, and
typecheck/test/visual/smoke commands. Everything is optional; with no file the run works the
commands out in the worktree where the gates execute, as literals, and prints the block to
paste here once they pass. It never writes this file itself. Two keys serve `--headless` runs
only: a diff touching `human_paths` never merges unattended (glob syntax in
`skills/run/references/configuration.md`); `after_merge` is the instruction the run gives itself
after cleanup, usually a deploy skill.

Claude Code and Codex use this same config and state directory; the `.claude` name is retained
for compatibility. There is no separate Codex config to keep in sync.

That directory holds the plugin's state: the config, and one folder per branch with its gate
receipt and gate logs. It ships its own `.gitignore` containing `*`, so none of it reaches
`git status` and your project's `.gitignore` is left alone. Runs keep their state in the main
checkout, never in the worktree, so tearing the worktree down can never trip over it.

Being ignored, the directory is disposable to `git clean -x`. Nothing breaks permanently: the
commands get worked out again, and the next merge asks for one more gate run before it lands.

### Staging review

The run records expected files before implementation in `planned-paths.txt` under its run
directory. This is a plain list of exact repository-relative paths, one per line; LF and CRLF
line endings are accepted. It supplies
the files to commit separately as literal arguments after `--`; directories and traversal are
refused. Paths may contain spaces, leading dashes or glob characters, but not CR, LF or tabs.
Renames declare both the deleted path and the added path.
Directory symlinks stage the link itself as a file.

`stage.sh review --plan <file> --reasons <file> -- <paths...>` stages each declared file in full.
`stage.sh commit --plan <file> --reasons <file> --message '<subject>' -- <paths...>` checks the
current index and commits without staging again. Undeclared staged files stop both commands
without changing those entries. Both commands require the declared set to match the staged
changed-path set. Commit hooks run normally; if a hook changes the commit tree, the script
stops before the run pushes it.

Each file has one primary group: source, tests, fixtures/snapshots, generated, binaries,
lockfiles or config. Classification uses path conventions, known binary suffixes, Git's
binary-change detection and a NUL-byte check on indexed blobs that diff attributes cannot
disable. Binary snapshots stay in fixtures/snapshots. Binary and new-file
totals are overlapping indicators; the unique-file total counts each file once. Sizes describe
indexed objects, with zero bytes for deleted files.
Deleted files retain binary classification from their previous contents.

Flags cover unplanned files, binaries, generated output, common do-not-commit paths (`*.log`,
`.env*`, `dist/`, `node_modules/`, `.claude/`, `test-results/`) and every member of a primary
group above 10 MiB. Reasons are exact `path<TAB>one-line explanation` rows in a TSV file; omit
`--reasons` when none are needed. A missing reason unstages that flagged path and stops with
exit 2. Generated issue-to-pr run state cannot be committed, even with a reason.
Policy patterns ignore case so Windows path variants cannot bypass these checks.
The Markdown inventory is saved as `staging-report.md` in the run directory for the PR and report.

### Review bots (optional)

The plugin can't see which GitHub apps a repo has installed, so there is nothing to configure
here. Two settings on the apps' side make the wait worth it:

- CodeRabbit's free plan only summarizes PRs on private repositories and reviews code on public
  ones, so install it on public repositories only (GitHub → Settings → Applications → CodeRabbit
  → Configure → Only select repositories).
- In Codex settings, turn on Code review for the repositories you want and leave Automatic
  reviews off. The run asks for a review itself on standard and complex tiers, so trivial changes
  don't spend the quota.

### Companion skills (optional)

The host supplies the tools; the plugin defines the checks. Review, simplification and runtime
verification apply on both hosts, whether performed through an available skill or directly.
Complex designs use three independent proposals and a parent judge when subagents are available;
otherwise the agent works through those perspectives sequentially and reports that limitation.
No hook or companion plugin is required. See the shared
[capability and fallback table](skills/run/references/companions.md).

## Usage

The skill activates when you ask to pick up a task ("take task 4", "work on issue #7") or
when you describe work that has no issue yet ("fix the flaky login test"). Or via the slash command:

```text
/issue-to-pr:run 4

/issue-to-pr:run "add dark mode to the settings page" --tier standard
```

In Codex, select `issue-to-pr:run` or `issue-to-pr:setup` from the skill picker; CLI/IDE users
can type `$` to select a skill. Pass the issue number and the same flags as above. A request
such as "Use issue-to-pr to work on issue #4" also identifies the plugin and task.

## Behavioral evals

The three starter cases in `evals/` check task activation, an unrelated code explanation,
and the merge decision after a PR report. They grade decisions with read-only tools;
they do not execute GitHub actions. The merge case resumes a synthetic conversation,
so it checks the next turn and the model's explanation of the earlier turn's restriction.
It does not execute the PR-opening turn. Script execution has separate contract tests.

### Codex

Run the same case prompts and result rubrics with Python 3.9+ and an authenticated
Codex CLI. Start with one repetition per arm:

```bash
python plugins/issue-to-pr/evals/run-codex.py --model gpt-6.1-sol --runs 1
```

For acceptance, use three repetitions per arm:

```bash
python plugins/issue-to-pr/evals/run-codex.py --model gpt-6.1-sol --runs 3
```

The adapter starts fresh Codex sessions with and without the native `run` skill,
checks the model-visible catalog, and disables other skills, plugins, repository
instructions, memory, apps, and browser access. It copies only file-backed Codex
authentication into a temporary home and removes that home after each session.
Credentials never enter the result directory. It keeps prompts, traces, answers,
grader verdicts, model ID, and CLI version under the ignored `evals/results/`.

A PreToolUse hook permits exact reads of the copied skill and reference files.
Other tool calls are denied before execution and count as a case failure. The
adapter trusts only its own audited hook for each invocation. On Windows it uses
Full Access behind that guard because restricted profiles can reject the skill
read itself; on other systems it requests read-only. This is a guarded local
evaluation, not a container or an OS isolation boundary. Run the adapter only
from a checkout you trust.

Native successful reads supply the activation indicator; a statement that the
model used the skill is insufficient. Outcome scores exclude positive activation,
while the no-trigger activation check scores both arms. Semantic graders run in
fresh Codex judge sessions with structured boolean-and-reason output. The Codex
adapter uses one judge verdict per semantic check; it does not reproduce Claude
Code's judge voting. Timeouts, CLI errors, missing completion, and judge failures
produce partial results and a nonzero exit. A denied action scores zero while the
suite continues to the other cases.

The merge fixture is supplied as quoted conversation context on Codex. This checks
the decision from that context, not native session resume. Require all three
with-arm scores at 1.0, all trigger activation indicators passing, a complete
report, and a positive trigger outcome delta. A one-repetition run is a smoke
check; the three-repetition run is the acceptance evidence. The maximum is 18
agent sessions plus 18 judge sessions, each limited to 120 seconds. Calls use the
current Codex account; this adapter has no monetary cost ceiling.

See [Codex skills](https://learn.chatgpt.com/docs/build-skills),
[JSON execution events](https://learn.chatgpt.com/docs/non-interactive-mode), and
[tool hooks](https://learn.chatgpt.com/docs/hooks) for the native interfaces.

### Claude Code (optional adapter)

Use Claude Code 2.1.269 or newer with `claude plugin eval` available and credentials
authorized for this repository. From the repository root, iterate on one case:

```bash
claude plugin eval plugins/issue-to-pr --case trigger --runs 1 --ablation none \
  --model claude-sonnet-5 --judge-model claude-haiku-4-5 \
  --threshold 1 --max-cost-usd 2 --no-publish --trust-plugin
```

After changing the skill's description or instructions, compare all three cases at
three runs per arm (18 agent runs, plus judge calls):

```bash
claude plugin eval plugins/issue-to-pr --runs 3 --ablation with-without -j 4 \
  --model claude-sonnet-5 --judge-model claude-haiku-4-5 \
  --threshold 1 --max-cost-usd 5 --no-publish --trust-plugin
```

The named models keep the agent and judge choices explicit. Record their IDs and the
Claude Code version with each result. `--trust-plugin` accepts this plugin's code and
suite; use it only for a checkout you trust. These commands grant no Bash, write tools,
scaffolding, or real MCP servers. `--no-publish` keeps reports local, and Git ignores
`evals/results/`. The cost ceiling uses list-price estimates and can overrun by the
runs already in flight, up to four in the full command.

Read `aggregate-result.json` and `report.html` in the resulting `evals/results/`
directory. Require a complete run, no run errors, aborts, or skipped paid graders,
all three with-arm scores at 1.0, and a passing Skill indicator for each trigger run. Record the trigger
case's positive with-minus-without delta in the PR; a zero delta does not meet that
acceptance condition. Skill invocation is an unscored indicator in the two-arm run,
so the trigger also grades the auth-first result. The no-trigger Skill check uses
`arm: both` so accidental activation affects the score. Explicit `with-without`
also includes the history case's baseline, which a path target otherwise omits.

See the [Claude Code eval reference](https://code.claude.com/docs/en/plugin-evals)
for the case format and scoring rules. The remaining cases and paid CI wait until
the starter report shows a useful signal. Claude-native loader and judge checks
are separate adapter evidence; they do not block Codex acceptance.

## License

MIT
