"""Independent Telethon sessions and one process lock for all account commands."""
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from telethon import TelegramClient, errors

# Chat titles carry emoji and Cyrillic; a piped stdout on Windows defaults to the ANSI code page.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


ROOT = Path.home() / ".tg-account" / "sessions"


@contextmanager
def session_lock():
    """Hold an OS lock until command exit; a crashed process releases it too."""
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if sys.platform == "win32":
        user = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True,
                                       encoding="utf-8", errors="replace")
        sid = next(csv.reader(user.strip().splitlines()))[1]
        subprocess.run(["icacls", str(ROOT), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                       check=True, stdout=subprocess.DEVNULL)
    else:
        ROOT.chmod(0o700)
    with (ROOT / "account.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("tg-account is already running; wait for that command to finish") from None
        # Keep the lock file: deleting it would let another process lock a different inode.
        yield


def credentials() -> tuple[int, str]:
    try:
        data = json.loads((ROOT / "api.json").read_text(encoding="utf-8"))
        api_id, api_hash = data["api_id"], data["api_hash"]
        if type(api_id) is not int or api_id <= 0 or not isinstance(api_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
            raise ValueError
        return api_id, api_hash
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit("Missing or invalid API credentials; run tg_login.py") from None


def accounts() -> list[SimpleNamespace]:
    ids = sorted(int(p.stem) for p in ROOT.glob("*.session") if p.stem.isascii() and p.stem.isdigit() and int(p.stem) > 0)
    if not ids:
        raise SystemExit("No Telegram accounts configured; run tg_login.py")
    return [SimpleNamespace(UserId=user_id) for user_id in ids]


def client_for(user_id: int | str) -> TelegramClient:
    session = ROOT / f"{int(user_id)}.session"
    if not session.is_file():
        raise SystemExit(f"account {user_id} is not configured; run tg_login.py")
    return TelegramClient(str(session), *credentials(), device_model="tg-account",
                          receive_updates=False, raise_last_call_error=True)


def peer(ref):
    """@username / t.me link stay strings, numeric ids become ints."""
    return int(ref) if ref.lstrip("-").isdigit() else ref


def name(e):
    """Display name of a user, chat or channel."""
    if e is None:
        return "?"
    return getattr(e, "title", None) or " ".join(filter(None, (getattr(e, "first_name", None), getattr(e, "last_name", None)))) \
        or getattr(e, "username", None) or "?"


async def warm(c, refs):
    """Numeric ids resolve only from the dialog cache; fill it when any ref is numeric."""
    if any(isinstance(r, int) for r in refs):
        try:
            await c.get_dialogs()
        except errors.RPCError:
            pass


async def open_chat(chat, acc=None):
    """Connect as ACC, or as the first account that can open CHAT. Returns (client, entity, account id)."""
    target = peer(chat)
    for a in [acc] if acc else [x.UserId for x in accounts()]:
        c = client_for(a)
        try:
            await c.connect()
            await warm(c, [target])
            return c, await c.get_entity(target), a
        except (ValueError, errors.RPCError) as ex:
            print(f"account {a}: cannot open {chat}: {ex}")
            await c.disconnect()
        except BaseException:
            await c.disconnect()
            raise
    raise SystemExit("no account can open " + chat)
