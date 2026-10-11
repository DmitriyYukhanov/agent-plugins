"""Offline writer tests. Run with the skill venv: python -m unittest test_tg_write."""
import contextlib
import datetime as dt
import io
import pathlib
import runpy
import sys
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from telethon import TelegramClient, errors, functions, types
from telethon.extensions import BinaryReader
import tg_write
from tg_write import parse_todo


DATE = dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)
FORUM = types.Channel(id=42, title="Forum", photo=types.ChatPhotoEmpty(), date=DATE, forum=True, megagroup=True)


def topic(root=37, latest=900):
    return types.ForumTopic(
        id=root, date=DATE, peer=types.PeerChannel(42), title="HTML", icon_color=0,
        top_message=latest, read_inbox_max_id=0, read_outbox_max_id=0, unread_count=0,
        unread_mentions_count=0, unread_reactions_count=0, unread_poll_votes_count=0,
        from_id=types.PeerUser(1), notify_settings=types.PeerNotifySettings(),
    )


class OfflineClient(TelegramClient):
    """Use Telethon's real builders; replace only transport and response extraction."""
    def __init__(self, topics=None):
        super().__init__(None, 1, "test")
        self.requests = []
        self.topics = [topic()] if topics is None else topics
        self.disconnect = AsyncMock()
        self.pin_message = AsyncMock()
        self.sent = SimpleNamespace(id=501)

    async def get_input_entity(self, entity):
        return types.InputPeerChannel(42, 0)

    async def __call__(self, request):
        self.requests.append(request)
        if isinstance(request, functions.messages.GetForumTopicsByIDRequest):
            return SimpleNamespace(topics=self.topics)
        return object()

    def _get_response_message(self, request, result, entity):
        return self.sent


class TopicWrites(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = pathlib.Path(self.temp.name) / "post.md"
        self.file.write_text("**Hello** topic", encoding="utf-8")

    async def write(self, command, root=None, client=None, entity=FORUM, pin=False):
        client = client or OfflineClient()
        args = SimpleNamespace(chat="-10042", account="1", file=str(self.file),
                               topic=root, pin=pin, todo=parse_todo("Plan\n[x] done\nopen"))
        output = io.StringIO()
        self.output = output
        with patch.object(tg_write, "a", args, create=True), \
             patch.object(tg_write, "open_chat", AsyncMock(return_value=(client, entity, "1"))), \
             contextlib.redirect_stdout(output):
            await tg_write.in_chat(getattr(tg_write, command))
        return client, output.getvalue()

    async def test_real_send_and_media_requests_route_to_root_and_preserve_defaults(self):
        for command in ("send", "todo"):
            for root in (37, None, 1):
                with self.subTest(command=command, root=root):
                    client = OfflineClient([topic(root or 37)])
                    client, output = await self.write(command, root, client, pin=True)
                    request_type = functions.messages.SendMessageRequest if command == "send" else functions.messages.SendMediaRequest
                    request = next(r for r in client.requests if isinstance(r, request_type))
                    with BinaryReader(bytes(request)) as reader:
                        wire = reader.tgread_object()
                    if root == 37:
                        self.assertEqual(wire.reply_to.reply_to_msg_id, 37)
                        self.assertIsNone(wire.reply_to.top_msg_id)
                        self.assertIn("topic='HTML' (37)", output)
                    else:
                        self.assertIsNone(wire.reply_to)
                    lookups = [r for r in client.requests if isinstance(r, functions.messages.GetForumTopicsByIDRequest)]
                    self.assertEqual(len(lookups), int(root is not None))
                    if lookups:
                        self.assertEqual(lookups[0].topics, [root])
                    self.assertIn("message=501", output)
                    self.assertLess(output.index("message=501"), output.index("pinned"))
                    client.pin_message.assert_awaited_once_with(FORUM, client.sent, notify=False)
                    client.disconnect.assert_awaited_once()
                    if command == "send":
                        self.assertEqual(wire.message, "Hello topic")
                        self.assertTrue(wire.no_webpage)
                        self.assertIsInstance(wire.entities[0], types.MessageEntityBold)
                    else:
                        self.assertEqual(wire.media.todo.title.text, "Plan")
                        self.assertEqual([i.title.text for i in wire.media.todo.list], ["done", "open"])
                        tick = next(r for r in client.requests if isinstance(r, functions.messages.ToggleTodoCompletedRequest))
                        self.assertEqual((tick.msg_id, tick.completed, tick.incompleted), (501, [1], []))
                        self.assertLess(output.index("message=501"), output.index("ticked=1"))

    async def test_topic_validation_rejects_nonforums_and_missing_or_deleted_roots(self):
        nonforums = [types.User(id=2), types.Chat(id=2, title="Basic", photo=types.ChatPhotoEmpty(), participants_count=1, date=DATE, version=1),
                     types.Channel(id=2, title="Channel", photo=types.ChatPhotoEmpty(), date=DATE)]
        for command in ("send", "todo"):
            for entity, roots in [(e, [topic()]) for e in nonforums] + [
                (FORUM, []), (FORUM, [types.ForumTopicDeleted(37)]), (FORUM, [topic(900)]),
            ]:
                with self.subTest(command=command, entity=type(entity).__name__, roots=roots):
                    client = OfflineClient(roots)
                    with self.assertRaisesRegex(SystemExit, "forum|topic"):
                        await self.write(command, 37, client, entity)
                    self.assertFalse(any(isinstance(r, (functions.messages.SendMessageRequest, functions.messages.SendMediaRequest)) for r in client.requests))
                    client.pin_message.assert_not_awaited()
                    client.disconnect.assert_awaited_once()

    async def test_lookup_rpc_failure_disconnects_before_writing(self):
        client = OfflineClient()
        with patch.object(OfflineClient, "__call__", AsyncMock(side_effect=errors.ChannelPrivateError(None))):
            with self.assertRaises(errors.ChannelPrivateError):
                await self.write("send", 37, client)
        client.disconnect.assert_awaited_once()
        self.assertEqual(client.requests, [])

    async def test_pin_failure_keeps_sent_id_visible_without_a_second_send(self):
        client = OfflineClient()
        client.pin_message.side_effect = errors.ChatAdminRequiredError(None)
        with self.assertRaises(errors.ChatAdminRequiredError):
            await self.write("todo", 37, client, pin=True)
        self.assertIn("message=501", self.output.getvalue())
        self.assertEqual(sum(isinstance(r, functions.messages.SendMediaRequest) for r in client.requests), 1)
        client.disconnect.assert_awaited_once()


class TopicCLI(unittest.TestCase):
    def test_invalid_topic_ids_fail_before_account_access(self):
        for command in ("send", "todo"):
            for value in ("bad", "0", "-1", "2147483648"):
                with self.subTest(command=command, value=value), \
                     patch.object(sys, "argv", ["tg_write.py", command, "chat", "file", "--topic", value]), \
                     patch("tgsess.accounts", Mock(side_effect=AssertionError("must not access tdata"))), \
                     contextlib.redirect_stderr(io.StringIO()) as output:
                    with self.assertRaises(SystemExit) as error:
                        runpy.run_path(tg_write.__file__, run_name="__main__")
                    self.assertEqual(error.exception.code, 2)
                    self.assertIn("topic ID must", output.getvalue())


class ParseTodo(unittest.TestCase):
    def test_title_tasks_and_marks(self):
        title, tasks = parse_todo("  Plan \n\n[x] done one\n[ ] open one\n[X]  upper done\nplain\n")
        self.assertEqual(title, "Plan")
        self.assertEqual(tasks, [("done one", True), ("open one", False), ("upper done", True), ("plain", False)])

    def test_bracket_text_that_is_not_a_mark_stays(self):
        self.assertEqual(parse_todo("T\n[x]ray scan\n[draft] notes")[1], [("[x]ray scan", False), ("[draft] notes", False)])

    def test_needs_a_task(self):
        for text in ("", "only title", "\n  \n", "T\n[x]", "T\n[ ]  "):
            with self.assertRaises(ValueError):
                parse_todo(text)

    def test_telegram_limits(self):
        self.assertEqual(len(parse_todo("T\n" + "\n".join(["a" * 100] * 30))[1]), 30)
        for text in ("T\n" + "t\n" * 31, "T\n" + "a" * 101, "a" * 256 + "\ntask"):
            with self.assertRaises(ValueError):
                parse_todo(text)


if __name__ == "__main__":
    unittest.main()
