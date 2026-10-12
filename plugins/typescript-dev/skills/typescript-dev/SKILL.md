---
name: typescript-dev
description: Use when implementing a TypeScript feature or fix, or when the user requests TypeScript architecture, implementation, review, or tests.
---

# TypeScript development workflow

Use the current host's tools to read files, edit code, run checks, and ask questions. Take the task from the user's request; ask for it if missing. Read the linked companion skills from this package when a phase calls for them.

## Phase 1: discovery

First, understand the project and task:

1. **Check for TypeScript project markers:**
   - `tsconfig.json`
   - `package.json`
   - `.ts`, `.tsx` files
   - Framework config files (next.config.js, vite.config.ts, etc.)

2. **Read existing architecture:**
   - Read `AGENTS.md`, then any applicable `CLAUDE.md` and project documentation
   - Look at existing code patterns in `src/`
   - Identify framework (React, Vue, Angular, Node.js, etc.)

3. **Clarify requirements** if ambiguity changes the implementation, using the current host's question tool or a normal chat question

## Phase 2: architecture

Read [the architecture skill](../typescript-architect/SKILL.md) to:

1. **Design module structure** - Interfaces, types, module boundaries
2. **Create test stubs** - Jest/Vitest test cases
3. **Generate Mermaid diagrams** - Class, data flow diagrams
4. **Define contracts** - Interfaces before implementations

Present the architecture to the user for approval before implementing.

## Phase 3: implementation

Read [the implementation skill](../typescript-coder/SKILL.md) to implement:

1. Follow TypeScript coding guidelines precisely
2. Implement against the test stubs created in Phase 2
3. Run tests continuously as you implement
4. Use strict types (avoid `any`)

## Phase 4: review

Read the review procedure in [the reviewer definition](../../agents/typescript-reviewer.md), ignoring its host-specific frontmatter. If the host supports delegation, give a bounded reviewer the task, changed files, project constraints, and that procedure. Otherwise, perform a separate review pass yourself and report that the review was sequential. Check:

- Type safety issues
- Async pattern problems
- React/Framework patterns (if applicable)
- Performance red flags
- Accessibility issues

## Phase 5: testing

Read [the testing skill](../typescript-testing/SKILL.md) to:

1. Ensure unit tests pass
2. Ensure integration tests pass
3. Generate coverage report for critical paths if requested

## Individual phases

You can run individual phases:
- "architect only" - Just Phase 2
- "implement only" - Just Phase 3 (requires existing architecture)
- "review only" - Just Phase 4
- "test only" - Just Phase 5

## Invocation

Use the host's skill selector, command syntax, or a natural-language request.

```
<invoke typescript-dev> Add user authentication with JWT
<invoke typescript-dev> Implement REST API with Express
<invoke typescript-dev> Create React component library
```
