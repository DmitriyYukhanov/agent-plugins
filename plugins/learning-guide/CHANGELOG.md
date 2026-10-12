# Changelog

All notable changes to the **learning-guide** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [4.1.0] - 2026-10-12

### Changed
- Use shared workflows and resource paths across agent hosts.

## [3.0.0] - 2026-08-16

### Changed
- Breaking: a generated tour loads Mermaid from a CDN instead of carrying it inside the file, which takes a tour with diagrams from 3.3 MB down to about 30 KB. Reading one now needs network access to draw its diagrams; navigation, quizzes, progress and embedded sources still work with none
- The plugin no longer ships the 3.2 MB Mermaid bundle, so installing it pulls that much less

### Security
- The Mermaid tag carries a Subresource Integrity hash, so a reader's browser refuses to run the file if the CDN ever serves different bytes

## [2.1.0] - 2026-08-16

### Changed
- Mermaid is downloaded on first use and cached instead of shipping inside the plugin, which takes 3.2 MB off every install
- Rendering a tour with diagrams now needs network access once per machine; the tour itself is unchanged, with Mermaid still inlined and still rendering offline

## [2.0.0] - 2026-07-14

### Removed
- Drop the generated `open.cmd` and `render.cmd` Windows launcher scripts, plus the `open_command` spec option — `index.html` is already double-clickable on its own, and `render.cmd` hardcoded the renderer's install path, so it silently broke the moment a rendered tour was moved to another machine or shared with a teammate.

## [1.1.1] - 2026-07-13

### Fixed
- Correct install command to use the marketplace name (`@dmitriy-claude-plugins`) instead of the repo path

## [1.1.0] - 2026-07-02

### Added
- The left sidebar can be collapsed (and reopened with a floating button) and resized by dragging its right edge or with the keyboard; the width and collapsed state persist per guide.

### Changed
- The "Next" button now also marks the current section as read — advancing counts as having read it.

## [1.0.11] - 2026-06-30

### Fixed
- Side-panel embedded docs no longer emit relative-path links (`/`, `./`, `../`) that would navigate the local filesystem and break the offline bundle; only external and in-document links are kept. Corrected a sample companion's source-line reference.

## [1.0.10] - 2026-06-30

### Fixed
- Critical: a `</script` sequence in an inlined comment truncated the runtime script, leaving every generated guide a dead page with no interactivity. The renderer now neutralizes close-tag sequences in every inlined script, style, and library block, so no embedded content can end its element early.

### Added
- Opt-in Playwright browser verification (`scripts/browser-verify.cjs`) that renders a fixture tour, opens it from `file://` in Chromium, and drives the real runtime: navigation, the side-panel source viewer with anchor scrolling, Mermaid rendering, quizzes, progress persistence, click-to-copy, and external links. It catches runtime regressions the string-level tests cannot.

## [1.0.9] - 2026-06-30

### Fixed
- A third review pass closed two cosmetic side-panel edge cases: a rare literal sentinel character in an embedded source no longer renders as the word "undefined", and `<SCRIPT>`/`</SCRIPT>` tags in an embedded source keep their original casing.

## [1.0.8] - 2026-06-30

### Fixed
- A second code-review pass caught three regressions/gaps in the first round of fixes. The cross-reference ReDoS screen now rejects multi-atom catastrophic patterns it previously missed (via a render-time timeout), the side-panel viewer again renders emphasis and links that wrap an inline code span (e.g. **a `b` c**), and embedded sources containing `<!--` or `<script` no longer show stray backslashes in the side panel.

## [1.0.7] - 2026-06-30

### Fixed
- An adversarial code-review pass found and fixed 15 implementation defects. The renderer no longer hangs on empty-matchable or catastrophic cross-reference patterns, `render.cmd` re-renders correctly on Windows, and out-of-range quiz answers, reserved section-id collisions, directory source paths, and non-object specs now fail with a clear message instead of a silent break or a stack trace. Embedded sources can no longer break out of their `<script>` container, the progress tracker works with the pager disabled, and the side-panel viewer hardens inline code spans, special-character anchors, and assistive-tech reachability.

## [1.0.6] - 2026-06-30

### Added
- Skill bodies for `analyze`, `render`, and the entry-point, plus reference docs covering the four archetypes, spec authoring, cross-reference design, the companion synthesis contract, renderer CLI troubleshooting, and `file://` browser constraints. The plugin's three skills are now functional end to end.

## [1.0.5] - 2026-06-30

### Added
- Sample inputs and golden tour-specs for the planning-session, refactor-plan, and codebase (synthesized companion) archetypes, plus an end-to-end smoke verifier (`scripts/verify.cjs`). The verifier renders each sample and checks linkify, callouts, companion embedding, cross-reference anchor resolution, the `</script>` escape, the external-link scheme allowlist, and CRLF-vs-LF parity.

## [1.0.4] - 2026-06-30

### Added
- Renderer (`scripts/render.cjs`) — turns a `tour-spec.json` into the self-contained `index.html` plus launcher scripts. Orchestrates schema validation, per-project override resolution, embedded-source inlining, conditional Mermaid, and section/quiz/glossary/final-quiz rendering. Final-quiz and glossary are navigable sections; Mermaid is detected by post-processing (not a raw-fence regex) and excluded from the payload-size warning; embedded-source containment now defeats symlink escapes; the launcher is skipped when `open_command` is `none`.

## [1.0.3] - 2026-06-30

### Added
- Browser-side assets: HTML template, styles, runtime JS (sidebar nav, progress tracking, on-demand side-panel source viewer, click-to-copy paths, quizzes), English and Russian i18n bundles, the static Windows launcher, and vendored Mermaid 10.9.1. The runtime resolves cross-reference anchors with a shared Unicode-aware slug, escapes and scheme-checks links inside embedded sources, keeps the side panel reachable by assistive tech, and announces quiz results.

## [1.0.2] - 2026-06-30

### Added
- Markdown processor (vendored markdown-it) with five custom transforms: callout fences, mermaid fences, click-to-copy file paths, cross-reference tokens, and external-link tokens. Hardened for Windows backslash paths, non-Latin (e.g. Cyrillic) heading slugs, an external-link scheme allowlist, and catastrophic-regex (ReDoS) cross-ref patterns.

## [1.0.1] - 2026-06-30

### Added
- Tour-spec JSON Schema (with an external-link scheme allowlist) and a zero-dependency validator that reports line-pointed errors.

## [1.0.0] - 2026-04-30

### Added
- Initial scaffold for the `learning-guide` plugin.
