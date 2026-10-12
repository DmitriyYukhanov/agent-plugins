# Changelog

All notable changes to the **humanizer** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.3.2] - 2026-10-12

### Changed
- Refresh installation links and catalog descriptions for the agent plugins collection.

## [1.3.1] - 2026-09-29

### Changed
- Refresh the Russian hard bans as AI-text markers change, with no fixed as-of date

## [1.3.0] - 2026-08-14

### Added
- Russian passes read `edit-log.md`, a file where you record the corrections you keep having to repeat, and apply them over the catalog's defaults on every later run
- The scanner now flags text that advertises its own honesty ("честный список", "без воды", "это не очередной") instead of showing the facts

### Changed
- English ruleset refreshed to upstream v2.9.1: a rewrite may no longer state a fact, name, number, date, or citation the source doesn't have, which the shipped examples themselves had been doing
- English ruleset gained file and embedded modes, so a humanizer call inside a larger task hands back finished prose instead of the draft-audit-final ceremony
- A writing sample you provide now outranks the English em dash ban, so matching the author beats scrubbing the tell
- Russian ruleset refreshed to upstream v3.15.4: the 54-pattern catalog moved into a file the model opens only when it edits or audits, which keeps the working prompt short

## [1.2.0] - 2026-07-21

### Added
- Russian audits can now run the upstream scanner, which scores text 0-100 on hard bans, marker density, sentence rhythm, morphology, and paragraph evenness, so a rewrite reports "was N, now M" instead of a verdict you have to take on trust
- The scanner is optional: a one-time `pip install razdel pymorphy3` turns it on, and without those packages the ruleset estimates the same score itself, exactly as it does on claude.ai

### Fixed
- Vendor the scanner that the 1.1.0 Russian ruleset already told the model to run, so its `scripts/scan.py` instruction stops pointing at a file the plugin never carried

### Changed
- Request the `Bash` tool, without which the scanner cannot run

## [1.1.0] - 2026-07-21

### Changed
- English ruleset refreshed to upstream v2.8.2: 29 → 33 patterns (diff-anchored writing, manufactured punchlines, aphorism formulas, conversational rhetorical openers), an outright ban on em and en dashes, and a rule that a rewrite must cover everything the original covered
- English ruleset now says which tells are false positives and which signs of human writing to leave alone, so clean prose survives the pass instead of getting flattened
- Russian ruleset refreshed to upstream v3.14.2: 44 → 54 patterns, adding persuasion tropes, information rhythm, systematic hedging, and 2025-2026 style fingerprints such as decorative emoji and pseudo-therapeutic register

## [1.0.0] - 2026-04-30

### Added
- English ruleset vendored from blader/humanizer (29 Wikipedia AI-writing patterns)
- Russian ruleset vendored from ilyautov/humanizer-ru (44 patterns, hard bans, triple-pass audit)
- Auto language detection by Cyrillic ratio with explicit override and mixed-text handling
