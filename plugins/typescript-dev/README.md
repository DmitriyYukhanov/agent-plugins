# typescript-dev

Shared TypeScript development skills for architecture, implementation, testing, and review.

## Host compatibility

Use the shared skills in Claude Code or Codex. Resolve bundled files from the installed skill directory and use the current host's tools. Optional Claude agent adapters have a direct or sequential skill fallback. See the [compatibility audit](../../docs/plugin-compatibility.md) for runtime coverage and requirements.

Codex installation:

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add typescript-dev@dmitriy-claude-plugins
```

## Installation

```bash
/plugin install typescript-dev@dmitriy-claude-plugins
```

## Features

### Skill: `typescript-dev:typescript-dev`

Orchestrates a complete TypeScript development workflow:

1. **Discovery** - Analyzes project structure and requirements
2. **Architecture** - Designs module structure, interfaces, test stubs, Mermaid diagrams
3. **Implementation** - Follows TypeScript coding guidelines
4. **Review** - TypeScript-specific code review for type safety, async, accessibility
5. **Testing** - Unit, integration, and E2E test patterns

### Skills (Reference Knowledge)

- **typescript-architect** - Architecture patterns, Mermaid diagrams, test stub templates
- **typescript-coder** - TypeScript naming conventions, coding guidelines, async patterns
- **typescript-testing** - Jest/Vitest patterns, mocking strategies, coverage guidelines

### Agents (Autonomous Tasks)

- **typescript-reviewer** - TypeScript-specific review, then a general code review

## Usage

```bash
# Full development workflow
/typescript-dev Add user authentication with JWT

# Individual phases
/typescript-dev architect only - Design a REST API
/typescript-dev review only - Review recent changes
```

## What It Checks

### Type Safety
- `any` usage without justification
- Missing null/undefined handling
- Incorrect type assertions
- Generic type misuse

### Async Patterns
- Floating promises
- Missing error handling
- Race conditions

### React/Framework
- Hook dependency arrays
- Component re-render optimization
- Prop type definitions

### Accessibility
- Semantic HTML elements
- ARIA attributes
- Keyboard navigation

## License

MIT
