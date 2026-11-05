"""Log in to an independent Telegram session. QR is the default; --code uses a phone code."""
import argparse
import asyncio
from getpass import getpass
import json
import os
import re
import sys

import qrcode
from telethon import TelegramClient, errors
from tgsess import ROOT, credentials, session_lock


def setup_credentials() -> tuple[int, str]:
    if (ROOT / "api.json").exists():
        return credentials()
    api_id = os.environ.get("TG_API_ID") or input("API ID from my.telegram.org: ").strip()
    api_hash = os.environ.get("TG_API_HASH") or getpass("API hash: ").strip()
    if not api_id.isascii() or not api_id.isdigit() or int(api_id) <= 0 or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise SystemExit("API ID must be positive and API hash must contain 32 hexadecimal characters")
    fd = os.open(ROOT / "api.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump({"api_id": int(api_id), "api_hash": api_hash}, file)
    return credentials()


async def login(code: bool = False) -> None:
    pending = ROOT / "login.session"
    client = TelegramClient(str(pending), *credentials(), device_model="tg-account", raise_last_call_error=True)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            try:
                if code:
                    phone = getpass("Phone number with country code: ").strip()
                    await client.send_code_request(phone)
                    await client.sign_in(phone=phone, code=getpass("Telegram login code: ").strip())
                else:
                    qr = await client.qr_login()
                    image = qrcode.QRCode()
                    image.add_data(qr.url)
                    print("Scan in Telegram: Settings > Devices > Link Desktop Device", flush=True)
                    image.print_ascii(invert=True)
                    sys.stdout.flush()
                    await qr.wait()
            except errors.SessionPasswordNeededError:
                await client.sign_in(password=getpass("Telegram 2FA password: "))
        me = await client.get_me()
        if me is None or me.bot:
            raise SystemExit("Login requires a Telegram user account")
    finally:
        await client.disconnect()
    destination = ROOT / f"{me.id}.session"
    if destination.exists():
        raise SystemExit(f"account {me.id} already configured; keep {pending} and revoke the redundant login in Devices")
    pending.rename(destination)
    print(f"account={me.id} configured", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    method = parser.add_mutually_exclusive_group()
    method.add_argument("--qr", action="store_true", help="Scan a QR code (default)")
    method.add_argument("--code", action="store_true", help="Receive a Telegram login code")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Run login in an interactive terminal; do not pipe login secrets")
    try:
        with session_lock():
            setup_credentials()
            asyncio.run(login(args.code))
    except (EOFError, KeyboardInterrupt):
        sys.exit("Login cancelled; rerun tg_login.py to continue")
    except asyncio.TimeoutError:
        sys.exit("Login timed out; rerun tg_login.py for a fresh QR code")
    except errors.RPCError as error:
        sys.exit(f"Login failed: {type(error).__name__}; rerun tg_login.py when ready")
