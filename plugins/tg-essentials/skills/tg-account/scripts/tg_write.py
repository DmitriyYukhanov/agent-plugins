"""Write to Telegram as a tdata account: groups, topics, messages, checklists, pins, photos.

Every call acts as the account owner and is seen by everyone in the chat. Show the owner
the exact target and text and get a yes before running it.

Usage:
  tg_write.py group TITLE MEMBER [MEMBER ...]   create a basic group, print its id
  tg_write.py topic CHAT TITLE --account ID --operation FILE  create a forum topic, print root ID
  tg_write.py send CHAT FILE [--pin] [--topic ID]  send FILE (UTF-8, Markdown), print message id
  tg_write.py edit CHAT MSG_ID FILE             replace the text of your own message
  tg_write.py todo CHAT FILE [--pin] [--topic ID]  send a native checklist (needs Telegram Premium)
  tg_write.py photo CHAT IMAGE                  set the group or channel photo
Every command takes --account ID; it is required when tdata holds more than one account.

MEMBER and CHAT: @username, t.me link or numeric id from tg_find.py.
TOPIC: a forum topic ID from tg_find.py --topics CHAT; 1 is General.
Creating a topic requires a numeric -100... forum ID and an explicit account.
Keep the operation receipt outside Git; reuse its path for the same operation.
After an unknown result (exit 2), inspect the forum before any new operation.
Checklist FILE: first line is the title, each next line one task. Telegram's limits (app config,
Bot API docs at the time of writing): title 1-255 chars, 1-30 tasks, task 1-100 chars.
A task starting with "[x] " is sent already ticked; "[ ] " is optional for open ones.
Members of the chat can tick tasks; they cannot add new ones.
"""
import argparse, asyncio, hashlib, json, os, pathlib, sys, unicodedata
from telethon import errors, functions, types, utils
from tgsess import accounts, client_for, name, open_chat, peer, warm


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8").strip()


def twe(text):
    return types.TextWithEntities(text=text, entities=[])


def topic_id(value):
    try:
        value = int(value)
        if 1 <= value <= 2147483647:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("topic ID must be an integer from 1 to 2147483647")


def forum_id(value):
    if value.isascii() and value.startswith("-100") and value[4:].isdigit() and -(2**63) < int(value) < -1000000000000:
        return value
    raise argparse.ArgumentTypeError("use the numeric -100... forum ID from tg_find.py")


def account_id(value):
    if value.isascii() and value.isdigit() and 0 < int(value) < 2**63:
        return int(value)
    raise argparse.ArgumentTypeError("account ID must be a positive signed 64-bit integer")


def topic_title(value):
    if value.strip() and len(value.encode("utf-8")) <= 128 and not any(unicodedata.category(c) == "Cc" for c in value):
        return value
    raise argparse.ArgumentTypeError("topic title must be nonblank, at most 128 UTF-8 bytes, without control characters")


def parse_todo(text):
    """Checklist file -> (title, [(task, done), ...]), checked against Telegram's limits."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if len(lines) < 2:
        raise ValueError("checklist needs a title line and at least one task line")
    tasks = []
    for line in lines[1:]:
        mark = line[:3].lower()
        if mark in ("[x]", "[ ]") and line[3:4] in ("", " "):
            line, ticked = line[3:].strip(), mark == "[x]"
        else:
            ticked = False
        if not line:
            raise ValueError("empty task line")
        tasks.append((line, ticked))
    if len(lines[0]) > 255 or len(tasks) > 30 or any(len(t) > 100 for t, _ in tasks):
        raise ValueError("over Telegram's limits: title 255 chars, 30 tasks, 100 chars per task")
    return lines[0], tasks


async def group():
    c = client_for(a.account)
    await c.connect()
    try:
        refs = [peer(m) for m in a.members]
        await warm(c, refs)
        users = [await c.get_entity(r) for r in refs]
        r = await c(functions.messages.CreateChatRequest(users=users, title=a.title))
        chat = getattr(r, "updates", r).chats[0]
        for m in getattr(r, "missing_invitees", []):
            print(f"not added (their privacy settings): user {m.user_id}", file=sys.stderr)
        print(f"group={-chat.id} title={chat.title!r}")
    finally:
        await c.disconnect()


async def in_chat(act):
    c, ent, acc = await open_chat(a.chat, a.account)
    try:
        # The resolved target, so a wrong id shows up in the output, not only in the chat.
        print(f"account={acc} chat={name(ent)!r} ({ent.id})", flush=True)
        if getattr(a, "topic", None) is not None:
            if not isinstance(ent, types.Channel) or not ent.forum:
                sys.exit("--topic requires a forum group")
            result = await c(functions.messages.GetForumTopicsByIDRequest(peer=ent, topics=[a.topic]))
            topic = next((t for t in result.topics if isinstance(t, types.ForumTopic) and t.id == a.topic), None)
            if topic is None:
                sys.exit(f"topic {a.topic} not found in this forum; run tg_find.py --topics CHAT")
            print(f"topic={topic.title!r} ({topic.id})", flush=True)
        await act(c, ent)
    finally:
        await c.disconnect()


async def send(c, ent):
    m = await c.send_message(ent, read(a.file), link_preview=False, reply_to=None if a.topic == 1 else a.topic)
    print(f"message={m.id}", flush=True)  # before the pin: a failed pin must not invite a duplicate send
    if a.pin:
        await c.pin_message(ent, m, notify=False)
        print("pinned")


async def edit(c, ent):
    m = await c.edit_message(ent, a.msg_id, read(a.file), link_preview=False)
    print(f"message={m.id} edited")


async def todo(c, ent):
    title, tasks = a.todo
    items = [types.TodoItem(id=i, title=twe(text)) for i, (text, _) in enumerate(tasks, 1)]
    done = [i for i, (_, ticked) in enumerate(tasks, 1) if ticked]
    todo = types.TodoList(title=twe(title), list=items, others_can_complete=True)
    m = await c.send_file(ent, types.InputMediaTodo(todo=todo), reply_to=None if a.topic == 1 else a.topic)
    print(f"message={m.id} tasks={len(items)}", flush=True)  # before the follow-ups, as in send
    if done:
        await c(functions.messages.ToggleTodoCompletedRequest(peer=ent, msg_id=m.id, completed=done, incompleted=[]))
        print(f"ticked={len(done)}")
    if a.pin:
        await c.pin_message(ent, m, notify=False)
        print("pinned")


async def photo(c, ent):
    if isinstance(ent, types.User):
        sys.exit("photo works on groups and channels, not on a user")
    img = types.InputChatUploadedPhoto(file=await c.upload_file(a.image))
    if isinstance(ent, types.Channel):
        await c(functions.channels.EditPhotoRequest(channel=ent, photo=img))
    else:
        await c(functions.messages.EditChatPhotoRequest(chat_id=ent.id, photo=img))
    print("photo updated")


async def create_topic(c, ent):
    me = await c.get_me()
    if me is None or me.id != int(a.account):
        sys.exit("connected account differs from --account; no topic created")
    if not isinstance(ent, types.Channel) or not ent.megagroup or not ent.forum:
        sys.exit("topic requires an existing forum supergroup")
    if str(utils.get_peer_id(ent)) != a.chat:
        sys.exit("resolved forum differs from CHAT; no topic created")
    binding = {"account": me.id, "chat": a.chat, "title": a.title}
    receipt = pathlib.Path(a.operation).expanduser()
    unknown = f"UNKNOWN: inspect tg_find.py --topics {a.chat} --account {me.id}; keep {receipt} and do not create another operation"
    try:
        with receipt.open(encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
    except FileNotFoundError:
        records = None
    except (OSError, ValueError):
        sys.exit("cannot read operation receipt; no request sent")
    if records is not None:
        if not records or not isinstance(records[0], dict) or any(records[0].get(k) != v for k, v in binding.items()):
            sys.exit("operation receipt does not match account, forum and title; no request sent")
        if len(records) == 2 and isinstance(records[1], dict) and type(records[1].get("topic")) is int and 1 < records[1]["topic"] <= 2147483647:
            print(f"topic={records[1]['topic']} title={a.title!r} reused", flush=True)
            return
        print(unknown, file=sys.stderr)
        raise SystemExit(2)

    permissions = await c.get_permissions(ent, me)
    participant = permissions.participant
    if permissions.is_creator:
        allowed = True
    elif permissions.is_admin:
        allowed = bool(participant.admin_rights.manage_topics) or not (
            ent.default_banned_rights and ent.default_banned_rights.manage_topics)
    else:
        bans = [getattr(participant, "banned_rights", None), ent.default_banned_rights]
        allowed = not permissions.has_left and not ent.left and not any(
            b and (b.view_messages or b.send_messages or b.manage_topics) for b in bans)
    if not allowed:
        sys.exit("account cannot create topics in this forum; no request sent")
    target = await c.get_input_entity(ent)
    if not isinstance(target, types.InputPeerChannel) or target.channel_id != ent.id:
        sys.exit("input peer differs from forum; no request sent")
    # Preserve server deduplication if a crash loses the receipt's directory entry.
    operation_key = json.dumps([binding, os.path.normcase(str(receipt.resolve()))], ensure_ascii=False, sort_keys=True).encode("utf-8")
    random_id = (int.from_bytes(hashlib.sha256(operation_key).digest()[:8], "big") & ((1 << 63) - 1)) or 1
    request = functions.messages.CreateForumTopicRequest(peer=target, title=a.title,
                                                        icon_color=0x6FB9F0, random_id=random_id)
    # Exclusive, flushed receipt claims the operation before Telegram can accept it.
    try:
        with receipt.open("x", encoding="utf-8") as f:
            f.write(json.dumps({**binding, "random_id": random_id}, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        sys.exit("cannot claim operation receipt; no request sent (reuse the existing receipt)")
    try:
        result = await c(request)
    except errors.RPCError as ex:
        print(f"Telegram: {type(ex).__name__}", file=sys.stderr)
        # A final refusal cannot disprove completion during an earlier transport retry.
        print(unknown, file=sys.stderr)
        raise SystemExit(2)
    except (OSError, asyncio.TimeoutError):
        print(unknown, file=sys.stderr)
        raise SystemExit(2)
    updates = getattr(result, "updates", [])
    mapped = {u.id for u in updates if isinstance(u, types.UpdateMessageID) and u.random_id == random_id}
    roots = {u.message.id for u in updates if isinstance(u, types.UpdateNewChannelMessage)
             and isinstance(u.message, types.MessageService)
             and isinstance(u.message.peer_id, types.PeerChannel) and u.message.peer_id.channel_id == ent.id
             and isinstance(u.message.action, types.MessageActionTopicCreate) and u.message.action.title == a.title
             and 1 < u.message.id <= 2147483647}
    if mapped:
        roots &= mapped
    if len(roots) != 1:
        print(unknown, file=sys.stderr)
        raise SystemExit(2)
    root = roots.pop()
    print(f"topic={root} title={a.title!r}", flush=True)
    try:
        with receipt.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"topic": root}) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        sys.exit("topic created but receipt update failed; use the printed topic ID and never repeat the creation")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("group")
    g.add_argument("title")
    g.add_argument("members", nargs="+")
    ft = sub.add_parser("topic", help="create a topic in an existing forum after owner approval",
                        description="Create an approved forum topic. Keep the receipt on reruns; after exit 2, inspect the forum before any new operation.")
    ft.add_argument("chat", type=forum_id, help="numeric -100... forum ID from tg_find.py")
    ft.add_argument("title", type=topic_title, help="exact approved title, at most 128 UTF-8 bytes")
    ft.add_argument("--account", required=True, type=account_id, metavar="ID", help="explicit Telegram account ID")
    ft.add_argument("--operation", required=True, metavar="FILE", help="private receipt path for this operation; reuse on reruns")
    s = sub.add_parser("send")
    s.add_argument("chat")
    s.add_argument("file")
    s.add_argument("--pin", action="store_true")
    e = sub.add_parser("edit")
    e.add_argument("chat")
    e.add_argument("msg_id", type=int)
    e.add_argument("file")
    t = sub.add_parser("todo")
    t.add_argument("chat")
    t.add_argument("file")
    t.add_argument("--pin", action="store_true")
    for x in (s, t):
        x.add_argument("--topic", type=topic_id, metavar="ID", help="forum topic ID from tg_find.py --topics CHAT (1 is General)")
    ph = sub.add_parser("photo")
    ph.add_argument("chat")
    ph.add_argument("image")
    for x in (g, s, e, t, ph):
        x.add_argument("--account")
    a = p.parse_args()

    if a.account is None:
        ids = [x.UserId for x in accounts()]
        if len(ids) != 1:
            sys.exit(f"tdata holds accounts {ids}; pass --account to pick who writes")
        a.account = ids[0]
    if a.cmd == "todo":
        try:
            a.todo = parse_todo(read(a.file))  # fail on a bad file before connecting
        except ValueError as ex:
            sys.exit(f"checklist: {ex}")

    if a.cmd == "group":
        asyncio.run(group())
    else:
        asyncio.run(in_chat({"send": send, "edit": edit, "todo": todo, "photo": photo, "topic": create_topic}[a.cmd]))
