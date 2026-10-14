"""Offline creation tests with real Telegram requests and local operation receipts."""
import contextlib
import asyncio
import datetime as dt
import io
import json
import pathlib
import runpy
import sys
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from telethon import TelegramClient, errors, functions, types
from telethon.extensions import BinaryReader
from telethon.tl.custom import ParticipantPermissions
import tg_write
import tgsess


DATE = dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
CHAT = "-1000000000042"
FORUM = types.Channel(id=42, title="Example forum", photo=types.ChatPhotoEmpty(),
                      date=DATE, forum=True, megagroup=True)


def created(title="Планы 🌿", chat=42, root=37):
    message = types.MessageService(id=root, peer_id=types.PeerChannel(chat), date=DATE,
                                   action=types.MessageActionTopicCreate(title=title, icon_color=0x6FB9F0))
    return types.UpdateNewChannelMessage(message=message, pts=1, pts_count=1)


class Client:
    def __init__(self, response=None, failure=None, participant=None):
        self.requests = []
        self.failure = failure
        self.response = response if response is not None else SimpleNamespace(updates=[created()])
        self.get_me = AsyncMock(return_value=types.User(id=7))
        self.get_input_entity = AsyncMock(return_value=types.InputPeerChannel(42, 1))
        self.get_permissions = AsyncMock(return_value=ParticipantPermissions(
            participant or types.ChannelParticipant(user_id=7, date=DATE), chat=False))
        self.disconnect = AsyncMock()

    async def __call__(self, request):
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return self.response


class CreateTopic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.operation = pathlib.Path(self.temp.name) / "topic.jsonl"
        self.args = SimpleNamespace(chat=CHAT, account="7", title="Планы 🌿", operation=str(self.operation))
        self.output = io.StringIO()
        self.stderr = io.StringIO()

    async def write(self, client=None, entity=FORUM):
        client = client or Client()
        with patch.object(tg_write, "a", self.args, create=True), \
             patch.object(tg_write, "open_chat", AsyncMock(return_value=(client, entity, "7"))), \
             contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.stderr):
            self.assertTrue(hasattr(tg_write, "create_topic"), "writer must support create_topic")
            await tg_write.in_chat(tg_write.create_topic)
        return client

    async def test_unicode_request_returns_root_and_confirmed_rerun_does_not_write(self):
        client = await self.write()
        self.assertEqual(len(client.requests), 1)
        with BinaryReader(bytes(client.requests[0])) as reader:
            wire = reader.tgread_object()
        self.assertIsInstance(wire, functions.messages.CreateForumTopicRequest)
        self.assertEqual(wire.peer.channel_id, 42)
        self.assertEqual(wire.title, "Планы 🌿")
        self.assertGreater(wire.random_id, 0)
        self.assertIn("topic=37", self.output.getvalue())
        records = [json.loads(line) for line in self.operation.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["account"], 7)
        self.assertEqual(records[0]["chat"], CHAT)
        self.assertEqual(records[0]["random_id"], wire.random_id)
        self.assertEqual(records[-1]["topic"], 37)
        second = await self.write()
        self.assertEqual(second.requests, [])
        client.disconnect.assert_awaited_once()

    async def test_unknown_or_interrupted_result_blocks_retries(self):
        for failure in (TimeoutError(), errors.ServerError(None, "INTERNAL", 500), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                self.operation.unlink(missing_ok=True)
                client = Client(failure=failure)
                with self.assertRaises(BaseException):
                    await self.write(client)
                self.assertTrue(self.operation.exists())
                second = Client()
                with self.assertRaises(SystemExit) as error:
                    await self.write(second)
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(second.requests, [])
                client.disconnect.assert_awaited_once()

    async def test_wrong_account_or_forum_never_writes(self):
        for entity, user in ((FORUM, 8), (types.User(id=42), 7),
                             (types.Channel(id=43, title="Other", photo=types.ChatPhotoEmpty(), date=DATE, forum=True, megagroup=True), 7),
                             (types.Channel(id=42, title="Channel", photo=types.ChatPhotoEmpty(), date=DATE), 7)):
            with self.subTest(entity=entity, user=user):
                client = Client()
                client.get_me.return_value = types.User(id=user)
                with self.assertRaises(SystemExit):
                    await self.write(client, entity)
                self.assertEqual(client.requests, [])
                self.assertFalse(self.operation.exists())
                client.disconnect.assert_awaited_once()

    async def test_restricted_or_departed_members_never_write(self):
        participants = [
            types.ChannelParticipantBanned(peer=types.PeerUser(7), kicked_by=1, date=DATE,
                                          banned_rights=types.ChatBannedRights(until_date=None, manage_topics=True)),
            types.ChannelParticipantLeft(peer=types.PeerUser(7)),
        ]
        for participant in participants:
            with self.subTest(participant=participant):
                client = Client(participant=participant)
                with self.assertRaises(SystemExit):
                    await self.write(client)
                self.assertEqual(client.requests, [])
                self.assertFalse(self.operation.exists())

    async def test_admin_can_use_default_topic_permission_without_explicit_admin_right(self):
        admin = types.ChannelParticipantAdmin(user_id=7, promoted_by=1, date=DATE,
                                             admin_rights=types.ChatAdminRights(change_info=True))
        await self.write(Client(participant=admin))
        self.assertIn("topic=37", self.output.getvalue())
        self.operation.unlink()
        forum = types.Channel(id=42, title="Forum", photo=types.ChatPhotoEmpty(), date=DATE,
                              forum=True, megagroup=True,
                              default_banned_rights=types.ChatBannedRights(until_date=None, manage_topics=True))
        client = Client(participant=admin)
        with self.assertRaises(SystemExit):
            await self.write(client, forum)
        self.assertEqual(client.requests, [])

    async def test_real_transport_retry_then_refusal_stays_unknown(self):
        client = TelegramClient(None, 1, "offline", raise_last_call_error=True)
        fixture = Client()
        client.get_me, client.get_permissions = fixture.get_me, fixture.get_permissions
        client.get_input_entity, client.disconnect = fixture.get_input_entity, fixture.disconnect
        outcomes = iter([errors.ServerError(None, "INTERNAL", 500), errors.ChatWriteForbiddenError(None)])
        requests = []
        def send(request, ordered=False):
            requests.append(request.random_id)
            future = asyncio.get_running_loop().create_future()
            future.set_exception(next(outcomes))
            return future
        client._sender = SimpleNamespace(send=send)
        with patch("telethon.client.users.asyncio.sleep", AsyncMock()), \
             self.assertLogs("telethon.client.users", level="WARNING"):
            with self.assertRaises(SystemExit) as error:
                await self.write(client)
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])
        second = Client()
        with self.assertRaises(SystemExit):
            await self.write(second)
        self.assertEqual(second.requests, [])

    async def test_default_topic_ban_blocks_member_but_owner_can_create(self):
        forum = types.Channel(id=42, title="Forum", photo=types.ChatPhotoEmpty(), date=DATE,
                              forum=True, megagroup=True,
                              default_banned_rights=types.ChatBannedRights(until_date=None, manage_topics=True))
        with self.assertRaises(SystemExit):
            await self.write(entity=forum)
        owner = types.ChannelParticipantCreator(user_id=7, admin_rights=types.ChatAdminRights())
        await self.write(Client(participant=owner), forum)
        self.assertIn("topic=37", self.output.getvalue())

    async def test_rpc_refusal_and_missing_or_wrong_updates_keep_retry_guard(self):
        clients = [Client(failure=errors.ChatWriteForbiddenError(None)),
                   Client(response=SimpleNamespace(updates=[])),
                   Client(response=SimpleNamespace(updates=[created(chat=43)])),
                   Client(response=SimpleNamespace(updates=[created(title="Other")])),
                   Client(response=SimpleNamespace(updates=[created(), created(root=38)]))]
        for client in clients:
            with self.subTest(client=client):
                self.operation.unlink(missing_ok=True)
                with self.assertRaises(SystemExit) as error:
                    await self.write(client)
                self.assertEqual(error.exception.code, 2)
                second = Client()
                with self.assertRaises(SystemExit):
                    await self.write(second)
                self.assertEqual(second.requests, [])

    async def test_receipt_cannot_be_rebound_or_overwritten(self):
        await self.write()
        original = self.operation.read_bytes()
        self.args.title = "Another topic"
        with self.assertRaises(SystemExit):
            await self.write()
        self.assertEqual(self.operation.read_bytes(), original)
        self.operation.write_text("partial", encoding="utf-8")
        client = Client()
        with self.assertRaises(SystemExit):
            await self.write(client)
        self.assertEqual(client.requests, [])

    async def test_lost_receipt_reuses_request_identity_for_server_deduplication(self):
        topics = {}
        async def server(instance, request):
            instance.requests.append(request)
            root = topics.setdefault(request.random_id, 37 + len(topics))
            return SimpleNamespace(updates=[created(root=root)])
        with patch.object(Client, "__call__", server):
            first = await self.write()
            self.operation.unlink()  # Simulate loss of the new directory entry after a power failure.
            second = await self.write()
        self.assertEqual(len(topics), 1)
        self.assertEqual(first.requests[0].random_id, second.requests[0].random_id)
        self.assertNotIn("topic=38", self.output.getvalue())

    async def test_distinct_operation_paths_get_distinct_request_ids(self):
        first = await self.write()
        self.args.operation = str(self.operation.with_name("second.jsonl"))
        second = await self.write()
        self.assertNotEqual(first.requests[0].random_id, second.requests[0].random_id)

    async def test_receipt_failure_prevents_dispatch_and_claim_race_does_not_overwrite(self):
        client = Client()
        with patch.object(tg_write.os, "fsync", side_effect=OSError("disk full")):
            with self.assertRaises(SystemExit):
                await self.write(client)
        self.assertEqual(client.requests, [])
        self.operation.unlink()
        async def race(entity):
            self.operation.write_text("another operation", encoding="utf-8")
            return types.InputPeerChannel(42, 1)
        client.get_input_entity.side_effect = race
        with self.assertRaises(SystemExit):
            await self.write(client)
        self.assertEqual(client.requests, [])
        self.assertEqual(self.operation.read_text(encoding="utf-8"), "another operation")

    async def test_failed_confirmation_save_keeps_root_visible_and_blocks_rerun(self):
        with patch.object(tg_write.os, "fsync", side_effect=[None, OSError("disk full")]):
            with self.assertRaises(SystemExit):
                await self.write()
        self.assertIn("topic=37", self.output.getvalue())
        second = await self.write()
        self.assertEqual(second.requests, [])

    async def test_permission_lookup_failure_prevents_dispatch(self):
        client = Client()
        client.get_permissions.side_effect = errors.ChannelPrivateError(None)
        with self.assertRaises(errors.ChannelPrivateError):
            await self.write(client)
        self.assertEqual(client.requests, [])
        self.assertFalse(self.operation.exists())
        client.disconnect.assert_awaited_once()

    async def test_message_id_mapping_selects_only_this_requests_root(self):
        client = Client()
        async def response(instance, request):
            client.requests.append(request)
            return SimpleNamespace(updates=[created(), created(root=900),
                                   types.UpdateMessageID(id=37, random_id=request.random_id)])
        with patch.object(Client, "__call__", response):
            await self.write(client)
        self.assertIn("topic=37", self.output.getvalue())
        self.assertNotIn("topic=900", self.output.getvalue())


class CreateTopicCLI(unittest.TestCase):
    def test_cli_accepts_large_account_id_and_creates_only_in_selected_forum(self):
        with TemporaryDirectory() as temp:
            operation = str(pathlib.Path(temp) / "operation.jsonl")
            client = Client()
            client.get_me.return_value = types.User(id=5000000007)
            argv = [tg_write.__file__, "topic", CHAT, "Планы 🌿", "--account", "5000000007", "--operation", operation]
            with patch.object(sys, "argv", argv), \
                 patch.object(tgsess, "open_chat", AsyncMock(return_value=(client, FORUM, 5000000007))) as connection, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                runpy.run_path(tg_write.__file__, run_name="__main__")
            connection.assert_awaited_once_with(CHAT, 5000000007)
            self.assertIn("topic=37", output.getvalue())
            self.assertEqual(len(client.requests), 1)

    def test_validation_rejects_ambiguous_destinations_and_titles_before_connecting(self):
        base = [str(pathlib.Path(tg_write.__file__)), "topic", CHAT, "Example", "--account", "7", "--operation", "example.jsonl"]
        variants = [base[:4] + base[6:], base[:6],
                    base[:2] + ["@forum"] + base[3:],
                    base[:2] + ["42"] + base[3:],
                    base[:3] + [" "] + base[4:],
                    base[:3] + ["а" * 65] + base[4:],
                    base[:3] + ["line\nbreak"] + base[4:],
                    base[:3] + ["line\x85break"] + base[4:]]
        variants.extend(base[:5] + [value] + base[6:] for value in ("0", "-7", str(2**63), "٧"))
        for argv in variants:
            with self.subTest(argv=argv), patch.object(sys, "argv", argv), \
                 patch.object(tgsess, "open_chat", AsyncMock(side_effect=AssertionError("invalid inputs must not connect"))) as connection, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runpy.run_path(tg_write.__file__, run_name="__main__")
                self.assertEqual(error.exception.code, 2)
                connection.assert_not_awaited()

    def test_title_accepts_exact_utf8_byte_boundary(self):
        for title in ("a" * 128, "а" * 64, "🌿" * 32):
            with self.subTest(title=title):
                self.assertEqual(tg_write.topic_title(title), title)


if __name__ == "__main__":
    unittest.main()
