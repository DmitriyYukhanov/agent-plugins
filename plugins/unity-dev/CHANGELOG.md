# Changelog

All notable changes to the **unity-dev** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.9.0] - 2026-10-12

### Changed
- Use shared workflows and resource paths across agent hosts.

## [1.8.0] - 2026-09-29

### Changed
- Reviewer and simplifier cover general code quality in the same pass; the reviewer reports only issues the code shows
- Keep Inspector data when the simplifier converts serialized fields to properties
- Stop passing `-quit` with `-runTests`, which could exit Unity before the tests ran

## [1.7.5] - 2026-09-15

### Fixed
- README called `feature-dev` and `code-simplifier` required; both agents fall back to working directly without them, so they are optional. `unity-reviewer` reviews without `feature-dev`, `unity-simplifier` simplifies without `code-simplifier`

## [1.7.3] - 2026-07-13

### Fixed
- Correct install command to use the marketplace name (`@dmitriy-claude-plugins`) instead of the repo path
- Document `/unity-dev`, `/unity-tests-run`, and `unity-run` as skills in the README and add the missing `unity-run` entry

## [1.7.2] - 2026-04-03

### Added
- CHANGELOG.md with backfilled version history

## [1.7.1] - 2026-04-01

### Fixed
- Replace unsupported `arguments` array with `argument-hint` string in skill frontmatter

## [1.7.0] - 2026-04-01

### Added
- `unity-run` skill for CLI execution — builds, tests, method execution, asset imports
- Unity installation auto-detection and batchmode execution with log monitoring

### Changed
- Enhance `unity-tests-write` skill with expanded patterns

## [1.5.2] - 2026-03-27

### Fixed
- Replace `grep -oP` with portable awk/sed in Unity scripts for cross-platform support

## [1.5.1] - 2026-03-27

### Changed
- Rewrite Unity scripts for cross-platform support (MINGW, WSL, macOS, Linux)
- Simplify documentation

## [1.3.0] - 2026-03-20

### Changed
- Rename test skills for clarity
- Improve orchestrator workflow

## [1.2.0] - 2026-03-18

### Added
- Wire run-tests into orchestrator workflow

### Changed
- Update unity-dev documentation

## [1.0.0] - 2026-02-01

### Added
- `unity-architect` skill with architecture design and Mermaid diagrams
- `unity-coder` skill with C# coding guidelines following Microsoft conventions
- EditMode/PlayMode testing patterns
- Unity-specific code review agent
- Code simplification agent
- `/unity-dev` command for full workflow orchestration
