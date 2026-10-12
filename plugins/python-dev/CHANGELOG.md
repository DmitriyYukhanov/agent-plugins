# Changelog

All notable changes to the **python-dev** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.4.0] - 2026-10-12

### Changed
- Use shared workflows and resource paths across agent hosts.

## [1.3.0] - 2026-09-29

### Changed
- Reviewer covers general code quality in the same pass and reports only issues the code shows
- Shorter coding guide without a PEP 8 naming recap

## [1.2.3] - 2026-08-28

### Fixed
- README called `feature-dev` required; the reviewer agent falls back to reviewing directly without it, so it is optional

## [1.2.2] - 2026-07-13

### Fixed
- Correct install command to use the marketplace name (`@dmitriy-claude-plugins`) instead of the repo path

## [1.2.1] - 2026-04-03

### Added
- CHANGELOG.md with backfilled version history

## [1.2.0] - 2026-03-25

### Added
- WSL support with shell safety fixes
- Agent tool restrictions and `allowed-tools` configuration
- Agent color theming

### Changed
- Add review guardrails to coding guidelines
- Improve coder workflow preambles

### Fixed
- Fix Task -> Agent delegation bug

## [1.0.0] - 2026-02-15

### Added
- `python-architect` skill for high-level architecture with protocols and Mermaid diagrams
- `python-coder` skill with PEP 8-aligned coding guidelines and type-hint best practices
- `python-testing` skill with pytest patterns, fixtures, mocking, and coverage
- `python-reviewer` agent for Python-specific code review
- `/python-dev` command for end-to-end workflows (discovery -> architecture -> implementation -> review -> testing)
