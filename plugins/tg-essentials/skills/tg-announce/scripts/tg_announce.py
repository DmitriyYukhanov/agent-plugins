#!/usr/bin/env python3
"""Validate announcement-v1 and send one Telegram message without retries."""
import argparse
import html
from http.client import HTTPException
from ipaddress import IPv6Address
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_ORIGIN = "https://api.telegram.org"
MAX_RESPONSE_BYTES = 65536
EXAMPLE = "🚀 v1.2.3\n<pre><code>• No audience-visible changes.</code></pre>"
EMOJI = {"🚀", "✅", "📦", "🛠", "🛠️", "🟢"}
NUMBER = r"(?:0|[1-9][0-9]*)"
PRERELEASE = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
IDENTIFIER = re.compile(
    rf"(?:v?{NUMBER}\.{NUMBER}\.{NUMBER}"
    rf"(?:-{PRERELEASE}(?:\.{PRERELEASE})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?|[0-9a-fA-F]{7,40})"
)
ENTITY = re.compile(r"&(?:lt|gt|amp|quot|#[0-9]+|#x[0-9a-fA-F]+);")
KEYS = ("ALERT_BOT_TOKEN", "ALERT_CHAT_ID", "ALERT_THREAD_ID", "ALERT_BOT_API_ORIGIN")


def validate_announcement(text: str) -> list[str]:
    """Return all detected shape errors; never judge what the release changes."""
    text = text.replace("\r\n", "\n")
    header, _, body = text.partition("\n")
    icon, _, identifier = header.partition(" ")
    errors = []
    if icon not in EMOJI or not IDENTIFIER.fullmatch(identifier):
        errors.append("header: use a supported release emoji and a SemVer tag or 7-40 hex revision.")
    block = re.fullmatch(r"<pre><code>(.*?)</code></pre>\n?", body, re.DOTALL)
    if block is None:
        errors.append("body: use exactly one <pre><code> block with no text outside it.")
        return errors
    lines = [line for line in block[1].split("\n") if line != ""]
    if not 1 <= len(lines) <= 8:
        errors.append("body: include 1-8 bullet lines.")
    decoded_lines = []
    for index, line in enumerate(lines, 1):
        prefix = f"bullet {index}:"
        unsafe_entities = "<" in line or ">" in line or "&" in ENTITY.sub("", line)
        if unsafe_entities:
            errors.append(f"{prefix} escape text and use only supported HTML entities.")
        for entity in ENTITY.findall(line):
            if entity.startswith("&#"):
                numeric = entity[2:-1]
                try:
                    value = int(numeric[1:], 16) if numeric.startswith("x") else int(numeric)
                except ValueError:
                    value = 0
                if (not 0 < value <= 0x10FFFF
                        or unicodedata.category(chr(value)).startswith("C")
                        or chr(value) in "\u2028\u2029"):
                    errors.append(f"{prefix} use a valid Unicode entity.")
                    unsafe_entities = True
        decoded = line if unsafe_entities else html.unescape(line)
        decoded_lines.append(decoded)
        if any(unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
               for char in decoded):
            errors.append(f"{prefix} remove control characters and encoded line breaks.")
        if not decoded.startswith("• ") or not decoded[2:].strip():
            errors.append(f"{prefix} start with '• ' followed by text.")
        if len(decoded) > 200:
            errors.append(f"{prefix} keep the visible line at or below 200 characters.")
        sentence = decoded[2:].strip()
        # shortcut: punctuation bounds sentences conservatively; reword abbreviations for v1.
        if not sentence.endswith((".", "!", "?")) or re.search(r"[.!?](?:\s|$)", sentence[:-1]):
            errors.append(f"{prefix} use one sentence ending in '.', '!' or '?'.")
    if any(line.rstrip() == "• No audience-visible changes." for line in decoded_lines) and len(lines) != 1:
        errors.append("body: the empty-release form must be its only bullet.")
    if not errors:
        visible = header + "\n" + html.unescape(block[1]) + ("\n" if body.endswith("\n") else "")
        if len(visible) > 4096:
            errors.append("body: keep the complete message at or below 4096 visible characters.")
    return errors


def load_config() -> dict[str, str]:
    """Read literal .env assignments for keys absent from the environment."""
    config = {}
    dotenv = Path(".env")
    if dotenv.exists() and any(key not in os.environ for key in KEYS):
        try:
            contents = dotenv.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise ValueError("Cannot read project .env as UTF-8.") from error
        for line in contents.splitlines():
            key, separator, value = line.strip().removeprefix("export ").partition("=")
            key, value = key.strip(), value.strip()
            if not separator or key not in KEYS or key in os.environ:
                continue
            if value.startswith(("'", '"')):
                quoted = re.fullmatch(r"(['\"])(.*?)\1(?:\s+#.*)?", value)
                if quoted is None:
                    raise ValueError(f"Invalid quoted value for {key} in .env.")
                value = quoted[2]
            else:
                value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
            config[key] = value
    config.update({key: os.environ[key] for key in KEYS if key in os.environ})
    config["ALERT_BOT_API_ORIGIN"] = validate_origin(config.get("ALERT_BOT_API_ORIGIN", API_ORIGIN))
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", config.get("ALERT_BOT_TOKEN", "")):
        raise ValueError("Missing or invalid ALERT_BOT_TOKEN.")
    chat = config.get("ALERT_CHAT_ID", "")
    if not re.fullmatch(r"-?[0-9]+|@[A-Za-z][A-Za-z0-9_]{4,}", chat):
        raise ValueError("Missing or invalid ALERT_CHAT_ID.")
    if not chat.startswith("@") and (len(chat) > 20 or not 0 < abs(int(chat)) < 2**63):
        raise ValueError("Invalid ALERT_CHAT_ID.")
    if "ALERT_THREAD_ID" in config:
        thread = config["ALERT_THREAD_ID"]
        if not re.fullmatch(r"[0-9]{1,10}", thread) or not 0 < int(thread) < 2**31:
            raise ValueError("Invalid ALERT_THREAD_ID; omit it to send to the chat itself.")
    return config


def validate_origin(origin: str) -> str:
    """Accept only an operator-supplied HTTP(S) origin, never a request URL."""
    try:
        # urlsplit strips some controls, so reject them before parsing.
        if not origin.isascii() or any(char.isspace() or ord(char) < 32 or ord(char) == 127
                                       or char in "\\?#" for char in origin):
            raise ValueError
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/")
                or not re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::[0-9]+)?", parsed.netloc)
                or parsed.port == 0):
            raise ValueError
        if parsed.netloc.startswith("["):
            IPv6Address(parsed.hostname)
    except ValueError:
        raise ValueError("Missing or invalid ALERT_BOT_API_ORIGIN.") from None
    return f"{parsed.scheme}://{parsed.netloc}"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_message(token: str, payload: dict, origin: str = API_ORIGIN) -> tuple[str, str]:
    origin = validate_origin(origin)
    request = Request(
        f"{origin}/bot{token}/sendMessage",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST",
    )
    try:
        try:
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                status = response.status
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            with error:
                status, body = error.code, error.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            return "UNKNOWN", "REASON=delivery_unconfirmed"
        reply = json.loads(body)
    except (OSError, HTTPException, ValueError, RecursionError):
        return "UNKNOWN", "REASON=delivery_unconfirmed"
    if isinstance(reply, dict) and reply.get("ok") is False:
        return "NOT_SENT", "REASON=telegram_rejected"
    if status == 200 and isinstance(reply, dict) and reply.get("ok") is True:
        sent = reply.get("result")
        message_id = sent.get("message_id") if isinstance(sent, dict) else None
        if type(message_id) is int and message_id > 0:
            return "SENT", f"MESSAGE_ID={message_id}"
    return "UNKNOWN", "REASON=delivery_unconfirmed"


def result(status: str, detail: str) -> int:
    print(f"RESULT={status} {detail}")
    return {"SENT": 0, "NOT_SENT": 1, "UNKNOWN": 2}[status]


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("announce", "note", "check"))
    parser.add_argument("file", type=Path, help="saved UTF-8 message file")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 0 if error.code == 0 else result("NOT_SENT", "REASON=arguments_invalid")
    try:
        text = args.file.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    except (OSError, UnicodeError):
        print("Cannot read message file as UTF-8.", file=sys.stderr)
        return result("NOT_SENT", "REASON=message_unreadable")
    if args.command != "note":
        errors = validate_announcement(text)
        if errors:
            print("\n".join(errors) + "\nExpected announcement-v1:\n" + EXAMPLE, file=sys.stderr)
            return result("NOT_SENT", "REASON=schema_rejected")
        if args.command == "check":
            print("SCHEMA=announcement-v1 VALID=true")
            return 0
    else:
        if not text.strip() or len(text) > 4096:
            print("Use 1-4096 visible characters without truncation.", file=sys.stderr)
            return result("NOT_SENT", "REASON=message_length")
        text = html.escape(text)
    try:
        config = load_config()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return result("NOT_SENT", "REASON=config_invalid")
    payload = {"chat_id": config["ALERT_CHAT_ID"], "text": text, "parse_mode": "HTML",
               "link_preview_options": {"is_disabled": True}}
    if "ALERT_THREAD_ID" in config:
        payload["message_thread_id"] = int(config["ALERT_THREAD_ID"])
    return result(*send_message(config["ALERT_BOT_TOKEN"], payload, config["ALERT_BOT_API_ORIGIN"]))


if __name__ == "__main__":
    sys.exit(main())
