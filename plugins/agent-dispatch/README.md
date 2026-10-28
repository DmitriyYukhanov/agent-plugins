# agent-dispatch

Label a GitHub issue `agent` and your own machine picks it up. A tick every three minutes runs
`/issue-to-pr:run N --headless` under your own Claude Code or Codex login; the run's question and
its "ready to merge" arrive as comments on the issue, and your reply there, or on the PR, starts
the next run. Windows, macOS and Linux.

## How it works

Each tick starts at most one run:

1. **Replies first.** An issue waiting on you (`agent:waiting` or `agent:review`) with a new
   comment of yours since the run parked.
2. **Then the queue.** The oldest open issue labelled `agent` by you, oldest first within a repo;
   repos are tried in the order `repos.conf` lists them.

The tick sets `agent:running`, starts the run and waits for it. The run itself parks the issue at
`agent:waiting` (it has a question), `agent:review` (a PR waits for your `merge`), or closes it by
merging. A run that ends without doing either is marked `agent:failed` with a comment pointing at
its log on your machine; the log itself never leaves it.

Only you count: an `agent` label someone else applied, or a comment someone else wrote, starts
nothing. The same goes for edits: if someone else changes the title or body after you label the
issue `agent`, it waits until you label it `agent` again, even if a run has parked it since.
Everything is posted from your own GitHub account, so GitHub will not notify you about it. When a
run asks you something, waits for your `merge`, or fails, the tick runs `~/.agent-dispatch/notify.sh`
if it exists. You choose where that script sends the message. Setup shows an example for ntfy and
a command to test it.

An optional [trusted SEO intake](references/seo-incidents.md) can apply `agent` through your local
GitHub login. It checks a pinned Actions workflow, its successful run and evidence artifact, and
the current public failure before admitting an issue. Without a local policy, the tick only uses
the owner queue above. Python 3.11 or newer is needed only for this intake.

## Install

```
/plugin install agent-dispatch@dmitriy-claude-plugins
```

or, in Codex, `codex plugin add agent-dispatch@dmitriy-claude-plugins`. It needs
[issue-to-pr](../issue-to-pr/README.md) 9.4.0 or newer in every host your repos use. Then run
`/agent-dispatch:setup`. It checks the machine, asks for each repo's auto-merge threshold and
shows everything it is about to change. Once you confirm, it writes the repo list, creates the
labels, copies the tick script and registers the scheduler entry. It also checks the optional
notification hook and shows how to configure it.

## `~/.agent-dispatch/`

- `repos.conf`: one repo per line, `<main checkout path> | claude|codex | trivial|standard|complex|none`.
  The last field is the `--auto-merge` threshold.
- `logs/`: `tick.log`, `notify.log`, and one log per run.
- `notify.sh`: optional, and yours to write. The tick runs it with bash as
  `notify.sh <waiting|review|failed> <owner/repo> <issue> <detail>`, where `<detail>` is the cause
  when the dispatcher itself marked the run failed (with a note if it also paused dispatching) and
  empty otherwise. After 30 seconds it is stopped along with anything it started. It never changes
  the tick's result. Its output goes to `logs/notify.log`. A failed send is not retried, and a tick
  that dies mid-send may send the same message again. If recovery cannot identify or stop a
  launcher, it keeps the process record and skips new notifications until cleanup succeeds.
- `paused`: created when a CLI errors out (usually logged out or out of allowance). No run starts
  until you delete it. Create it yourself to stop dispatching: disabling or uninstalling the plugin
  leaves the scheduled tick running.
- `lock/`: the run in progress. A tick that died leaves it behind; the next tick stops what is
  left of that run and marks the issue failed. Process records include the boot identity, so
  recovery ignores IDs saved before a restart. An uncertain GitHub response keeps the lock for
  the next tick to reconcile, without repeating an acknowledged failure comment.
  A failed attempt before launch clears its old queue label; apply `agent` again to retry.
  A queue label you add after launch survives failure of that run.

## Limits

One run at a time, on one machine. A run is stopped after four hours of polling; laptop sleep
and wall-clock changes do not consume extra polling intervals. On Windows, install
PowerShell with `winget install --id Microsoft.PowerShell -e --source winget --installer-type wix
--scope machine` rather than from the Store: processes the Store build starts cannot be stopped
with the rest of the run. Setup offers to run it for you; the Store package can stay once the
machine PATH lists this build first. If Windows policy blocks the job
object the launcher needs to hold a run, no run starts at all, and the tick reports it as a
failure. On macOS and Linux a process that detaches into its own session escapes the stop; none
of the tested CLIs does. The check for edits runs when the tick picks the issue, so an edit that
lands in the few seconds before the run reads the issue still gets through.

Boot checks cover full restarts. They do not distinguish reused IDs within one boot or Windows
Fast Startup, which preserves the kernel. Recovery preserves older records without a readable
boot identity; check that their processes have stopped before removing those records.
An applied comment POST whose response is lost, or a crash before its receipt is written, can
still repeat that comment on recovery.
