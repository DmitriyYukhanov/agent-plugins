---
name: slim-claude-md
description: Slim or restructure an oversized CLAUDE.md into path-scoped .claude/rules/ files, verifying nothing was lost. Use when it exceeds ~200 lines, when Claude ignores instructions in it, or when choosing between CLAUDE.md, rules, skills and @import.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Slim a CLAUDE.md

CLAUDE.md loads in full on every session. Past roughly 200 lines it costs context on every request
*and* reduces adherence, so instructions get ignored precisely because there are too many of them.
This moves subsystem detail into `.claude/rules/` files that load only when the matching files are
opened, and proves the move lost nothing.

**Scope:** restructuring an existing file. Writing a CLAUDE.md from scratch is `/init`'s job; auditing
content quality against templates is what `claude-md-management`'s `claude-md-improver` does.

Mechanics (load order, `paths:` syntax, the `@import` trap, `/doctor`, hierarchy) live in
[references/mechanics.md](references/mechanics.md). Read the section you need when you need it.

Locate this installed `SKILL.md` through the current host's skill metadata or file tools. Resolve `../..` from its directory to get the absolute plugin root. Replace `<absolute-plugin-root>` below with that path and verify both scripts under `skills/slim-claude-md/scripts/` exist. If a resource is unavailable, report the missing path and stop; do not assume a host environment variable supplies it.

## Phase 1 — Measure

```bash
python "<absolute-plugin-root>/skills/slim-claude-md/scripts/audit_claude_md.py" CLAUDE.md
```

Reports loaded size (HTML comments excluded, since they are stripped before loading), ranks sections
by size, marks the set whose removal gets you under budget, and flags derivable content plus
staleness hints. Exit 1 means over budget.

Run it on every CLAUDE.md in the repo, not just the root one: `find . -name CLAUDE.md -not -path "*/node_modules/*"`.

**If the file is within budget, stop and say so.** Do not restructure a file that is already fine.

## Phase 2 — Decide what moves

For each section, apply the documented test: **"Would removing this cause Claude to make mistakes?
If not, cut it."** Then sort what remains into three piles.

**Stays in CLAUDE.md** — needed in *every* session regardless of what you touch:
- Build/test commands that can't be guessed
- Safety rules ("never run X", "never commit Y") — these must never be behind a path scope
- Conventions that apply repo-wide
- Gotchas that bite before you open any particular file

**Moves to a `paths:`-scoped rule** — only matters while editing one subsystem:
- Per-feature implementation narratives
- Deep rationale for one module's design
- Anything whose first sentence is effectively "when working on X…"

**Gets deleted** — the docs' exclude list: content derivable from the code, directory trees,
dependency lists, standard language conventions, tutorials, self-evident advice.

Two rules that override the sorting:

- **A rule that must never be violated belongs in a hook, not in prose.** CLAUDE.md is advisory.
- **Stale content is worse than verbose content.** A confident sentence that is no longer true will
  actively mislead. When the audit flags a staleness hint, verify it against reality — the code, the
  live system, `git log` — and fix or delete it. Do not carry it across the move unverified.

## Phase 3 — Choose the mechanism

| Goal | Use |
| --- | --- |
| Cut context cost | `.claude/rules/*.md` **with** `paths:` |
| Organise for humans, cost unchanged | `.claude/rules/*.md` without `paths:` |
| Multi-step procedure | a skill |
| Must happen every time | a hook |

**Do not reach for `@import`.** Imports load eagerly at launch, so they save zero context. This is
the most common wrong turn because splitting into imports looks like it should help.

Scope each rule to where the knowledge is used, e.g. `paths: ["src/api/**"]`. If several subsystems
share the same files, path-scoping cannot separate them — that is fine and still worth doing, because
sessions that never open those files stay lean.

## Phase 4 — Extract verbatim

Move whole sections **byte-for-byte**. Do not reword while moving: a rewrite during a move makes the
next step unable to distinguish a rewording from a deletion.

Each rules file gets frontmatter, a title, and a line saying where the core rules live:

```markdown
---
paths:
  - "src/api/**"
---

# API subsystem

Loaded when you open `src/api/`. Repo-wide rules live in the root CLAUDE.md.

<moved sections, unchanged>
```

Then leave a pointer in CLAUDE.md so nothing is silently unreachable:

```markdown
## Where the feature detail lives

These load automatically when you open the matching files:
- `.claude/rules/api.md` — endpoint conventions, error envelope, auth flow.
```

The pointer is load-bearing. If the glob ever fails to match, a reader still knows the file exists.

## Phase 5 — Verify nothing was lost

```bash
python "<absolute-plugin-root>/skills/slim-claude-md/scripts/verify_extraction.py" \
    --original-git HEAD:CLAUDE.md \
    --section "API" --section "Billing" \
    --now .claude/rules/api.md --now .claude/rules/billing.md
```

Name the sections you moved with `--section`. Without it the script compares the whole file and
reports every rewritten line as lost, which buries real losses in noise.

Exit 0 means every substantive line survived. Exit 1 lists what vanished: restore it, or delete it
deliberately and say so. Exit 2 means a section name didn't match — fix the name; do not proceed on
an unmatched selector, because it silently checks nothing.

Rewrite the slimmed core **after** this passes, as a separate reviewable edit. Keeping the move and
the rewrite apart is what makes the check trustworthy.

## Phase 6 — Confirm it loads

Re-run the audit to confirm the new size, then verify the rules actually load:

- `/context` → **Memory files** lists what loaded. A missing file is invisible to Claude.
- Open a file matching each glob and confirm the rule appears. A malformed glob matches nothing
  silently, so "no error" is not evidence.
- `/doctor` (CLI 2.1.206+) proposes further trims.

Report the before/after numbers, what moved where, and anything deleted rather than moved.

## Common mistakes

- **Splitting with `@import` to save context.** It doesn't. Only `paths:`-scoped rules defer loading.
- **Path-scoping a safety rule.** "Never run `docker compose down -v`" must load every session.
- **Rewriting while moving.** Breaks the verification and hides losses.
- **Trusting a `--section` name that didn't match.** The script exits 2 for exactly this reason.
- **Carrying stale prose across the move.** The move is the moment to check claims against reality;
  restructuring a file nobody has pruned in months means auditing what it asserts, not just relocating it.
- **Slimming a file that was already fine.** Measure first.
