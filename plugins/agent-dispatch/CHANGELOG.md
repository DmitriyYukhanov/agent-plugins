# Changelog

All notable changes to the **agent-dispatch** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.3.3] - 2026-10-12

### Changed
- Refresh installation links and catalog descriptions for the agent plugins collection.

## [1.3.2] - 2026-10-08

### Fixed
- Recover interrupted runs after restarts and uncertain GitHub responses without repeating acknowledged failure comments.
- Publish each lock with its owner and preserve the four-hour polling budget across laptop sleep.
- Fail incomplete test runs and make Windows launcher checks reliable.

## [1.3.1] - 2026-10-07

### Fixed
- Report failed GitHub repository lookups as GitHub errors and retry on the next tick.

## [1.3.0] - 2026-10-07

### Added
- Recognize completed runs without hiding failures from a later retry.

## [1.2.0] - 2026-10-01

### Added
- Tell you through your own command when a run asks a question, waits for your merge, or fails, since GitHub never notifies you of your own activity.

## [1.1.1] - 2026-09-29

### Fixed
- Say in the failure comment when a run ended its turn with background work still running, instead of the generic cause.

## [1.1.0] - 2026-09-29

### Changed
- Set up the repo list, labels, tick and scheduler entry after one confirmation instead of printing commands to paste.
- Ask each repo's auto-merge threshold as its own question, explaining what merges without you and what a merge sets off.

### Added
- Offer to install the machine-wide PowerShell under the same confirmation when only the Store build is present.

## [1.0.0] - 2026-09-26

### Added
- Run issue-to-pr headless on a scheduled tick whenever you label an issue `agent`, under your own Claude Code or Codex login.
- Resume a parked run when you reply on its issue or PR; only your own comments and labels count.
- Hold an issue whose title or body someone else edited after you labelled it `agent`, until you label it `agent` again.
- Stop a hung run after four hours and mark a dead run failed with a pointer to its local log.
- Pause dispatching on a logged-out or rate-limited CLI instead of failing every queued issue.
- Add a setup skill that checks the machine and prints the labels, repo list and scheduler entry for Windows, macOS or Linux.
