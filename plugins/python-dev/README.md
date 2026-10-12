# python-dev

Shared Python development skills for architecture, implementation, testing, and review.

## Host compatibility

Use the shared skills in Claude Code or Codex. Resolve bundled files from the installed skill directory and use the current host's tools. Optional Claude agent adapters have a direct or sequential skill fallback. See the [compatibility audit](../../docs/plugin-compatibility.md) for runtime coverage and requirements.

Codex installation:

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add python-dev@dmitriy-claude-plugins
```

## Installation

```bash
/plugin install python-dev@dmitriy-claude-plugins
```

## Features

### Skill: `python-dev:python-dev`

Orchestrates a complete Python development workflow:

1. **Discovery** - Analyzes project structure and requirements
2. **Architecture** - Designs module structure, protocols, test stubs, Mermaid diagrams
3. **Implementation** - Follows PEP 8 and Python coding guidelines
4. **Review** - Python-specific code review for type safety, error handling, async
5. **Testing** - pytest patterns, fixtures, mocking, coverage

### Skills (Reference Knowledge)

- **python-architect** - Architecture patterns, protocols, Mermaid diagrams, test stub templates
- **python-coder** - PEP 8, type hints, naming conventions, async patterns
- **python-testing** - pytest patterns, fixtures, mocking strategies, coverage guidelines

### Agents (Autonomous Tasks)

- **python-reviewer** - Python-specific review, then a general code review

## Usage

```bash
# Full development workflow
/python-dev Add REST API with FastAPI

# Individual phases
/python-dev architect only - Design a data pipeline
/python-dev review only - Review recent changes
```

## What It Checks

### Type Safety
- Missing type hints on public functions
- `Any` usage without justification
- Incorrect Optional handling

### PEP 8 Compliance
- Naming convention violations
- Import ordering
- Whitespace issues

### Error Handling
- Bare except clauses
- Missing context managers
- Error logging without context

### Async Patterns
- Blocking calls in async code
- Floating coroutines
- Missing resource cleanup

## License

MIT
