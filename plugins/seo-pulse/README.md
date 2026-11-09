# SEO Pulse

Use Search Console evidence to choose one SEO change per site, then measure it.
SEO Pulse checks the query against the current page and gives a concrete
recommendation or a reason to wait.

## See SEO Pulse in action

In this 26-second demo, a sample project goes from three failed local source checks to zero.

https://github.com/user-attachments/assets/af8d0f3e-5f91-4598-b82d-9cb0cef5ad9f

[Download the MP4](../../assets/seo-pulse-demo.mp4?raw=true)

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
The assessment reuses product docs to judge buyer fit and the current goal;
an optional context summary is proposed without writing it during a read-only run.
Standalone content planning and recorded AI-citation analysis do not activate
this GSC workflow by themselves.

## Decisions it supports

| Question | How SEO Pulse handles it |
| --- | --- |
| What deserves attention? | Screens impressions, CTR and position, then checks the actual query and page. |
| Does the page answer the query? | Checks destination, canonical and page role; returns `match`, `mismatch` or `uncertain` with a reason. |
| Does this need another page? | Groups tasks before proposing pages; checks actual results when intent is ambiguous and asks what useful content would differ. |
| Are pages competing? | Compares intent and destinations. Redirects, document sections and different product/docs roles can be normal overlap. |
| Where would a link help? | Gives source URL/repo, target, natural anchor and placement; checks existing links and both pages' holds. |
| Is traffic falling consistently? | Weekly mode screens three equal weeks for two consecutive click drops, with sample and coverage checks. |
| Did a change help? | Shows a fixed baseline and +14/+28-day checks with clicks, impressions, CTR and position; unequal windows include daily counts. |

Small samples, partial data, unclear intent and active measurement holds can
mean **wait**. Missing rows stay unknown. Check dates can precede finalized data;
review waits for sufficient coverage. Observed movement does not prove causation.

## Use it effectively

Start with a real query and page. When that opportunity needs a content review,
supply product docs or other factual evidence and ask:

> Identify the user's task, missing answers and relevant product facts. Propose
> the smallest useful content brief: opening answer, headings and exact placement.
> Separate verified facts from assumptions. Check existing pages before suggesting
> a new one.

The [task review](skills/seo-pulse/references/research.md) records the user's input,
result and execution surface, with dated product sources and inspected result URLs
when research is needed. The brief gives the source owner and placement, a supported
answer, necessary steps and limits, proof or missing checks, and the measurement plan.
It distinguishes an interactive demo from a completed operation. Synonyms and
device names need useful differences before they justify new pages.

Competitor content can reveal questions; product evidence supports the answers.
Keyword metrics are estimates, not visitor forecasts or ranking guarantees.
Localized candidates need local task evidence and checked translations while
preserving working URLs. The review requires no paid research service.

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

## Check known public routes automatically

The [technical checker](skills/seo-pulse/references/technical.md) verifies an explicit URL list against reviewed redirect, canonical, noindex, metadata and sitemap expectations. It needs Python 3.11+ and public HTTP access, without GSC or GitHub credentials. It reports failures and incomplete collection separately.

Start with the [example config](skills/seo-pulse/assets/technical.example.json) and review each page's role. Opt into title, article text and language checks for public documentation; selected source pages can reveal broken links within reviewed owned paths in one hop. Coverage lists omitted pages and link targets when the 100-request budget is too small. The [technical guide](skills/seo-pulse/references/technical.md) explains manifests, batching and intentional exceptions.

Run the checker from the installed package. The [manual workflow template](skills/seo-pulse/assets/technical.yml) uploads a report without editing the site or opening issues. Review the URL policy and verify a manual run before enabling any schedule.

For automatic reports, add the same pinned command to the site's existing reviewed workflow. Verify an actual scheduled run before relying on delivery.
