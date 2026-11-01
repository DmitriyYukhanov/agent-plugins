# Technical checks

Run the bundled `scripts/technical.py` with a reviewed project config:

```sh
python /path/to/installed/seo-pulse/skills/seo-pulse/scripts/technical.py --config .claude/seo-pulse.json
```

Resolve the script relative to the installed skill directory. Use `--format markdown` for a compact readable report. Both formats go to stdout; redirect them to the project's local work directory when retaining evidence. JSON includes raw monitored URLs, redirect traces, minimal content-type/robots headers, findings and grouped failures. Raw HTML and cookies are not needed in the report.

The checker reads only the additive `technical` section, so a technical-only project needs no GSC property, report issue or credentials. The existing weekly command still requires its own complete config. See the [example](../assets/technical.example.json).

## Expectations

- `origins`: one to eight public HTTP/HTTPS origins, compared by scheme, case-insensitive hostname and effective default port. Host case and an explicit default port do not escape checking; original URL text remains in evidence. No credentials, wildcard hosts or non-default ports. Pin only reviewed owned hosts.
- `pages`: one to 1000 distinct raw URLs in a finite manifest. Each run still permits only 100 HTTP requests, including redirects and link targets. `final_url` defaults to the raw URL; `status` defaults to 200. An alias that stays at its original URL fails an expected final destination. Two intentional 200 directory/index aliases can share one canonical while retaining their own final URLs.
- `role: public`: require exactly one canonical matching the configured absolute `canonical` and no applicable noindex directive.
- `role: nonindexable`: require page or Googlebot-applicable response-header noindex/none. Canonical and metadata checks run only if explicitly configured.
- `role: excluded`: check the expected HTTP status and final URL only, plus an explicitly configured sitemap assertion. A reserved route can expect 404.
- `required_meta`: optional names from description, og:title/description/image and twitter:card/title/description/image. Missing configured values are warnings. Unconfigured metadata creates no finding.
- `organization: true`: optional Organization JSON-LD expectation. The checker never infers Article schema from a page label.
- `in_sitemap`: optional true/false assertion against the canonical or expected final URL. It requires `sitemap_url`, a namespaced XML urlset; sitemap indexes are reported unsupported/unknown.
- `group`: optional lowercase page-family identifier for grouping variants. Every raw URL remains in the report.
- Public pages can opt into `require_title: true`, `article: true` and `lang: "en"`. Title requires one nonblank head title. Article requires nonblank text inside `<article>` outside navigation, headings, headers, footers, sidebars and script/style/template/noscript content. A short API definition passes; this is an empty-content check, not an editorial quality score. Language compares the root HTML tag case-insensitively and exactly: `EN` matches `en`, but `en-US` does not. Ambiguous or unclosed relevant markup is unknown. TOC fragments and intentional nonindexable pages omit these public-content expectations.
- `check_links: true` on a public source page requires `link_prefixes`, a list of reviewed absolute owned origin/path roots. `/docs/` excludes `/docs-other/` and `/user/`. Resolve anchors against the observed final URL and first head base, remove fragments only for HTTP access and retain the original href/query in JSON. Encoded path separators or repeated escaping are unsupported/unknown. Third-party links and owned paths outside these roots are outside coverage. Restrict the roots so user-hosted content is excluded.

Noindex checks describe directives, not actual Google indexing. Ordinary GET access does not prove access by a real search bot. Deliberately excluded/noindex pages never inherit public metadata or sitemap requirements. Enumerate showcase paths only when they are part of the reviewed policy.

Link checks take one hop from selected source pages. A valid source linking to an unlisted 404 target produces a failure with source, href, target, final status and trace. Shared exact targets use one observation; distinct queries remain distinct. An excluded route that intentionally expects 404 still fails as a link target if a public source actually links to it. Targets get status checks only, without inferred content or schema rules, and never become new link sources. Fragment IDs themselves are not validated. Origin and path restrictions apply before every derived redirect request.

## Limits and outcomes

Each response is capped at 1 MiB and five redirects. The scan allows at most 100 requests and 60 seconds overall, with a ten-second elapsed collection limit per fetch. An elapsed timeout stops further collection; remaining pages become unknown. Each redirect is validated before the next request. Public DNS addresses are checked before access. The reviewed hostname allowlist remains a trust boundary; this is not an adversarial DNS sandbox.

JSON coverage records the manifest hash, configured/observed page counts, actual request count, omitted pages, discovered/unknown targets and unknown/truncated sources. At most 1000 source edges are retained per run and 1000 anchors per parsed page; truncation is explicit unknown coverage. Collection errors and budget omissions keep `complete: false`. Completion covers this manifest and selected links, not every page on the site.

For generated documentation, reuse the product's generated-output validation to create the finite URL manifest. Assign article/title/lang expectations by page role, exclude TOC fragments from article rules, and review alias and sitemap policy. Use deterministic small batches from the same source revision, reserving request capacity for link targets. Retain the full manifest hash and a local batch-to-manifest mapping; one successful batch cannot certify 325+ files. A large single manifest is accepted, but omitted URLs must be checked in later batches. The checker stores no queue or history.

Exit 0 means every configured check passed, 1 means a confirmed failure (including configured metadata warnings), and 2 means incomplete collection or invalid config. Config/file errors still emit a valid error report so workflow artifacts are readable. A mixed failed/incomplete report retains both counts and `complete: false`. TLS, timeout, oversized or unreadable responses cannot establish missing metadata or recovery. Status-only excluded routes and derived link probes do not read/decode bodies. Sitemap assertions remain independent of page collection; DTDs and sitemap indexes are unsupported/unknown. No historical runs or measurement baselines are written.

The command makes no GitHub mutations, indexing requests or repairs. It is independent of agent-dispatch incident admission and does not emit that intake's evidence format.

## Optional workflow

Copy the [manual template](../assets/technical.yml) through the site's reviewed change process after confirming the policy. Supply a reviewed plugin commit/tag accessible to that workflow. It has read-only repository permission, no provider secrets and no schedule. A report artifact and successful manual run do not prove installation in another host or actual unattended execution. Adding a schedule, provisioning GSC or enabling issue admission/repair requires its own authorized step.
For automatic reports, integrate the same command into the site's existing reviewed workflow with a full plugin commit pin. Confirm the actual next run in the owner's timezone and the first completed scheduled event: run ID, source/config, report artifact and coverage counts. A failed or incomplete run cannot establish recovery. Avoid a second producer or repair queue.
