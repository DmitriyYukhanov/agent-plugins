# Trusted SEO incident intake

The optional intake admits bot-authored SEO incidents into the existing owner queue. It uses the
owner's local `gh` login to add `agent`; Actions needs no personal GitHub token. Other issues still
require an owner-applied label. A missing Python runtime or failed intake leaves that queue usable.

## Local policy

Create `~/.agent-dispatch/seo-incidents.json` after reviewing its repository, workflow, origin,
and monitored URLs. Keep this file outside repositories that a worker can edit. The policy has
exactly these fields:

```json
{
  "version": 1,
  "repository": "octo/website",
  "workflow": ".github/workflows/seo-health.yml",
  "branch": "main",
  "producer": "github-actions[bot]",
  "origin": "https://example.com",
  "sitemap_url": "https://example.com/sitemap.xml",
  "pages": {"https://example.com/": "https://example.com/"},
  "http_only_urls": ["https://example.com/.well-known/seo-health.txt"]
}
```

`pages` maps each raw monitored URL to its expected canonical. `http_only_urls` permits only the
HTTP-status rule, with that URL as its expected canonical. Either collection may be empty; their
combined size must be 1 to 100. Every URL must use the pinned HTTPS origin, without credentials,
query, fragment, ambiguous dot segments, or encoded controls. The intake preserves URL strings.

Before activation, test without writes from the installed plugin directory:

```sh
python3 scripts/seo_intake.py --policy "$HOME/.agent-dispatch/seo-incidents.json" --repository octo/website
```

On Windows use `python` in place of `python3`. Python 3.11 or newer and the owner's authenticated
`gh` are required. To admit eligible issues immediately, append `--admit`. This command adds
labels but never launches workers. Each candidate prints `SEO_INTAKE=eligible`, `admitted`, or
`skipped`; a policy or listing failure returns nonzero and prints `SEO_INTAKE=error`.
Each scan has a 60-second budget. The first scan starts with the most recently updated issues;
admission scans save the next candidate number in `seo-incidents.json.cursor` beside the policy.
Later scans resume there so a slow candidate cannot monopolize every tick. Already admitted or
malformed issues in the listing need no further requests. Runs without `--admit` never write
labels or cursor state. GitHub subprocesses and public HTTP requests share the remaining budget;
each public request also has a 15-second elapsed limit, including headers and redirects.
Expiry prevents further label requests.
An exhausted scan prints `SEO_INTAKE=deferred` when candidates remain.

For scheduled admission, add the verified primary checkout to `repos.conf` through setup with the
chosen worker host and merge threshold. Each tick runs intake only for repositories in that file,
before picking from the owner queue. The scheduler's `tick.sh claude|codex` argument selects the
installed dispatch plugin; it does not override the worker host in each repository's row.
Removing the policy disables new admissions. It leaves already admitted work in the owner queue.

## Producer contract

An open issue must have the `seo-incident` label and author `github-actions[bot]` of type `Bot`.
Its title is exactly `SEO incident: <rule> <url>`. Its body is only this marker line, with an
optional final newline:

```text
<!-- seo-incident:v1 BASE64URL_JSON -->
```

The token is unpadded base64url of a UTF-8 JSON object, at most 8192 decoded bytes. Duplicate keys,
unknown fields, extra body text, and multiple markers are rejected. The object has exactly:

| Field | Value |
| --- | --- |
| `version` | Integer `1` |
| `repository` | Exact local repository pin |
| `run_id` | Positive integer, at most 2^53 - 1 |
| `head_sha` | 40 lowercase hexadecimal characters |
| `observed_at` | RFC3339 UTC timestamp ending in `Z`, optionally with microseconds |
| `incident_key` | Lowercase SHA-256 of compact JSON `[repository,rule,url]` |
| `rule` | One rule from the table below |
| `url` | Raw monitored URL from local policy |
| `expected_canonical` | Raw canonical pinned for that URL |
| `observed` | The rule's exact typed object below |

Compact JSON uses separators `,` and `:`, with the default JSON ASCII escaping. No URL
normalization precedes hashing. Observations may be at most two hours old or five minutes ahead
of the local UTC clock. The five-minute allowance also covers the observation-to-run-end bound.

| Rule | `observed` | Live failure required |
| --- | --- | --- |
| `http-status` | `{"status":503}`: integer 100 to 599 except 200 | Final HTTP status differs from 200 |
| `noindex` | `{"noindex":true}` | Robots meta or applicable X-Robots-Tag says noindex/none |
| `canonical` | `{"canonical":null}` or a raw string of at most 2048 characters | Canonical link in the explicit or implicit head is missing, duplicated, or differs from the pinned string |
| `robots` | `{"allowed":false}` | The origin's robots.txt blocks Googlebot for the page |
| `sitemap` | `{"present":false}` | The page URL is absent from the pinned XML sitemap |

Rules other than `http-status` require a live page status of 200. The intake follows at most
five redirects, checking each destination against the same origin and URL restrictions before
requesting it. It sends no GitHub credentials to the website and limits each response to 1 MiB.
Network failures do not count as an observed HTTP status.

The successful run must belong to the pinned repository and workflow, use `schedule` or
`workflow_dispatch`, and have the pinned default branch and evidence SHA. The workflow must still
be active, the repository's default branch must still match the pin, and that SHA must be an
ancestor of the current default branch. The observation must fall within the run, and the run
must have completed within two hours. An in-progress or failed run grants no admission.

The run uploads one artifact named `seo-health-evidence`, containing only `report.json`:

```json
{
  "version": 1,
  "repository": "octo/website",
  "run_id": 123,
  "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "observed_at": "2026-10-27T12:00:00Z",
  "incidents": []
}
```

`incidents` contains up to 100 exact marker payload objects. An issue's payload must appear
exactly once, with matching report metadata. The compressed archive and unpacked report must
each fit within 1 MiB. Artifact paths never reach the filesystem. Expired, missing, ambiguous,
or incomplete artifact listings grant no admission. See GitHub's [run](https://docs.github.com/en/rest/actions/workflow-runs)
and [artifact](https://docs.github.com/en/rest/actions/artifacts) API documentation.

The detector keeps the initial title and body immutable. It can renew evidence in marker-only
comments authored by the same producer. The intake selects the newest valid comment with the
same version, repository, incident key, rule, URL and expected canonical as the body, then
checks that comment's own run and artifact. The original body's observation may be old; the
selected evidence must meet the freshness limit. A newer selected payload that fails
provenance grants no admission, even if an older payload passed. Explanatory comments are data
and do not participate in selection. After any
`agent` or `agent:*` label has ever been applied, the intake skips the issue, even if the label
was later removed. Put later observations in comments and keep the body immutable. Ordinary
owner approval checks still reject outside title/body edits after admission.

## Verification and limits

The test suite uses fake GitHub and public HTTP responses; it does not dispatch live work.
CI runs the shell and Python contracts on Windows, macOS, and Linux. Live workflow admission
and worker behavior need a separate pilot acceptance run with the installed version.

Sitemaps must be namespaced XML `urlset` documents; sitemap indexes need a separate check.
Robots matching supports ASCII paths, wildcard rules, Googlebot groups and longest-match
precedence. Encoded or non-ASCII robots paths wait for manual review. An edit between the final
read and label application remains subject to the existing queue's edit-history check.
