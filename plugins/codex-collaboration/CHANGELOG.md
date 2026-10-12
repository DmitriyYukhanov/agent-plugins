# Changelog

All notable changes to the **codex-collaboration** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.13.1] - 2026-10-12

### Changed
- Refresh installation links and catalog descriptions for the agent plugins collection.

## [1.13.0] - 2026-09-29

### Fixed
- Run Codex review, status, result and cancel through the companion script, since the Skill tool cannot invoke those commands
- Use one 15-minute silence limit and the wait-for-codex helper instead of conflicting timeouts and Monitor advice
- Count cross-review rounds once per round

## [1.12.0] - 2026-09-23

### Changed
- Run the latest Opus and the latest Codex Astra model at medium effort by default instead of a pinned Codex model at extra-high effort

## [1.11.0] - 2026-08-28

### Added
- Declare the Codex plugin as a manifest dependency so it installs with this one; the workflows need both models and have no Claude-only mode

## [1.10.1] - 2026-07-13

### Added
- Plugin README covering both workflows, invocation syntax, model defaults, and the no-degraded-mode policy

## [1.10.0] - 2026-07-10

### Changed
- Default Codex model updated from `gpt-5.5` to `gpt-5.6-sol` (OpenAI's new flagship, shipped in Codex CLI 0.143.0 on 2026-07-08) in the config example and all Direct CLI Fallback commands; fallback chain extended to `gpt-5.5` → `gpt-5.4`
- Documented that `gpt-5.6-sol`'s auth requirement (ChatGPT sign-in vs. API-key) is not yet confirmed by OpenAI, unlike `gpt-5.5`'s known ChatGPT-only rollout — treat as open and rely on the fallback chain if the model errors as unavailable
- Noted that Codex CLI ≥ 0.143.0 is required for `gpt-5.6-sol`, and that the model's own reasoning-effort default (`low`) differs from this config's deliberate `xhigh` override

## [1.9.0] - 2026-05-08

### Changed
- Cross-review now auto-applies findings backed by reviewer agreement, cross-validation, or evidence; the user is consulted only for genuinely inconclusive disagreements (code-verified-only findings stay in the consultation bucket and never auto-apply)
- Cross-review exits early on a stable round (zero auto-fixable, zero needs-decision)
- Rollback uses `git restore --patch` for files with pre-existing changes; bare `git restore .` is never emitted
- All-agreed and zero-disagreement-after-cross-validation paths now route through auto-apply before presentation (previously skipped the apply step)

### Added
- Helper scripts: `wait-for-codex` (poll with terminal phase enum) and `dirty-tree-probe` (per-file dirty/untracked/would-create probe), each in Bash and PowerShell; complementary `internals.md` reference doc covering schemas, response enums, branch tables, the auto-apply algorithm, and the test plan
- Per-round delta-based dirty-tree gate (with pre-apply re-probe to catch mid-round manual edits) and lazy per-touched-file baseline map (with size guard for large files; tracks pre-existing untracked status) enabling safe rollback across four file partitions: clean-tracked, dirty-tracked, pre-existing-untracked, and newly-created
- Partial-apply failure prompt (`retry` / `revert` / `skip` / `stop`); `revert` operates on a per-pass journal so earlier rounds' fixes are not touched; `stop` halts the run while preserving earlier successful fixes
- Per-round progress status with explicit final-round wording (no false "moving to round N+1" on the last allowed round)
- "Dirty-tree decline" exit condition; "Skipped (apply failed)" subsection in the summary
- Canonical response enums for needs-decision (`fix` / `dismiss` / `fix with changes:` / `stop`, with `stop` overriding all other verbs in a batched response), partial-apply (`retry [N]:` / `revert` / `skip` / `stop`), and dirty-tree gate (`proceed` / `stop`); all parsing rules in `internals.md`
- `--max-rounds < 1` is now rejected at parse time with a clear error

### Fixed
- Round numbering off-by-one (`ROUND` starts at 1 before first review; increment moves to before next-dispatch)
- "Applied This Round" and "Resolved by Evidence" are now mutually exclusive
- README.md, Overview, and Core principle reflect the autonomous default
- Polling guidance no longer references the non-existent `completed` phase

## [1.8.0] - 2026-04-24

### Changed
- Default Codex model updated from `gpt-5.4` to `gpt-5.5` (OpenAI's recommended Codex model, released 2026-04-23) in the config example and all Direct CLI Fallback commands
- Added rollout note — `gpt-5.5` requires ChatGPT sign-in; users on API-key auth should stay on `gpt-5.4` until API availability ships

## [1.7.0] - 2026-04-21

### Fixed
- Broken companion script path replaced with Skill tool invocations (`/codex:status`, `/codex:result`, `/codex:cancel`, `/codex:rescue --fresh`) — the old `${CLAUDE_PLUGIN_ROOT}/../codex/scripts/...` path never resolved when the two plugins lived in different marketplace caches
- Preflight Check numbering — failure modes are now sub-items of step 1, not separate top-level steps
- Health-check wording normalized — all skills now point to `/codex:status` as the primary path, with companion script only mentioned in the explicit fallback section
- Connectivity test distinguishes dead runtime from Skill-gate errors — `disable-model-invocation` no longer misclassified as a dead connection
- Liveness probe capped at 90 seconds (down from unbounded); harmonized across prerequisites.md and collaborative-loop
- Direct CLI Fallback no longer discards stderr with `2>/dev/null` — runtime errors (sandbox failures, websocket errors, auth issues) are now merged into the output log so Monitor can see them
- `EXIT_CODE=` completion marker now appends to the same log file Monitor tails (previously echoed to terminal, making the marker unobservable)
- Internal contradiction removed — stale "poll every 5 minutes" guidance conflicted with the Polling Efficiency section that says to use Monitor without looped polls

### Added
- Distinct branch for Skill-gate rejection (user denies `/codex:rescue` or `/codex:review` at the permission prompt) covering both the validate phase (Step 4) and review phase (Step 6) — Auto-Retry Protocol no longer fires against a non-dispatched job; instead the user is offered Direct CLI Fallback and the decision stays with them
- Concrete Monitor filter examples with both Bash (tail -f + grep) and PowerShell (Get-Content -Wait + Select-String) variants, framed as a starting point to adapt per workflow
- PowerShell-native `codex exec` example for native Windows users — prior Bash-only snippet failed under PowerShell due to `$TMP`, stdin redirection, and `>>` append differences
- Windows sandbox reliability note — intermittent `CreateProcessWithLogonW failed: 1056` errors may occur and do not invalidate a review when context is inlined; only Monitor silence past the response-generation threshold signals a real stall
- Cross-platform temp file and timeout guidance — Unix/`$TMPDIR`, Windows/`$TEMP`, and documented that `timeout 600` requires GNU coreutils (not native Windows cmd/PowerShell)

## [1.6.0] - 2026-04-16

### Added
- Direct CLI Fallback — when companion retries fail, bypass the broker and run `codex exec` directly before giving up
- Session reliability tracking — after the first companion failure, lower patience thresholds and prefer CLI for complex tasks
- Code-level verification in cross-review — when Codex cross-validation fails, verify single-source findings against source code instead of marking them all "unverified"
- Graceful degradation for cross-validation — initial review still requires both models, but cross-validation can continue with partial results
- Polling efficiency guidance — use Monitor tool for waiting, limit manual bash checks to reduce context waste
- Explicit `codex:result` error handling — fall back to companion bash commands when Skill tool returns `disable-model-invocation`

### Changed
- Reduce response-generation max wait from 45 minutes to 15 minutes — session data shows silence >10 min is almost always a dead task
- In degraded sessions, reduce max wait further to 8 minutes and skip to CLI after one companion retry
- Runtime failure policy now requires CLI fallback attempt before stopping — "STOP and report" is the last resort, not the first
- Clarify that "both models required" applies to initial review; cross-validation can degrade gracefully

## [1.5.0] - 2026-04-15

### Changed
- Remove degraded mode from cross-review — both models are now required, same as collaborative-loop
- Replace PID-based liveness checks with companion task status checks — Windows CLI launcher exits immediately, making `tasklist` unreliable
- Increase starting-stuck threshold from 2 minutes to 5 minutes to reduce false positives
- Replace log-staleness timer with response-generation awareness (wait up to 45 min after tool calls go quiet)
- Increase max auto-retries from 1 to 2, with diagnostic check between retries
- Polling interval from 2 minutes to 5 minutes to reduce context waste

### Added
- Response-generation awareness — after tool calls go quiet, Codex is likely composing its response (10-30 min); do NOT cancel
- Diagnostic escalation protocol — run connectivity test and check companion status for errors before blindly retrying
- WebSocket connection limit guidance — detect and recover from OpenAI's 60-minute WebSocket TTL
- Common failure signature table with specific remediation steps

### Removed
- `tasklist` / `kill -0` PID liveness commands — replaced by companion status checks
- Degraded mode (Claude-only fallback) from cross-review — cross-review now ABORTs on Codex failure

## [1.4.0] - 2026-04-14

### Added
- Context gathering guidance for non-code artifacts — reviewers now read referenced source files before reviewing design/plan/architecture specs
- Cross-reference triage table showing which reviewers found each issue at what severity
- Fallback path when `/codex:status` Skill tool fails with `disable-model-invocation`
- Stale task dismissal step in auto-retry protocol to ignore late-arriving notifications from dead tasks

### Fixed
- Flow interruption after Codex setup — setup → dispatch is now explicitly uninterruptible
- Triage → cross-validation flow runs without stopping for user acknowledgment

## [1.3.0] - 2026-04-14

### Added
- PID liveness verification within 30 seconds of Codex dispatch to catch dead processes early
- Starting-stuck detection at 2-minute threshold (down from 9+ minutes in practice)
- Fresh `/codex:setup` re-invocation before each Codex dispatch to prevent pipe-mismatch zombie tasks
- Auto-retry protocol on dead process: re-setup then re-dispatch with max 1 retry

### Changed
- Hang detection is now two-tier: PID liveness (fast) then log staleness (slow)
- Stale-log monitor re-runs `/codex:setup` before retry to establish fresh runtime

## [1.2.0] - 2026-04-08

### Added
- Cross-validation step — each model verifies the other's findings before presenting to user
- Evidence-based dispute resolution — resolve disagreements via docs/code research instead of always asking the user
- Per-artifact-type domain agents for design, plan, and architecture reviews
- REFINE verdict — agree with an issue but adjust its severity or fix
- Fast-path exits for zero findings, full agreement, and degraded mode

### Changed
- Evidence-first resolution replaces immediate user escalation as core principle

## [1.1.0] - 2026-04-04

### Added
- Liveness check after preflight to catch zombie broker processes
- Stale-log monitor for hang detection with automatic single-retry

### Changed
- Codex monitoring uses log-staleness detection instead of hard timeouts

## [1.0.2] - 2026-04-03

### Fixed
- Add `--fresh` to all `/codex:rescue` invocations to prevent thread-resume prompts during automated workflows

## [1.0.1] - 2026-03-29

### Fixed
- Minor refinements to collaboration workflows

## [1.0.0] - 2026-03-29

### Added
- `collaborative-loop` skill — sequential drive/validate/act cycles between Claude and Codex
- `cross-review` skill — parallel dual review with independent analysis, cross-validation, and triage
- Unified plugin replacing separate collaborative-loop and cross-review plugins
