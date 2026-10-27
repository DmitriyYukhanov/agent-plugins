"""Admit workflow-backed SEO incidents through the owner's local GitHub login."""

import argparse
import base64
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
import hashlib
from http.client import HTTPException
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile


LIMIT = 1_048_576
MAX_AGE = timedelta(hours=2)
SKEW = timedelta(minutes=5)
FIELDS = set("version repository run_id head_sha observed_at incident_key rule url expected_canonical observed".split())
MARKER = re.compile(r"<!-- seo-incident:v1 ([A-Za-z0-9_-]{1,10923}) -->\n?")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def json_object(pairs: list) -> dict:
    require(len(pairs) == len(dict(pairs)), "duplicate JSON keys")
    return dict(pairs)


def load_json(raw: bytes | str, limit: int = LIMIT) -> object:
    require(len(raw) <= limit, "JSON exceeds limit")
    return json.loads(raw, object_pairs_hook=json_object)


def compact(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def utc(value: str) -> datetime:
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value), "invalid UTC timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def scope_url(value: str, origin: str) -> None:
    require(isinstance(value, str) and 0 < len(value) <= 2048, "invalid URL")
    decoded = unquote(value)
    require(not re.search(r"[\x00-\x20\x7f\\]", decoded), "ambiguous URL")
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and f"https://{parsed.netloc}" == origin
            and not parsed.query and not parsed.fragment and "?" not in value and "#" not in value
            and not parsed.username and not parsed.password
            and not any(part in (".", "..") for part in unquote(parsed.path).split("/")),
            "URL leaves policy scope")


def validate_policy(policy: dict) -> None:
    require(isinstance(policy, dict) and set(policy) == set(
        "version repository workflow branch producer origin sitemap_url pages http_only_urls".split()), "invalid policy fields")
    require(type(policy["version"]) is int and policy["version"] == 1, "invalid policy version")
    require(isinstance(policy["repository"], str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", policy["repository"]), "invalid repository pin")
    require(isinstance(policy["workflow"], str) and re.fullmatch(
        r"\.github/workflows/[A-Za-z0-9_-]+\.ya?ml", policy["workflow"]), "invalid workflow pin")
    require(isinstance(policy["branch"], str) and re.fullmatch(
        r"[A-Za-z0-9_-]+", policy["branch"]), "invalid branch pin")
    require(policy["producer"] == "github-actions[bot]", "invalid producer pin")
    require(isinstance(policy["origin"], str) and re.fullmatch(
        r"https://[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", policy["origin"]), "invalid origin pin")
    scope_url(policy["sitemap_url"], policy["origin"])
    require(isinstance(policy["pages"], dict) and isinstance(policy["http_only_urls"], list)
            and 0 < len(policy["pages"]) + len(policy["http_only_urls"]) <= 100,
            "invalid monitored URL list")
    for url, canonical in policy["pages"].items():
        scope_url(url, policy["origin"])
        scope_url(canonical, policy["origin"])
    for url in policy["http_only_urls"]:
        scope_url(url, policy["origin"])
        require(url not in policy["pages"], "duplicate monitored URL")
    require(len(set(policy["http_only_urls"])) == len(policy["http_only_urls"]), "duplicate HTTP-only URL")


def gh_api(path: str, *, data: dict | None = None, paginate: bool = False,
           binary: bool = False) -> object:
    args = ["gh", "api", "--hostname", "github.com", path]
    if paginate:
        args += ["--paginate", "--slurp"]
    if data is not None:
        args += ["--method", "POST", "--input", "-"]
    result = subprocess.run(args, input=compact(data).encode() if data is not None else None,
                            capture_output=True, timeout=45, check=False)
    require(result.returncode == 0, "GitHub request failed")
    require(len(result.stdout) <= (LIMIT if binary else 8 * LIMIT), "GitHub response exceeds limit")
    if binary:
        return result.stdout
    value = load_json(result.stdout, 8 * LIMIT)
    if paginate:
        require(isinstance(value, list) and all(isinstance(page, list) for page in value),
                "invalid paginated response")
        return [row for page in value for row in page]
    return value


def parse_evidence(issue: dict, policy: dict) -> dict:
    require(issue.get("state") == "open" and "pull_request" not in issue,
            "issue is closed or is a pull request")
    require(issue.get("user", {}).get("login") == policy["producer"]
            and issue.get("user", {}).get("type") == "Bot",
            "untrusted producer")
    labels = [label["name"] for label in issue["labels"]]
    require("seo-incident" in labels and not any(
        label == "agent" or label.startswith("agent:") for label in labels), "issue already admitted")
    body = issue.get("body")
    require(isinstance(body, str), "missing marker body")
    match = MARKER.fullmatch(body)
    require(match is not None, "body must contain only one marker line")
    token = match[1]
    raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
    require(len(raw) <= 8192 and base64.urlsafe_b64encode(raw).decode().rstrip("=") == token,
            "noncanonical or oversized marker encoding")
    value = load_json(raw.decode("utf-8"))
    require(isinstance(value, dict) and set(value) == FIELDS, "invalid evidence fields")
    require(type(value["version"]) is int and value["version"] == 1, "invalid evidence version")
    require(value["repository"] == policy["repository"], "wrong evidence repository")
    require(type(value["run_id"]) is int and 0 < value["run_id"] <= 2**53 - 1, "invalid run id")
    require(isinstance(value["head_sha"], str) and re.fullmatch(r"[0-9a-f]{40}", value["head_sha"]),
            "invalid head SHA")
    utc(value["observed_at"])
    for key in ("url", "expected_canonical"):
        scope_url(value[key], policy["origin"])
    if value["url"] in policy["http_only_urls"]:
        require(value["rule"] == "http-status" and value["expected_canonical"] == value["url"],
                "HTTP-only URL has a different rule or canonical")
    else:
        require(policy["pages"].get(value["url"]) == value["expected_canonical"], "URL is not locally monitored")
    require(isinstance(value["rule"], str), "invalid rule")
    key = hashlib.sha256(json.dumps([value["repository"], value["rule"], value["url"]],
                                   separators=(",", ":")).encode()).hexdigest()
    require(value["incident_key"] == key, "wrong incident key")
    require(issue.get("title") == f"SEO incident: {value['rule']} {value['url']}", "untrusted title")
    observed = value["observed"]
    require(isinstance(observed, dict), "invalid observation")
    rule = value["rule"]
    if rule == "http-status":
        require(set(observed) == {"status"} and type(observed["status"]) is int
                and 100 <= observed["status"] <= 599 and observed["status"] != 200, "invalid status")
    elif rule == "canonical":
        require(set(observed) == {"canonical"} and (observed["canonical"] is None or (
            isinstance(observed["canonical"], str) and len(observed["canonical"]) <= 2048
            and not re.search(r"[\x00-\x20\x7f]", observed["canonical"]))), "invalid canonical")
        require(observed["canonical"] != value["expected_canonical"], "canonical already matches")
    else:
        expected = {"noindex": {"noindex": True}, "robots": {"allowed": False},
                    "sitemap": {"present": False}}
        require(rule in expected and compact(observed) == compact(expected[rule]), "invalid observation")
    return value


def verify_run(value: dict, policy: dict, now: datetime) -> None:
    prefix = f"repos/{policy['repository']}"
    repo = gh_api(prefix)
    require(repo["full_name"] == policy["repository"] and repo["default_branch"] == policy["branch"],
            "default branch pin changed")
    workflow = gh_api(f"{prefix}/actions/workflows/{policy['workflow'].rsplit('/', 1)[1]}")
    require(workflow["path"] == policy["workflow"] and workflow["state"] == "active", "wrong workflow")
    run = gh_api(f"{prefix}/actions/runs/{value['run_id']}")
    require(run["id"] == value["run_id"] and run["workflow_id"] == workflow["id"]
            and run["path"] == policy["workflow"] and run["head_branch"] == policy["branch"]
            and run["head_sha"] == value["head_sha"]
            and run["repository"]["full_name"] == policy["repository"]
            and run["head_repository"]["full_name"] == policy["repository"]
            and run["event"] in ("schedule", "workflow_dispatch")
            and run["status"] == "completed" and run["conclusion"] == "success", "untrusted run")
    started, ended = utc(run["run_started_at"]), utc(run["updated_at"])
    require(now - MAX_AGE <= ended <= now + SKEW
            and started <= utc(value["observed_at"]) <= ended + SKEW, "stale run or mismatched observation time")
    comparison = gh_api(f"{prefix}/compare/{value['head_sha']}...{policy['branch']}")
    require(comparison["status"] in ("ahead", "identical")
            and comparison["merge_base_commit"]["sha"] == value["head_sha"], "head is outside default branch")
    listing = gh_api(f"{prefix}/actions/runs/{value['run_id']}/artifacts?per_page=100")
    require(listing["total_count"] == len(listing["artifacts"]), "incomplete artifact listing")
    artifacts = [item for item in listing["artifacts"] if item["name"] == "seo-health-evidence"]
    require(len(artifacts) == 1, "missing or ambiguous evidence artifact")
    artifact = artifacts[0]
    require(artifact["expired"] is False and 0 < artifact["size_in_bytes"] <= LIMIT
            and artifact["workflow_run"]["id"] == value["run_id"]
            and artifact["workflow_run"]["head_branch"] == policy["branch"]
            and artifact["workflow_run"]["head_sha"] == value["head_sha"], "untrusted artifact")
    with zipfile.ZipFile(io.BytesIO(gh_api(
            f"{prefix}/actions/artifacts/{artifact['id']}/zip", binary=True))) as bundle:
        members = bundle.infolist()
        require(len(members) == 1 and members[0].filename == "report.json"
                and 0 < members[0].file_size <= LIMIT, "invalid artifact archive")
        report = load_json(bundle.read(members[0]))
    require(isinstance(report, dict) and set(report) == set(
        "version repository run_id head_sha observed_at incidents".split()), "invalid report fields")
    require(all(compact(report[key]) == compact(value[key]) for key in (
        "version", "repository", "run_id", "head_sha", "observed_at")), "report metadata mismatch")
    require(isinstance(report["incidents"], list) and len(report["incidents"]) <= 100
            and sum(compact(item) == compact(value) for item in report["incidents"]) == 1,
            "evidence differs from workflow artifact")


class ScopedRedirect(HTTPRedirectHandler):
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.count = 0

    def redirect_request(self, req: Request, fp: object, code: int, msg: str,
                         headers: object, newurl: str) -> Request:
        scope_url(newurl, self.origin)
        self.count += 1
        require(self.count <= 5, "too many redirects")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url: str, origin: str) -> tuple:
    scope_url(url, origin)
    request = Request(url, headers={"User-Agent": "Googlebot", "Cache-Control": "no-cache"})
    opener = build_opener(ScopedRedirect(origin))
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        scope_url(response.geturl(), origin)
        body = response.read(LIMIT + 1)
        require(len(body) <= LIMIT, "HTTP response exceeds limit")
        return response.code, response.headers, body


class PageSignals(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.noindex = False
        self.canonicals = []
        self.in_head = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        values = dict(attrs)
        if tag == "head":
            self.in_head = True
        elif tag == "body":
            self.in_head = False
        if tag not in ("meta", "link"):
            return
        require(len(attrs) == len(values), "ambiguous HTML attributes")
        if tag == "meta" and (values.get("name") or "").lower() in ("robots", "googlebot"):
            self.noindex |= noindex_directive(values.get("content") or "")
        if tag == "link" and self.in_head and not set(values).intersection(
                ("hreflang", "lang", "media", "type")) and "canonical" in (values.get("rel") or "").lower().split():
            self.canonicals.append(values.get("href"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False


def noindex_directive(text: str, *, header: bool = False) -> bool:
    agent = ""
    for part in text.lower().split(","):
        first, colon, rest = part.strip().partition(":")
        if header and colon and first not in (
                "max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"):
            agent, part = first.strip(), rest
        if agent in ("", "googlebot") and ":" not in part and set(part.split()) & {"noindex", "none"}:
            return True
    return False


def robots_allowed(text: str, url: str) -> bool:
    # shortcut: encoded/non-ASCII robots paths need RFC 9309 normalization before admission.
    require(text.isascii() and "%" not in text and "%" not in url, "unsupported robots encoding")
    groups, agents, rules, have_rule = [], [], [], False
    for line in text.splitlines():
        name, sep, value = line.split("#", 1)[0].partition(":")
        name, value = name.strip().lower(), value.strip()
        if not sep:
            continue
        if name == "user-agent":
            if have_rule:
                groups.append((agents, rules))
                agents, rules, have_rule = [], [], False
            agents.append(value.lower())
        elif name in ("allow", "disallow") and agents:
            have_rule = True
            if value:
                require(value.startswith("/"), "invalid robots path")
                rules.append((value, name == "allow"))
    if agents:
        groups.append((agents, rules))
    selected = [rules for agents, rules in groups if "googlebot" in agents]
    if not selected:
        selected = [rules for agents, rules in groups if "*" in agents]
    matches = [(-1, True)]
    for rules in selected:
        for pattern, allow in rules:
            glob = "".join("[[]" if c == "[" else "[?]" if c == "?" else c
                           for c in pattern.removesuffix("$"))
            if not pattern.endswith("$"):
                glob += "*"
            if fnmatchcase(urlsplit(url).path or "/", glob):
                matches.append((len(pattern.replace("*", "").removesuffix("$")), allow))
    return max(matches)[1]


def confirm_failure(value: dict, policy: dict) -> bool:
    status, headers, body = fetch_url(value["url"], policy["origin"])
    rule = value["rule"]
    if rule == "http-status":
        return status != 200
    require(status == 200, "page unavailable for this rule")
    page = PageSignals()
    if rule in ("noindex", "canonical"):
        page.feed(body.decode("utf-8", errors="replace"))
    if rule == "noindex":
        tags = headers.get_all("X-Robots-Tag", []) if hasattr(headers, "get_all") else [
            val for key, val in headers.items() if key.lower() == "x-robots-tag"]
        for tag in tags:
            page.noindex |= noindex_directive(tag, header=True)
        return page.noindex
    if rule == "canonical":
        return page.canonicals != [value["expected_canonical"]]
    target = policy["origin"] + "/robots.txt" if rule == "robots" else policy["sitemap_url"]
    status, _, body = fetch_url(target, policy["origin"])
    require(status == 200, "robots or sitemap unavailable")
    if rule == "robots":
        return not robots_allowed(body.decode("utf-8"), value["url"])
    root = ET.fromstring(body)
    require(root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset", "expected a sitemap urlset")
    return value["url"] not in [node.text for node in root.findall(
        "{*}url/{*}loc")]


def check_history(prefix: str) -> None:
    events = gh_api(prefix + "/events?per_page=100", paginate=True)
    require(not any(event.get("event") == "labeled" and (
        event.get("label", {}).get("name", "") == "agent"
        or event.get("label", {}).get("name", "").startswith("agent:")) for event in events),
        "issue previously admitted")


def select_evidence(issue: dict, prefix: str, policy: dict, now: datetime) -> dict:
    original = parse_evidence(issue, policy)
    selected, newest = original, 0
    identity = ("version", "repository", "incident_key", "rule", "url", "expected_canonical")
    for comment in gh_api(prefix + "/comments?per_page=100", paginate=True):
        if (comment.get("user", {}).get("login") != policy["producer"]
                or comment.get("user", {}).get("type") != "Bot"
                or type(comment.get("id")) is not int or comment["id"] <= newest):
            continue
        try:
            candidate = parse_evidence({**issue, "body": comment.get("body")}, policy)
        except ValueError:
            continue
        if all(candidate[key] == original[key] for key in identity):
            selected, newest = candidate, comment["id"]
    require(now - MAX_AGE <= utc(selected["observed_at"]) <= now + SKEW, "stale or future evidence")
    return selected


def admit_issue(number: int, policy: dict, now: datetime, *, admit: bool = False) -> str:
    validate_policy(policy)
    prefix = f"repos/{policy['repository']}/issues/{number}"
    issue = gh_api(prefix)
    value = select_evidence(issue, prefix, policy, now)
    check_history(prefix)
    verify_run(value, policy, now)
    require(confirm_failure(value, policy), "live URL recovered")
    latest = gh_api(prefix)
    require(compact(select_evidence(latest, prefix, policy, now)) == compact(value)
            and latest["body"] == issue["body"], "issue changed during validation")
    check_history(prefix)
    if not admit:
        return "eligible"
    require(gh_api("user").get("type") == "User", "local gh login must be a user")
    gh_api(prefix + "/labels", data={"labels": ["agent"]})
    return "admitted"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--admit", action="store_true")
    args = parser.parse_args()
    try:
        policy = load_json(args.policy.read_bytes())
        validate_policy(policy)
        if args.repository != policy["repository"]:
            return 0
        issues = gh_api(f"repos/{policy['repository']}/issues?state=open&labels=seo-incident&sort=created&direction=asc&per_page=100",
                        paginate=True)
        require(isinstance(issues, list), "invalid issue listing")
        for issue in issues:
            number = issue["number"]
            require(type(number) is int and number > 0, "invalid issue number")
            try:
                outcome = admit_issue(number, policy, datetime.now(timezone.utc), admit=args.admit)
                print(f"SEO_INTAKE={outcome} ISSUE={number}")
            except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError,
                    HTTPException, zipfile.BadZipFile, ET.ParseError):
                print(f"SEO_INTAKE=skipped ISSUE={number}")
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print("SEO_INTAKE=error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
