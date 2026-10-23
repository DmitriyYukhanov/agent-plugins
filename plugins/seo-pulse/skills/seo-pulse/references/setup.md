# Set up SEO pulse

## Project config

Copy [the example](../assets/seo-pulse.example.json) to `.claude/seo-pulse.json` in
the site repository. Set `repository` to the GitHub repository that will receive
reports, and keep only properties and page prefixes you own. The same script
accepts codestage.net, yarrtifacts.com or another site through this config.
Overlapping prefixes are rejected so scoped totals cannot count pages twice.
Logs are relative to this repository; a property in a separate repository needs
that repository's own config and normal implementation flow.

Create an issue titled "SEO pulse" with these markers in its body, record its
number in `report_issue`, and pin it using the issue's sidebar:

```markdown
<!-- seo-pulse:start -->
The first weekly run will put the report here.
<!-- seo-pulse:end -->
```

Create the `seo-signal` label. Do not use execution/dispatcher labels. The routine
updates only its blocks; owner notes belong outside them. Existing signal issues
must have the configured `publisher_login` (default `github-actions[bot]`). Closed
signal identities stay closed, including after a human picks up the work.

Reports include search queries. For a public destination, review that disclosure
and set `allow_public_reports` to `true` only when publication is intended.

After an implemented change, record it in the SEO log and add a measurement:

```json
{
  "page": "https://example.com/product/",
  "changed_on": "2026-10-01",
  "baseline_start": "2026-09-03",
  "baseline_end": "2026-09-30"
}
```

The runner holds that exact page through October 29 and reports checks on October
15 and 29. Remove a completed measurement through the normal reviewed config flow.
The fixed baseline survives each weekly run. Weekly totals separately compare the
last finalized 28 days with the preceding 28 days, using a three-day lag. Empty
responses are unknown. GSC's query rows can omit anonymized or low-volume queries.
Only a sufficiently large successful exact query/page recheck can close a signal.
The 100-impression, 2% CTR and position 5/20 cutoffs are screening heuristics;
reviewers still decide whether an issue deserves a change.

## Local OAuth and MCP

Install Python 3.11+ and `uv`/`uvx`. Enable the
[Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)
in a Google Cloud project. Configure its OAuth consent screen, add your account
as a test user when required, and create an OAuth client of type **Desktop app**.
Download the client JSON outside the repository. Export
`GSC_OAUTH_CLIENT_SECRETS_FILE` as its absolute path before starting the agent.

The bundled `.mcp.json` targets the Claude Code plugin adapter. Other hosts must
register the same stdio command using their own MCP configuration:

```text
command: uvx
args: --python 3.11 mcp-search-console==0.4.1
env: GSC_ALLOW_DESTRUCTIVE=false, GSC_DATA_STATE=final
```

Approve the server in your host, then request `get_capabilities` and
`list_properties`. Complete the first Google consent in the browser. Check that
the configured property is visible; no data is different from failed access.
Do not paste passwords, consent codes or keys into chat.

Upstream 0.4.1 requests Google's broad `webmasters` OAuth scope. Its destructive
flag blocks some mutations but is not a universal read-only sandbox: sitemap
submission remains a write capability. This skill prohibits all mutation calls.
Use a restricted Search Console account for local access if you need a provider
permission boundary. CI uses the narrower `webmasters.readonly` scope directly.
See [upstream authentication](https://github.com/AminForou/mcp-gsc#readme),
[Google scopes](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing)
and [Search Console roles](https://support.google.com/webmasters/answer/7687615).

## CI service account

1. In the Google Cloud project with the API enabled, create a service account.
   Add its email in each GSC property's **Settings > Users and permissions** as a
   **Restricted** user. Cloud IAM project roles alone do not grant property access.
2. Create a JSON key, store it in the target repository's Actions secret
   `GSC_SERVICE_ACCOUNT_KEY`, and retain it only in your approved credential store.
   Rotate it according to your account policy. Never commit it.
3. Copy [`weekly.py`](../scripts/weekly.py) to `.github/seo-pulse/weekly.py` and the
   [workflow](../assets/weekly.yml) to `.github/workflows/seo-pulse.yml` in that repo.
   Review both copies through its normal PR flow. Keep the report issue/config
   there too. Installation alone does not enable a schedule.
4. Start with a manual dry run: run the copied script without `--publish`, with
   `GSC_CREDENTIALS_PATH` pointing to the service-account JSON and `GH_TOKEN` able
   to read the configured repository. The runner never uses local OAuth caches.
   Install its auth dependency first with
   `python -m pip install 'google-auth[requests]==2.62.0'`. The MCP adapter's isolated
   environment does not install packages into this Python. A supplied short-lived
   `GSC_ACCESS_TOKEN` can replace the key and avoids that dependency entirely.
5. Check scope, windows, report destination and proposed issue writes. Then enable
   the workflow on the default branch and run it manually. Read back the issue
   updates. A green job or an uploaded template alone does not prove delivery.

The workflow runs Monday at 07:23 UTC and also supports manual dispatch. It needs
`contents: read` and `issues: write` in the configured repository; the default token
does not grant access to a different destination repository. Use one publisher
per destination. Its concurrency group serializes scheduled/manual Actions runs;
do not start a local publisher alongside them.

The job uses a service-account key without a local OAuth token or paid agent
session. It calls only GSC analytics reads and GitHub issue operations. It has
neither a commit/push step nor PR write permissions. It reads every required
response before mutations and stops on failure. After a timeout during a write,
inspect its stderr receipts and GitHub markers before rerunning. Writes already
completed remain; the plan is not a transaction. Intervening issue edits stop
publication, but external concurrent writers still need coordination.
Before writing, the runner checks the authenticated GitHub actor against
`publisher_login`; a local personal token needs its own login there. A dry run
can preview the plan without changing that setting.

## Validate installation

Run `python -m unittest discover -s plugins/seo-pulse/tests` from this source
repository for deterministic contract/runtime checks with fake API transport.
Then verify host skill activation and MCP tools in your actual agent. For each
real property, verify auth, a dry run, an authorized publication and a same-date
rerun. Keep those receipts separate from local tests. Current packaging does not
claim that every host installs `.mcp.json` automatically.
