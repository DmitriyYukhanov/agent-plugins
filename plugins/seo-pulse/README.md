# SEO Pulse

Use Google Search Console and your site's content to decide what to fix next.
SEO Pulse recommends one change per site, or tells you why to wait. After you
make a change, compare clicks, impressions, click-through rate, and position
with your baseline.

## Quick start

1. **Install.** If you already have the marketplace, run only the second command for your host.

   Claude Code

   ```text
   /plugin marketplace add DmitriyYukhanov/agent-plugins
   /plugin install seo-pulse@dmitriy-claude-plugins
   ```

   Codex

   ```powershell
   codex plugin marketplace add DmitriyYukhanov/agent-plugins
   codex plugin add seo-pulse@dmitriy-claude-plugins
   ```

2. **Run.** Open the site's repository. Connect a Search Console property you can read, then ask:

   > Use SEO Pulse for a read-only review of this project. Verify which pages we own and check any active measurements. Recommend one change per site or explain why we should wait.

3. **Apply and measure.** Review the recommendation and make the change in the repository that owns the page. Record the page, change date, and pre-change baseline in your SEO log and project config. Keep the page and its inbound links steady while you measure.

A first review can use verified scope without saving a config. For repeat runs,
set up `.claude/seo-pulse.json` and Search Console access with the
[setup guide](skills/seo-pulse/references/setup.md).

## What it does

| Feature | What you get |
| --- | --- |
| Project scope | A review limited to verified properties and owned pages, informed by your product docs, goals, and SEO log. |
| Search opportunities | Queries and pages worth checking, with evidence from impressions, clicks, click-through rate, and position. |
| Search intent and page overlap | A check of the current page, redirects, and canonical URL. See whether the page answers the query and whether similar pages serve the same task. |
| Content briefs | A recommendation to improve an existing page or create a distinct one, including localized pages. The brief uses inspected search results and product facts to specify what to write and where. [Task review](skills/seo-pulse/references/research.md). |
| Internal links | A source page, target, suggested anchor text, and exact placement. Existing links and active measurements inform the suggestion. |
| Change measurement | A fixed baseline and checks at 14 and 28 days. Small samples or incomplete data can mean waiting for a fair comparison. |
| Weekly GitHub reports | A pinned report with due measurements and sustained click declines, plus deduplicated issues for click-through rate and position opportunities. |
| Public-page audits | Compare approved URLs with their expected status, redirects, canonical URLs, noindex directives, and sitemap entries. You can also check titles, metadata, empty docs, page language, and broken links within owned paths. [Technical guide](skills/seo-pulse/references/technical.md). |

Search Console covers Google Search. Use separate evidence for AI citations,
marketplace rankings, sales, and conversions. A change in metrics alone doesn't
show what caused it.

## See SEO Pulse in action

Watch a local project go from three failed checks to zero, then see how clicks,
impressions, and click-through rate fit together in a 28-day example.

[Download the MP4](../../assets/seo-pulse-demo.mp4?raw=true)

## Set up recurring checks

- **Weekly reporting** uses Python 3.11+, Search Console access, and a GitHub destination. Start with a dry run and review the output before enabling publication. [Setup guide](skills/seo-pulse/references/setup.md).
- **Public-page audits** use Python 3.11+ and public HTTP access. Start with the [example config](skills/seo-pulse/assets/technical.example.json) and [manual workflow](skills/seo-pulse/assets/technical.yml). Review the URL scope and a manual report before scheduling it.

The [full skill](skills/seo-pulse/SKILL.md) covers evidence, measurement holds, and report limits.
