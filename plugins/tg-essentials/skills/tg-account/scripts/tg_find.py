"""List tdata accounts and, per account, the dialogs whose title or @username contains any keyword.

Usage: tg_find.py [keyword ...]      (no keywords = accounts only)
       tg_find.py --topics CHAT [--account ID]  list a forum's topic names and IDs
"""
import argparse, asyncio, sys
from telethon import errors, functions, types
from tgsess import accounts, client_for, name, open_chat


async def topics(chat, account=None):
    c, ent, acc = await open_chat(chat, account)
    try:
        if not isinstance(ent, types.Channel) or not ent.forum:
            sys.exit("--topics requires a forum group")
        print(f"account={acc} chat={name(ent)!r} ({ent.id})")
        offset_date, offset_id, offset_topic = None, 0, 0
        seen = set()
        while True:
            result = await c(functions.messages.GetForumTopicsRequest(
                peer=ent, offset_date=offset_date, offset_id=offset_id, offset_topic=offset_topic, limit=100))
            if not result.topics:
                if len(seen) < result.count:
                    sys.exit("topic listing incomplete: Telegram returned an empty page")
                break
            page = [t for t in result.topics if isinstance(t, types.ForumTopic)]
            if not page:
                sys.exit("topic listing incomplete: no topic available for pagination")
            previous_count = len(seen)
            for t in page:
                if t.id not in seen:
                    print(f"  topic={t.id} title={t.title!r}")
                    seen.add(t.id)
            if len(seen) == previous_count:
                sys.exit("topic listing incomplete: pagination did not advance")
            if len(seen) >= result.count:
                break
            last = page[-1]
            # Activity ordering needs the latest message date, not the topic's creation date.
            date = last.date if result.order_by_create_date else next(
                (m.date for m in result.messages if m.id == last.top_message), None)
            if date is None:
                sys.exit("topic listing incomplete: pagination date is missing")
            offset_date, offset_id, offset_topic = date, last.top_message, last.id
    except errors.RPCError as ex:
        print(f"  topics unavailable right now: {ex}; retry later")
    finally:
        await c.disconnect()


async def main(keywords):
    kw = [k.lower().lstrip("@") for k in keywords]
    for a in accounts():
        print(f"account {a.UserId} (dc {a.MainDcId})")
        if not kw:
            continue
        c = client_for(a.UserId)
        await c.connect()
        try:
            async for d in c.iter_dialogs():
                e = d.entity
                user = getattr(e, "username", None)
                if any(k in f"{d.name} {user or ''}".lower() for k in kw):
                    print(f"  {d.id}  {d.name!r}  {'@' + user if user else ''}{'  forum' if getattr(e, 'forum', False) else ''}")
        except errors.RPCError as ex:  # e.g. MSGID_DECREASE_RETRY outlasting Telethon's retries
            print(f"  dialogs unavailable right now: {ex}; retry later")
        finally:
            await c.disconnect()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("keywords", nargs="*")
    p.add_argument("--topics", metavar="CHAT")
    p.add_argument("--account", metavar="ID")
    a = p.parse_args()
    if a.topics is not None:
        if a.keywords:
            p.error("use --topics CHAT without keyword arguments")
        asyncio.run(topics(a.topics, a.account))
    else:
        if a.account is not None:
            p.error("--account requires --topics CHAT")
        asyncio.run(main(a.keywords))
