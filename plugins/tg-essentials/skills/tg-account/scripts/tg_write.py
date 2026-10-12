"""Write to Telegram as a tdata account: groups, messages, checklists, pins, chat photos.

Every call acts as the account owner and is seen by everyone in the chat. Show the owner
the exact target and text and get a yes before running it.

Usage:
  tg_write.py group TITLE MEMBER [MEMBER ...]   create a basic group, print its id
  tg_write.py send CHAT FILE [--pin] [--topic ID]  send FILE (UTF-8, Markdown), print message id
  tg_write.py edit CHAT MSG_ID FILE             replace the text of your own message
  tg_write.py todo CHAT FILE [--pin] [--topic ID]  send a native checklist (needs Telegram Premium)
  tg_write.py photo CHAT IMAGE                  set the group or channel photo
Every command takes --account ID; it is required when tdata holds more than one account.

MEMBER and CHAT: @username, t.me link or numeric id from tg_find.py.
TOPIC: a forum topic ID from tg_find.py --topics CHAT; 1 is General.
Checklist FILE: first line is the title, each next line one task. Telegram's limits (app config,
Bot API docs at the time of writing): title 1-255 chars, 1-30 tasks, task 1-100 chars.
A task starting with "[x] " is sent already ticked; "[ ] " is optional for open ones.
Members of the chat can tick tasks; they cannot add new ones.
"""
import argparse, asyncio, pathlib, sys
from telethon import functions, types
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


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("group")
    g.add_argument("title")
    g.add_argument("members", nargs="+")
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
        asyncio.run(in_chat({"send": send, "edit": edit, "todo": todo, "photo": photo}[a.cmd]))
