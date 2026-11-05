"""Export a Telegram chat to per-day text files.

Usage: tg_export.py CHAT SINCE OUT [ACCOUNT_ID] [--no-transcribe]
  CHAT        @username, t.me link or numeric id (-100..., user id for a DM); see tg_find.py
  SINCE       first day to keep, YYYY-MM-DD (local time)
  OUT         output dir, one YYYY-MM-DD.txt per day
  ACCOUNT_ID  configured account to read with; default: first account that can open CHAT
  --no-transcribe  skip automatic voice and video-note transcription

Line format, sorted by id, local time:  [HH:MM] #id ->#reply Name: text

Pagination is manual: on large forums Telegram answers MSGID_DECREASE_RETRY for some
offsets. Telethon's iter_messages gives up after 6 tries, so we step offset_id down by 7
and carry on. Each step can skip up to 7 messages; the skip count is printed at the end.
"""
import argparse, asyncio, collections, datetime as dt, os
from pathlib import Path
from telethon import errors, utils

async def main(chat, since, out, acc=None, transcribe=True):
    from tgsess import name, open_chat
    since = dt.datetime.fromisoformat(since).astimezone()
    os.makedirs(out, exist_ok=True)
    c, ent, acc = await open_chat(chat, acc)
    print(f"account {acc}: {name(ent)}", flush=True)
    days = collections.defaultdict(list)
    n = offset = skips = transcribed = failures = 0
    transcriber = None
    try:
        if transcribe:
            from tg_transcribe import Transcriber
            transcriber = Transcriber(Path(out) / ".transcripts" / str(acc) / str(utils.get_peer_id(ent)))
        done = False
        while not done:
            try:
                batch = await c.get_messages(ent, limit=100, offset_id=offset)
            except errors.MsgidDecreaseRetryError:  # its str() carries no error code, match the class
                if not offset:
                    offset = (await c.get_messages(ent, limit=1))[0].id + 1
                offset -= 7
                skips += 1
                await asyncio.sleep(1)
                continue
            if not batch:
                break
            for m in batch:
                t = m.date.astimezone()
                if t < since:
                    done = True
                    break
                txt = (m.message or "").replace("\n", " ").strip()
                kind = "voice" if m.voice else "video note" if m.video_note else None
                if transcriber and kind:
                    try:
                        speech = await transcriber.transcribe(c, m)
                        if speech:
                            note = f"[{kind}] {speech}"
                            transcribed += 1
                        else:
                            note = f"[{kind}: no speech detected]"
                            failures += 1
                    except Exception as ex:
                        note = f"[{kind}: transcription failed ({type(ex).__name__})]"
                        failures += 1
                    txt = f"{txt} {note}".strip()
                txt = txt or ("[media]" if m.media else "")
                if not txt:
                    continue
                head = f"[{t:%H:%M}] #{m.id}"
                if m.reply_to and getattr(m.reply_to, "reply_to_msg_id", None):
                    head += f" ->#{m.reply_to.reply_to_msg_id}"
                days[f"{t:%Y-%m-%d}"].append((m.id, f"{head} {name(m.sender)}: {txt}"))
                n += 1
            offset = batch[-1].id
            if n % 5000 < 100:
                print("...", n, f"{t:%Y-%m-%d %H:%M}", "skips", skips, flush=True)
            await asyncio.sleep(0.25)
    finally:
        try:
            if transcriber:
                await transcriber.close()
        finally:
            await c.disconnect()
    for d, lines in days.items():
        with open(os.path.join(out, d + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(line for _, line in sorted(dict(lines).items())))
    rng = f"{min(days)}..{max(days)}" if days else "empty"
    summary = f"messages={n} days={len(days)} range={rng} skips={skips}"
    if transcribe:
        summary += f" transcribed={transcribed} transcription_failures={failures}"
    print(summary)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chat")
    parser.add_argument("since")
    parser.add_argument("out")
    parser.add_argument("account", nargs="?")
    parser.add_argument("--transcribe", action=argparse.BooleanOptionalAction, default=True,
                        help="Transcribe voice and video notes locally (enabled by default)")
    args = parser.parse_args()
    from tgsess import session_lock
    with session_lock():
        asyncio.run(main(args.chat, args.since, args.out, args.account, args.transcribe))
