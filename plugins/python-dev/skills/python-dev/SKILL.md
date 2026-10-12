---
name: python-dev
description: Use when implementing a Python feature or fix, or when the user requests Python architecture, implementation, review, or tests.
---

# Python development workflow

Use the current host's tools to read files, edit code, run checks, and ask questions. Take the task from the user's request; ask for it if missing. Read the linked companion skills from this package when a phase calls for them.

## Phase 1: discovery

First, understand the project and task:

1. **Check for Python project markers:**
   - `pyproject.toml`
   - `requirements.txt` or `Pipfile`
   - `setup.py` or `setup.cfg`
   - `.py` files
   - Framework config (FastAPI, Django, Flask)

2. **Read existing architecture:**
   - Read `AGENTS.md`, then any applicable `CLAUDE.md` and project documentation
   - Look at existing code patterns in `src/`
   - Identify framework and dependencies

3. **Clarify requirements** if ambiguity changes the implementation, using the current host's question tool or a normal chat question

## Phase 2: architecture

Read [the architecture skill](../python-architect/SKILL.md) to:

1. **Design module structure** - Protocols, package hierarchy
2. **Create test stubs** - pytest test cases
3. **Generate Mermaid diagrams** - Class, data flow diagrams
4. **Define contracts** - Protocols/ABCs before implementations

Present the architecture to the user for approval before implementing.

## Phase 3: implementation

Read [the implementation skill](../python-coder/SKILL.md) to implement:

1. Follow PEP 8 and project conventions precisely
2. Implement against the test stubs created in Phase 2
3. Run tests continuously as you implement
4. Use type hints everywhere

## Phase 4: review

Read the review procedure in [the reviewer definition](../../agents/python-reviewer.md), ignoring its host-specific frontmatter. If the host supports delegation, give a bounded reviewer the task, changed files, project constraints, and that procedure. Otherwise, perform a separate review pass yourself and report that the review was sequential. Check:

- Type hint coverage
- PEP 8 compliance
- Error handling patterns
- Async correctness
- Performance concerns

## Phase 5: testing

Read [the testing skill](../python-testing/SKILL.md) to:

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
<invoke python-dev> Add REST API with FastAPI
<invoke python-dev> Implement data processing pipeline
<invoke python-dev> Create CLI tool with Click
```
