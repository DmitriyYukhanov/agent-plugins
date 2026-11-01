# Technical checks

Run the bundled `scripts/technical.py` with a reviewed project config:

```sh
python /path/to/installed/seo-pulse/skills/seo-pulse/scripts/technical.py --config .claude/seo-pulse.json
```

Resolve the script relative to the installed skill directory. Use `--format markdown` for a compact readable report. Both formats go to stdout; redirect them to the project's local work directory when retaining evidence. JSON includes raw monitored URLs, redirect traces, minimal content-type/robots headers, findings and grouped failures. Raw HTML and cookies are not needed in the report.

The checker reads only the additive `technical` section, so a technical-only project needs no GSC property, report issue or credentials. The existing weekly command still requires its own complete config. See the [example](../assets/technical.example.json).

## Expectations

- `origins`: one to eight exact public HTTP/HTTPS origins. No credentials or non-default ports. Pin only reviewed owned hosts.
- `pages`: one to 100 distinct raw URLs. `final_url` defaults to the raw URL; `status` defaults to 200. An alias that stays at its original URL fails an expected final destination.
- `role: public`: require exactly one canonical matching the configured absolute `canonical` and no applicable noindex directive.
- `role: nonindexable`: require page or Googlebot-applicable response-header noindex/none. Canonical and metadata checks run only if explicitly configured.
- `role: excluded`: check the expected HTTP status and final URL only, plus an explicitly configured sitemap assertion. A reserved route can expect 404.
- `required_meta`: optional names from description, og:title/description/image and twitter:card/title/description/image. Missing configured values are warnings. Unconfigured metadata creates no finding.
- `organization: true`: optional Organization JSON-LD expectation. The checker never infers Article schema from a page label.
- `in_sitemap`: optional true/false assertion against the canonical or expected final URL. It requires `sitemap_url`, a namespaced XML urlset; sitemap indexes are reported unsupported/unknown.
- `group`: optional lowercase page-family identifier for grouping variants. Every raw URL remains in the report.

Noindex checks describe directives, not actual Google indexing. Ordinary GET access does not prove access by a real search bot. Deliberately excluded/noindex pages never inherit public metadata or sitemap requirements. Enumerate showcase paths only when they are part of the reviewed policy; a finite page list does not crawl unlisted content.

## Limits and outcomes

Each response is capped at 1 MiB and five redirects. The scan allows at most 100 requests and 60 seconds overall, with a ten-second elapsed collection limit per fetch. An elapsed timeout stops further collection; remaining pages become unknown. Each redirect is validated before the next request. Public DNS addresses are checked before access. The reviewed hostname allowlist remains a trust boundary; this is not an adversarial DNS sandbox.

Exit 0 means every configured check passed, 1 means a confirmed failure (including configured metadata warnings), and 2 means incomplete collection or invalid config. A mixed failed/incomplete report retains both counts and `complete: false`. TLS, timeout, oversized or unreadable responses cannot establish missing metadata or recovery. No historical runs or measurement baselines are written.

The command makes no GitHub mutations, indexing requests or repairs. It is independent of agent-dispatch incident admission and does not emit that intake's evidence format.

## Optional workflow

Copy the [manual template](../assets/technical.yml) through the site's reviewed change process after confirming the policy. Supply a reviewed plugin commit/tag accessible to that workflow. It has read-only repository permission, no provider secrets and no schedule. A report artifact and successful manual run do not prove installation in another host or actual unattended execution. Adding a schedule, provisioning GSC or enabling issue admission/repair requires its own authorized step.


For automatic future checks, the [scheduled template](../assets/technical-scheduled.yml) invokes the same command daily at 09:00 UTC (12:00 Europe/Moscow), with manual dispatch as well. This is a proposed cadence, not an enabled schedule. It requires a reviewed full commit SHA through the SEO_PULSE_COMMIT repository variable or manual input and fails before checkout if that pin is absent. It retains contents: read and report artifacts only.

After merge and owner approval, replace the site's manual workflow with the reviewed scheduled template through the site PR flow; do not install both templates under the same workflow name. Confirm the configured pin, actual next run in the owner's timezone and the first completed event=schedule run. Inspect its run ID, commit, exact config, report artifact, non-empty observations and coverage/failure counts. A failed or incomplete run is not a healthy canary. No real unattended run has been verified by shipping this template.
