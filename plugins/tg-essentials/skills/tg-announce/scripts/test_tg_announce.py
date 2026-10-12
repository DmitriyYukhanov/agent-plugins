"""Offline announcement checks; run with unittest discovery from this directory."""
import os
import contextlib
import io
import json
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import tg_announce


SCRIPT = Path(__file__).with_name("tg_announce.py")
VALID = "🚀 v1.2.3\n<pre><code>• No audience-visible changes.</code></pre>"
TOKEN = "123:TEST_SECRET"
ENV = {"ALERT_BOT_TOKEN": TOKEN, "ALERT_CHAT_ID": "-10042"}
SUCCESS = {"ok": True, "result": {
    "message_id": 501, "date": 1791820000,
    "chat": {"id": -10042, "type": "supergroup", "title": "Test"},
    "text": "Deployment", "from": {"id": 123, "is_bot": True, "first_name": "Test"},
}}


class Schema(unittest.TestCase):
    def test_numeric_controls_are_rejected_before_html5_rewriting(self):
        for entity in ("&#11;", "&#x7F;", "&#128;", "&#x85;", "&#x9F;", "&#xFFFF;", "&#xFDD0;"):
            with self.subTest(entity=entity):
                self.assertTrue(tg_announce.validate_announcement(
                    f"🚀 v1.2.3\n<pre><code>• Fixed{entity}.</code></pre>"))

    def test_empty_release_cannot_mix_with_changes_using_trailing_space(self):
        for suffix in (" ", "\u00a0", "&#32;"):
            with self.subTest(suffix=suffix):
                self.assertTrue(tg_announce.validate_announcement(
                    "🚀 v1.2.3\n<pre><code>• No audience-visible changes." + suffix
                    + "\n• Fixed export.</code></pre>"))

    def test_release_identifiers_and_empty_forms(self):
        for header in ("🚀 v1.2.3", "✅ 1.0.0-rc.1+build.9", "📦 abc1234",
                       "🛠️ ABCDEF123", "🟢 " + "a" * 40):
            for bullet in ("• No audience-visible changes.",
                           "• Deployment completed; publishing is unaffected.",
                           "• Исправлен экспорт версии 1.2.3."):
                with self.subTest(header=header, bullet=bullet):
                    text = f"{header}\n<pre><code>\n{bullet}\n</code></pre>\n"
                    self.assertEqual(tg_announce.validate_announcement(text), [])

    def test_escaped_visible_text_and_boundary(self):
        for bullet in ("• " + "a" * 197 + ".", "• Show &lt;tag&gt; &amp; &#39;quotes&#39;."):
            self.assertEqual(tg_announce.validate_announcement(
                f"🚀 v1.2.3\n<pre><code>{bullet}</code></pre>"), [])
        self.assertEqual(tg_announce.validate_announcement(VALID.replace("\n", "\r\n")), [])
        self.assertEqual(tg_announce.validate_announcement(
            "🚀 v1.2.3\n<pre><code>" + "\n".join(["• Fixed export."] * 8)
            + "</code></pre>"), [])

    def test_shape_rejects_prose_markup_and_hidden_line_breaks(self):
        invalid = [
            VALID.replace("🚀", "release"), VALID.replace("v1.2.3", "v01.2.3"),
            VALID.replace("v1.2.3", "v1.2.3-01"), VALID.replace("v1.2.3", "abc123"),
            VALID.replace("v1.2.3", "a" * 41), VALID.replace("v1.2.3", "v1.2.3 production"),
            "Preface\n" + VALID, VALID + "\nExplanation", VALID + VALID,
            VALID.replace("<code>", '<code class="text">'),
            VALID.replace("<pre><code>", "<pre>"),
            VALID.replace("• No audience-visible changes.", "Plain prose."),
            VALID.replace("• No audience-visible changes.", "• "),
            VALID.replace("• No audience-visible changes.", ""),
            VALID.replace("• No audience-visible changes.", "• Fixed. Another sentence."),
            VALID.replace("• No audience-visible changes.", "• Missing terminator"),
            VALID.replace("• No audience-visible changes.", "• " + "a" * 198 + "."),
            VALID.replace("• No audience-visible changes.", "\n".join(["• Fixed."] * 9)),
            VALID.replace("• No audience-visible changes.", "• <b>Fixed</b>."),
            VALID.replace("• No audience-visible changes.", "• Raw & text."),
            VALID.replace("• No audience-visible changes.", "• Unknown &copy; entity."),
            VALID.replace("• No audience-visible changes.", "• Raw > sign."),
            VALID.replace("• No audience-visible changes.", "• Fixed.&#10;Hidden line."),
            VALID.replace("• No audience-visible changes.", "• Fixed.&#x2028;Hidden line."),
            VALID.replace("• No audience-visible changes.", "• &#0;Nul."),
            VALID.replace("• No audience-visible changes.", "• &#xD800;Surrogate."),
            VALID.replace("• No audience-visible changes.", "• &#x110000;Invalid."),
            VALID.replace("• No audience-visible changes.", "• \u202eHidden."),
            VALID.replace("• No audience-visible changes.", "• Fixed.\n "),
            VALID.replace("• No audience-visible changes.",
                          "• No audience-visible changes.\n• Fixed export."),
        ]
        for text in invalid:
            with self.subTest(text=text):
                self.assertTrue(tg_announce.validate_announcement(text))


class Sender(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        previous = Path.cwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)
        environment = patch.dict(os.environ, ENV, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.file = self.directory / "release.txt"
        self.file.write_text(VALID, encoding="utf-8")

    def run_main(self, command="announce"):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = tg_announce.main([command, str(self.file)])
        return code, output.getvalue(), errors.getvalue()

    @contextlib.contextmanager
    def response(self, reply=SUCCESS):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(reply).encode())
        opener.open.return_value.status = 200
        with patch.object(tg_announce, "build_opener", return_value=opener):
            yield opener

    def test_success_posts_json_to_topic_and_preserves_utf8_file(self):
        os.environ["ALERT_THREAD_ID"] = "37"
        self.file.write_bytes(VALID.replace("\n", "\r\n").encode("utf-8-sig"))
        before = self.file.read_bytes()
        with self.response() as opener:
            code, output, errors = self.run_main()
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("RESULT=SENT MESSAGE_ID=501", output)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, f"https://api.telegram.org/bot{TOKEN}/sendMessage")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {
            "chat_id": "-10042", "text": VALID, "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True}, "message_thread_id": 37,
        })
        self.assertGreater(opener.open.call_args.kwargs["timeout"], 0)
        self.assertEqual(self.file.read_bytes(), before)

    def test_invalid_shape_reports_all_errors_before_transport(self):
        self.file.write_text("🚀 v1.2.3\n<pre><code>Plain prose\n• Fixed. More.</code></pre>",
                             encoding="utf-8")
        with patch.object(tg_announce, "build_opener", side_effect=AssertionError("network")):
            code, output, errors = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("RESULT=NOT_SENT", output)
        self.assertIn("bullet 1", errors)
        self.assertIn("bullet 2", errors)
        self.assertIn(VALID, errors)

    def test_pathological_numeric_entities_reject_without_a_traceback(self):
        for ending in (";", ""):
            with self.subTest(ending=ending):
                self.file.write_text("🚀 v1.2.3\n<pre><code>• &#" + "9" * 5000
                                     + ending + ".</code></pre>", encoding="utf-8")
                with patch.object(tg_announce, "build_opener", side_effect=AssertionError("network")):
                    code, output, errors = self.run_main()
                self.assertEqual(code, 1)
                self.assertIn("RESULT=NOT_SENT", output)
                self.assertNotIn("Traceback", errors)

    def test_check_rejects_aggregate_length_without_loading_credentials(self):
        self.file.write_text("🚀 v1.2.3\n<pre><code>" + "\n" * 5000
                             + "• Fixed export.</code></pre>", encoding="utf-8")
        with patch.object(tg_announce, "load_config", side_effect=AssertionError("credentials")):
            code, output, errors = self.run_main("check")
        self.assertEqual(code, 1)
        self.assertIn("RESULT=NOT_SENT", output)
        self.assertNotIn("VALID=true", output)

    def test_nested_response_json_is_unknown_after_one_request(self):
        with self.response() as opener:
            opener.open.return_value = io.BytesIO(b"[" * 3000 + b"]" * 3000)
            opener.open.return_value.status = 200
            code, output, errors = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("RESULT=UNKNOWN", output)
        self.assertNotIn("Traceback", errors)
        opener.open.assert_called_once()

    def test_missing_or_invalid_config_stops_before_transport(self):
        for key, value in (("ALERT_BOT_TOKEN", ""), ("ALERT_BOT_TOKEN", "../bad"),
                           ("ALERT_CHAT_ID", ""), ("ALERT_CHAT_ID", "0"),
                           ("ALERT_THREAD_ID", "0"), ("ALERT_THREAD_ID", "abc")):
            with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}):
                with patch.object(tg_announce, "build_opener", side_effect=AssertionError("network")):
                    code, output, errors = self.run_main()
                self.assertEqual(code, 1)
                self.assertIn(key, errors)
                self.assertIn("RESULT=NOT_SENT", output)
                self.assertNotIn(TOKEN, output + errors)

    def test_environment_precedence_and_literal_dotenv(self):
        Path(".env").write_text(
            '\ufeffexport ALERT_BOT_TOKEN="999:OTHER"\r\nALERT_CHAT_ID=-10099 # test\r\n'
            'ALERT_THREAD_ID="42" # test\r\nUNRELATED=$(echo should-not-run)\r\n',
            encoding="utf-8",
        )
        with self.response() as opener:
            self.assertEqual(self.run_main()[0], 0)
            payload = json.loads(opener.open.call_args.args[0].data)
        self.assertEqual((payload["chat_id"], payload["message_thread_id"]), ("-10042", 42))
        with patch.dict(os.environ, {}, clear=True), self.response() as opener:
            self.assertEqual(self.run_main()[0], 0)
            self.assertEqual(json.loads(opener.open.call_args.args[0].data)["chat_id"], "-10099")
        with patch.dict(os.environ, {"ALERT_BOT_TOKEN": ""}):
            self.assertEqual(self.run_main()[0], 1)

    def test_note_escapes_plain_text_and_checks_visible_length(self):
        text = '<b>Вопрос</b> & "тест"\n' + "a" * 4073
        self.assertEqual(len(text), 4096)
        self.file.write_text(text, encoding="utf-8")
        with self.response() as opener:
            self.assertEqual(self.run_main("note")[0], 0)
            payload = json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(payload["text"], '&lt;b&gt;Вопрос&lt;/b&gt; &amp; &quot;тест&quot;\n' + "a" * 4073)
        self.assertNotIn("message_thread_id", payload)
        self.file.write_text(text + "a", encoding="utf-8")
        with patch.object(tg_announce, "build_opener", side_effect=AssertionError("network")):
            self.assertEqual(self.run_main("note")[0], 1)

    def test_file_and_dotenv_read_failures_are_safe(self):
        for data in (b"", b"\xff"):
            self.file.write_bytes(data)
            with patch.object(tg_announce, "build_opener", side_effect=AssertionError("network")):
                code, output, errors = self.run_main()
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", errors)
            self.assertIn("RESULT=NOT_SENT", output)
        self.file.unlink()
        self.assertEqual(self.run_main()[0], 1)
        self.file.write_text(VALID, encoding="utf-8")
        Path(".env").write_bytes(b"\xff")
        self.assertEqual(self.run_main()[0], 1)

    def test_api_refusal_does_not_expose_response_or_credentials(self):
        refusal = {"ok": False, "error_code": 403, "description": f"secret {TOKEN}"}
        with self.response(refusal):
            code, output, errors = self.run_main()
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, output + errors)
        error = HTTPError(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 403,
                          TOKEN, {}, io.BytesIO(json.dumps(refusal).encode()))
        with self.response() as opener:
            opener.open.side_effect = error
            self.assertEqual(self.run_main()[0], 1)
            opener.open.assert_called_once()

    def test_ambiguous_results_never_claim_failure_or_retry(self):
        for reply in ({}, [], {"ok": True}, {"ok": True, "result": {"message_id": True}},
                      {"ok": True, "result": {"message_id": 0}},
                      {"ok": True, "result": {"message_id": "501"}}):
            with self.subTest(reply=reply), self.response(reply) as opener:
                code, output, errors = self.run_main()
                self.assertEqual(code, 2)
                self.assertIn("RESULT=UNKNOWN", output)
                opener.open.assert_called_once()
        for error in (TimeoutError(TOKEN), URLError(TOKEN), IncompleteRead(b"partial")):
            with self.subTest(error=type(error).__name__), self.response() as opener:
                opener.open.side_effect = error
                code, output, errors = self.run_main()
                self.assertEqual(code, 2)
                self.assertNotIn(TOKEN, output + errors)
                opener.open.assert_called_once()
        with self.response() as opener:
            opener.open.return_value = io.BytesIO(b"not json")
            opener.open.return_value.status = 200
            self.assertEqual(self.run_main()[0], 2)

    def test_utf8_diagnostics_survive_windows_console_encoding(self):
        self.file.write_text("invalid", encoding="utf-8")
        out, err = io.BytesIO(), io.BytesIO()
        output = io.TextIOWrapper(out, encoding="cp1251")
        errors = io.TextIOWrapper(err, encoding="cp1251")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(tg_announce.main(["announce", str(self.file)]), 1)
        output.flush()
        errors.flush()
        self.assertIn(VALID, err.getvalue().decode("utf-8").replace("\r\n", "\n"))

    def test_real_http_surface_success_drop_and_redirect(self):
        for outcome, expected in (("success", 0), ("drop", 2), ("redirect", 2)):
            requests = []

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_POST(self):
                    requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                    if outcome == "drop":
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    body = json.dumps(SUCCESS).encode() if outcome == "success" else b""
                    self.send_response(200 if outcome == "success" else 302)
                    if outcome == "redirect":
                        self.send_header("Location", "/redirected")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_GET(self):
                    requests.append("redirected")
                    self.send_error(500)

            with self.subTest(outcome=outcome), ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
                thread = threading.Thread(target=server.serve_forever,
                                          kwargs={"poll_interval": 0.01}, daemon=True)
                thread.start()
                try:
                    with patch.object(tg_announce, "API_ORIGIN", f"http://127.0.0.1:{server.server_port}"):
                        self.assertEqual(self.run_main()[0], expected)
                    self.assertEqual(len(requests), 1)
                    self.assertEqual(requests[0]["text"], VALID)
                finally:
                    server.shutdown()
                    thread.join(timeout=2)


class CommandLine(unittest.TestCase):
    def test_syntax_rejection_is_not_sent_instead_of_unknown(self):
        for arguments in (("announce",), ("announce", "release.txt", "--bypass")):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT), *arguments], capture_output=True,
                    encoding="utf-8", timeout=10,
                )
                self.assertEqual(completed.returncode, 1, completed.stderr)
                self.assertIn("RESULT=NOT_SENT", completed.stdout)

    def test_check_accepts_saved_announcement_without_credentials(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "release.txt"
            file.write_text(VALID, encoding="utf-8")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith("ALERT_")}
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "check", str(file)],
                cwd=directory, env=env, capture_output=True,
                encoding="utf-8", timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("VALID=true", completed.stdout)
            self.assertEqual(file.read_text(encoding="utf-8"), VALID)


if __name__ == "__main__":
    unittest.main()
