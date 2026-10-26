# SEO Pulse

Use Search Console evidence to choose one SEO change per site, then measure it.
SEO Pulse checks the query against the current page and gives a concrete
recommendation or a reason to wait.

## Start with one read-only run

Install from the marketplace in Claude Code:

```text
/plugin install seo-pulse@dmitriy-claude-plugins
```

In Codex, use the app's plugin installer or
`codex plugin add seo-pulse@dmitriy-claude-plugins`. The shared workflow uses your
host's tools; MCP setup depends on the host.

Open the site or product repository and ask:

> Use SEO Pulse for this project. Verify owned pages, Search Console access and
> existing measurement holds. Run a read-only assessment and recommend at most
> one change, or explain why we should wait. Do not install config or publish.

You need GSC access and readable current pages. The first assessment can use
verified temporary scope. For repeat runs, the
[setup guide](skills/seo-pulse/references/setup.md) covers
`.claude/seo-pulse.json`, authentication and optional adapters.

## Decisions it supports

| Question | How SEO Pulse handles it |
| --- | --- |
| What deserves attention? | Screens impressions, CTR and position, then checks the actual query and page. |
| Does the page answer the query? | Checks destination, canonical and page role; returns `match`, `mismatch` or `uncertain` with a reason. |
| Are pages competing? | Compares intent and destinations. Redirects, document sections and different product/docs roles can be normal overlap. |
| Where would a link help? | Gives source URL/repo, target, natural anchor and placement; checks existing links and both pages' holds. |
| Is traffic falling consistently? | Weekly mode screens three equal weeks for two consecutive click drops, with sample and coverage checks. |
| Did a change help? | Shows a fixed baseline and +14/+28-day checks with clicks, impressions, CTR and position; unequal windows include daily counts. |

Small samples, partial data, unclear intent and active measurement holds can
mean **wait**. Missing rows stay unknown. Check dates can precede finalized data;
review waits for sufficient coverage. Observed movement does not prove causation.

## Use it effectively

Start with a real query and page. For a content review, supply product docs or
other factual evidence and ask:

> Identify the user's task, missing answers and relevant product facts. Propose
> the smallest useful content brief: opening answer, headings and exact placement.
> Separate verified facts from assumptions. Check existing pages before suggesting
> a new one.

Use semantic analysis to explain relevant features, limits and relationships.
Competitor content can reveal questions; your product evidence must support the
answers. Keyword repetition and copied outlines do not establish usefulness.
Localized keywords need market/language evidence beyond a literal translation.

Implement one justified change through the page owner's reviewed flow. Record
its date, page, fixed baseline and check dates in the SEO log and config. Hold
the page while measuring, including new inbound links. Keep other ideas parked.

## Add weekly reporting when ready

Weekly mode puts due measurements and decline flags in a pinned GitHub report.
It separately maintains deduplicated `seo-signal` issues for CTR and position
opportunities. It does not edit sites or open PRs. The Python runner makes no
paid model call.

Follow [setup](skills/seo-pulse/references/setup.md) for Python 3.11+, credentials
and the opt-in workflow. Inspect a dry run, authorize publication, then read back
the issues. Installation alone does not enable a schedule. Connected GSC read
tools can replace the bundled MCP adapter, which requires `uvx`.

GSC covers Google Search traffic to verified owned pages, including product
landings and docs across source repos. Sales, marketplace rankings, conversions,
competitor search results and AI citations need separate evidence; SEO Pulse
does not collect them automatically. The [skill](skills/seo-pulse/SKILL.md)
defines the full workflow.

Local tests use a fake API transport. Verify actual host activation, GSC access
and first unattended delivery separately before relying on recurring reports.
