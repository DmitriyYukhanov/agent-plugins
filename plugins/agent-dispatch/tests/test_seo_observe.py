from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_observe as observer


REPO = "owner/site"
ROOT = "repos/" + REPO
HEAD = "a" * 40
WORKFLOW = ".github/workflows/deploy.yml"
URL = "https://example.com/"
START = "2026-11-09T01:00:00Z"
END = "2026-11-09T01:03:00Z"
NOW = datetime(2026, 11, 9, 2, tzinfo=timezone.utc)


def feed():
    return dict(format="technical-v1", workflow=WORKFLOW, job="technical", events=["schedule"],
                artifact="report", member="report.json", since=START,
                source_pins={WORKFLOW: "b" * 40, "policy.json": "c" * 40},
                manifests=[dict(origins=["https://example.com"], pages=[dict(url=URL, role="excluded")])])


def evidence(manifest, *, omitted=False):
    obs = dict(url=URL, error="timeout") if omitted else dict(
        url=URL, status=200, final_url=URL, headers=[], trace=[dict(url=URL, status=200)])
    findings = [dict(url=URL, group=URL, severity="error", rule=rule, status="pass", observed=value)
                for rule, value in (("http-status", 200), ("destination", URL))]
    if omitted:
        findings = [dict(url=URL, group=URL, severity="error", rule="collection", status="unknown",
                         observed="timeout")]
    groups = [dict(rule="collection", group=URL, status="unknown", severity="error", urls=[URL])] if omitted else []
    coverage = dict(manifest_sha256=observer.digest(json.dumps(manifest, sort_keys=True).encode()),
                    configured_pages=1, observed_pages=int(not omitted), omitted_pages=[URL] if omitted else [],
                    unknown_sources=[], unknown_targets=[], truncated_sources=[], discovered_targets=0)
    return dict(version=1, observed_at="2026-11-09T01:02:00+00:00",
                status="unknown" if omitted else "pass", complete=not omitted,
                counts={"pass": 0 if omitted else 2, "fail": 0, "unknown": int(omitted)},
                findings=findings, groups=groups, observations=[obs], coverage=coverage, links=[])


def run(run_id=41, attempt=1):
    return dict(id=run_id, run_attempt=attempt, repository={"id": 101, "full_name": REPO},
                head_repository={"id": 101}, path=WORKFLOW, head_branch="main", head_sha=HEAD,
                event="schedule", status="completed", conclusion="success",
                created_at=START, run_started_at=START, updated_at=END)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.feed = feed()
        self.report = evidence(self.feed["manifests"][0])
        self.run_info = run()
        self.job = dict(name="technical", conclusion="success", status="completed", head_sha=HEAD,
                        run_id=41, run_attempt=1, started_at=START, completed_at=END)
        self.artifact = dict(id=51, name="report", size_in_bytes=200, expired=False, created_at=END,
                             workflow_run=dict(id=41, repository_id=101, head_repository_id=101,
                                               head_branch="main", head_sha=HEAD))
        self.compare = {"status": "ahead", "merge_base_commit": {"sha": HEAD}}
        self.tree = {"truncated": False, "tree": [dict(path=p, sha=s, mode="100644")
                                                for p, s in self.feed["source_pins"].items()]}

    def api(self, path, *, binary=False):
        if "/jobs?" in path:
            return {"jobs": [self.job]}
        if "/compare/" in path:
            return self.compare
        if "/git/trees/" in path:
            return self.tree
        if "/artifacts?" in path:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as zipped:
                zipped.writestr("report.json", observer.compact(self.report))
            self.archive = buffer.getvalue()
            self.artifact.setdefault("digest", "sha256:" + observer.digest(self.archive))
            return {"artifacts": [self.artifact]}
        if binary and path == f"{ROOT}/actions/artifacts/51/zip":
            return self.archive
        self.fail(f"Unexpected GitHub API call: {path}")

    def verify(self):
        return observer.verify(self.api, ROOT, REPO, self.feed, self.run_info)

    def test_verifies_owned_report(self):
        receipt = self.verify()
        self.assertEqual(receipt["status"], "healthy")
        self.assertEqual(receipt["counts"], {"pass": 2, "fail": 0, "unknown": 0})
        self.assertEqual(receipt["artifact_id"], 51)

    def test_rejects_fork_old_artifact_and_changed_source(self):
        for target, key, value, message in [
            (self.run_info, "head_repository", {"id": 999}, "run mismatch"),
            (self.artifact, "created_at", "2026-11-09T00:00:00Z", "attempt artifact"),
            (self.tree["tree"][1], "sha", "f" * 40, "source inputs"),
            (self.compare, "status", "diverged", "outside main"),
            (self.artifact, "digest", "sha256:" + "f" * 64, "digest mismatch"),
        ]:
            with self.subTest(key=key), patch.dict(target, {key: value}):
                with self.assertRaisesRegex(ValueError, message):
                    self.verify()

    def test_rejects_wrong_manifest_and_missing_check(self):
        manifest = self.feed["manifests"][0]
        for key, value in [("manifest_sha256", "0" * 64), ("observed_pages", 0)]:
            with self.subTest(key=key), patch.dict(self.report["coverage"], {key: value}):
                with self.assertRaises(ValueError):
                    observer.technical(self.report, manifest)
        self.report["findings"].pop()
        self.report["counts"]["pass"] -= 1
        with self.assertRaisesRegex(ValueError, "missing or inconsistent"):
            observer.technical(self.report, manifest)

    def test_unknown_stays_inconclusive(self):
        self.report = evidence(self.feed["manifests"][0], omitted=True)
        self.assertEqual(self.verify()["status"], "unknown")
        self.report["complete"] = True
        with self.assertRaisesRegex(ValueError, "completeness"):
            observer.technical(self.report, self.feed["manifests"][0])

    def test_failed_job_and_expected_skip_are_separate(self):
        self.job["conclusion"] = "failure"
        self.assertEqual(self.verify()["status"], "unknown")
        self.job["conclusion"] = "skipped"
        self.assertEqual(self.verify()["status"], "skipped")

    def test_report_on_failure_retains_valid_checker_evidence(self):
        self.feed.update(report_on_failure=True, upload_step="upload")
        self.job["steps"] = [dict(name="upload", conclusion="success")]
        self.job["conclusion"] = self.run_info["conclusion"] = "failure"
        self.report = evidence(self.feed["manifests"][0], omitted=True)
        self.assertEqual(self.verify()["artifact_id"], 51)
        self.assertEqual(self.verify()["status"], "unknown")
        self.job["steps"][0]["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "upload did not succeed"):
            self.verify()

    def test_trace_cannot_contradict_http_findings(self):
        self.report["observations"][0]["trace"][0].update(url="https://elsewhere.invalid/", status=500)
        with self.assertRaisesRegex(ValueError, "invalid HTTP trace"):
            self.verify()

    def test_invalid_attempt_does_not_prevent_later_receipt(self):
        with tempfile.TemporaryDirectory() as td, patch.object(
            observer, "verify", side_effect=[RecursionError(), {"status": "healthy"}]
        ):
            state = Path(td)
            observer.scan(lambda *_: {"workflow_runs": [run(41), run(42)]}, state, REPO, self.feed, NOW)
            self.assertEqual(len(list(state.glob("*.retry"))), 1)
            self.assertEqual(len(list(state.glob("*.json"))), 1)

    def test_weekly_empty_plan_does_not_attribute_current_report_to_old_attempt(self):
        start, end = observer.MARKERS
        body = f"{start}\n### sc-domain:example.com\n\nScope: {URL}\n{end}"
        weekly = dict(format="weekly-search-report", report_issue=11,
                      property="sc-domain:example.com", scope=URL)
        api = lambda _: {"body": body, "updated_at": END}
        actual = observer.report_summary([], weekly, self.run_info, api, ROOT)
        self.assertEqual(actual["readback"], "current_block_only")
        self.assertNotIn("report_block_sha256", actual)

    def test_weekly_signal_patch_is_separate_from_report_patch(self):
        start, end = observer.MARKERS
        body = f"{start}\n### sc-domain:example.com\n\nScope: {URL}\n{end}"
        weekly = dict(format="weekly-search-report", report_issue=11,
                      property="sc-domain:example.com", scope=URL)
        api = lambda _: {"body": body, "updated_at": END}
        identity = observer.base64.urlsafe_b64encode(
            json.dumps([weekly["property"], "query", URL]).encode()).decode()
        signal = f"<!-- seo-pulse:signal:{identity} -->"
        plan = [dict(method="PATCH", path=f"/{ROOT}/issues/12",
                     data=dict(body=signal, state="closed"), before=dict(body=signal, number=12)),
                dict(method="PATCH", path=f"/{ROOT}/issues/11", data=dict(body=body))]
        actual = observer.report_summary(plan, weekly, self.run_info, api, ROOT)
        self.assertEqual(actual["readback"], "matched_plan")
        plan[0]["path"] = "/repos/other/site/issues/12"
        with self.assertRaisesRegex(ValueError, "signal scope"):
            observer.report_summary(plan, weekly, self.run_info, api, ROOT)

    def test_late_run_and_rerun_recorded_once(self):
        rows = [run(42)]
        api = lambda *_: {"workflow_runs": rows}
        with tempfile.TemporaryDirectory() as td, patch.object(observer, "verify", return_value={"status": "healthy"}) as verify:
            state = Path(td)
            observer.scan(api, state, REPO, self.feed, NOW)
            rows[:] = [run(42, 2), run(41)]
            observer.scan(api, state, REPO, self.feed, NOW)
            observer.scan(api, state, REPO, self.feed, NOW)
            self.assertEqual(verify.call_count, 3)
            self.assertEqual(len(list(state.glob("*.json"))), 3)

    def test_write_failure_leaves_run_retryable(self):
        with tempfile.TemporaryDirectory() as td, patch.object(observer, "verify", return_value={"status": "healthy"}) as verify:
            state = Path(td)
            api = lambda *_: {"workflow_runs": [run()]}
            replace = observer.os.replace

            def break_receipt(src, dest):
                if dest.suffix == ".json":
                    raise OSError("simulated interruption")
                replace(src, dest)

            with patch.object(observer.os, "replace", side_effect=break_receipt):
                with self.assertRaises(OSError):
                    observer.scan(api, state, REPO, self.feed, NOW)
            self.assertEqual(list(state.glob("*.json")), [])
            observer.scan(lambda *_: {"workflow_runs": []}, state, REPO, self.feed, NOW)
            self.assertEqual(verify.call_count, 2)

    def test_new_attempt_takes_priority_over_due_retries(self):
        with tempfile.TemporaryDirectory() as td, patch.object(
            observer, "verify", side_effect=ValueError("unverified")
        ) as verify:
            state = Path(td)
            rows = [run(41), run(42), run(43)]
            api = lambda *_: {"workflow_runs": rows}
            observer.scan(api, state, REPO, self.feed, NOW)
            for retry in state.glob("*.retry"):
                observer.os.utime(retry, (NOW.timestamp() - 3600,) * 2)
            rows.append(run(44))
            verify.reset_mock()
            observer.scan(api, state, REPO, self.feed, NOW)
            self.assertEqual(verify.call_args_list[0].args[-1]["id"], 44)

    def test_second_observer_does_not_acquire_lock(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "lock"
            with observer.observation_lock(path) as first, observer.observation_lock(path) as second:
                self.assertTrue(first)
                self.assertFalse(second)
            with observer.observation_lock(path) as again:
                self.assertTrue(again)


if __name__ == "__main__":
    unittest.main()
