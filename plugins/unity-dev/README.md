# unity-dev

A Claude Code plugin for Unity C# development with architecture design, coding guidelines, testing patterns, and specialized review agents.

## Host compatibility

Use the shared skills in Claude Code or Codex. Resolve bundled files from the installed skill directory and use the current host's tools. Optional Claude agent adapters have a direct or sequential skill fallback. See the [compatibility audit](../../docs/plugin-compatibility.md) for runtime coverage and requirements.

Codex installation:

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add unity-dev@dmitriy-claude-plugins
```

## Installation

```bash
/plugin install unity-dev@dmitriy-claude-plugins
```

## Features

### Skill: `/unity-dev`

Orchestrates a complete Unity development workflow:

1. **Discovery** - Analyzes project structure and requirements
2. **Architecture** - Designs component hierarchies, interfaces, test stubs, Mermaid diagrams
3. **Implementation** - Follows Unity C# coding guidelines
4. **Review** - Unity-specific code review for performance, lifecycle, serialization issues
5. **Testing** - EditMode and PlayMode test patterns

### Skill: `/unity-tests-run`

Runs Unity Test Framework tests via CLI batchmode with auto-detection of Unity installation. Supports platform, category, and filter arguments.

### Skill: `unity-run`

CLI execution layer used by the other skills: builds, tests, method execution, and asset imports, with Unity installation auto-detection, batchmode execution, and log monitoring.

### Skills (Reference Knowledge)

- **unity-architect** - Architecture patterns, Mermaid diagrams, test stub templates
- **unity-coder** - C# naming conventions, member ordering, Unity-specific guidelines
- **unity-tests-write** - EditMode/PlayMode patterns, performance testing, code coverage

### Agents (Autonomous Tasks)

- **unity-reviewer** - Unity-specific review, then a general code review
- **unity-simplifier** - Unity patterns, then general cleanup
- **unity-test-runner** - Runs Unity tests via CLI batchmode (used by `/unity-tests-run`)

## Usage

```bash
# Full development workflow
/unity-dev Add player health system with damage and healing

# Individual phases
/unity-dev architect only - Design a save system
/unity-dev review only - Review recent changes
```

## What It Checks

### Performance
- Uncached `GetComponent` in Update loops
- Allocations in hot paths (LINQ, string concatenation)
- Missing object pooling

### Lifecycle
- Proper Awake/Start/OnEnable/OnDisable/OnDestroy usage
- Event subscription/unsubscription symmetry
- Static state cleanup with `[RuntimeInitializeOnLoadMethod]`

### Serialization
- Correct use of `[SerializeField]` and `[field:SerializeField]`
- Missing `[System.Serializable]` on nested classes

### Platform
- IL2CPP compatibility (no runtime reflection)
- Platform-specific `#if` directives

## License

MIT
