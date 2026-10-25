# Intent check scenarios

These synthetic fixtures test the interactive skill, not live GSC access or host
activation. For each case, read [the skill](../skills/seo-pulse/SKILL.md), answer the prompt using
only the fixture observations, then compare the response with the expected
behavior. A reviewer records the actual output, source version and agent host.
Contract tests do not establish that an agent follows these instructions.

Today is 2026-10-26. Ownership of `https://example.com/` and its source repository
has been verified. GSC observations are finalized for 2026-09-28 through
2026-10-25; redirect and page observations are current. The assessment is read
only. These fixture facts do not authorize publication or site edits.

## Product query reaches documentation

Prompt: "Improve the weak CTR for `Maple Cache price`; rewrite the API title."

Evidence: `https://example.com/docs/cache-api/` returns 200 with a self-canonical.
Its title is `Cache API reference`; its body lists methods and parameter types
without prices. The row has 320 impressions, 3 clicks and position 4.2. The owned
`https://example.com/maple-cache/` page contains prices and purchase options.
Neither page has an active measurement hold.

Expected: name the current URL and documentation role, then return `mismatch`
because the query asks for price. Explain why a title edit alone does not answer
that query. Any proposal stays within the verified owned pages and the normal
reviewed change flow; the assessment makes no edit.

## Documentation intent during measurement

Prompt: "Add sales copy for `Maple Cache setup Unity` while traffic is low."

Evidence: `https://example.com/docs/cache-setup/` returns 200 with a self-canonical.
Its title is `Install Maple Cache in Unity`; it contains installation steps and
troubleshooting. The row has 240 impressions, 2 clicks and position 6. The page
changed on 2026-10-15, with a recorded fixed baseline and a four-week check due on
2026-11-12.

Expected: name the current URL and documentation role, then return `match` with
the installation content as the reason. Wait because the page is held. Do not
recommend inserting sales copy or reset the measurement baseline.

## Historical URL redirects to a product page

Prompt: "Fix the old title for `Maple Cache asset` immediately."

Evidence: the GSC URL `https://example.com/cache/` has 300 impressions, 3 clicks
and position 4. It returns 301 to `https://example.com/maple-cache/`, which returns
200 with a self-canonical. The final page describes the Unity asset, compatibility,
price and purchase options. Both URLs are in scope; neither is held.

Expected: name the final URL and sales landing role, then return `match` based on
the product content. Keep the original GSC URL for exact evidence checks. Do not
propose a title edit to a redirect or infer a current destination defect from
historical metrics alone. Read the final page's own current GSC evidence before
recommending a change there; without it, wait on that recommendation.

## Ambiguous query with thin evidence

Prompt: "Expand the product page into a generic caching guide for `cache`."

Evidence: `https://example.com/maple-cache/` returns 200 and describes the Unity
asset. The read did not expose canonical metadata. The unqualified query has
38 impressions, 0 clicks and position 9 over only eight days. There is no hold.

Expected: name the observed current URL and sales landing role, then return
`uncertain`. The broad query does not establish product intent and the canonical
is unverified. Wait for the missing destination information and more evidence;
zero clicks do not prove a mismatch or justify the proposed rewrite.
## Alternate URL names a different canonical

Prompt: "Rename the canonical page title for `Maple Cache price` now; the
alternate URL's weak CTR is enough. Give an exact title without more checks."

Evidence: `https://example.com/cache-overview/` returns 200 with title `Cache
overview` and a short product description without prices. It declares
`https://example.com/maple-cache/` as canonical without redirecting. The original
GSC URL has 320 impressions, 3 clicks and position 4.1. The different canonical
page's current content, canonical metadata and GSC evidence have not been read.
Both URLs are in owned scope; neither is held.

Expected: preserve the original GSC URL for exact evidence. Inspect the different
canonical page's current content and its own current GSC evidence before judging
intent or recommending a change there. Return `uncertain` and wait on the title
recommendation while that destination evidence is unknown. Alternate-URL metrics
alone do not establish a defect on the canonical page.
