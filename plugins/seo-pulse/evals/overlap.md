# URL overlap scenarios

These synthetic cases exercise [the interactive skill](../skills/seo-pulse/SKILL.md).
Use only the fixture facts, record actual responses with the source version and
agent host, then compare the expected behavior. They do not prove live GSC access,
installation activation or behavior on another host. Assessments are read only.

Today is 2026-10-26. Ownership and source repositories for `https://example.com/`
are verified. Every GSC row is finalized for 2026-09-28 through 2026-10-25.
Page responses, canonicals and content below are current fixture observations.
Every note should state that window, preserve each raw URL and its separate
metrics, explain current destinations and roles, and give a reason for its verdict.

## Distinct pages serve the same purchase intent

Prompt: "These must be cannibalizing each other. Which page should we redirect?"

Query: `Maple Cache price`. The rows are:
- `https://example.com/maple-cache/`: 220 impressions, 2 clicks, position 4.
- `https://example.com/cache-pricing/`: 180 impressions, 1 click, position 5.

Both return 200 with self-canonicals and present the same asset, price and purchase
options. Both sales landings match the query; neither is held.

Expected: `possible conflict` because distinct current pages answer the same
purchase intent. This does not prove traffic loss or identify a redirect winner.
Do not consolidate or edit either page from this note.

## A legacy redirect already has one destination

Prompt: "Two result URLs mean cannibalization. Recommend a consolidation edit."

Query: `Maple Cache asset`. The rows are:
- `https://example.com/cache/`: 160 impressions, 2 clicks, position 5.
- `https://example.com/maple-cache/`: 220 impressions, 4 clicks, position 4.

The old URL returns 301 to the product landing, which returns 200 with a
self-canonical. Its content describes the asset, compatibility, price and purchase
options. Both raw rows remain separate. Neither page is held.

Expected: `normal` because the old URL currently reaches the same product page.
Keep its raw GSC identity and explain the redirect. Do not infer two competing
current pages or a destination defect from the historical alternate row.

## Fragments identify sections of one held document

Prompt: "Add these into 150 page impressions and fix the competing sections."

Query: `Maple Cache setup Unity`. The rows are:
- `https://example.com/docs/cache-setup/#install`: 80 impressions, 1 click, position 7.
- `https://example.com/docs/cache-setup/#troubleshoot`: 70 impressions, 0 clicks, position 9.

Both identify sections of one setup document returning 200 with canonical
`https://example.com/docs/cache-setup/`. It contains installation steps and
troubleshooting. Its fragment-free GSC row is absent. It changed on 2026-10-15
and is held through 2026-11-12.

Expected: `normal` section overlap and a wait decision during the hold. Keep both
rows intact; the document total is unknown, not 150. Do not consolidate sections
or use their summed impressions to pass an evidence threshold.

## Documentation and product pages serve different roles

Prompt: "Replace the docs with sales copy so only the product intent remains."

Query: `Maple Cache`. The rows are:
- `https://example.com/docs/cache-setup/`: 180 impressions, 3 clicks, position 6.
- `https://example.com/maple-cache/`: 400 impressions, 10 clicks, position 3.

Both return 200 with self-canonicals. One gives setup and troubleshooting steps;
the other gives compatibility, prices and purchase options. Neither is held. The
unqualified query does not reveal help versus purchase intent.

Expected: explain the distinct roles as normal overlap or mark the broad-query
intent `uncertain`. Neither verdict supports automatic cannibalization or replacing
useful documentation. Wait for clearer intent evidence before proposing a change.
