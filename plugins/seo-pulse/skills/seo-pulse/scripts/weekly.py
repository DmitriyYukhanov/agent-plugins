"""Read finalized Search Console data and maintain explicitly scoped GitHub issues."""

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


START = "<!-- seo-pulse:start -->"
END = "<!-- seo-pulse:end -->"
SIGNAL = re.compile(r"<!-- seo-pulse:signal:([A-Za-z0-9_=-]+) -->")


def page_url(value: str) -> tuple:
    """Parse a canonical HTTP URL without ambiguous path traversal."""
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment
            or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
            or "\\" in unquote(value) or re.search(r"[\x00-\x20]", value)):
        raise ValueError("Invalid page URL")
    return parsed.scheme, parsed.hostname, parsed.port, parsed.path or "/", parsed.query


def in_scope(site: dict, page: str) -> bool:
    """Match origins and path boundaries, never a hostname string prefix."""
    try:
        target = page_url(page)
        for prefix in site["page_prefixes"]:
            allowed = page_url(prefix)
            path = allowed[3]
            if target[:3] == allowed[:3] and (
                target[3] == path or target[3].startswith(path.rstrip("/") + "/")
            ):
                return True
    except ValueError:
        return False
    return False


def validate_config(config: dict) -> dict:
    """Reject unsafe destinations and ambiguous site scopes before API access."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", config["repository"]):
        raise ValueError("Invalid repository")
    if type(config["report_issue"]) is not int or config["report_issue"] < 1:
        raise ValueError("report_issue must name a precreated pinned issue")
    if type(config.get("allow_public_reports", False)) is not bool:
        raise ValueError("allow_public_reports must be a boolean")
    if not config["sites"]:
        raise ValueError("Configure at least one site")
    seen = set()
    for site in config["sites"]:
        prop = site["property"]
        if prop in seen or not site["page_prefixes"]:
            raise ValueError("Duplicate property or empty page scope")
        seen.add(prop)
        if prop.startswith("sc-domain:"):
            domain = prop.removeprefix("sc-domain:")
            if not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", domain):
                raise ValueError("Invalid domain property")
        else:
            page_url(prop)
        prefixes = site["page_prefixes"]
        for prefix in prefixes:
            parsed = page_url(prefix)
            if parsed[4]:
                raise ValueError("Page prefixes cannot contain queries")
            if prop.startswith("sc-domain:"):
                if parsed[1] != domain and not parsed[1].endswith("." + domain):
                    raise ValueError("Page scope escapes its GSC property")
            elif not in_scope({"page_prefixes": [prop]}, prefix):
                raise ValueError("Page scope escapes its URL-prefix property")
        for index, prefix in enumerate(prefixes):
            if any(in_scope({"page_prefixes": [other]}, prefix)
                   for i, other in enumerate(prefixes) if i != index):
                raise ValueError("Overlapping page prefixes would double-count totals")
        log = Path(site["log"])
        if log.is_absolute() or ".." in log.parts or not site["log"]:
            raise ValueError("Log must be a repository-relative path")
        for measurement in site.get("measurements", []):
            if not in_scope(site, measurement["page"]):
                raise ValueError("Measurement escapes page scope")
            changed = date.fromisoformat(measurement["changed_on"])
            first = date.fromisoformat(measurement["baseline_start"])
            last = date.fromisoformat(measurement["baseline_end"])
            if first > last or last >= changed:
                raise ValueError("Measurement baseline must precede its change")
    return config


def windows(today: date) -> tuple[str, str, str, str]:
    """Compare equal 28-day windows with three days of reporting lag."""
    end = today - timedelta(days=3)
    start = end - timedelta(days=27)
    return tuple(day.isoformat() for day in
                 (start, end, start - timedelta(days=28), start - timedelta(days=1)))


def classify(row: dict) -> str | None:
    """Select evidence-backed title/CTR or striking-distance opportunities."""
    if row["impressions"] < 100:
        return None
    if row["position"] <= 5 and row["ctr"] < .02:
        return "low-ctr"
    if 5 < row["position"] <= 20:
        return "striking-distance"
    return None


def on_hold(site: dict, page: str, today: date) -> bool:
    """Hold a changed page through its four-week measurement date."""
    return any(m["page"] == page and today <= date.fromisoformat(m["changed_on"])
               + timedelta(days=28) for m in site.get("measurements", []))


def signal_key(prop: str, query: str, page: str) -> str:
    return hashlib.sha256(json.dumps([prop, query, page], ensure_ascii=True).encode()).hexdigest()


def safe_text(value: str) -> str:
    value = html.escape(" ".join(value.split()), quote=True).replace("@", "&#64;")
    return re.sub(r"([\\`*_|\[\]~])", r"\\\1", value)


def block(content: str) -> str:
    return f"{START}\n{content}\n{END}"


def replace_block(body: str, content: str) -> str:
    if body.count(START) != 1 or body.count(END) != 1 or body.index(START) >= body.index(END):
        raise ValueError("Expected exactly one ordered SEO pulse block")
    first, rest = body.split(START)
    _, last = rest.split(END)
    return first + block(content) + last


def metrics(rows: list[dict]) -> str:
    if not rows:
        return "unknown | unknown | unknown | unknown"
    impressions = sum(row["impressions"] for row in rows)
    clicks = sum(row["clicks"] for row in rows)
    position = (sum(row["position"] * row["impressions"] for row in rows)
                / impressions if impressions else 0)
    return f"{clicks:g} | {impressions:g} | {clicks / impressions:.2%} | {position:.2f}" if impressions else "0 | 0 | unknown | unknown"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Authenticated API redirect refused")


class API:
    """Restrict authenticated requests to the Google and GitHub API origins."""

    def __init__(self, gsc_token: str, gh_token: str):
        self.gsc_token = gsc_token
        self.gh_token = gh_token

    def request(self, url: str, token: str, method: str, data: dict | None = None):
        if urlsplit(url).netloc not in ("www.googleapis.com", "api.github.com"):
            raise ValueError("API origin refused")
        request = Request(url, method=method, data=None if data is None else json.dumps(data).encode(),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                   "Accept": "application/json", "User-Agent": "seo-pulse"})
        try:
            with build_opener(NoRedirect()).open(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"API request failed with HTTP {error.code}; no automatic retry") from None

    def github(self, method: str, path: str, data: dict | None = None):
        return self.request("https://api.github.com" + path, self.gh_token, method, data)

    def viewer(self) -> str:
        result = self.github("POST", "/graphql", {"query": "query { viewer { login } }"})
        return result["data"]["viewer"]["login"]

    def gsc(self, site: dict, start: str, end: str,
            dimensions: tuple = (), exact: tuple | None = None) -> list[dict]:
        rows = []
        for prefix in site["page_prefixes"]:
            scheme, host, port, path, _ = page_url(prefix)
            host = f"[{host}]" if ":" in host else host
            origin = f"{scheme}://{host}" + (f":{port}" if port else "")
            expression = "^" + re.escape(origin)
            if path == "/":
                expression += r"(?:/|\?|$)"
            else:
                expression += re.escape(path) + ("" if path.endswith("/") else r"(?:/|\?|$)")
            filters = [{"dimension": "page", "operator": "includingRegex",
                        "expression": expression}]
            if exact:
                filters += [{"dimension": dimension, "operator": "equals", "expression": value}
                            for dimension, value in zip(("query", "page"), exact) if value is not None]
            offset = 0
            while True:
                payload = {"startDate": start, "endDate": end, "dataState": "final",
                           "type": "web", "dimensions": list(dimensions), "rowLimit": 25000,
                           "startRow": offset, "dimensionFilterGroups": [{"filters": filters}]}
                result = self.request("https://www.googleapis.com/webmasters/v3/sites/"
                                      + quote(site["property"], safe="") + "/searchAnalytics/query",
                                      self.gsc_token, "POST", payload)
                batch = result.get("rows", [])
                for row in batch:
                    for name in ("clicks", "impressions", "ctr", "position"):
                        if type(row.get(name)) not in (int, float) or not math.isfinite(row[name]) or row[name] < 0:
                            raise ValueError("Malformed GSC metrics")
                    if (row["clicks"] > row["impressions"] or row["ctr"] > 1
                            or (row["impressions"] and row["position"] < 1)
                            or not math.isclose(row["ctr"], row["clicks"] / row["impressions"]
                                                if row["impressions"] else 0, abs_tol=1e-6, rel_tol=1e-4)):
                        raise ValueError("Inconsistent GSC metrics")
                    if dimensions and (len(row.get("keys", [])) != len(dimensions)
                                       or not in_scope(site, row["keys"][-1])):
                        raise ValueError("GSC row escapes configured scope")
                    if dimensions and exact and row["keys"][-1] != exact[1]:
                        raise ValueError("GSC row does not match the exact page")
                    if "date" in dimensions:
                        observed = date.fromisoformat(row["keys"][dimensions.index("date")])
                        if not date.fromisoformat(start) <= observed <= date.fromisoformat(end):
                            raise ValueError("GSC date escapes the requested window")
                rows.extend(batch)
                if len(batch) < 25000:
                    break
                offset += len(batch)
                if offset >= 100000:
                    raise ValueError("GSC pagination limit reached; narrow the configured scope")
        return rows


def plan_run(config: dict, today: date, api: API) -> list[dict]:
    """Finish all reads and validations before producing an issue-only write plan."""
    validate_config(config)
    root = "/repos/" + config["repository"]
    repo = api.github("GET", root)
    if not repo["private"] and not config.get("allow_public_reports", False):
        raise ValueError("Public reports need allow_public_reports: true")
    report_path = root + "/issues/" + str(config["report_issue"])
    report = api.github("GET", report_path)
    if "pull_request" in report or report["state"] != "open":
        raise ValueError("Report target must be an open issue, not a PR")
    replace_block(report.get("body") or "", "validate")
    api.github("GET", root + "/labels/seo-signal")
    existing = {}
    page = 1
    while True:
        batch = api.github("GET", root + f"/issues?state=all&labels=seo-signal&page={page}&per_page=100")
        for issue in batch:
            if "pull_request" in issue:
                continue
            markers = SIGNAL.findall(issue.get("body") or "")
            if not markers:
                continue
            if len(markers) != 1 or issue["user"]["login"] != config.get("publisher_login", "github-actions[bot]"):
                raise ValueError("Ambiguous signal marker or unexpected issue author")
            identity = json.loads(base64.urlsafe_b64decode(markers[0]).decode())
            if not isinstance(identity, list) or len(identity) != 3 or not all(isinstance(v, str) for v in identity):
                raise ValueError("Invalid signal identity")
            key = signal_key(*identity)
            if key in existing:
                raise ValueError("Duplicate signal identities need manual repair")
            existing[key] = (identity, issue)
        if len(batch) < 100:
            break
        page += 1
    start, end, before_start, before_end = windows(today)
    lines = [f"## SEO pulse: {today.isoformat()}", "",
             "Finalized web search, 28-day windows. Query rows are partial; absent rows are unknown.", ""]
    operations = []
    for site in config["sites"]:
        lines += [f"### {safe_text(site['property'])}", "",
                  "Scope: " + ", ".join(safe_text(p) for p in site["page_prefixes"]), "",
                  "| Window | Clicks | Impressions | CTR | Position |",
                  "|---|---|---|---|---|"]
        for first, last, label in ((start, end, "Current"), (before_start, before_end, "Baseline")):
            lines.append(f"| {label} {first} to {last} | {metrics(api.gsc(site, first, last))} |")
        lines += ["", "Decision: review at most one signal per site; wait on measured pages."]
        rows = api.gsc(site, start, end, ("query", "page"))
        candidates = {signal_key(site["property"], *row["keys"]): row for row in rows}
        for key, (identity, issue) in existing.items():
            if identity[0] != site["property"] or issue["state"] != "open":
                continue
            if not in_scope(site, identity[2]):
                raise ValueError("Existing signal escaped the current scope; review it manually")
            candidates.pop(key, None)
            exact = api.gsc(site, start, end, ("query", "page"), tuple(identity[1:]))
            # Only positive, sufficiently large exact evidence can resolve an old signal.
            matched = [r for r in exact if r["keys"] == identity[1:]]
            if len(matched) == 1:
                candidates[key] = matched[0]
        for key, row in sorted(candidates.items()):
            query, url = row["keys"]
            kind = classify(row)
            old = existing.get(key, (None, None))[1]
            if old and old["state"] == "closed":
                continue
            if on_hold(site, url, today):
                note = f"- Wait: {safe_text(url)} is being measured."
                if note not in lines:
                    lines.append(note)
                continue
            if kind and not old:
                dates = api.gsc(site, start, end, ("date", "page"), (query, url))
                observed = [date.fromisoformat(r["keys"][0]) for r in dates]
                if not observed or (date.fromisoformat(end) - min(observed)).days < 13:
                    lines.append(f"- Wait: {safe_text(query)} has less than two weeks of dated evidence.")
                    continue
            recovered = (row["impressions"] >= 100 and row["position"] <= 5 and row["ctr"] >= .02)
            status = kind or ("resolved" if recovered else "needs review")
            content = (f"Signal: {status}. Query: {safe_text(query)}. Page: {safe_text(url)}.\n\n"
                       f"Window: {start} to {end}.\n\n"
                       "| Clicks | Impressions | CTR | Position |\n|---|---|---|---|\n"
                       f"| {metrics([row])} |\n\n"
                       "Review the evidence and choose one change through the normal PR flow. "
                       "Record its baseline and checks at +2 and +4 weeks in the configured SEO log.")
            if old:
                state = "closed" if recovered else "open"
                data = {"body": replace_block(old["body"], content), "state": state}
                if any(old.get(k) != v for k, v in data.items()):
                    operations.append({"method": "PATCH", "path": root + "/issues/" + str(old["number"]),
                                       "data": data, "before": old})
            elif kind:
                identity = base64.urlsafe_b64encode(json.dumps([site["property"], query, url]).encode()).decode()
                operations.append({"method": "POST", "path": root + "/issues",
                                   "data": {"title": f"SEO: {kind}: {safe_text(url)[:160]}",
                                            "labels": ["seo-signal"], "body":
                                            f"<!-- seo-pulse:signal:{identity} -->\n" + block(content)}})
            if kind:
                lines.append(f"- {kind}: {safe_text(query)}; {safe_text(url)} ({row['impressions']:g} impressions).")
        for measurement in site.get("measurements", []):
            changed = date.fromisoformat(measurement["changed_on"])
            lines += ["", f"Measurement: {safe_text(measurement['page'])}"]
            for days in (14, 28):
                check = changed + timedelta(days=days)
                lines.append(f"- +{days // 7} weeks: {check.isoformat()} ({'due' if today >= check else 'pending'}).")
            baseline = api.gsc(site, measurement["baseline_start"], measurement["baseline_end"],
                               exact=(None, measurement["page"]))
            lines.append("Fixed pre-change baseline: " + measurement["baseline_start"] + " to "
                         + measurement["baseline_end"] + ". Metrics: " + metrics(baseline) + ".")
    body = replace_block(report["body"], "\n".join(lines))
    if body != report["body"]:
        operations.append({"method": "PATCH", "path": report_path, "data": {"body": body}, "before": report})
    if any(len(op["data"].get("body", "")) > 60000 for op in operations):
        raise ValueError("Report or signal body exceeds the safe size; narrow the configured scope")
    return operations


def publish(operations: list[dict], api: API, publisher_login: str = "github-actions[bot]") -> None:
    """Check for intervening human edits and apply each planned mutation once."""
    if operations and api.viewer() != publisher_login:
        raise ValueError("Authenticated GitHub actor differs from publisher_login")
    for operation in operations:
        if "before" in operation:
            current = api.github("GET", operation["path"])
            if any(current.get(key) != operation["before"].get(key) for key in ("body", "state", "updated_at")):
                raise ValueError("Issue changed since planning; rerun before publishing")
    for operation in operations:
        result = api.github(operation["method"], operation["path"], operation["data"])
        print(f"Applied {operation['method']} {operation['path']} #{result.get('number', '')}", file=sys.stderr)


def gsc_token() -> str:
    """Use an explicit token or a service account; never fall back to cached OAuth."""
    if os.environ.get("GSC_ACCESS_TOKEN"):
        return os.environ["GSC_ACCESS_TOKEN"]
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import service_account

    info = json.loads(Path(os.environ["GSC_CREDENTIALS_PATH"]).read_text(encoding="utf-8"))
    if info.get("type") != "service_account" or info.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise ValueError("Expected a Google service-account key with the standard token endpoint")
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    credentials.refresh(GoogleRequest())
    return credentials.token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=".claude/seo-pulse.json")
    parser.add_argument("--date", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date())
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    try:
        config = validate_config(json.loads(Path(args.config).read_text(encoding="utf-8")))
        api = API(gsc_token(), os.environ["GH_TOKEN"])
        operations = plan_run(config, args.date, api)
        print(json.dumps([{k: v for k, v in op.items() if k != "before"} for op in operations], indent=2))
        if args.publish:
            publish(operations, api, config.get("publisher_login", "github-actions[bot]"))
        return 0
    except Exception as error:
        # Provider exceptions can contain credentials; expose only the safe error class.
        print(f"SEO pulse stopped ({type(error).__name__}); check config, API access and prior write receipts. "
              "Do not retry an uncertain create without checking existing signal markers.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
