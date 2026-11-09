"""Record observations from explicitly enrolled GitHub Actions report feeds."""
import argparse
import base64
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from time import monotonic
from urllib.parse import unquote, urlsplit
import zipfile
import zlib

import seo_intake as github
from seo_intake import compact, load_json, require, utc

WINDOW = timedelta(days=7)
STATES = ("pass", "fail", "unknown")
INVALID = (ValueError, KeyError, TypeError, AttributeError, OSError, RecursionError,
           zipfile.BadZipFile, zlib.error, subprocess.SubprocessError)
SHA = re.compile(r"[0-9a-f]{40}")
MARKERS = ("<!-- seo-pulse:start -->", "<!-- seo-pulse:end -->")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), "duplicate evidence keys")
    return result


def technical(report, manifest):
    pages = unique(manifest["pages"], "url")
    coverage = report["coverage"]
    obs = unique(report["observations"], "url")
    require(type(report["version"]) is int and report["version"] == 1
            and coverage["manifest_sha256"] == digest(json.dumps(manifest, sort_keys=True).encode())
            and obs.keys() == pages.keys(), "technical manifest or URL scope mismatch")
    omitted = {url for url, row in obs.items() if "error" in row}
    require(sorted(coverage["omitted_pages"]) == sorted(omitted)
            and coverage["configured_pages"] == len(pages)
            and coverage["observed_pages"] == len(pages) - len(omitted), "invalid page coverage")
    findings = report["findings"]
    counts = Counter(row["status"] for row in findings)
    require(not counts.keys() - set(STATES)
            and report["counts"] == {key: counts[key] for key in STATES}, "invalid finding counts")
    expected = {}
    link_sources = {url for url, page in pages.items() if page.get("check_links")}
    for url, page in pages.items():
        rules = {"sitemap"} if "in_sitemap" in page else set()
        row = obs[url]
        if url in omitted:
            require(isinstance(row["error"], str) and bool(row["error"]), "invalid omission")
            rules.add("collection")
        elif "rejected_destination" in row:
            verify_trace(row["trace"], url, row["final_url"], None,
                         lambda hop: owned_link(hop, {"link_prefixes": manifest["origins"]}))
            require(row["status"] is None and isinstance(row["rejected_destination"], str),
                    "invalid rejected redirect")
            rules.update(("destination", "collection"))
        else:
            require(type(row["status"]) is int, "invalid HTTP observation")
            verify_trace(row["trace"], url, row["final_url"], row["status"],
                         lambda hop: owned_link(hop, {"link_prefixes": manifest["origins"]}))
            rules.update(("http-status", "destination"))
            if row["status"] == 200 and page["role"] != "excluded":
                media = [v.split(";", 1)[0].strip().lower()
                         for k, v in row["headers"] if k.lower() == "content-type"]
                if any(v not in ("text/html", "application/xhtml+xml") for v in media):
                    rules.add("html-content")
                    headers = [v for k, v in row["headers"] if k.lower() == "x-robots-tag"]
                    if header_noindex(headers):
                        rules.add("noindex-directive")
                else:
                    rules.add("noindex-directive")
                    rules.update(key for key in ("canonical", "organization", "lang", "article")
                                 if page.get(key))
                    rules.update("meta:" + key for key in page.get("required_meta", []))
                    if page.get("require_title"):
                        rules.add("title")
        expected[url] = rules

    unknown_sources = set(coverage["unknown_sources"])
    require(unknown_sources <= link_sources and set(coverage["truncated_sources"]) <= unknown_sources,
            "invalid link-source coverage")
    actual = {url: set() for url in pages}
    link_findings = []
    groups = {}
    for row in findings:
        url, rule, status = row["url"], row["rule"], row["status"]
        require(url in pages, "finding leaves manifest")
        if rule == "link-target":
            link_findings.append(row["observed"])
            require(url == row["observed"]["source"] and status == row["observed"]["status"]
                    and row["group"] == row["observed"]["target"], "link finding mismatch")
        elif rule == "link-source":
            require(url in unknown_sources and status == "unknown", "unexpected link-source finding")
        else:
            require(rule not in actual[url], "duplicate page finding")
            actual[url].add(rule)
            if rule in ("collection", "html-content"):
                require(status == "unknown", "collection gap marked conclusive")
            if rule == "destination" and "rejected_destination" in obs[url]:
                require(status == "fail" and row["observed"] == obs[url]["rejected_destination"],
                        "rejected redirect finding mismatch")
            elif rule in ("http-status", "destination") and "rejected_destination" not in obs[url]:
                key, value = (("status", pages[url].get("status", 200)) if rule == "http-status"
                              else ("final_url", pages[url].get("final_url", url)))
                require(row["observed"] == obs[url][key]
                        and status == ("pass" if obs[url][key] == value else "fail"),
                        "HTTP finding contradicts observation")
        if status != "pass":
            key = (rule, row["group"], status, row["severity"])
            groups.setdefault(key, dict(rule=rule, group=key[1], status=status,
                                        severity=key[3], urls=[]))["urls"].append(url)
    require(actual == expected and report["groups"] == list(groups.values()), "missing or inconsistent checks")
    require({row["url"] for row in findings if row["rule"] == "link-source"} == unknown_sources,
            "missing link-source checks")
    require(link_findings == report["links"], "missing link checks")
    targets = set()
    unknown_targets = set()
    for link in report["links"]:
        target = link["target"]
        require(link["source"] in link_sources and owned_link(target, manifest), "link leaves scope")
        targets.add(target)
        if link["status"] == "unknown":
            unknown_targets.add(target)
        else:
            require(type(link["http_status"]) is int
                    and link["status"] == ("pass" if 200 <= link["http_status"] < 300 else "fail"),
                    "invalid link response")
            verify_trace(link["trace"], target, link["final_url"], link["http_status"],
                         lambda hop: owned_link(hop, manifest))
    require(coverage["discovered_targets"] == len(targets)
            and sorted(coverage["unknown_targets"]) == sorted(unknown_targets), "invalid link coverage")
    require(report["complete"] is (not counts["unknown"])
            and report["status"] == ("fail" if counts["fail"] else "unknown" if counts["unknown"] else "pass"),
            "invalid report completeness")
    return counts, sorted({(r["rule"], r["group"], r["url"]) for r in findings if r["status"] == "fail"})


def verify_trace(trace, initial, final, status, allowed):
    redirects = {301, 302, 303, 307, 308}
    require(isinstance(trace, list) and 1 <= len(trace) <= 6
            and trace[0]["url"] == initial and trace[-1]["url"] == final
            and all(type(hop["status"]) is int and 100 <= hop["status"] <= 599
                    and allowed(hop["url"]) for hop in trace)
            and all(hop["status"] in redirects for hop in trace[:-1])
            and (trace[-1]["status"] in redirects if status is None else trace[-1]["status"] == status),
            "invalid HTTP trace")


def header_noindex(values):
    parameters = {"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"}
    for value in values:
        scope = None
        for directive in value.lower().split(","):
            part = directive.strip()
            prefix, sep, rest = part.partition(":")
            if sep and prefix.strip() not in parameters:
                scope, part = prefix.strip(), rest.strip()
            if scope in (None, "googlebot") and part in ("noindex", "none"):
                return True
    return False


def owned_link(url, manifest):
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    return (not parsed.fragment and not re.search(r"[\x00-\x20\\]|%2f|%5c|%25", parsed.path, re.I)
            and not re.search(r"[\x00-\x20\\]", path)
            and not {".", ".."}.intersection(path.split("/"))
            and any((parsed.scheme, parsed.netloc) == (p.scheme, p.netloc)
                    and (path == unquote(p.path).rstrip("/") or path.startswith(unquote(p.path).rstrip("/") + "/"))
                    for p in map(urlsplit, manifest.get("link_prefixes", []))))


def report_summary(report, feed, run, api, root):
    kind = feed["format"]
    if kind == "technical-v1":
        if "checker_commit" in feed and feed.get("wrapped"):
            require(report["source_sha"] == run["head_sha"]
                    and report["plugin_commit"] == feed["checker_commit"]
                    and report["outside_scope"] == feed["outside_scope"], "technical provenance mismatch")
            reports = report["reports"]
        else:
            reports = [report]
        require(len(reports) == len(feed["manifests"]) > 0, "missing technical batches")
        counts = Counter()
        findings = set()
        for batch, manifest in zip(reports, feed["manifests"]):
            observed = datetime.fromisoformat(batch["observed_at"])
            require(utc(run["run_started_at"]) <= observed <= utc(run["updated_at"]) + timedelta(seconds=1),
                    "technical report timestamp outside attempt")
            batch_counts, batch_findings = technical(batch, manifest)
            counts.update(batch_counts)
            findings.update(batch_findings)
        return {"status": "unknown" if counts["unknown"] else "finding" if counts["fail"] else "healthy",
                "counts": {key: counts[key] for key in STATES}, "findings": sorted(findings)}
    if kind == "indexing-observations":
        rows = unique(report["results"], "url")
        collected = datetime.fromisoformat(report["collected_at"])
        require(report["property"] == feed["property"] and rows.keys() == set(feed["urls"])
                and utc(run["run_started_at"]) <= collected <= utc(run["updated_at"]) + timedelta(seconds=1),
                "indexing provenance or URL scope mismatch")
        counts = Counter(row["verdict"] for row in rows.values())
        require(not counts.keys() - {"PASS", "NEUTRAL", "FAIL", "PARTIAL", "VERDICT_UNSPECIFIED"},
                "invalid indexing verdict")
        return {"status": "observation", "counts": dict(counts)}
    require(kind == "weekly-search-report" and isinstance(report, list), "unsupported report format")
    issue = feed["report_issue"]
    require(type(issue) is int and issue > 0, "invalid report issue")
    report_path = f"/{root}/issues/{issue}"
    patches = []
    for row in report:
        method, path, data = row["method"], row["path"], row["data"]
        if method == "PATCH" and path == report_path:
            require(set(data) == {"body"}, "unexpected report write")
            patches.append(report_block(data["body"], feed))
            continue
        post = method == "POST" and path == f"/{root}/issues"
        patch = method == "PATCH" and re.fullmatch(re.escape(f"/{root}/issues/") + r"[1-9][0-9]*", path)
        marker = re.match(r"<!-- seo-pulse:signal:([A-Za-z0-9_=-]{1,4096}) -->", data["body"])
        require((post or patch) and marker, "weekly plan leaves configured report or signal scope")
        prop, query, url = load_json(base64.b64decode(marker[1], altchars=b"-_", validate=True))
        require(prop == feed["property"] and isinstance(query, str)
                and owned_link(url, {"link_prefixes": [feed["scope"]]}), "weekly signal leaves scope")
        require((post and data.get("labels") == ["seo-signal"])
                or (patch and data.get("state") in ("open", "closed")
                    and row["before"]["number"] == int(path.rsplit("/", 1)[-1])
                    and marker[0] in row["before"]["body"]), "invalid weekly signal write")
    require(len(patches) <= 1, "duplicate weekly report write")
    current = api(f"{root}/issues/{issue}")
    block = report_block(current["body"], feed)
    result = {"status": "observation", "planned_writes": len(report)}
    if not patches:
        return dict(result, readback="current_block_only", current_block_sha256=digest(block.encode()))
    if patches[0] == block:
        return dict(result, readback="matched_plan", report_block_sha256=digest(block.encode()))
    require(utc(current["updated_at"]) > utc(run["updated_at"]), "weekly report readback differs")
    return dict(result, readback="superseded", planned_block_sha256=digest(patches[0].encode()))


def report_block(body, feed):
    start, end = MARKERS
    require(body.count(start) == body.count(end) == 1 and body.index(start) < body.index(end),
            "weekly report block missing or ambiguous")
    block = body.split(start, 1)[1].split(end, 1)[0]
    require(f"\n### {feed['property']}\n" in block and f"\nScope: {feed['scope']}\n" in block,
            "weekly report scope mismatch")
    return block


def pages(api, path, key, maximum=10):
    for page in range(1, maximum + 1):
        response = api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        rows = response[key]
        yield from rows
        if len(rows) < 100:
            return
    raise ValueError("GitHub listing exceeds scan limit")


def verify(api, root, repository, feed, run):
    run_id, attempt, head = run["id"], run["run_attempt"], run["head_sha"]
    require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0
            and SHA.fullmatch(head) and run["repository"]["full_name"].lower() == repository.lower()
            and run["head_repository"]["id"] == run["repository"]["id"]
            and run["path"] == feed["workflow"] and run["head_branch"] == "main"
            and run["event"] in feed["events"] and run["status"] == "completed", "workflow run mismatch")
    run_path = f"{root}/actions/runs/{run_id}"
    jobs = [j for j in pages(api, f"{run_path}/attempts/{attempt}/jobs", "jobs")
            if j["name"] in [feed["job"], *feed.get("prerequisites", [])]]
    jobs = unique(jobs, "name")
    job = jobs.get(feed["job"])
    require(set(jobs) == {feed["job"], *feed.get("prerequisites", [])}
            and all(j["head_sha"] == head and j["run_id"] == run_id and j["run_attempt"] == attempt
                    and j["status"] == "completed" for j in jobs.values()), "required job identity mismatch")
    compare = api(f"{root}/compare/{head}...main?per_page=1")
    require(compare["status"] in ("identical", "ahead") and compare["merge_base_commit"]["sha"] == head,
            "run source is outside main history")
    tree = api(f"{root}/git/trees/{head}?recursive=1")
    pins = feed["source_pins"]
    require(not tree["truncated"] and feed["workflow"] in pins
            and all(SHA.fullmatch(sha) for sha in pins.values()), "missing reviewed source pins")
    inputs = {row["path"]: row["sha"] for row in tree["tree"]
              if row["path"] in pins and row["mode"] in ("100644", "100755", "040000")}
    require(inputs == pins, "reviewed source inputs changed")
    if job["conclusion"] == "skipped" and run["conclusion"] in ("success", "failure"):
        return {"status": "skipped"}
    # Some pinned checkers upload a usable report after exiting nonzero for findings.
    accepts_failure = feed.get("report_on_failure") is True and feed["format"] == "technical-v1"
    allowed = ("success", "failure") if accepts_failure else ("success",)
    if (run["conclusion"] not in allowed or job["conclusion"] not in allowed
            or any(jobs[name]["conclusion"] != "success" for name in feed.get("prerequisites", []))):
        return {"status": "unknown", "reason": "required workflow or job did not succeed"}
    if accepts_failure:
        steps = unique([step for step in job["steps"] if step["name"] == feed["upload_step"]], "name")
        require(steps[feed["upload_step"]]["conclusion"] == "success", "artifact upload did not succeed")
    artifacts = [a for a in pages(api, f"{run_path}/artifacts", "artifacts") if a["name"] == feed["artifact"]
                 and utc(job["started_at"]) <= utc(a["created_at"]) <= utc(job["completed_at"])]
    require(len(artifacts) == 1, "missing or ambiguous attempt artifact")
    artifact = artifacts[0]
    expected = dict(id=run_id, repository_id=run["repository"]["id"], head_repository_id=run["repository"]["id"],
                    head_branch="main", head_sha=head)
    require(artifact["workflow_run"] == expected and artifact["expired"] is False
            and type(artifact["id"]) is int and artifact["id"] > 0
            and 0 < artifact["size_in_bytes"] <= github.LIMIT, "invalid artifact provenance")
    archive = api(f"{root}/actions/artifacts/{artifact['id']}/zip", binary=True)
    archive_sha = digest(archive)
    require(artifact["digest"] == "sha256:" + archive_sha, "artifact digest mismatch")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        members = zipped.infolist()
        require(len(members) == 1 and members[0].filename == feed["member"]
                and 0 < members[0].file_size <= 8 * github.LIMIT, "unexpected artifact contents")
        raw = zipped.read(members[0])
    summary = report_summary(load_json(raw, 8 * github.LIMIT), feed, run, api, root)
    require(job["conclusion"] != "failure" or summary["status"] in ("finding", "unknown"),
            "failed checker contradicts healthy report")
    return dict(summary, artifact_id=artifact["id"], archive_sha256=archive_sha, report_sha256=digest(raw))


@contextmanager
def observation_lock(path):
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            lock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            lock = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            lock()
        except BlockingIOError:
            yield False
        except OSError as error:
            if os.name != "nt" or error.errno != 13:
                raise
            yield False
        else:
            yield True  # Closing the descriptor also releases a dead process's lock.


def save(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as tmp:
        try:
            tmp.write(compact(value) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


def scan(api, state, repository, feed, now):
    require(re.fullmatch(r"[\w.-]+/[\w.-]+", repository, re.ASCII)
            and re.fullmatch(r"\.github/workflows/[\w.-]+\.ya?ml", feed["workflow"], re.ASCII),
            "invalid repository or workflow")
    root = f"repos/{repository}"
    workflow = feed["workflow"].split("/")[-1]
    since = utc(feed["since"])
    cutoff = max(now - WINDOW, since)
    endpoint = (f"{root}/actions/workflows/{workflow}/runs?branch=main&status=completed"
                f"&created=%3E%3D{cutoff:%Y-%m-%dT%H:%M:%SZ}")
    contract = digest(compact([repository, feed]).encode())
    scan_state = state / f"{contract}.scan"
    prior = load_json(scan_state.read_bytes(), 8 * github.LIMIT) if scan_state.exists() else {}
    last = datetime.fromisoformat(prior["scanned_at"]) if prior else since
    gap = prior.get("gap_before")
    if last < cutoff:
        gap = cutoff.isoformat()
    pending = prior.get("pending", {})
    for run in pages(api, endpoint, "workflow_runs"):
        if run["event"] not in feed["events"]:
            continue
        require(type(run["id"]) is int and type(run["run_attempt"]) is int, "invalid run identity")
        key = f"{run['id']}-{run['run_attempt']}"
        if (state / f"{contract}-{key}.json").exists():
            continue
        pending[key] = {field: run[field] for field in (
            "id", "run_attempt", "head_sha", "head_branch", "path", "event", "status", "conclusion",
            "created_at", "run_started_at", "updated_at")}
        pending[key]["repository"] = {k: run["repository"][k] for k in ("id", "full_name")}
        pending[key]["head_repository"] = {"id": run["head_repository"]["id"]}
    pending = {key: run for key, run in pending.items() if not (state / f"{contract}-{key}.json").exists()}
    if gap != prior.get("gap_before"):
        print(f"OBSERVATION={repository}/{workflow} coverage gap before {gap}", file=sys.stderr)
    save(scan_state, {"scanned_at": now.isoformat(), "gap_before": gap, "pending": pending})
    ready = []
    for key, run in pending.items():
        target = state / f"{contract}-{key}.json"
        retry = target.with_suffix(".retry")
        last_try = retry.stat().st_mtime if retry.exists() else 0
        if now.timestamp() - last_try >= 1800:
            ready.append((last_try, run, target, retry))
    for _, run, target, retry in sorted(ready, key=lambda item: (item[0], item[1]["created_at"]))[:3]:
        if monotonic() >= github.DEADLINE:
            break
        try:
            result = verify(api, root, repository, feed, run)
        except INVALID as error:
            reason = str(error) if type(error) is ValueError else type(error).__name__
            if now - utc(run["run_started_at"]) < 2 * WINDOW:
                save(retry, {"status": "unverified", "checked_at": now.isoformat(), "reason": reason})
                print(f"OBSERVATION={repository}/{workflow}/{run['id']} unverified", file=sys.stderr)
                continue
            result = {"status": "unknown", "reason": f"retry window elapsed: {reason}"}
        save(target, dict(result, repository=repository, workflow=feed["workflow"], contract=contract,
                          run_id=run["id"], attempt=run["run_attempt"], source_sha=run["head_sha"],
                          created_at=run["created_at"], checked_at=now.isoformat()))
        retry.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    registry = load_json(args.registry.read_bytes(), 8 * github.LIMIT)
    require(registry["version"] == 1, "unsupported monitoring registry")
    feeds = [(site["repository"], feed) for site in registry["sites"] for feed in site.get("observations", [])]
    require(len(feeds) <= 4, "too many observation feeds for one tick")
    if not feeds:
        return
    args.state.mkdir(parents=True, exist_ok=True)
    with observation_lock(args.state / "observer.lock") as acquired:
        if not acquired:
            return
        now = datetime.now(timezone.utc)
        for repository, feed in feeds:
            github.DEADLINE = monotonic() + 22
            try:
                scan(github.gh_api, args.state, repository, feed, now)
            except INVALID as error:
                print(f"OBSERVATION={repository} retry: {type(error).__name__}", file=sys.stderr)


if __name__ == "__main__":
    main()
