# Changelog

All notable changes to the **tg-essentials** plugin (named **tg-alerts** before 2.0.0) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.5.0] - 2026-10-15

### Added
- Send announcements through a trusted, privately configured HTTP or HTTPS Bot API service.

## [2.4.0] - 2026-10-15

### Added
- Create topics in existing Telegram forums with permission checks and protection against duplicate creation after an interrupted attempt.

## [2.3.1] - 2026-10-12

### Changed
- Refresh installation links and catalog descriptions for the agent plugins collection.

## [2.3.0] - 2026-10-12

### Added
- Send short deployment announcements and operational notes, with format checks and explicit delivery outcomes.

## [2.2.0] - 2026-10-11

### Added
- List forum topics by name and ID, and post messages or checklists into a selected topic.

## [2.1.0] - 2026-10-04

### Added
- Automatically include local transcripts of voice messages and video notes in chat exports, with cached results and visible failures.

## [2.0.0] - 2026-09-29

### Changed
- Rename the plugin from tg-alerts to tg-essentials; reinstall it under the new name, and call the alerts skill as `tg-essentials:tg-alerts` instead of `tg-alerts:tg-alerts`

### Added
- `tg-account` skill: work in Telegram as yourself through the local Telegram Desktop session to find chats, export history to text files, create groups, send, edit and pin messages, post native checklists and set a chat photo

## [1.0.1] - 2026-07-13

### Added
- Plugin README with setup phases, reference implementations, and usage

## [1.0.0] - 2026-04-05

### Added
- `tg-alerts` skill with interactive 7-phase setup flow
- Step-by-step @BotFather and chat ID discovery guide (private chat, group, channel, forum topics)
- Reference implementations for Python async (FastAPI), Python sync (Django/Flask), and Node.js/TypeScript (Express/NestJS)
- Built-in deduplication, HTML formatting, graceful failure handling, and fire-and-forget delivery
- Framework-specific integration guidance for error handlers and logging bridges
