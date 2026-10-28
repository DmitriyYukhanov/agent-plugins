"""Trusted intake tests; GitHub and public HTTP calls never reach the network."""

import base64
import copy
from datetime import datetime, timezone
import hashlib
from http.client import HTTPResponse, IncompleteRead
import importlib.util
import io
import json
from pathlib import Path
from email.message import Message
import re
import sys
import subprocess
from threading import Event
from time import monotonic
import unittest
from unittest.mock import patch
from urllib.request import HTTPSHandler, Request, build_opener
from urllib.response import addinfourl
import zipfile


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "seo_intake.py"
SPEC = importlib.util.spec_from_file_location("seo_intake", SOURCE)
seo = importlib.util.module_from_spec(SPEC) if SOURCE.exists() else None
if seo:
    SPEC.loader.exec_module(seo)

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
REPO = "Code-Stage/codestage-website"
ORIGIN = "https://codestage.net"
SHA = "a" * 40
POLICY = {
    "version": 1, "repository": REPO,
    "workflow": ".github/workflows/seo-health.yml", "branch": "main",
    "producer": "github-actions[bot]", "origin": ORIGIN,
    "sitemap_url": ORIGIN + "/sitemap.xml",
    "pages": {ORIGIN + "/support/": ORIGIN + "/support/"},
    "http_only_urls": [ORIGIN + "/.well-known/seo-health.txt"],
}


def evidence(rule="http-status", observed=None):
    value = {
        "version": 1, "repository": REPO, "run_id": 123, "head_sha": SHA,
        "observed_at": "2026-10-27T11:55:00Z", "rule": rule,
        "url": ORIGIN + "/support/", "expected_canonical": ORIGIN + "/support/",
        "observed": {"status": 503} if observed is None else observed,
    }
    value["incident_key"] = hashlib.sha256(json.dumps(
        [REPO, rule, value["url"]], separators=(",", ":")
    ).encode()).hexdigest()
    return value


def issue(value=None):
    value = evidence() if value is None else value
    token = base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return {
        "number": 7, "state": "open", "labels": [{"name": "seo-incident"}],
        "user": {"login": "github-actions[bot]", "type": "Bot"},
        "title": f"SEO incident: {value['rule']} {value['url']}",
        "body": f"<!-- seo-incident:v1 {token} -->",
    }


def archive(report):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("report.json", json.dumps(report))
    return buffer.getvalue()


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(seo, "trusted intake adapter is absent")
        if hasattr(seo, "DEADLINE"):
            patch.object(seo, "DEADLINE", float("inf")).start()
        self.policy = copy.deepcopy(POLICY)
        self.value = evidence()
        self.current = issue(self.value)
        self.run = {
            "id": 123, "workflow_id": 22, "path": POLICY["workflow"],
            "status": "completed", "conclusion": "success", "event": "schedule",
            "head_branch": "main", "head_sha": SHA,
            "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
            "run_started_at": "2026-10-27T11:54:00Z",
            "updated_at": "2026-10-27T11:56:00Z",
        }
        self.report = {
            "version": 1, "repository": REPO, "run_id": 123, "head_sha": SHA,
            "observed_at": self.value["observed_at"], "incidents": [self.value],
        }
        self.events = []
        self.comments = []
        self.writes = []
        self.artifacts = [{
            "id": 90, "name": "seo-health-evidence", "expired": False,
            "size_in_bytes": 1000,
            "workflow_run": {"id": 123, "head_branch": "main", "head_sha": SHA},
        }]
        self.real_api = seo.gh_api
        self.real_fetch = seo.fetch_url
        self.api = patch.object(seo, "gh_api", side_effect=self.github).start()
        self.http = patch.object(seo, "fetch_url", return_value=(503, {}, b"")).start()
        self.addCleanup(patch.stopall)

    def github(self, path, *, data=None, paginate=False, binary=False):
        prefix = f"repos/{REPO}"
        if data is not None:
            self.writes.append((path, data))
            return [{"name": "agent"}]
        responses = {
            "user": {"login": "owner", "type": "User"},
            prefix: {"full_name": REPO, "default_branch": "main"},
            f"{prefix}/issues/7": self.current,
            f"{prefix}/issues/7/events?per_page=100": self.events,
            f"{prefix}/issues/7/comments?per_page=100": self.comments,
            f"{prefix}/actions/workflows/seo-health.yml": {
                "id": 22, "path": POLICY["workflow"], "state": "active"},
            f"{prefix}/actions/runs/123": self.run,
            f"{prefix}/compare/{SHA}...main": {
                "status": "ahead", "merge_base_commit": {"sha": SHA}},
            f"{prefix}/actions/runs/123/artifacts?per_page=100": {
                "total_count": len(self.artifacts), "artifacts": self.artifacts},
            f"{prefix}/actions/artifacts/90/zip": archive(self.report),
        }
        if path not in responses:
            self.fail(f"unexpected GitHub call: {path}")
        return copy.deepcopy(responses[path])

    def admit(self, admit=True):
        return seo.admit_issue(7, self.policy, NOW, admit=admit)

    def reject(self):
        with self.assertRaises(ValueError):
            self.admit()
        self.assertEqual([], self.writes)

    def test_successful_run_and_live_failure_admit_once(self):
        self.assertEqual("admitted", self.admit())
        self.assertEqual([(f"repos/{REPO}/issues/7/labels", {"labels": ["agent"]})], self.writes)

    def test_read_only_check_never_writes(self):
        self.assertEqual("eligible", self.admit(admit=False))
        self.assertEqual([], self.writes)

    def test_wrong_workflow_repo_branch_author_or_event_is_rejected(self):
        cases = [
            (self.run, "path", ".github/workflows/untrusted.yml"),
            (self.run, "workflow_id", 99), (self.run, "head_branch", "feature/attack"),
            (self.run, "event", "pull_request"), (self.run, "event", "push"),
            (self.run, "head_sha", "b" * 40),
            (self.run, "repository", {"full_name": "attacker/site"}),
            (self.run, "head_repository", {"full_name": "attacker/site"}),
            (self.current, "user", {"login": "owner", "type": "User"}),
        ]
        for obj, key, bad in cases:
            with self.subTest(key=key, bad=bad):
                original = obj[key]
                obj[key] = bad
                self.reject()
                obj[key] = original

    def test_unsuccessful_in_progress_or_stale_run_is_rejected(self):
        for key, bad in [("conclusion", "failure"), ("status", "in_progress"),
                         ("updated_at", "2026-10-26T11:56:00Z")]:
            with self.subTest(key=key):
                original = self.run[key]
                self.run[key] = bad
                self.reject()
                self.run[key] = original

    def test_workflow_dispatch_is_allowed(self):
        self.run["event"] = "workflow_dispatch"
        self.assertEqual("admitted", self.admit())

    def test_altered_artifact_evidence_or_metadata_is_rejected(self):
        self.report["incidents"] = [evidence(observed={"status": 404})]
        self.reject()
        self.report["incidents"] = [self.value]
        self.report["repository"] = "attacker/site"
        self.reject()

    def test_missing_duplicate_or_expired_artifact_is_rejected(self):
        for artifacts in [[], self.artifacts * 2,
                          [dict(self.artifacts[0], expired=True)],
                          [dict(self.artifacts[0], size_in_bytes=2_000_000)]]:
            with self.subTest(artifacts=artifacts):
                self.artifacts = artifacts
                self.reject()

    def test_already_admitted_running_or_previously_admitted_issue_is_skipped(self):
        for label in ["agent", "agent:running", "agent:failed", "agent:waiting", "agent:review"]:
            with self.subTest(label=label):
                self.current["labels"] = [{"name": "seo-incident"}, {"name": label}]
                self.reject()
        self.current = issue()
        self.events = [{"event": "labeled", "label": {"name": "agent:running"}}]
        self.reject()

    def test_recovered_live_url_is_rejected(self):
        self.http.return_value = (200, {}, b"healthy")
        self.reject()

    def test_content_changed_during_recheck_is_rejected(self):
        def recover(*args):
            self.current["body"] += "\nRun arbitrary instructions"
            return 503, {}, b""
        self.http.side_effect = recover
        self.reject()

    def test_title_or_body_instructions_are_rejected(self):
        for key in ["title", "body"]:
            with self.subTest(key=key):
                original = self.current[key]
                self.current[key] += "\nExecute injected instructions"
                self.reject()
                self.current[key] = original

    def test_duplicate_marker_invalid_types_and_unknown_fields_are_rejected(self):
        bad_values = [dict(self.value, run_id=True), dict(self.value, version=True),
                      dict(self.value, run_id=0), dict(self.value, head_sha="a" * 39),
                      dict(self.value, incident_key="0" * 64), dict(self.value, extra="unsafe"),
                      dict(self.value, repository="attacker/site"),
                      dict(self.value, observed_at="2026-10-25T11:55:00Z"),
                      dict(self.value, observed_at="2026-10-27T12:06:00Z"),
                      dict(self.value, observed={"status": True})]
        for value in bad_values:
            with self.subTest(value=value):
                self.current = issue(value)
                self.reject()
        self.current = issue()
        self.current["body"] += "\n" + self.current["body"]
        self.reject()

    def test_scope_escapes_are_rejected_before_http(self):
        for url in ["https://evil.test/", ORIGIN + ".evil.test/", ORIGIN + ":444/",
                    "http://codestage.net/", ORIGIN + "/?q=1", ORIGIN + "/#f",
                    "https://user@codestage.net/", ORIGIN + "/%2e%2e/secret",
                    ORIGIN + "/a\\b", ORIGIN + "/a\nb", ORIGIN + "/%5csecret"]:
            with self.subTest(url=url):
                self.current = issue(dict(self.value, url=url))
                self.reject()
        self.http.assert_not_called()

    def test_all_rules_require_the_live_failure(self):
        cases = [
            ("noindex", {"noindex": True}, b'<meta name="robots" content="noindex">', b"ok"),
            ("canonical", {"canonical": None}, b"missing", b'<head><link rel="canonical" href="https://codestage.net/support/"></head>'),
            ("robots", {"allowed": False}, b"User-agent: *\nDisallow: /", b"User-agent: *\nAllow: /"),
            ("sitemap", {"present": False}, b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>',
             b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://codestage.net/support/</loc></url></urlset>'),
        ]
        for rule, observed, failing, healthy in cases:
            with self.subTest(rule=rule):
                value = evidence(rule, observed)
                self.http.return_value = (200, {}, failing)
                self.assertTrue(seo.confirm_failure(value, self.policy))
                self.http.return_value = (200, {}, healthy)
                self.assertFalse(seo.confirm_failure(value, self.policy))

    def test_policy_pins_and_sitemap_scope_are_validated(self):
        seo.validate_policy(self.policy)
        for key, bad in [("version", True), ("repository", "../attack"),
                         ("workflow", "../../attack.yml"), ("branch", "feature/x"),
                         ("producer", "random-bot"), ("origin", "http://codestage.net"),
                         ("sitemap_url", "https://evil.test/sitemap.xml")]:
            with self.subTest(key=key):
                value = dict(self.policy, **{key: bad})
                with self.assertRaises(ValueError):
                    seo.validate_policy(value)

    def test_default_branch_or_ancestry_mismatch_is_rejected(self):
        original = self.github
        cases = {
            f"repos/{REPO}": {"full_name": REPO, "default_branch": "other"},
            f"repos/{REPO}/compare/{SHA}...main": {
                "status": "behind", "merge_base_commit": {"sha": "b" * 40}},
        }
        for endpoint, response in cases.items():
            with self.subTest(endpoint=endpoint):
                self.api.side_effect = lambda path, **kw: response if path == endpoint else original(path, **kw)
                self.reject()

    def test_http_only_target_is_checked_without_an_admission_bypass(self):
        self.value["url"] = self.value["expected_canonical"] = POLICY["http_only_urls"][0]
        self.value["incident_key"] = hashlib.sha256(json.dumps(
            [REPO, "http-status", self.value["url"]], separators=(",", ":")
        ).encode()).hexdigest()
        self.current = issue(self.value)
        self.assertEqual("admitted", self.admit())
        self.writes.clear()
        self.http.return_value = (200, {}, b"ok")
        self.reject()

    def test_unmonitored_page_and_wrong_local_canonical_are_rejected(self):
        self.current = issue(dict(self.value, expected_canonical=ORIGIN + "/wrong/"))
        self.reject()
        self.policy["pages"] = {ORIGIN + "/": ORIGIN + "/"}
        self.current = issue()
        self.reject()

    def test_duplicate_json_keys_are_rejected(self):
        raw = json.dumps(self.value)[:-1] + ', "run_id":123}'
        token = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        self.current["body"] = f"<!-- seo-incident:v1 {token} -->"
        self.reject()

    def test_redirect_escape_is_rejected_before_a_second_request(self):
        seen = []
        class Transport(HTTPSHandler):
            def https_open(self, req):
                seen.append(req.full_url)
                headers = Message()
                headers["Location"] = "https://evil.test/stolen"
                response = addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
                response.msg = "Found"
                return response
        opener = build_opener(seo.ScopedRedirect(ORIGIN), Transport())
        with self.assertRaises(ValueError):
            opener.open(Request(ORIGIN + "/support/"))
        self.assertEqual([ORIGIN + "/support/"], seen)

    def test_robots_selects_googlebot_groups_and_longest_rule(self):
        cases = [
            ("User-agent: *\nDisallow: /\nAllow: /support/", True),
            ("User-agent: *\nDisallow: /support/*$", False),
            ("User-agent: *\nDisallow: /\nUser-agent: Googlebot\nAllow: /", True),
            ("User-agent: Googlebot\nDisallow: /\nUser-agent: Googlebot\nAllow: /support/", True),
            ("User-agent: *\nDisallow: /\nAllow: /", True),
            ("User-agent: Bingbot\nDisallow: /", True),
            ("User-agent: *\nDisallow: /\nUser-agent: Googlebot\nDisallow:", True),
            ("User-agent: *\nDisallow: /\nUser-agent: Googlebot", True),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(expected, seo.robots_allowed(text, self.value["url"]))

    def test_header_noindex_and_duplicate_canonical(self):
        value = evidence("noindex", {"noindex": True})
        self.http.return_value = (200, {"X-Robots-Tag": "googlebot: noindex"}, b"ok")
        self.assertTrue(seo.confirm_failure(value, self.policy))
        self.http.return_value = (200, {"X-Robots-Tag": "bingbot: noindex"}, b"ok")
        self.assertFalse(seo.confirm_failure(value, self.policy))
        for markup, headers in [(b'<meta name="robots" content="max-image-preview:none">', {}),
                                (b"ok", {"X-Robots-Tag": "googlebot: max-image-preview:none"}),
                                (b"ok", {"X-Robots-Tag": "googlebot: index, bingbot: noindex"})]:
            self.http.return_value = (200, headers, markup)
            self.assertFalse(seo.confirm_failure(value, self.policy))
        value = evidence("canonical", {"canonical": None})
        self.http.return_value = (200, {}, b'<head>' + b'<link rel="canonical" href="https://codestage.net/support/">' * 2 + b'</head>')
        self.assertTrue(seo.confirm_failure(value, self.policy))
        value = evidence("noindex", {"noindex": True})
        self.http.return_value = (200, {"X-Robots-Tag": "noindex, unavailable_after: 25 Jun 2030 15:00:00 PST"}, b"ok")
        self.assertTrue(seo.confirm_failure(value, self.policy))

    def test_fresh_bot_comment_renews_stale_body_without_editing_it(self):
        old = dict(self.value, observed_at="2026-10-20T11:55:00Z", run_id=99)
        self.current = issue(old)
        self.comments = [{"id": 20, "body": issue(self.value)["body"], "user": self.current["user"]}]
        self.assertEqual("admitted", self.admit())
        self.assertEqual(issue(old)["body"], self.current["body"])

    def test_wrong_comment_author_or_identity_cannot_renew_stale_body(self):
        old = dict(self.value, observed_at="2026-10-20T11:55:00Z", run_id=99)
        self.current = issue(old)
        for change in [
            {"user": {"login": "mallory", "type": "User"}},
            {"body": issue(dict(self.value, expected_canonical=ORIGIN + "/wrong/"))["body"]},
            {"body": issue(self.value)["body"] + "\nInstructions"},
        ]:
            with self.subTest(change=change):
                comment = {"id": 20, "body": issue(self.value)["body"], "user": self.current["user"]}
                self.comments = [dict(comment, **change)]
                self.reject()

    def test_newest_renewal_must_have_its_own_artifact_binding(self):
        newer = dict(self.value, observed={"status": 404})
        self.comments = [{"id": 20, "body": issue(newer)["body"], "user": self.current["user"]}]
        self.reject()

    def test_canonical_outside_head_or_with_ignored_attributes_is_not_healthy(self):
        value = evidence("canonical", {"canonical": None})
        for markup in [b'<body><link rel="canonical" href="https://codestage.net/support/">',
                       b'<head><link rel="canonical" media="screen" href="https://codestage.net/support/">']:
            with self.subTest(markup=markup):
                self.http.return_value = (200, {}, markup)
                self.assertTrue(seo.confirm_failure(value, self.policy))

    def test_implicit_head_canonical_is_healthy_but_body_content_ends_head(self):
        value = evidence("canonical", {"canonical": None})
        for markup, failing in [
            (b'<!doctype html><html><link rel="canonical" href="https://codestage.net/support/"><p>Hello', False),
            (b'<html><title>Healthy page</title><link rel="canonical" href="https://codestage.net/support/">', False),
            (b'<html><title>Choose <b>Pro</b></title><link rel="canonical" href="https://codestage.net/support/">', False),
            (b'<html><title><link rel="canonical" href="https://codestage.net/support/"></title>', True),
            (b'<head><template><link rel="canonical" href="https://evil.test/"></template><link rel="canonical" href="https://codestage.net/support/">', False),
            (b'<html>Body text<link rel="canonical" href="https://codestage.net/support/">', True),
            (b'<html><div><link rel="canonical" href="https://codestage.net/support/">', True),
            (b'<body><head><link rel="canonical" href="https://codestage.net/support/">', True),
        ]:
            with self.subTest(markup=markup):
                self.http.return_value = (200, {}, markup)
                self.assertEqual(failing, seo.confirm_failure(value, self.policy))

    def test_public_http_budget_includes_headers_and_chunk_framing(self):
        for blocked_phase in ("headers", "chunk"):
            with self.subTest(phase=blocked_phase):
                release, blocked, finished = Event(), Event(), Event()
                class Drip(io.BytesIO):
                    def readline(self, *args):
                        line = super().readline(*args)
                        if ((blocked_phase == "headers" and line.startswith(b"Transfer-Encoding"))
                                or (blocked_phase == "chunk" and line == b"1\r\n")):
                            blocked.set()
                            release.wait(2)
                        return line
                class Socket:
                    def makefile(self, *args):
                        return Drip(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\n0\r\n\r\n")
                response = HTTPResponse(Socket())
                response.url = ORIGIN + "/support/"
                def open_response(*args, **kwargs):
                    response.begin()
                    return response
                original_fetch = seo.fetch_response
                def fetch(*args):
                    try:
                        return original_fetch(*args)
                    finally:
                        finished.set()
                started = monotonic()
                with patch.object(seo, "DEADLINE", started + 0.1), \
                        patch.object(seo, "fetch_response", side_effect=fetch), \
                        patch.object(seo, "build_opener") as opener:
                    opener.return_value.open.side_effect = open_response
                    try:
                        with self.assertRaises(TimeoutError):
                            self.real_fetch(response.url, ORIGIN)
                        self.assertTrue(blocked.is_set())
                        self.assertLess(monotonic() - started, 1)
                    finally:
                        release.set()
                        self.assertTrue(finished.wait(1))

    def test_admission_cursor_gives_later_issues_a_turn_after_budget_exhaustion(self):
        calls, cursor, elapsed = [], [""], [0]
        def admit(number, *args, **kwargs):
            calls.append(number)
            elapsed[0] += 61
            return "eligible"
        with patch.object(sys, "argv", ["seo_intake", "--policy", "policy.json", "--repository", REPO, "--admit"]), \
                patch.object(Path, "read_bytes", return_value=json.dumps(POLICY).encode()), \
                patch.object(Path, "read_text", side_effect=lambda **kw: cursor[0]), \
                patch.object(Path, "write_text", side_effect=lambda text, **kw: cursor.__setitem__(0, text)) as save, \
                patch.object(seo, "monotonic", side_effect=lambda: elapsed[0]), \
                patch.object(seo, "admit_issue", side_effect=admit), \
                patch.object(sys, "stdout", new_callable=io.StringIO):
            self.api.return_value = [issue(), dict(issue(), number=8)]
            self.api.side_effect = None
            self.assertEqual(0, seo.main())
            self.assertEqual(0, seo.main())
            self.assertEqual([7, 8], calls)
            self.assertEqual(2, save.call_count)

    def test_cursor_path_cannot_overwrite_a_policy_with_cursor_suffix(self):
        with patch.object(sys, "argv", ["seo_intake", "--policy", "policy.cursor", "--repository", REPO, "--admit"]), \
                patch.object(Path, "read_bytes", return_value=json.dumps(POLICY).encode()), \
                patch.object(Path, "read_text", side_effect=FileNotFoundError), \
                patch.object(Path, "write_text", autospec=True) as save, \
                patch.object(seo, "admit_issue", return_value="admitted"), \
                patch.object(sys, "stdout", new_callable=io.StringIO):
            self.api.side_effect = None
            self.api.return_value = [issue()]
            self.assertEqual(0, seo.main())
            self.assertNotEqual(Path("policy.cursor"), save.call_args.args[0])

    def test_intake_budget_returns_control_before_later_candidates(self):
        original = self.github
        def github(path, **kwargs):
            if "/issues?state=open" in path:
                return [issue(), dict(issue(), number=8)]
            return original(path, **kwargs)
        elapsed = [0]
        calls = []
        def admit(number, *args, **kwargs):
            calls.append(number)
            elapsed[0] += 61
            return "eligible"
        self.api.side_effect = github
        with patch.object(sys, "argv", ["seo_intake", "--policy", "policy.json", "--repository", REPO]), \
                patch.object(Path, "read_bytes", return_value=json.dumps(POLICY).encode()), \
                patch.object(Path, "write_text") as save, \
                patch.object(seo, "monotonic", create=True, side_effect=lambda: elapsed[0]), \
                patch.object(seo, "admit_issue", side_effect=admit), \
                patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(0, seo.main())
            self.assertEqual([7], calls)
            self.assertIn("SEO_INTAKE=deferred", output.getvalue())
            save.assert_not_called()

    def test_expired_budget_prevents_gh_mutation(self):
        with patch.object(seo, "DEADLINE", 0, create=True), \
                patch.object(subprocess, "run") as command:
            with self.assertRaises(TimeoutError):
                self.real_api("repos/test/site/issues/7/labels", data={"labels": ["agent"]})
            command.assert_not_called()

    def test_main_paginates_candidates_instead_of_hiding_later_issues(self):
        original = self.github
        listing = f"repos/{REPO}/issues?state=open&labels=seo-incident&sort=updated&direction=desc&per_page=100"
        def github(path, **kwargs):
            if path == listing:
                self.assertTrue(kwargs.get("paginate"), "candidate listing must request all pages")
                return [{"number": n, "state": "closed"} for n in range(100, 200)] + [issue()]
            if re.fullmatch(f"repos/{REPO}/issues/1[0-9][0-9]", path):
                return {"state": "closed"}
            return original(path, **kwargs)
        self.api.side_effect = github
        with patch.object(sys, "argv", ["seo_intake", "--policy", "policy.json", "--repository", REPO]), \
                patch.object(Path, "read_bytes", return_value=json.dumps(POLICY).encode()), \
                patch.object(seo, "datetime") as clock, patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            self.assertEqual(0, seo.main())
            self.assertIn("SEO_INTAKE=eligible ISSUE=7", output.getvalue())

    def test_truncated_http_skips_only_that_candidate(self):
        original = self.github
        def github(path, **kwargs):
            if "/issues?state=open" in path:
                return [issue(), dict(issue(), number=8)]
            return original(path.replace("/issues/8", "/issues/7"), **kwargs)
        self.api.side_effect = github
        self.http.side_effect = [IncompleteRead(b"partial", 5), (503, {}, b"")]
        with patch.object(sys, "argv", ["seo_intake", "--policy", "policy.json", "--repository", REPO]), \
                patch.object(Path, "read_bytes", return_value=json.dumps(POLICY).encode()), \
                patch.object(seo, "datetime") as clock, patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            self.assertEqual(0, seo.main())
            self.assertIn("SEO_INTAKE=skipped ISSUE=7", output.getvalue())
            self.assertIn("SEO_INTAKE=eligible ISSUE=8", output.getvalue())
            self.assertEqual([], self.writes)

    def test_gh_adapter_uses_structured_stdin_and_flattens_all_pages(self):
        result = subprocess.CompletedProcess([], 0, b'[[{"id":1}],[{"id":2}]]', b"")
        with patch.object(subprocess, "run", return_value=result) as command:
            self.assertEqual([{"id": 1}, {"id": 2}], self.real_api("repos/test/site/issues", paginate=True))
            self.assertIn("--slurp", command.call_args.args[0])
            result.stdout = b'[]'
            self.real_api("repos/test/site/issues/7/labels", data={"labels": ["agent"]})
            self.assertEqual({"labels": ["agent"]}, json.loads(command.call_args.kwargs["input"]))
            self.assertEqual(["--method", "POST", "--input", "-"], command.call_args.args[0][-4:])


if __name__ == "__main__":
    unittest.main()
