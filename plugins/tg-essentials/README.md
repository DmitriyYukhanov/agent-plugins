# tg-essentials

Telegram toolkit for agents. Error alerts and short deployment announcements go out through a bot, and everything you do in Telegram as yourself (chats, exports, groups, posts, checklists) runs through your local Telegram Desktop session.

Renamed from `tg-alerts` in 2.0.0. If you had the old plugin, uninstall `tg-alerts` and install `tg-essentials`. The alerts skill is now `tg-essentials:tg-alerts`, so update any CLAUDE.md or AGENTS.md line that names `tg-alerts:tg-alerts`.

## Host compatibility

Use the shared skills in Claude Code or Codex. Resolve bundled files from the installed skill directory and use the current host's tools. Optional Claude agent adapters have a direct or sequential skill fallback. See the [compatibility audit](../../docs/plugin-compatibility.md) for runtime coverage and requirements.

Codex installation:

```sh
codex plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin add tg-essentials@dmitriy-claude-plugins
```

## Installation

```bash
/plugin install tg-essentials@dmitriy-claude-plugins
```

## Features

### Skill: `tg-alerts`

Interactive setup in seven phases:

1. Assess the project (language, framework, existing error handling)
2. Create a bot with @BotFather
3. Discover the chat, channel, or forum-topic ID
4. Generate the alert service code
5. Integrate with the framework
6. Wire environment variables
7. Test end to end

Reference implementations included for Python async (FastAPI), Python sync (Django/Flask), and Node.js/TypeScript (Express/NestJS). The generated service deduplicates repeated errors, formats messages as HTML, delivers fire-and-forget, and never crashes the host app when Telegram is unreachable.

### Skill: `tg-announce`

Compose a short release summary from verified deployment evidence and send it to an operational chat or forum topic. The skill works in Claude Code and Codex and reuses the existing alert bot and `ALERT_*` setup.

One bundled Python script checks `announcement-v1` before sending. The format allows a deployment tag or revision and up to eight sentence-length bullets, including an honest empty-release form. `announce` sends a checked release note, `note` escapes arbitrary plain text, and `check` validates a saved UTF-8 file without credentials or network access. The executable stays in the installed plugin; consuming projects keep their own release orchestration.

Delivery returns `SENT` (exit 0, message ID), `NOT_SENT` (exit 1, local rejection or confirmed API refusal), or `UNKNOWN` (exit 2, delivery unconfirmed). The script retries nothing and preserves the message file. After `UNKNOWN`, check the destination before a manual retry. The release flow owns rerun identity and prior results; the sender stores no receipts. See the [skill](skills/tg-announce/SKILL.md) for composition, authorization and integration.

### Skill: `tg-account`

Talks to Telegram as you, using the session Telegram Desktop already keeps on disk. You don't log in or scan a QR code.

- Find chats and export their history into one text file per day
- List and create forum topics, and send posts or checklists into a selected topic
- Include local transcripts of voice messages and video notes automatically
- Create a group, send, edit and pin posts, and set the group photo
- Post a native checklist that members can tick (sending one needs Telegram Premium)

Every write waits for your yes first. Requires Telegram Desktop and Python 3.12. Run the skill's setup script once; a portable Telegram install also needs `TG_TDATA` pointing at its `tdata` folder.

Normal exports include voice messages and video notes on their original message lines. On the first note without a cached transcript, the exporter installs any missing transcription dependencies and downloads Whisper `small` (about 500 MB). One local CPU process handles recognition without an API key or agent tokens. Successful transcripts are cached inside the export's `.transcripts` folder; temporary media files are deleted after processing. Keep that folder private along with the exported chat. Failures stay visible and retry on the next export. Use `--no-transcribe` only when you want to skip speech.

For forum groups, run `tg_find.py --topics CHAT [--account ID]` to see topic names and root IDs. Pass the selected ID to `tg_write.py send` or `todo` with `--topic ID`. Include the topic in the write approval. Omitting the flag keeps the usual routing; topic `1` is General. See the [skill commands](skills/tg-account/SKILL.md#use) for full examples.

To create a topic in an existing forum, use `tg_write.py topic CHAT "Project planning" --account ID --operation FILE` after approving the account, forum and exact title. `CHAT` must be the forum's numeric `-100...` ID. Keep the receipt file outside Git and reuse it for the same operation: confirmed reruns return the saved root ID, and unconfirmed attempts block further creation. After a lost response or interruption, inspect the forum before considering a new operation. See [creating a forum topic](skills/tg-account/SKILL.md#creating-a-forum-topic) for limits, permissions and recovery.

## Usage

```text
Add Telegram error alerts to this project
Announce the verified deploy in the operations topic
Export last week of the work chat
Create a Telegram group with @alice, pin the agenda and a checklist
```

## License

MIT
