"""Offline scheduling checks with real TL serialization and durable receipts."""
import contextlib
import datetime as dt
import io
import pathlib
import runpy
import sys
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon import functions, types
from telethon.extensions import BinaryReader

import tg_write
from test_tg_write import FORUM, topic


class Client:
    def __init__(self, failure=None):
        self.requests = []
        self.failure = failure
        self.flood_sleep_threshold = 60
        self.get_me = AsyncMock(return_value=types.User(id=7))
        self.get_input_entity = AsyncMock(return_value=types.InputPeerChannel(42, 0))
        self.disconnect = AsyncMock()
        self.pin_message = AsyncMock()

    async def __call__(self, request):
        self.requests.append(request)
        if isinstance(request, functions.messages.GetForumTopicsByIDRequest):
            return SimpleNamespace(topics=[topic()])
        if self.failure:
            raise self.failure
        message = types.Message(id=501, peer_id=types.PeerChannel(42),
                                date=request.schedule_date, message=request.message,
                                reply_to=types.MessageReplyHeader(reply_to_msg_id=37))
        return SimpleNamespace(updates=[types.UpdateNewScheduledMessage(message)])


class ScheduledSend(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = pathlib.Path(self.temp.name) / "post.md"
        self.file.write_text("**Scheduled** report", encoding="utf-8")
        self.receipt = pathlib.Path(self.temp.name) / "scheduled.jsonl"
        self.args = SimpleNamespace(chat="-1000000000042", account="7", topic=37,
                                    file=str(self.file), pin=False, operation=str(self.receipt),
                                    schedule_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2))
        self.output = io.StringIO()

    async def write(self, client=None):
        client = client or Client()
        with patch.object(tg_write, "a", self.args, create=True), \
             patch.object(tg_write, "open_chat", AsyncMock(return_value=(client, FORUM, "7"))), \
             contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(io.StringIO()):
            await tg_write.in_chat(tg_write.send)
        return client

    async def test_server_queue_request_is_audible_routed_and_reused(self):
        client = await self.write()
        request = next(r for r in client.requests if isinstance(r, functions.messages.SendMessageRequest))
        with BinaryReader(bytes(request)) as reader:
            wire = reader.tgread_object()
        self.assertIsNotNone(wire.schedule_date)
        wire_time = wire.schedule_date
        if wire_time.tzinfo is None:
            wire_time = wire_time.replace(tzinfo=dt.timezone.utc)
        self.assertEqual(int(wire_time.timestamp()), int(self.args.schedule_at.timestamp()))
        self.assertFalse(wire.silent)
        self.assertEqual(wire.reply_to.reply_to_msg_id, 37)
        self.assertEqual(wire.message, "Scheduled report")
        self.assertIsInstance(wire.entities[0], types.MessageEntityBold)
        self.assertTrue(wire.no_webpage)
        self.assertEqual(client.flood_sleep_threshold, 0)
        self.assertIn("scheduled_message=501", self.output.getvalue())
        client.pin_message.assert_not_awaited()
        second = await self.write()
        self.assertFalse(any(isinstance(r, functions.messages.SendMessageRequest) for r in second.requests))
        self.assertIn("reused", self.output.getvalue())

    async def test_unknown_result_blocks_a_second_dispatch_and_changed_text(self):
        with self.assertRaises(SystemExit) as error:
            await self.write(Client(TimeoutError()))
        self.assertEqual(error.exception.code, 2)
        self.assertTrue(self.receipt.exists())
        second = Client()
        with self.assertRaises(SystemExit):
            await self.write(second)
        self.assertFalse(any(isinstance(r, functions.messages.SendMessageRequest) for r in second.requests))
        self.file.write_text("Different report", encoding="utf-8")
        with self.assertRaises(SystemExit):
            await self.write()

    async def test_stale_dates_pin_and_wrong_account_never_write(self):
        for change in ("stale", "pin", "account"):
            with self.subTest(change=change):
                self.args.pin = change == "pin"
                self.args.schedule_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5 if change == "stale" else 120)
                client = Client()
                if change == "account":
                    client.get_me.return_value = types.User(id=8)
                with self.assertRaises(SystemExit):
                    await self.write(client)
                self.assertFalse(self.receipt.exists())
                self.assertFalse(any(isinstance(r, functions.messages.SendMessageRequest) for r in client.requests))

    async def test_missing_confirmation_retains_unknown_receipt(self):
        client = Client()
        with patch.object(Client, "__call__", AsyncMock(return_value=SimpleNamespace(updates=[]))):
            with patch.object(tg_write, "a", self.args, create=True), contextlib.redirect_stderr(io.StringIO()):
                self.assertTrue(hasattr(tg_write, "scheduled_send"))
                with self.assertRaises(SystemExit) as error:
                    await tg_write.scheduled_send(client, FORUM)
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(len(self.receipt.read_text().splitlines()), 1)

    async def test_torn_receipt_is_unknown_and_never_dispatches(self):
        self.receipt.write_text('{"account":7}\n{"scheduled_message":', encoding="utf-8")
        client = Client()
        with self.assertRaises(SystemExit) as error:
            await self.write(client)
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(any(isinstance(r, functions.messages.SendMessageRequest) for r in client.requests))

    async def test_dispatch_timeout_leaves_a_receipt_and_no_blind_retry(self):
        async def timeout(coro, timeout):
            coro.close()
            self.assertGreater(timeout, 0)
            self.assertLess(timeout, 105)
            raise TimeoutError()

        with patch.object(tg_write.asyncio, "wait_for", side_effect=timeout):
            with self.assertRaises(SystemExit) as error:
                await self.write()
        self.assertEqual(error.exception.code, 2)
        with self.assertRaises(SystemExit) as error:
            await self.write()
        self.assertEqual(error.exception.code, 2)


class ScheduledCLI(unittest.TestCase):
    def test_invalid_schedule_options_fail_before_connecting(self):
        for options in (["--schedule-at", "tomorrow"],
                        ["--schedule-at", "2026-11-01T19:00:00"],
                        ["--schedule-at", "2026-11-01T19:00:00+03:00"],
                        ["--operation", "receipt.jsonl"],
                        ["--schedule-at", "2026-11-01T19:00:00+03:00", "--operation", "receipt.jsonl", "--pin"]):
            with self.subTest(options=options), \
                 patch.object(sys, "argv", [tg_write.__file__, "send", "chat", "file", *options]), \
                 patch("tgsess.accounts", side_effect=AssertionError("must not read tdata")), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runpy.run_path(tg_write.__file__, run_name="__main__")
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
