---
name: tg-announce
description: Compose and send a short Telegram deployment announcement, or send an operational note, through an existing bot. Use for "announce this deploy", "post release summary" or "send a heads-up"; keep runtime error alerts in tg-alerts.
argument-hint: "[announce|note|check] <message-file>"
---

# Telegram deployment announcements

Use one workflow in Claude Code and Codex. Resolve bundled paths from this installed
`SKILL.md` and use the current host's file, deployment and shell tools. Run the shipped
[sender](scripts/tg_announce.py) with Python 3.10 or newer; report a missing Python
runtime and stop. Keep the executable in the installed plugin, rather than generating
or copying it into the consuming project. It uses only the standard library.

## 1. Establish the destination and deployed facts

Identify the project, environment, audience, destination chat and optional forum topic.
Use the bot and `ALERT_BOT_TOKEN`, `ALERT_CHAT_ID`, `ALERT_THREAD_ID` contract from
[tg-alerts](../tg-alerts/SKILL.md#phase-2-create-alert-bot). If setup is missing, follow
its bot creation and chat/topic discovery phases, then return here. Reuse the existing
operational bot and keep credentials in the environment or the project's private `.env`.

Read deployment evidence with the available host tools. Establish the revision previously
deployed and the revision actually deployed now, then read their difference. A working-tree
diff, branch HEAD or merged PR alone does not establish what reached the environment.
If either revision or deploy verification is unavailable, report the missing evidence
and stop before sending.

Use the deployed revision plus destination (chat and topic) as the message identity.
Read the consuming release flow's prior result for that identity before a rerun:

- `SENT`: report the existing message ID and skip another send.
- `UNKNOWN`: stop for a person to check the destination and reconcile delivery.
- `NOT_SENT`: keep the saved file available for a deliberate retry.

Let the consuming release flow retain these results with its existing deploy evidence.
The sender stores no receipts and does not deduplicate reruns itself.

## 2. Compose for the audience

Name the audience first: product users, or developers and operators. Keep changes they
can observe and actions they must take. Describe outcomes, using commit types only as
a first filter. Humanize the prose with the current host's humanizer capability before
saving it. If unavailable, self-edit for plain language and report that fallback.

If nothing qualifies, use the exact empty-release form below. Do not invent bullets.
For an infrastructure-only deployment where no change passes the audience test, collapse
the whole deployment into one bullet saying it completed and the audience's work is
unaffected. For a publishing service, use the infrastructure example below. Keep the
cause, previous incident, before/after comparison and mechanism in the PR, outside the
announcement. The shape checker cannot perform this audience test.

Save the complete rendered message to a private UTF-8 file in the consuming project's
existing release-output location. Use the same file for every release channel.

## 3. Validate announcement-v1

Run the callable `validate_announcement(text)` on the rendered message before sending when integrating with
a release flow, or run the credential-free `check` command on the saved file:

```text
python "<absolute installed skill directory>/scripts/tg_announce.py" check "<message-file>"
```

The named schema accepts this shape:

```html
🚀 v1.2.3
<pre><code>• No audience-visible changes.</code></pre>
```

For the infrastructure-only publishing case:

```html
🛠️ abc1234
<pre><code>• Deployment completed; publishing is unaffected.</code></pre>
```

- Header: one of `🚀`, `✅`, `📦`, `🛠`/`🛠️`, `🟢`, one space, then a SemVer tag
  (optional `v`, prerelease/build allowed) or a 7-40 character hexadecimal revision.
- Body: exactly one literal `<pre><code>` block; keep other markup and prose outside
  the saved message. Blank lines inside the block and one final newline are allowed.
- Include 1-8 nonempty lines, each starting with `• ` and containing one sentence.
  Keep each visible line, including its marker, at or below 200 Unicode code points.
- End each bullet with `.`, `!` or `?`. A sentence terminator followed by whitespace
  inside the bullet is rejected; dots within decimals and versions are allowed.
  Reword abbreviations such as `e.g.` when this conservative rule rejects them.
- HTML-escape bullet text. Use `&lt;`, `&gt;`, `&amp;`, `&quot;` or valid numeric
  entities. Keep control characters, hidden formatting and encoded line breaks out.
- Use the canonical empty-release bullet alone. The checker validates shape, not meaning.

On rejection, read every reported problem and the literal example, fix the saved file,
then check again. Keep schema rules in the shipped checker; callers supply no regex,
custom limit or bypass flag. A different contract needs a new named schema.

## 4. Send after verified deployment

Confirm that the user's existing authorization covers this destination, purpose and
message. If it does, proceed; otherwise show the exact file and destination and obtain
approval before sending. End-user broadcasts require their own authorization.

Keep the working directory on the consuming project so `.env` fallback reads that
project's configuration. Environment values override `.env` per key; an explicitly
empty value is an error. `.env` accepts literal `KEY=VALUE` assignments and optional
quotes/comments, with no shell execution or variable expansion.

```text
python "<absolute installed skill directory>/scripts/tg_announce.py" announce "<message-file>"
```

`announce` checks the schema again before opening a connection. It normalizes CRLF to
LF, checks the 4096-character visible-text limit and sends one JSON POST with a timeout.
It escapes and encodes without shell interpolation, follows no redirects and retries
nothing. Keep tokens, request URLs and raw API error bodies out of reports.

| Result | Exit | Release-flow action |
|--------|------|---------------------|
| `RESULT=SENT MESSAGE_ID=<id>` | 0 | Record confirmed delivery for this identity. |
| `RESULT=NOT_SENT REASON=<reason>` | 1 | Report the local rejection or confirmed API refusal; preserve the file. |
| `RESULT=UNKNOWN REASON=delivery_unconfirmed` | 2 | Report uncertain delivery; preserve the file and stop automatic resends. |

Keep announcement failure separate from the already completed deployment: `NOT_SENT`
and `UNKNOWN` appear in the release report and must not mark deployed code as failed.
A timeout can follow delivery. Before a manual retry after `UNKNOWN`, have a person
check the destination; show the saved file and retry command without credentials.

## Operational notes

For a heads-up or question covered by the user's send authorization, save arbitrary
plain text to a UTF-8 file and run:

```text
python "<absolute installed skill directory>/scripts/tg_announce.py" note "<message-file>"
```

`note` HTML-escapes the whole file and uses the same destination and delivery protocol.
Use `announce` for release notes. Runtime error alerts keep their existing `tg-alerts`
deduplication and background delivery rules.
