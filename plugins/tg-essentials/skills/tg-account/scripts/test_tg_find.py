"""Offline forum discovery and compatibility tests."""
import contextlib
import datetime as dt
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from telethon import errors, functions, types
from test_tg_write import DATE, FORUM, topic

# Importing the old finder must not read tdata during the red test run.
with patch("tgsess.accounts", return_value=[]):
    import tg_find


def page(topics, count=3, by_create=False, messages=None):
    return SimpleNamespace(topics=topics, count=count, order_by_create_date=by_create,
                           messages=messages if messages is not None else [
                               SimpleNamespace(id=t.top_message, date=DATE + dt.timedelta(days=1))
                               for t in topics if isinstance(t, types.ForumTopic)])


class FindTopics(unittest.IsolatedAsyncioTestCase):
    async def listing(self, pages, entity=FORUM):
        client = AsyncMock(side_effect=pages)
        opened = AsyncMock(return_value=(client, entity, "1"))
        output = io.StringIO()
        with patch.object(tg_find, "open_chat", opened, create=True), contextlib.redirect_stdout(output):
            await tg_find.topics("-10042", "1")
        return client, opened, output.getvalue()

    async def test_short_pages_print_root_ids_and_use_latest_message_cursors(self):
        client, opened, output = await self.listing([
            page([topic(), types.ForumTopicDeleted(9)]),
            page([topic(51, 800)]), page([topic(1, 700)]),
        ])
        opened.assert_awaited_once_with("-10042", "1")
        self.assertIn("topic=37 title='HTML'", output)
        self.assertIn("topic=51", output)
        self.assertIn("topic=1", output)
        self.assertNotIn("topic=900", output)
        self.assertNotIn("topic=9 ", output)
        requests = [call.args[0] for call in client.await_args_list]
        self.assertTrue(all(isinstance(r, functions.messages.GetForumTopicsRequest) for r in requests))
        self.assertEqual((requests[0].offset_date, requests[0].offset_id, requests[0].offset_topic), (None, 0, 0))
        self.assertEqual((requests[1].offset_date, requests[1].offset_id, requests[1].offset_topic), (DATE + dt.timedelta(days=1), 900, 37))
        client.disconnect.assert_awaited_once()

    async def test_creation_order_uses_topic_date(self):
        client, _, _ = await self.listing([page([topic()], count=2, by_create=True), page([topic(51)], count=2, by_create=True)])
        self.assertEqual(client.await_args_list[1].args[0].offset_date, DATE)

    async def test_empty_result_disconnects(self):
        client, _, output = await self.listing([page([], count=0)])
        self.assertNotIn("topic=", output)
        client.disconnect.assert_awaited_once()

    async def test_empty_page_with_remaining_topics_fails_visibly(self):
        client = AsyncMock(side_effect=[page([topic()], count=2), page([], count=2)])
        with patch.object(tg_find, "open_chat", AsyncMock(return_value=(client, FORUM, "1"))), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, "incomplete"):
                await tg_find.topics("chat", "1")
        client.disconnect.assert_awaited_once()

    async def test_nonadjacent_repeated_pages_stop_without_another_fetch(self):
        client = AsyncMock(side_effect=[page([topic()]), page([topic(51, 800)]), page([topic()]),
                                       SystemExit("topic listing incomplete: offline request cap")])
        with patch.object(tg_find, "open_chat", AsyncMock(return_value=(client, FORUM, "1"))), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, "incomplete"):
                await tg_find.topics("chat", "1")
        self.assertEqual(client.await_count, 3)
        client.disconnect.assert_awaited_once()

    async def test_unusable_cursors_fail_visibly_and_disconnect(self):
        for pages in ([page([topic()], messages=[])], [page([types.ForumTopicDeleted(37)])],
                      [page([topic()]), page([topic()])]):
            with self.subTest(pages=pages):
                client = AsyncMock(side_effect=pages)
                with patch.object(tg_find, "open_chat", AsyncMock(return_value=(client, FORUM, "1")), create=True), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(SystemExit, "incomplete"):
                        await tg_find.topics("chat", "1")
                client.disconnect.assert_awaited_once()

    async def test_nonforum_rejected_and_rpc_error_reported(self):
        client = AsyncMock(side_effect=errors.ChannelPrivateError(None))
        for entity in (types.User(id=2), FORUM):
            with self.subTest(entity=type(entity).__name__), \
                 patch.object(tg_find, "open_chat", AsyncMock(return_value=(client, entity, "1")), create=True), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                if entity is FORUM:
                    await tg_find.topics("chat", "1")
                    self.assertIn("topics unavailable right now", output.getvalue())
                else:
                    with self.assertRaisesRegex(SystemExit, "forum"):
                        await tg_find.topics("chat", "1")
        self.assertEqual(client.disconnect.await_count, 2)

    async def test_accounts_only_never_connects(self):
        with patch.object(tg_find, "accounts", return_value=[SimpleNamespace(UserId=1, MainDcId=2)]), \
             patch.object(tg_find, "client_for", Mock(side_effect=AssertionError("must not connect"))), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            await tg_find.main([])
        self.assertIn("account 1 (dc 2)", output.getvalue())

    async def test_keyword_search_still_matches_names_and_usernames(self):
        async def dialogs():
            for name, username in (("Other", "alice"), ("Work Chat", None), ("Skip", None)):
                yield SimpleNamespace(id=42, name=name, entity=SimpleNamespace(username=username))
        client = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(), iter_dialogs=dialogs)
        with patch.object(tg_find, "accounts", return_value=[SimpleNamespace(UserId=1, MainDcId=2)]), \
             patch.object(tg_find, "client_for", return_value=client), contextlib.redirect_stdout(io.StringIO()) as output:
            await tg_find.main(["@ALICE", "WORK"])
        self.assertIn("'Other'  @alice", output.getvalue())
        self.assertIn("'Work Chat'", output.getvalue())
        self.assertNotIn("'Skip'", output.getvalue())
        client.disconnect.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
