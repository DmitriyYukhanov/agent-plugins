# Changelog

All notable changes to the **tg-voice** plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.2] - 2026-10-12

### Fixed
- Restore automatic voice transcription and pass the transcript to the agent.

### Changed
- Refresh installation links and catalog descriptions for the agent plugins collection.

## [1.0.1] - 2026-07-13

### Added
- Plugin README with hook behavior, requirements, and model configuration

## [1.0.0] - 2026-04-05

### Added
- PostToolUse hook that automatically transcribes `.oga` voice messages downloaded via the Telegram channel plugin
- `voice-to-text-config` skill for guided setup: faster-whisper installation, model download, and end-to-end verification
- `transcribe-voice.py` script with model cache detection and actionable error guidance
- Configurable model size via `WHISPER_MODEL` env var (default: `base`)
