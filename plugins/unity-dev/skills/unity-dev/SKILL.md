---
name: unity-dev
description: Use when implementing a Unity C# feature or fix, or when the user requests Unity architecture, implementation, review, or tests.
---

# Unity development workflow

Use the current host's tools to read files, edit code, run checks, and ask questions. Take the task from the user's request; ask for it if missing. Read companion skills from this package when a phase calls for them.

## Phase 1: discovery

First, understand the project and task:

1. **Check for Unity project markers:**
   - `*.csproj` files
   - `ProjectSettings/` folder
   - `Assets/` folder
   - `*.unity` scene files

2. **Read existing architecture:**
   - Read `AGENTS.md`, then any applicable `CLAUDE.md` and project documentation
   - Look at existing code patterns in `Assets/Scripts/`
   - Identify assembly definitions (`.asmdef` files)

3. **Clarify requirements** if ambiguity changes the implementation, using the current host's question tool or a normal chat question

## Phase 2: architecture

Use the [unity-architect](../unity-architect/SKILL.md) skill knowledge to:

1. **Design component hierarchy** - MonoBehaviour structure, interfaces
2. **Create test stubs** - EditMode + PlayMode test cases
3. **Generate Mermaid diagrams** - Class, sequence, state machine
4. **Define contracts** - Interfaces before implementations

Present the architecture to the user for approval before implementing.

## Phase 3: implementation

Use the [unity-coder](../unity-coder/SKILL.md) skill knowledge to implement:

1. Follow Unity C# coding guidelines precisely
2. Implement against the test stubs created in Phase 2
3. Use the [unity-tests-run](../unity-tests-run/SKILL.md) skill to run tests continuously as you implement
4. Use proper serialization attributes (`[SerializeField]`, `[field:SerializeField]`)

## Phase 4: review

Read the review procedure in [the reviewer definition](../../agents/unity-reviewer.md), ignoring its host-specific frontmatter. If the host supports delegation, give a bounded reviewer the task, changed files, project constraints, and that procedure. Otherwise, perform a separate review pass yourself and report that the review was sequential. Check:

- MonoBehaviour lifecycle issues
- Serialization problems
- Performance red flags
- Memory leaks (static events, unsubscribed handlers)
- Platform compatibility

## Phase 5: testing

Use the [unity-tests-write](../unity-tests-write/SKILL.md) skill knowledge to write missing tests, then use the [unity-tests-run](../unity-tests-run/SKILL.md) skill to execute them:

1. Write tests following `unity-tests-write` patterns (EditMode for editor/utilities, PlayMode for runtime behavior)
2. Run EditMode tests
3. Run PlayMode tests
4. Fix any failures before proceeding
5. Generate coverage report for critical paths if requested

## Individual phases

You can run individual phases:
- "architect only" - Just Phase 2
- "implement only" - Just Phase 3 (requires existing architecture)
- "review only" - Just Phase 4
- "test only" - Just Phase 5

## Invocation

Use the host's skill selector, command syntax, or a natural-language request.

```
<invoke unity-dev> Add player health system with damage and healing
<invoke unity-dev> Implement object pooling for projectiles
<invoke unity-dev> Create save/load system using ScriptableObjects
```
