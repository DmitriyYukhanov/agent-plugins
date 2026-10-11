# Changelog

All notable changes to the **issue-to-pr** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [9.10.0] - 2026-10-09

### Fixed
- Use the originating issue number when merging and cleaning up an approved PR.

## [9.9.0] - 2026-10-07

### Added
- Record completed headless runs and restart reopened issues only after a fresh owner queue.

## [9.8.0] - 2026-10-06

### Changed
- Simplify code before further fixes when review bug counts stop falling, and weigh deleting the affected feature.
- Start every confirmed review fix with a failing regression test and report any missing coverage.

## [9.7.0] - 2026-10-04

### Added
- Review each commit's file groups, sizes and flagged-file explanations before committing, and include them in the PR and report.

## [9.6.0] - 2026-10-04

### Fixed
- Keep generated plans and run state out of Git from the first write, including in worktrees.
- Preserve tracked run files during setup and cleanup, and report them for targeted index cleanup.
- Refuse state paths that redirect writes or cleanup through symbolic links.

## [9.5.3] - 2026-10-01

### Fixed
- Preserve quotes and substitutions in configured gate commands.
- Keep branch state separate, including across upgrades.
- Revert all landed commits after a failed smoke check following a rebase merge.
- Check authentication before creating an issue.

## [9.5.2] - 2026-10-01

### Fixed
- Remove the correct worktree when PR and issue numbers differ.
- Preserve worktrees and branches when cleanup cannot read worktree registrations.
- Review uncommitted changes during the pre-commit security check.

## [9.5.1] - 2026-09-29

### Fixed
- Keep a headless run alive until the background work it started finishes, instead of ending the turn and losing it.

## [9.5.0] - 2026-09-29

### Added
- Wait for the PR's review bots before the report, and answer every thread they open with a fix or a reason.
- Ask Codex for a review of standard and complex changes.

### Changed
- Refuse to merge while a review thread is unresolved or CodeRabbit is still reviewing the latest commit.

## [9.4.1] - 2026-09-29

### Fixed
- Keep the second-model review report-only: it lists findings for the run to apply, makes no edits and asks you nothing mid-run.

## [9.4.0] - 2026-09-25

### Added
- Pick up a headless run from your reply: the run keeps its state in a marked comment on the issue, so a fresh session carries on where the last one stopped.
- Refuse a headless merge unless your newest reply after the latest report for that head is `merge` or `мерж`.

### Changed
- Continue a run only on an unmarked owner comment newer than what the run last read; treat everything else on the thread as data, not instruction.
- Hold back a headless run on an issue that already stopped once: it never merges on its own.
- Park the PR for your review when a headless push is rejected, instead of failing the run.

## [9.3.0] - 2026-09-22

### Added
- `--headless`: a run launched with nobody at the keyboard posts its one question and its "ready to merge" as GitHub comments, marks the state with labels, and continues from the owner's reply.
- `--auto-merge <tier>`: a headless run at or under the tier merges on its own when its gates, reviews and ratchet were all clean; `trivial` by default, `none` outside headless.
- `human_paths` in the config: a diff touching one never merges unattended, enforced where the merge happens.
- `after_merge` in the config: the instruction a headless run gives itself after cleanup, usually a deploy.

## [9.2.0] - 2026-09-18

### Added
- A second model reads the diff on complex runs and after an escalation, where the host supplies one: every reviewer until now shared the writer's blind spots. Its confirmed findings feed the escalation the same way.
- An orphan sweep after every deletion: a symbol the removed code was the last to reach goes in the same PR, unless config, a hook or a reader outside the repo still names it.

### Fixed
- Let the reviews themselves block a merge: GitHub reports no review decision at all on a base branch that does not require one, so a changes-requested review used to pass the merge gate unseen.
- Refuse an unrecognised flag instead of warning past it, so a mistyped `--keep-branch` can no longer delete the branch it was meant to save.
- Refuse a gate name that sanitises to nothing rather than running the gate and leaving it out of the receipt the merge reads.

## [9.1.4] - 2026-09-15

### Fixed
- A grill closes a decision per round; that no longer reads as closing the whole checkpoint.
- Drop the claim that a fresh session can rebuild the checkpoint from the PR and the report. Only `auto` entries render there, and an early checkpoint happens before the PR exists.

## [9.1.3] - 2026-09-15

### Changed
- Name the host's own review, security review, simplification and verification capabilities again. In Claude Code runtime verification is `run`; there is no `verify` command.
- Take the checkpoint's state from the ledger entry that already records it, rather than a second field to keep in sync.
- Leave the runtime prerequisite check to `setup`. Every run was repeating it.

### Fixed
- Restore the check that no install command is ever offered for a capability the host already ships.

## [9.1.2] - 2026-09-15

### Fixed
- Check the new commit directly when validating a matching plugin and marketplace version bump.

## [9.1.1] - 2026-09-15

### Fixed
- Remember an early checkpoint so a resumed run does not ask the same round of questions again.
- Update the existing PR after new commits instead of trying to create it again.
- Disclose all changes made after the last review, including fixes found during runtime verification.
- Refuse cleanup when the issue worktree is on another branch or a detached head.

## [9.1.0] - 2026-09-14

### Added
- Run the same issue-to-PR workflow in Claude Code and Codex, with global Codex installation instructions.

### Changed
- Use each agent's available tools for research, review and verification while keeping the same quality and merge gates.
- Check Git Bash on Windows and preserve the active Ponytail level without relying on agent hooks.

### Fixed
- Refuse to reuse another task's worktree or switch a dirty or occupied main checkout.
- Restart review and verification when new commits arrive after the PR was reported.

## [9.0.0] - 2026-09-08

### Changed
- Keep bash only where the action cannot be undone: two scripts, one that runs the gates and writes the receipt, one that merges and cleans up
- Pass each gate as its own argument, `gates.sh test "npm test"`, instead of a packed `name=cmd` value that needed four guards of its own
- Create the worktree with a plain `git worktree add` from the instructions rather than a script with three states
- Squash-merge, and on a refusal report GitHub's own message with the next move, instead of classifying the refusal and retrying by rung; `--method merge|rebase` is the retry, and nothing else reaches gh as a flag
- Refuse to merge on a receipt that never ran the test gate, whatever else it covers
- Raise the review level once after a pass confirms two real bugs; the tier's pass cap is the cap

### Removed
- Drop the merge-guard hook: the rules against `--admin` and a bare force-push are instructions now
- Drop the merge's review-thread query, mergeability pre-check and behind-base auto-update; a merge that does not happen needs no machinery
- Drop the scripts' contract reference and the merge ladder; each script says what it refuses in the stop itself
- Drop the guard against two gate names that shorten to one output key; a red gate now exits 1 and reports the gate's own code alongside

## [8.0.0] - 2026-09-07

### Changed
- Keep everything a run owns - gate receipt, gate logs, design - in one directory in the main checkout that the scripts create, find and delete by themselves
- Put each merge stop's instruction in the stop itself, where the run reads it, instead of in a reference that had drifted from it twice
- Clean up after a merge into any base, and report which branch it landed on rather than refusing to tidy up

### Removed
- Remove `--log-dir` from the gate runner and `--ladder-attempt` from the merge: two values a run had to carry between shells, neither of which it can get wrong now
- Drop the merge's issue-state and PR-URL output and each gate's elapsed time, which nothing read

### Fixed
- Refuse a gate call whose value a quote of its own split apart, and one the caller single-quoted, named, positional or special, instead of running what is left or nothing at all and reporting it green
- Stop writing run state into the worktree, which left an untracked `.claude/` that made cleanup half-succeed: remote branch gone, worktree and local branch still there
- Fail closed on the merge gate's unreadable reads, the review threads and the PR's mergeable state, rather than treating either as an all-clear, and on a PR carrying more review threads than the one page the query asks for
- Refuse a receipt that only covers the post-merge smoke run, which a stacked PR's base would otherwise collect as proof its own gates had passed
- Read review threads in repositories whose owner or name is all digits, which the query used to reject outright
- Refuse to build a fresh worktree for a branch whose PR has already merged, and ask GitHub for merged pull requests when checking, which its default listing never returns
- Refuse two gate names that shorten to the same output key, and gates on a detached checkout, whose receipt the merge could never find
- Say so when green gates leave no receipt behind, instead of reporting a pass the merge will then refuse
- Stop reading a `<<` inside a quoted string as a heredoc, which let a `gh pr merge --admin` on the next line past the guard as if it were message text
- Tell an unreadable pull-request listing apart from a branch that simply has no PR, instead of taking silence for the second
- Give every branch its own run directory, so two names differing only by a slash can no longer share the one cleanup deletes
- Say that the merge prefers a squash and falls back to whatever else the repository allows, which the plugin's own descriptions had been promising away
- Name no worktree path on a failure that never built one

## [7.0.0] - 2026-09-05

### Changed
- Fold the twelve steps into the ten the plugin exists to run: research happens inside the design, and everything between the code and the commit is one hardening step
- Cut what a run reads before it can start from 396 lines to 314, keeping each fact only where the run has to act on it
- Ask one page how deep a run should go and what it may decide alone, instead of two
- Say why a check exists in the message it prints when it fails, rather than in a comment only a reader of the file would find

### Removed
- Remove the config's nested `commands:` alias for the `*_cmd` fields; a run that meets one now says so instead of quietly working the commands out again
- Stop mentioning the pre-2.5 config path, four majors after anything read it

### Fixed
- Say plainly that the merge guard denies `gh pr merge --admin` and nothing else, so nobody infers a plain merge is covered
- Pull the updated head before re-gating a PR that was behind its base, which the recovery had stopped saying and without which it never finishes
- Pass every gate command the quote-safe way, so an apostrophe in a configured test or smoke command can no longer truncate it while the gate still reports green
- Revert what actually landed when a post-merge smoke fails: one commit for a squash, the merge commit for a merge, and the whole replayed range for a rebase
- Fetch the default branch as well as the base, which the in-place fallback needs and only the base was getting

## [6.1.1] - 2026-09-02

### Fixed
- Name every companion by its full invocation path, so the docs say what to type rather than only what the capability is called
- Both READMEs now list `ponytail:ponytail`, which the run sets before the design and neither mentioned

## [6.1.0] - 2026-09-02

### Changed
- Cut the instructions an agent reads before it can start from 382 lines to 361, dropping justification that had outgrown the rules it explained

### Removed
- Remove the friction log, which nothing has read since the `tune` skill went away

## [6.0.0] - 2026-08-31

### Added
- Drive the built change at its own surface after the diff settles, so a PR has to do what it says and not only keep the tests green

### Changed
- Replace `--drill` with `--grill`, which interviews you over the design in rounds instead of teaching you one already made, and spends the checkpoint rather than adding a fourth interruption

### Removed
- Remove the `drill-me` marketplace from the setup skill's install table

## [5.3.0] - 2026-08-30

### Fixed
- Stop promising cleanup and the issue's auto-close unconditionally in the plugin's description; both wait for a merge into the default branch

### Changed
- Say in the report when a review pass ran out with fixes still unread, instead of arriving at the merge gate as though everything had been reviewed

## [5.2.0] - 2026-08-30

### Added
- Check an external claim before building on it, at every tier, and record what settled it in the PR body

## [5.1.0] - 2026-08-29

### Fixed
- Stop presenting `deep-research` as something to install or to route Step 2 through: Claude Code ships it and only starts it when you type it yourself, so Step 2 always uses its own research subagent

## [5.0.0] - 2026-08-28

### Removed
- Remove epic mode: no run ever used it, and a request too large for one PR now gets split into issues by hand
- Remove `/issue-to-pr:tune`: it never finished a pass, and the friction log it was meant to batch gets read directly
- Remove the staging hook that denied `git add -A` in every project: the artifacts it named are already covered by `.gitignore`, and the rule stays where it belongs, in the pipeline's own instructions
- Remove `state.json`, `step.log`, and the resume path built on them: nothing read them back, and the last two real runs never wrote them
- Remove `changed-paths.sh`, `--salvage-to`, and `worktree.sh teardown`, which is now `cleanup --keep-branch`
- Stop guessing the install command from a lockfile: Step 1 works it out in the worktree it is standing in, the way it already works out the gate commands
- Author both design workflows inline instead of shipping them as files, which drops the argument channel that kept failing along with the guards written against it
- Remove the board's `next` entry and its draft-card conversion: both were advertised in the skill with nothing behind them
- Remove `worktree.sh revert`: opening a draft revert PR is four ordinary git and gh commands, and four of its five failure branches had never been exercised by a test
- Replace `preflight.sh` and `board-sync.sh` with instructions the run follows itself: neither made a promise only a script can keep, and reading a config or calling three GraphQL queries is not worth a shell that has to hand-roll YAML and dodge jq's TSV encoder

### Fixed
- Close three bypasses in the merge guard, all the same shape: anything sitting between the words defeated the matcher, so a quoted subcommand, `gh pr --repo o/r merge --admin` and `git -C . push --force` each walked straight past it
- Refuse to delete a branch that another open PR is based on, and stop rather than guess when that cannot be read
- Report which branch a merge landed in, and say `unknown` rather than claim success when the answer cannot be read
- Carry `--match-head-commit` on the merge retry after pending checks, so a commit landing in that window can no longer slip in unseen
- Fail the test run when a test file cannot be parsed; one unbalanced quote used to drop 42 tests while the suite printed ALL GREEN
- Make the heredoc test see the defeat it exists to prevent: the guard used to let a forbidden command through while every test stayed green
- Test `merge-guard.sh`, which shipped untested from the first release and is the one script whose failure says nothing
- Cover the eight failure branches that had no test: an unrecognised `gh pr merge` failure used to report a merge that never happened, an unclassified `git worktree add` failure passed silently, an unwritable log directory ran the gates with nowhere to record them, and a board with no Status field was reported as a board with no matching column; the four argument and environment degrades in `worktree.sh` had none either
- Document the failure text the scripts hand back on a stop, which was emitted and described nowhere
- Hand a gate command that carries a quote of its own to the runner intact, instead of letting it close the wrapper the command template puts around it
- Stop the escalation ratchet sending a trivial run back to a design step the tier matrix never gave it
- Say plainly in both READMEs and the marketplace listing that cleanup and the issue's auto-close follow only a merge into the default branch
- Correct three documents that described the opposite of the code: how `base_branch: auto` picks a branch, what the merge ladder does on a behind-base PR and after a rejected push, and what Step 0 still reports

### Changed
- Cut the per-command cost of the safety hook by an order of magnitude, which every session pays on every shell command
- Fold triage into the worktree step and the report into the PR step, two steps fewer to follow
- Run preflight's claim on every run, and report the warnings it hands back instead of dropping them
- Cut the tier matrix to the rows that route a decision; the rest repeated the step they routed
- Drop the design panel's two adversarial critics: `/cross-review` reads the same design with a different model
- Stop pinning the spine's exact wording in tests, which went red on rewrites that changed no meaning
- Check the spine against the scripts that actually ship, so a deleted script and a forgotten call stop looking the same to the test
- Let `git push --force-with-lease` through the safety hook without a confirmation: it refuses when the remote has moved, so the thing the rule guards against cannot happen
- Move the postmortems out of the prose: the reference files carry the rule, this changelog carries the story

## [4.4.0] - 2026-08-25

### Added
- Add `/issue-to-pr:setup`, which checks what the pipeline needs, says what each missing companion would sharpen, and hands you the install commands to run yourself

## [4.3.0] - 2026-08-25

### Added
- Add `--drill`, which hands the design to the drill tutor before anything gets built, for runs where you would rather understand the plan than save the time

## [4.2.0] - 2026-08-25

### Changed
- Run the pre-PR gate as two lenses over two passes, deletion and simplification, so a cut that broke something gets caught by the next pass instead of by nobody

### Fixed
- Review the diff with the reviewer Claude Code ships rather than an inline stand-in; the pipeline had been avoiding it over a caveat that only applies to plugin commands of the same name

## [4.1.0] - 2026-08-25

### Changed
- Set ponytail's lazy mode before the design instead of after the code, so it prevents over-engineering rather than reporting it

### Fixed
- Point the final over-engineering review at the work in progress; it was diffing two commits and seeing nothing

## [4.0.0] - 2026-08-22

### Changed
- The main skill answers to `/issue-to-pr:run`, which is shorter to type and no longer loses the completion race to `/issue-to-pr:tune`

## [3.1.0] - 2026-08-22

### Changed
- A run keeps its design, notes, state and gate logs beside the plugin's other state instead of inside your project tree, where test discovery and bundlers were picking them up

## [3.0.1] - 2026-08-22

### Fixed
- Cleanup now removes the branch's gate receipt, so the plugin's state directory stops growing after every merge

## [3.0.0] - 2026-08-21

### Removed
- The approval marker and `approve.sh`. A merge no longer needs a file written first; the go-ahead you give in the session is the gate, and it never proved more than that anyway

### Changed
- The merge binds to the head you were shown with GitHub's own `--match-head-commit`, so a commit landing after your go-ahead stops the merge instead of shipping unseen
- The hook is down to what a hook can enforce: `gh pr merge --admin` denied, force-push asked about

## [2.11.0] - 2026-08-21

### Added
- The merge now refuses a head no green gate run covers, so "tests green" is checked rather than remembered

### Changed
- The merge reads the GitHub review itself and fails closed: an unreadable review state stops the merge instead of passing as clear
- Say plainly what the approval marker proves: freshness, single use and a head-SHA binding, not that a human agreed

## [2.10.0] - 2026-08-21

### Removed
- Writing gate commands into the project's config. A run that worked commands out now prints the block for you to paste, instead of appending to a file your team may have committed

## [2.9.0] - 2026-08-21

### Changed
- The security overlay now reads the diff and decides for itself whether a change touches auth, crypto, secrets, sessions, payments or migrations, over a floor of paths it can never argue down
- `sensitive-paths.sh` is now `changed-paths.sh` and only lists what the branch touched

## [2.8.0] - 2026-08-21

### Changed
- Gate commands now come from the config or from the run itself at Step 6, worked out in the worktree the gates execute in and always as a literal command

### Removed
- Gate-command detection from `preflight.sh`, roughly 90 lines of shell that guessed a command from a tree the gates never run in

## [2.7.0] - 2026-08-21

### Added
- A final over-engineering pass with ponytail before the PR opens, when that plugin is installed

### Removed
- The tier classifier scripts: a run now reads the issue and picks the tier itself, defaulting to `standard`

## [2.6.1] - 2026-08-20

### Changed
- Propose the cheapest fix first when tuning friction: deletion, explicit input, or clearer wording before another script or test

## [2.5.1] - 2026-08-20

### Changed
- Keep the plugin's repository-level state in `.claude/issue-to-pr/`, a directory that hides itself from git, so a teammate without the plugin installed never finds files they cannot place
- Read the config from `.claude/issue-to-pr/config.md`

### Removed
- Support for a config at the older `.claude/issue-to-pr.local.md` path. A run points at it once and leaves it alone, rather than copying it somewhere and deciding which copy wins

### Added
- Clear away approval markers once they expire, and never one whose timestamp cannot be read

## [2.4.1] - 2026-08-18

### Added
- Detect a test runner that lives inside a project, when the repository has exactly one tracked runner and none at the top
- Leave two or more runners ambiguous and report no test command, so the one you want gets pinned in the config ([#23](https://github.com/DmitriyYukhanov/claude-plugins/issues/23))

### Fixed
- Resolve every Step-0 probe against the repository, so gate detection no longer depends on the directory you start the run from
- Find the pinned config from anywhere in the repository; a run started from a subdirectory used to miss it and replace your pinned test command, base branch and board with guesses
- Report `make check` for a `check:`-only Makefile, instead of a `make typecheck` that no rule defines and that stopped the run on a red gate

## [2.3.2] - 2026-08-17

### Fixed
- The documented salvage list names the files cleanup actually copies
- A PR number now works wherever a branch name does: the merge finds the approval recorded under the branch name instead of refusing it, and cleanup deletes the branch instead of reporting success and leaving it behind
- A relative `--salvage-to` path lands in the main checkout, not inside the worktree that cleanup is about to remove
- Cleanup reports what it salvaged even when it then refuses to remove a worktree with uncommitted changes

## [2.3.0] - 2026-08-16

### Removed
- The `--json` flag on the pipeline's scripts. Nothing ever passed it; board sync still reports JSON exactly as before
- The bundled `research` sub-skill. That step now uses `/deep-research` when it is installed and a plain Explore subagent otherwise, which is what the sub-skill was configured to do anyway

### Changed
- Dead code and stale comments swept out of the scripts and the reference docs: a documented helper that was never written, a header printed twice, a note describing run-directory behaviour this version does not have, and a board-sync flag whose feature shipped elsewhere

## [2.2.1] - 2026-08-15

### Fixed
- Two shellcheck warnings that turned the release build red; no change to how the pipeline behaves

## [2.2.0] - 2026-08-15

### Added
- The security overlay reads uncommitted edits to tracked files as well as new untracked ones, so a change to an existing auth or crypto file triggers the extra review pass
- The overlay also flags Alembic, Flyway, Liquibase and `db/migrate` migration layouts
- Test-command detection covers shell harnesses such as `tests/run-tests.sh`

### Changed
- `base_branch: auto` asks the remote instead of trusting local refs, so a stale `dev` whose remote was deleted no longer becomes the branch point, and `BASE_SOURCE` reports whether the answer was confirmed or guessed
- The security overlay is one call that collects the changed files itself, rather than a shell pipeline the pipeline had to assemble by hand
- The design panel refuses to run when its inputs fail to arrive, and reports which issue it received so the caller can prove it
- Review subagents run in the foreground and never alongside the gates, which used to produce phantom failures
- Cleanup no longer invents a salvage directory on every run; it keeps a run's scratch files only when you name somewhere to put them

### Fixed
- The post-merge smoke check actually runs. It was called without the log directory the gate runner requires, and after cleanup had already removed it, so a merge that broke the base was never caught and the draft revert PR never opened
- The security overlay stops with a reason when it cannot read the diff, instead of reporting a clean scan and skipping the security review
- Installing dependencies at Step 1 no longer omits the log directory the gate runner requires
- Approvals work on macOS: the timestamp check only understood GNU `date`, so every marker was undatable and no merge could ever be approved
- An approval is spent only once the merge has actually run, and never silently when the write fails
- The merge gate's refusal explains that approval and merge must be separate calls, since chaining them could never pass
- The approval quote survives embedded quotes, backslashes and line breaks

### Security
- `worktree.sh` could be made to remove arbitrary directories, including the repository's own `.git`, by an issue argument containing `..`. Every script now rejects a non-numeric issue before building a path from it

## [2.1.0] - 2026-07-22

### Changed
- Step 7's review loop now defaults straight to adversarial review subagents instead of first attempting `/code-review`, since most copies of that command block model-invocation and can never fire mid-pipeline anyway

## [2.0.3] - 2026-07-21

### Fixed
- The merge and stage guards now ignore heredoc bodies, so a commit message that merely quotes `gh pr merge` or `git add -A` in prose no longer trips the gate it's describing

## [2.0.2] - 2026-07-13

### Changed
- Expand the plugin README to cover v2 behavior: tiers, autonomy contract, epic decomposition, the merge gate, post-merge smoke check with draft revert, and the `/issue-to-pr:tune` skill

### Fixed
- Correct install command to use the marketplace name (`@dmitriy-claude-plugins`) instead of the repo path

## [2.0.1] - 2026-07-11

### Fixed
- The merge-approval marker now resolves a PR number to its branch name, so `gh pr merge <PR#>` and `approve.sh <PR#>` key the same approval as their branch-name equivalents instead of silently missing each other
- Merge-gate denial messages now name the plugin and give the exact `approve.sh` command to run, so the model can't mistake the gate for a GitHub restriction or lose time hunting for the script

## [2.0.0] - 2026-07-07

### Added
- Epic tier — decompose a from-scratch request into dependency-ordered child issues, each shipped through its own gated pipeline, gated on one approval of the breakdown
- Start from a plain request with no issue number: the pipeline drafts the issue and proceeds, asking only when the scope is ambiguous
- Merge-failure ladder — a behind-base PR is updated, re-checked, and re-approved automatically only when the base merge leaves the PR's own diff untouched; a conflict or a failed check stops and hands back
- GitHub review ingestion — a changes-requested review or an unresolved thread routes through the change-request path instead of a silent merge
- Post-merge smoke check that opens a draft revert PR (never auto-reverts) when the merged change breaks the base

### Changed
- Major release: the pipeline now accepts free-text and epic entry points alongside a single issue number, and the merge gate gained the failure ladder and review ingestion

## [1.3.0] - 2026-07-06

### Added
- Tier scaling — the pipeline sizes research, design, review depth, and the report to the task's tier (trivial through epic), chosen deterministically from the issue's signals
- Ask contract — at most one batched question per run; every other decision is made autonomously and surfaced in the report and the PR body
- Autonomous design panel (three proposers, two adversarial critics, a judge) replaces the one-question-at-a-time brainstorming interview for complex work
- Forked research that keeps raw exploration out of context, plus a security-review overlay that triggers on sensitive paths
- Self-writing config that pins verified gate commands, and a `/issue-to-pr:tune` skill that turns a friction log into batched improvements
- A hook that denies `git add -A` / `.`, keeping staging explicit

### Changed
- SKILL trimmed to a lean ~140-line spine now that tested scripts own the mechanics; per-task state enables deterministic resume after a context compaction

## [1.2.1] - 2026-07-04

### Fixed
- Post-merge cleanup no longer stalls on Windows and leaves the merged branch behind

## [1.2.0] - 2026-07-03

### Added
- Enforced merge gate — a hook allows a merge only with a fresh, single-use, head-matching in-session approval, always denies `gh pr merge --admin` protection bypass, and asks before a force-push
- Contract-tested bash scripts run the pipeline's git/gh mechanics, with a fake-gh test harness verified under Git Bash on Windows and in CI on Linux and Windows

### Changed
- Preflight, worktree, gate, board-sync, and triage mechanics moved from prose into deterministic scripts sharing one exit-code contract — same pipeline behavior, mechanically enforced gates

## [1.1.0] - 2026-07-03

### Added
- Worktree isolation — each run works in its own `../<repo>-worktrees/issue-<N>` git worktree, so concurrent local agents on different issues never clash
- Approval-gated merge — after you approve the PR in-session, the skill squash-merges and tears down the branch, worktree, and temp artifacts

## [1.0.0] - 2026-06-26

### Added
- `issue-to-pr` skill — one gated pipeline that drives a single GitHub issue from triage to a merge-ready PR (design cross-review, tests green, code-review loop)
- Unified input handling — a bare issue or a Project board card runs the same pipeline; the PR always links the issue to auto-close on merge
- Board-status sync — advances a Projects (v2) card to in-progress when work starts and to in-review when the PR opens, degrading to link-only when the `project` token scope is absent
- Optional `.claude/issue-to-pr.local.md` configuration for board URL, base branch, and typecheck/test/visual commands, with auto-detection when unset
- Graceful companion-skill integration — uses Superpowers, deep-research, cross-review, humanizer, and code-review when installed, with inline fallbacks when they are not
