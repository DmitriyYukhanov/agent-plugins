"""Exercise report-only SEO behavior without Google or GitHub credentials."""

from copy import deepcopy
from datetime import date
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "skills/seo-pulse/scripts/weekly.py"


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "The weekly runner is not implemented")
        spec = importlib.util.spec_from_file_location("weekly", SCRIPT)
        self.w = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.w)
        self.site = {
            "property": "sc-domain:example.com",
            "page_prefixes": ["https://example.com/"],
            "log": "docs/seo/log.md",
            "measurements": [],
        }
        self.config = {"repository": "owner/site", "report_issue": 1,
                       "allow_public_reports": False, "sites": [self.site]}

    def test_config_accepts_an_arbitrary_third_site(self):
        self.assertEqual(self.w.validate_config(self.config), self.config)

    def test_config_rejects_scope_escape_and_duplicate_property(self):
        for prefix in ("https://example.com.evil/", "http://other.com/", "file:///x"):
            with self.subTest(prefix=prefix):
                self.site["page_prefixes"] = [prefix]
                with self.assertRaises(ValueError):
                    self.w.validate_config(self.config)
        self.site["page_prefixes"] = ["https://example.com/"]
        self.config["sites"].append(deepcopy(self.site))
        with self.assertRaises(ValueError):
            self.w.validate_config(self.config)

    def test_page_scope_has_origin_and_path_boundaries(self):
        self.site["page_prefixes"] = ["https://example.com/docs/"]
        self.assertTrue(self.w.in_scope(self.site, "https://example.com/docs/a"))
        for page in ("https://example.com.evil/docs/a", "https://example.com/docset/a",
                     "https://example.com/docs/../secret", "http://example.com/docs/a"):
            self.assertFalse(self.w.in_scope(self.site, page), page)

    def test_windows_are_equal_inclusive_and_finalized(self):
        self.assertEqual(self.w.windows(date(2026, 10, 23)),
                         ("2026-09-23", "2026-10-20", "2026-08-26", "2026-09-22"))

    def test_gsc_accepts_document_anchors_without_widening_scope(self):
        self.site["page_prefixes"] = ["https://example.com/docs/"]
        api = self.w.API("fake", "fake")
        page = "https://example.com/docs/manual/index.html#how-to-use-this-manual"
        row = {"keys": ["manual", page], "impressions": 30, "clicks": 0,
               "ctr": 0, "position": 3.8666666666666667}
        requests = []
        api.request = lambda url, token, method, data=None: requests.append(data) or {"rows": [row]}
        self.assertEqual(api.gsc(self.site, "2026-09-01", "2026-09-28",
                                 ("query", "page"), ("manual", page)), [row])
        self.assertEqual(requests[0]["dimensionFilterGroups"][0]["filters"][-1]["expression"], page)
        for outside in ("https://example.com/docset/a#section",
                        "https://other.com/docs/a#section"):
            row["keys"][1] = outside
            with self.subTest(outside=outside), self.assertRaises(ValueError):
                api.gsc(self.site, "2026-09-01", "2026-09-28", ("query", "page"))

    def test_fragment_variants_share_the_canonical_pages_measurement_hold(self):
        self.site["measurements"] = [{"page": "https://example.com/a", "changed_on": "2026-10-15",
                                      "baseline_start": "2026-09-17", "baseline_end": "2026-10-14"}]
        rows = [{"keys": ["manual", f"https://example.com/a#section-{i}"], "impressions": 200,
                 "clicks": 1, "ctr": .005, "position": 3} for i in range(2000)]
        api = self.api(rows=rows)
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["data"]["body"].count("is being measured."), 1)
        self.assertNotIn("#section-", plan[0]["data"]["body"])
        self.assertFalse(self.w.on_hold(self.site, "https://example.com/a?lang=en#section", date(2026, 10, 23)))
        self.assertEqual(api.writes, [])

    def test_configured_prefixes_and_measurements_remain_fragment_free(self):
        self.site["page_prefixes"] = ["https://example.com/#section"]
        with self.assertRaises(ValueError):
            self.w.validate_config(self.config)
        self.site["page_prefixes"] = ["https://example.com/"]
        self.site["measurements"] = [{"page": "https://example.com/a#section", "changed_on": "2026-10-15",
                                      "baseline_start": "2026-09-17", "baseline_end": "2026-10-14"}]
        with self.assertRaises(ValueError):
            self.w.validate_config(self.config)

    def test_signal_floor_and_hold(self):
        row = {"keys": ["actk", "https://example.com/a"], "impressions": 100,
               "clicks": 0, "ctr": 0, "position": 3}
        self.assertEqual(self.w.classify(row), "low-ctr")
        self.assertIsNone(self.w.classify({**row, "impressions": 99}))
        self.site["measurements"] = [{"page": row["keys"][1], "changed_on": "2026-10-15",
                                      "baseline_start": "2026-09-17", "baseline_end": "2026-10-14"}]
        self.assertTrue(self.w.on_hold(self.site, row["keys"][1], date(2026, 10, 23)))
        self.assertFalse(self.w.on_hold(self.site, row["keys"][1], date(2026, 11, 13)))

    def test_stable_key_separates_sites_and_queries(self):
        key = self.w.signal_key(self.site["property"], "actk", "https://example.com/a")
        self.assertEqual(key, self.w.signal_key(self.site["property"], "actk", "https://example.com/a"))
        self.assertNotEqual(key, self.w.signal_key(self.site["property"], "other", "https://example.com/a"))

    def test_managed_block_preserves_human_text_and_rejects_duplicates(self):
        original = "Human notes\n\n<!-- seo-pulse:start -->\nold\n<!-- seo-pulse:end -->\nKeep me"
        updated = self.w.replace_block(original, "new")
        self.assertTrue(updated.startswith("Human notes\n\n"))
        self.assertTrue(updated.endswith("\nKeep me"))
        for body in ("no markers", original + original,
                     "<!-- seo-pulse:end -->\n<!-- seo-pulse:start -->"):
            with self.assertRaises(ValueError):
                self.w.replace_block(body, "new")

    def test_untrusted_text_cannot_inject_markdown_or_mentions(self):
        text = self.w.safe_text("@all | <script>\n`code` <!-- seo-pulse:start -->")
        self.assertNotIn("@all", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("<!--", text)
        self.assertNotIn("\n", text)

    def api(self, issues=None, rows=None):
        w = self.w
        row = {"keys": ["actk", "https://example.com/a"], "impressions": 200,
               "clicks": 1, "ctr": .005, "position": 3}

        class FakeAPI:
            def __init__(self):
                self.issues = deepcopy(issues or [])
                self.writes = []
                self.report = {"number": 1, "state": "open", "body":
                               "Owner notes\n" + w.block("old"), "updated_at": "now"}

            def viewer(self):
                return "github-actions[bot]"

            def gsc(self, site, start, end, dimensions=(), exact=None):
                if dimensions == ("date", "page"):
                    return [{"keys": [start, exact[1]], "impressions": 200,
                             "clicks": 1, "ctr": .005, "position": 3}]
                if dimensions:
                    return deepcopy([row] if rows is None else rows)
                return [{"clicks": 10, "impressions": 200, "ctr": .05, "position": 4}]

            def github(self, method, path, data=None):
                if method != "GET":
                    self.writes.append((method, path, data))
                    if method == "POST":
                        created = {**data, "number": len(self.issues) + 2, "state": "open",
                                   "user": {"login": "github-actions[bot]"}}
                        self.issues.append(created)
                        return created
                    if path.endswith("/1"):
                        self.report.update(data)
                    else:
                        next(i for i in self.issues if path.endswith('/' + str(i['number']))).update(data)
                    return data
                if "/issues?" in path:
                    return deepcopy(self.issues) if "page=1&" in path else []
                if "/issues/" in path:
                    return deepcopy(self.report if path.endswith("/1") else
                                    next(i for i in self.issues if path.endswith('/' + str(i['number']))))
                if "/labels/" in path:
                    return {"name": "seo-signal"}
                return {"private": True}

        return FakeAPI()

    def test_plan_then_publish_then_identical_rerun_is_noop(self):
        api = self.api()
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertEqual(api.writes, [])
        self.assertEqual([op["method"] for op in plan], ["POST", "PATCH"])
        self.w.publish(plan, api)
        self.assertIn("Owner notes", api.report["body"])
        self.assertEqual(self.w.plan_run(self.config, date(2026, 10, 23), api), [])

    def test_public_destination_needs_explicit_consent(self):
        api = self.api()
        real = api.github
        api.github = lambda method, path, data=None: (
            {"private": False} if path == "/repos/owner/site" else real(method, path, data))
        with self.assertRaises(ValueError):
            self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertEqual(api.writes, [])

    def test_report_pr_or_invalid_markers_abort_before_writes(self):
        for changes in ({"pull_request": {}}, {"body": "no markers"}):
            api = self.api()
            api.report.update(changes)
            with self.assertRaises(ValueError):
                self.w.plan_run(self.config, date(2026, 10, 23), api)
            self.assertEqual(api.writes, [])

    def test_missing_rows_do_not_close_signal_but_positive_resolution_does(self):
        api = self.api()
        self.w.publish(self.w.plan_run(self.config, date(2026, 10, 23), api), api)
        existing = api.issues
        missing = self.api(existing, [])
        plan = self.w.plan_run(self.config, date(2026, 10, 23), missing)
        self.assertFalse(any(op["data"].get("state") == "closed" for op in plan))
        healthy = [{"keys": ["actk", "https://example.com/a"], "impressions": 200,
                    "clicks": 40, "ctr": .2, "position": 3}]
        resolved = self.w.plan_run(self.config, date(2026, 10, 23), self.api(existing, healthy))
        self.assertTrue(any(op["data"].get("state") == "closed" for op in resolved))

    def test_duplicate_or_forged_signal_ownership_aborts(self):
        api = self.api()
        self.w.publish(self.w.plan_run(self.config, date(2026, 10, 23), api), api)
        for issues in ([api.issues[0], api.issues[0]],
                       [{**api.issues[0], "user": {"login": "someone"}}]):
            with self.assertRaises(ValueError):
                self.w.plan_run(self.config, date(2026, 10, 23), self.api(issues))

    def test_failed_read_and_changed_body_prevent_writes(self):
        api = self.api()
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        api.report["body"] += "\nOwner edit"
        with self.assertRaises(ValueError):
            self.w.publish(plan, api)
        self.assertEqual(api.writes, [])

    def test_uncertain_create_is_not_retried(self):
        api = self.api()
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        calls = []
        real = api.github

        def fail(method, path, data=None):
            if method == "POST":
                calls.append(path)
                raise TimeoutError("response lost")
            return real(method, path, data)

        api.github = fail
        with self.assertRaises(TimeoutError):
            self.w.publish(plan, api)
        self.assertEqual(len(calls), 1)

    def test_top_row_cannot_resolve_without_positive_exact_probe(self):
        api = self.api()
        self.w.publish(self.w.plan_run(self.config, date(2026, 10, 23), api), api)
        real = api.gsc

        def missing_probe(site, start, end, dimensions=(), exact=None):
            if exact:
                return []
            return [{**row, "ctr": .5, "position": 2} for row in real(site, start, end, dimensions)]

        api.gsc = missing_probe
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertFalse(any(op["data"].get("state") == "closed" for op in plan))
        self.assertFalse(any("Signal: resolved" in op["data"].get("body", "") for op in plan))

    def test_measurement_baseline_does_not_filter_for_an_empty_query(self):
        api = self.w.API("fake", "fake")
        requests = []
        api.request = lambda url, token, method, data=None: requests.append(data) or {}
        api.gsc(self.site, "2026-09-01", "2026-09-28", exact=(None, "https://example.com/a"))
        filters = requests[0]["dimensionFilterGroups"][0]["filters"]
        self.assertFalse(any(f["dimension"] == "query" for f in filters))

    def test_worsening_rank_does_not_close_signal(self):
        api = self.api()
        self.w.publish(self.w.plan_run(self.config, date(2026, 10, 23), api), api)
        worsening = [{"keys": ["actk", "https://example.com/a"], "impressions": 200,
                      "clicks": 1, "ctr": .005, "position": 40}]
        plan = self.w.plan_run(self.config, date(2026, 10, 23), self.api(api.issues, worsening))
        self.assertFalse(any(op["data"].get("state") == "closed" for op in plan))
        self.assertFalse(any("Signal: resolved" in op["data"].get("body", "") for op in plan))

    def test_gsc_filter_agrees_with_scope_for_slashes_and_queries(self):
        api = self.w.API("fake", "fake")
        import re
        for prefix in ("https://example.com/docs", "https://example.com/docs/"):
            self.site["page_prefixes"] = [prefix]
            payloads = []
            api.request = lambda url, token, method, data=None: payloads.append(data) or {}
            api.gsc(self.site, "2026-09-01", "2026-09-28")
            expression = payloads[0]["dimensionFilterGroups"][0]["filters"][0]["expression"]
            for page in ("https://example.com/docs", "https://example.com/docs?lang=en",
                         "https://example.com/docs/", "https://example.com/docs/a",
                         "https://example.com/docs#section", "https://example.com/docs/#section",
                         "https://example.com/docset/a"):
                self.assertEqual(bool(re.search(expression, page)), self.w.in_scope(self.site, page),
                                 (prefix, page))

    def test_impossible_metrics_abort_collection(self):
        api = self.w.API("fake", "fake")
        valid = {"impressions": 200, "clicks": 1, "ctr": .005, "position": 3}
        for change in ({"ctr": 2}, {"clicks": 201}, {"impressions": True},
                       {"ctr": .5}, {"position": 0}):
            api.request = lambda *args: {"rows": [{**valid, **change}]}
            with self.subTest(change=change), self.assertRaises(ValueError):
                api.gsc(self.site, "2026-09-01", "2026-09-28")

    def test_oversized_plan_aborts_before_any_mutation(self):
        rows = [{"keys": ["q" * 70000, "https://example.com/a"], "impressions": 200,
                 "clicks": 1, "ctr": .005, "position": 3}]
        api = self.api(rows=rows)
        with self.assertRaises(ValueError):
            self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertEqual(api.writes, [])

    def test_four_days_of_evidence_waits_even_with_many_impressions(self):
        api = self.api()
        real = api.gsc

        def recent(site, start, end, dimensions=(), exact=None):
            result = real(site, start, end, dimensions, exact)
            if dimensions == ("date", "page"):
                result[0]["keys"][0] = "2026-10-17"
            return result

        api.gsc = recent
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertFalse(any(op["method"] == "POST" for op in plan))

    def test_server_accepted_create_with_lost_response_is_reconciled(self):
        api = self.api()
        real = api.github

        def lost(method, path, data=None):
            result = real(method, path, data)
            if method == "POST":
                raise TimeoutError("response lost after save")
            return result

        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        api.github = lost
        with self.assertRaises(TimeoutError):
            self.w.publish(plan, api)
        api.github = real
        rerun = self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertFalse(any(op["method"] == "POST" for op in rerun))
        self.w.publish(rerun, api)
        self.assertEqual(self.w.plan_run(self.config, date(2026, 10, 23), api), [])

    def test_scope_regex_handles_hostname_case_and_bare_origin(self):
        import re
        api = self.w.API("fake", "fake")
        for prefix, page in (("https://EXAMPLE.com/docs", "https://example.com/docs/a"),
                             ("https://example.com/", "https://example.com")):
            payloads = []
            self.site["page_prefixes"] = [prefix]
            api.request = lambda url, token, method, data=None: payloads.append(data) or {}
            api.gsc(self.site, "2026-09-01", "2026-09-28")
            expression = payloads[0]["dimensionFilterGroups"][0]["filters"][0]["expression"]
            self.assertEqual(bool(re.search(expression, page)), self.w.in_scope(self.site, page))

    def test_dated_provider_rows_must_match_window_and_exact_page(self):
        api = self.w.API("fake", "fake")
        for keys in (("2000-01-01", "https://example.com/a"),
                     ("2026-09-10", "https://example.com/b")):
            api.request = lambda *args: {"rows": [{"keys": keys, "impressions": 200,
                                                 "clicks": 1, "ctr": .005, "position": 3}]}
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                api.gsc(self.site, "2026-09-01", "2026-09-28", ("date", "page"),
                        ("actk", "https://example.com/a"))

    def test_publisher_identity_mismatch_aborts_before_writes(self):
        api = self.api()
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        api.viewer = lambda: "someone-else"
        with self.assertRaises(ValueError):
            self.w.publish(plan, api)
        self.assertEqual(api.writes, [])

    def test_held_page_reports_wait_once_even_with_thousands_of_queries(self):
        self.site["measurements"] = [{"page": "https://example.com/a", "changed_on": "2026-10-15",
                                      "baseline_start": "2026-09-17", "baseline_end": "2026-10-14"}]
        rows = [{"keys": [f"query-{i}", "https://example.com/a"], "impressions": 1,
                 "clicks": 0, "ctr": 0, "position": 3} for i in range(2000)]
        api = self.api(rows=rows)
        plan = self.w.plan_run(self.config, date(2026, 10, 23), api)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["method"], "PATCH")
        self.assertEqual(plan[0]["data"]["body"].count("is being measured."), 1)
        self.assertEqual(api.writes, [])


    def measurement_api(self, overrides=None):
        self.site["measurements"] = [{"page": "https://example.com/a", "changed_on": "2026-10-01",
                                      "baseline_start": "2026-09-03", "baseline_end": "2026-09-30"}]
        api = self.api(rows=[])
        original = api.gsc
        api.measurement_reads = []

        def measured(site, start, end, dimensions=(), exact=None):
            if exact == (None, "https://example.com/a"):
                api.measurement_reads.append((start, end, dimensions, exact))
                if overrides and (start, end) in overrides:
                    return deepcopy(overrides[(start, end)])
                return [{"keys": [end, exact[1]], "clicks": 28, "impressions": 280,
                         "ctr": .1, "position": 4}]
            return original(site, start, end, dimensions, exact)

        api.gsc = measured
        return api

    def test_due_measurements_keep_fixed_dates_and_compare_daily_counts(self):
        api = self.measurement_api()
        config_before = deepcopy(self.config)
        plan = self.w.plan_run(self.config, date(2026, 11, 1), api)
        body = plan[-1]["data"]["body"]
        self.assertIn("Reconstructed fixed baseline 2026-09-03 to 2026-09-30 (28 days)", body)
        self.assertIn("+2 weeks 2026-10-02 to 2026-10-15 (14 days)", body)
        self.assertIn("+4 weeks 2026-10-02 to 2026-10-29 (28 days)", body)
        self.assertIn("| 28 | 280 | 10.00% | 4.00 | 1 | 10 |", body)
        self.assertIn("| 28 | 280 | 10.00% | 4.00 | 2 | 20 |", body)
        self.assertEqual(body.count("Enough evidence to review"), 2)
        self.assertIn("daily counts", body)
        self.assertIn("original logged baseline", body)
        self.assertEqual(self.config, config_before)
        self.assertEqual(api.writes, [])
        self.assertEqual(api.measurement_reads, [
            ("2026-09-03", "2026-09-30", ("date", "page"), (None, "https://example.com/a")),
            ("2026-10-02", "2026-10-15", ("date", "page"), (None, "https://example.com/a")),
            ("2026-10-02", "2026-10-29", ("date", "page"), (None, "https://example.com/a")),
        ])

    def test_measurements_wait_on_low_volume_and_keep_missing_rows_unknown(self):
        for rows, expected in (([], "Unavailable: missing baseline or post-change rows"),
                               ([{"keys": ["2026-10-29", "https://example.com/a"],
                                  "clicks": 0, "impressions": 0, "ctr": 0, "position": 0}],
                                "Keep measuring: fewer than 100 impressions")):
            with self.subTest(rows=rows):
                api = self.measurement_api({("2026-10-02", "2026-10-29"): rows})
                body = self.w.plan_run(self.config, date(2026, 11, 1), api)[-1]["data"]["body"]
                self.assertIn(expected, body)
                self.assertIn("unknown | unknown | unknown | unknown" if not rows else
                              "0 | 0 | unknown | unknown | 0 | 0", body)

    def test_measurements_wait_when_finalized_endpoint_is_absent(self):
        for window, endpoint in ((("2026-09-03", "2026-09-30"), "2026-09-29"),
                                 (("2026-10-02", "2026-10-29"), "2026-10-28")):
            with self.subTest(window=window):
                api = self.measurement_api({window: [{"keys": [endpoint, "https://example.com/a"],
                                                       "clicks": 28, "impressions": 280,
                                                       "ctr": .1, "position": 4}]})
                body = self.w.plan_run(self.config, date(2026, 11, 1), api)[-1]["data"]["body"]
                self.assertIn("Keep measuring: finalized coverage is unconfirmed", body)
                self.assertIn(endpoint, body)
                self.assertNotIn("+4 weeks: Enough evidence", body)

    def test_missing_baseline_and_failed_measurement_reads_never_publish(self):
        api = self.measurement_api({("2026-09-03", "2026-09-30"): []})
        body = self.w.plan_run(self.config, date(2026, 11, 1), api)[-1]["data"]["body"]
        self.assertEqual(body.count("Unavailable: missing baseline or post-change rows"), 2)
        original = api.gsc

        def fail_checkpoint(site, start, end, dimensions=(), exact=None):
            if start == "2026-10-02":
                raise RuntimeError("measurement collection failed")
            return original(site, start, end, dimensions, exact)

        api.gsc = fail_checkpoint
        with self.assertRaises(RuntimeError):
            self.w.plan_run(self.config, date(2026, 11, 1), api)
        self.assertEqual(api.writes, [])

    def test_measurements_reject_invalid_baseline_before_collection(self):
        api = self.measurement_api()
        for first, last in (("2026-10-01", "2026-10-01"), ("2026-09-30", "2026-09-03")):
            self.site["measurements"][0].update(baseline_start=first, baseline_end=last)
            with self.subTest(first=first, last=last), self.assertRaises(ValueError):
                self.w.plan_run(self.config, date(2026, 11, 1), api)
        self.assertEqual(api.measurement_reads, [])
        self.assertEqual(api.writes, [])

    def test_measurement_rerun_is_noop_and_does_not_complete_hold(self):
        api = self.measurement_api()
        self.w.publish(self.w.plan_run(self.config, date(2026, 10, 29), api), api)
        self.assertEqual(self.w.plan_run(self.config, date(2026, 10, 29), api), [])
        self.assertEqual(len(self.site["measurements"]), 1)
        self.assertTrue(self.w.on_hold(self.site, "https://example.com/a#section", date(2026, 10, 29)))

    def test_pending_measurement_does_not_query_post_change_window(self):
        api = self.measurement_api()
        body = self.w.plan_run(self.config, date(2026, 10, 14), api)[-1]["data"]["body"]
        self.assertIn("+2 weeks: 2026-10-15 (pending)", body)
        self.assertIn("+4 weeks: 2026-10-29 (pending)", body)
        self.assertEqual(len(api.measurement_reads), 1)

    def test_measurement_date_reads_use_only_final_data_and_exact_page(self):
        api = self.w.API("fake", "fake")
        payloads = []
        api.request = lambda url, token, method, data=None: payloads.append(data) or {}
        self.assertEqual(api.gsc(self.site, "2026-10-02", "2026-10-15", ("date", "page"),
                                 (None, "https://example.com/a")), [])
        self.assertEqual(payloads[0]["dataState"], "final")
        self.assertEqual(payloads[0]["dimensions"], ["date", "page"])
        self.assertEqual(payloads[0]["dimensionFilterGroups"][0]["filters"][-1],
                         {"dimension": "page", "operator": "equals", "expression": "https://example.com/a"})


if __name__ == "__main__":
    unittest.main()
