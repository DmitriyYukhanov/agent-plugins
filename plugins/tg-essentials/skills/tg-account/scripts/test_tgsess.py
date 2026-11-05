"""Offline checks for independent login and process exclusion."""
import asyncio
import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import tgsess


class Sessions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-account-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.patcher = patch.object(tgsess, "ROOT", self.root, create=True)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_only_registered_accounts_are_listed_without_connecting(self):
        for filename in ("42.session", "7.session", "login.session", "42.session-journal"):
            (self.root / filename).touch()
        with patch.object(tgsess, "TelegramClient") as client:
            self.assertEqual([a.UserId for a in tgsess.accounts()], [7, 42])
        client.assert_not_called()

    def test_missing_session_fails_without_creating_or_importing_a_desktop_key(self):
        with patch.object(tgsess, "TelegramClient") as client:
            with self.assertRaisesRegex(SystemExit, "tg_login.py"):
                tgsess.client_for(42)
        client.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_client_uses_private_session_and_own_api_credentials(self):
        (self.root / "42.session").touch()
        (self.root / "api.json").write_text(json.dumps({"api_id": 123, "api_hash": "a" * 32}))
        with patch.object(tgsess, "TelegramClient") as client:
            tgsess.client_for(42)
        self.assertEqual(client.call_args.args, (str(self.root / "42.session"), 123, "a" * 32))
        self.assertFalse(client.call_args.kwargs["receive_updates"])

    def test_lock_rejects_another_process_and_recovers_after_termination(self):
        script = ("import pathlib,sys; import tgsess; tgsess.ROOT=pathlib.Path(sys.argv[1]); "
                  "\nwith tgsess.session_lock():\n print('locked',flush=True); sys.stdin.readline()")
        command = [sys.executable, "-c", script, str(self.root)]
        child = subprocess.Popen(command, cwd=pathlib.Path(tgsess.__file__).parent,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready = child.stdout.readline().strip()
            if ready != "locked":
                self.fail(child.communicate(timeout=10)[1])
            rejected = subprocess.run(command, cwd=pathlib.Path(tgsess.__file__).parent,
                                      input="", capture_output=True, text=True, timeout=10)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("already running", rejected.stderr)
        finally:
            child.kill()
            child.communicate(timeout=10)
        with tgsess.session_lock():
            pass


class Login(unittest.IsolatedAsyncioTestCase):
    async def test_qr_and_code_login_handle_2fa_and_always_disconnect(self):
        import tg_login
        from telethon import errors
        for code in (False, True):
            with self.subTest(code=code), tempfile.TemporaryDirectory(prefix="tg-account-login-") as directory:
                root = pathlib.Path(directory)
                client = AsyncMock()
                client.is_user_authorized.return_value = False
                client.get_me.return_value = SimpleNamespace(id=42, bot=False)
                qr = SimpleNamespace(url="tg://login?token=private", wait=AsyncMock(
                    side_effect=errors.SessionPasswordNeededError(None)))
                client.qr_login.return_value = qr
                client.sign_in.side_effect = [errors.SessionPasswordNeededError(None), None] if code else [None]
                (root / "login.session").touch()
                with patch.object(tg_login, "ROOT", root), \
                     patch.object(tg_login, "credentials", return_value=(123, "a" * 32)), \
                     patch.object(tg_login, "TelegramClient", return_value=client), \
                     patch.object(tg_login, "getpass", side_effect=["+123", "12345", "secret"] if code else ["secret"]), \
                     patch.object(tg_login.qrcode, "QRCode") as image, contextlib.redirect_stdout(io.StringIO()):
                    await tg_login.login(code)
                if code:
                    client.send_code_request.assert_awaited_once_with("+123")
                else:
                    image.return_value.add_data.assert_called_once_with(qr.url)
                    qr.wait.assert_awaited_once()
                self.assertEqual(client.sign_in.call_args.kwargs, {"password": "secret"})
                client.disconnect.assert_awaited_once()
                self.assertTrue((root / "42.session").exists())
                self.assertFalse((root / "login.session").exists())

    async def test_interrupted_login_retains_pending_session_and_disconnects(self):
        import tg_login
        with tempfile.TemporaryDirectory(prefix="tg-account-login-") as directory:
            root = pathlib.Path(directory)
            (root / "login.session").touch()
            client = AsyncMock()
            client.is_user_authorized.return_value = False
            client.qr_login.side_effect = asyncio.TimeoutError
            with patch.object(tg_login, "ROOT", root), \
                 patch.object(tg_login, "credentials", return_value=(123, "a" * 32)), \
                 patch.object(tg_login, "TelegramClient", return_value=client):
                with self.assertRaises(asyncio.TimeoutError):
                    await tg_login.login(False)
            client.disconnect.assert_awaited_once()
            self.assertTrue((root / "login.session").exists())

    async def test_resume_does_not_log_in_again_or_overwrite_an_existing_account(self):
        import tg_login
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory(prefix="tg-account-login-") as directory:
                root = pathlib.Path(directory)
                (root / "login.session").write_text("pending")
                if duplicate:
                    (root / "42.session").write_text("existing")
                client = AsyncMock()
                client.is_user_authorized.return_value = True
                client.get_me.return_value = SimpleNamespace(id=42, bot=False)
                with patch.object(tg_login, "ROOT", root), \
                     patch.object(tg_login, "credentials", return_value=(123, "a" * 32)), \
                     patch.object(tg_login, "TelegramClient", return_value=client), contextlib.redirect_stdout(io.StringIO()):
                    if duplicate:
                        with self.assertRaisesRegex(SystemExit, "already configured"):
                            await tg_login.login()
                    else:
                        await tg_login.login()
                client.qr_login.assert_not_awaited()
                client.send_code_request.assert_not_awaited()
                self.assertEqual((root / "42.session").read_text(), "existing" if duplicate else "pending")
                self.assertEqual((root / "login.session").exists(), duplicate)


if __name__ == "__main__":
    unittest.main()
