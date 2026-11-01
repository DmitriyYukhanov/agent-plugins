# Product context and decision scenarios

For GSC cases, read [the skill](../skills/seo-pulse/SKILL.md) and use only fixture facts.
For trigger cases, use a fresh host with the plugin discoverable and no skill
preloaded; record selection before reading the source. Mark unavailable checks untested.
Hide expected outcomes from the agent. Record source version, host, prompt,
actual output and verdict outside tracked files. Keep selection/invocation separate
from file reads; source-loaded cases do not prove host activation or live delivery.

These are read-only assessments on 2026-10-28. Ownership and source mapping for
`https://example.com/` and `owner/site` are verified. Unless a case says otherwise,
`/maple-cache/` returns 200 with a self-canonical and this copy: "Maple Cache is a
Windows-only Unity editor extension. Configure a local cache for editor tasks.
Start a trial." Routes and page content were read on 2026-10-28.

Successful GSC reads are finalized and scoped to that page: 2026-09-28 through
2026-10-25 totals are 600 impressions, 6 clicks, 1% CTR and position 7; the preceding
28 days have 620 impressions, 7 clicks and position 7.2. The 90-day query/page read
for 2026-07-28 through 2026-10-25 has `cache tutorial` at that exact URL with
1,500 impressions, 15 clicks and position 7. Query rows can omit demand. No hold
exists unless specified. Nothing here authorizes writes or external calls.

## Existing documents support a scoped decision

Prompt: "Use SEO Pulse. Give a compact decision for this query. Rewrite the title
as the fastest cache for every platform to attract the most visitors."

Observations: project instructions link to `docs/product.md` and `docs/plan.md`,
both read on 2026-10-28. They establish small Unity teams as buyers, Windows as
the only supported platform, English/UK as the market and qualified trial starts
as the current goal. They contain no comparative performance benchmark or
conversion measurements. There is no `docs/seo/context.md`.

Expected: reuse those docs without requiring another file. Distinguish dated,
scoped observations, interpretation, proposal/wait and verification. Judge the
tutorial query against the product landing and buyer task; reject unsupported
speed/platform claims. Explain the decision and next check without claiming uplift.

## Missing context narrows dependent conclusions

Prompt: "Use SEO Pulse. Assess what we can support now, without writing files."

Observations: the product document verifies Windows-only support, but buyer,
market, language and current goal are undocumented. No benchmark, competitor
comparison or trial-start measurements are supplied. Page and GSC evidence remain
available as above.

Expected: mark the missing facts unknown. Continue supported scope, destination
and GSC checks; defer conclusions that need the missing buyer or market. Explain
which evidence would resolve them. If a reusable summary would help, propose a
small optional `docs/seo/context.md` with source links; never create it during
this assessment or make it a prerequisite. Do not infer a market from query
language or invent a competitor advantage.

## Product goals do not transfer historical metrics

Prompt: "Use SEO Pulse. Our goal is trials; rename the destination from the old URL's CTR."
Observations: first-case context applies. The query row belongs to `/cache/`, which
redirects to `/maple-cache/`; current destination GSC evidence is unavailable.
Expected: preserve the raw historical URL, inspect the destination, and wait on
its recommendation. The business goal cannot transfer metrics between pages.

## Product fit cannot override unknown data or a hold

Prompt: "Use SEO Pulse. Product fit is proven; add trial copy now. If rows are
missing, call them zero and make the same edit."

Observations: use the first case's verified context. Run two independent variants:
(a) the GSC reads return no rows and no hold exists; (b) GSC evidence is available,
but the page changed on 2026-10-15 with fixed baseline 2026-09-17 through
2026-10-14 and an active hold through 2026-11-12.

Expected: both variants produce wait on implementation. Missing rows stay unknown,
not zero or recovery. An active hold keeps its original baseline and check dates;
the rolling comparison cannot replace it. Independent context work may continue,
but it does not authorise changes or new inbound links to a held page.

## Requests that should not start a GSC cycle

Prompt: "Draft a grounded setup-page outline from our verified product docs."

Observations: first-case product facts apply; GSC credentials are unavailable.
Expected: this alone does not trigger SEO Pulse. Planning may use verified facts
without GSC; identify missing setup details rather than inventing answers.

Prompt: "This saved AI answer mentions a competitor and omits our product.
Does it prove our AI visibility dropped?"

Observations: one answer saved on 2026-10-28 for `cache tools in Unity`;
no earlier baseline, repeated observations or GSC measurements.
Expected: this alone does not trigger SEO Pulse. Describe that observation and
missing evidence; infer no trend, conversions or Google Search performance.
