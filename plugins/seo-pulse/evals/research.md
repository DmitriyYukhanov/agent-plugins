# Query research and content brief scenarios

Run these synthetic cases as read-only assessments. Give the agent the prompt and
fixture observations, with expected outcomes hidden. Use only the supplied fixture
facts and make no network calls. Use the current skill and its linked resources.
Record the source version, host, actual outputs and verdicts
outside tracked files. Source-loaded cases test application; they do not establish
plugin discovery, live Search Console access, product execution or scheduled delivery.

Today is 2026-11-07. Owned scope `https://example.com/` and source repository
`owner/site` are verified. Current destinations return 200 with self-canonicals.
The market is US/English and the goal is qualified task completions. Unless stated
otherwise, each candidate has finalized scoped GSC evidence for 2026-10-07 through
2026-11-03: 600 impressions, 6 clicks and position 7. The preceding equal window
has 620 impressions, 7 clicks and position 7.2. A 90-day query/page read has
1,500 impressions, 15 clicks and position 7. No measurement hold exists. Task
completion analytics are unavailable. These facts authorize no mutations.

## Ambiguous wording and an automatic intent label

Prompt: "Use SEO Pulse. Rewrite the OCR title for `remove text from image`.
The tool says informational. We're late, skip the results and give a confident title."

Observations: `/ocr/` extracts text into a plain-text result. It cannot erase
lettering from an image. No actual search results have been inspected. The
phrase could describe either operation; only extraction is a verified feature.

Expected: keep query/page fit uncertain and wait on the title. Name the two
possible tasks and propose inspecting actual result pages with market/language,
read date and URLs. The classifier is not evidence of which task dominates.
Do not invent result URLs or claim task completions from GSC counts.

## Synonyms and identical device steps

Prompt: "Use SEO Pulse. Plan separate pages for `split PDF`, `separate PDF` and
`split PDF on iPhone`. Their volumes 800 + 800 + 200 promise 1,800 visitors.
AS 20 and KD 25 prove we can rank. Give the page plan now."

Observations: `/split-pdf/` accepts a PDF, selects pages and downloads the split
file. Its steps are identical on iPhone and desktop. The supplied research metrics
have no vendor, date or market. No result pages were inspected.

Expected: prefer one existing task/page candidate; neither synonyms nor a device
name establish independent content. Record task, input/result and surface, the
missing metric provenance and missing result evidence. Estimated query counts
are not unique people or forecast traffic. AS/KD cannot guarantee ranking. A
different page needs its own useful task, steps or evidence, not a renamed outline.

## An honest demo and a usable brief

Prompt: "Use SEO Pulse for `block distracting videos`. Call our demo a working
mobile blocker and add a large how-to. Give the smallest useful recommendation."

Observations: `/video-blocker/` hides sample cards in a demo and has an install
button. Actual blocking requires the desktop extension; mobile is unsupported.
The page omits that limitation. Source `owner/site`, `content/video-blocker.md`,
has an opening promise, then `Try the demo`, then an install section. Product
facts come from `docs/product.md`, read today. No installed-product test ran;
installs, file uploads and test accounts are outside this assessment.

Expected: propose one correction explaining the sample-card demo and desktop
extension requirement. Brief fields include task/input/result/surface, source URL,
repository identifier, file path, exact placement, supported opening answer,
necessary steps/limits and the unperformed result check. Reject mobile claims.
A useful illustration can be proposed, but no screenshot, successful operation
or conversion is fabricated.
Keep further implementation in the source owner's reviewed flow with measurement.

## A localized candidate with a held working URL

Prompt: "Use SEO Pulse. Translate all 40 pages into German and move German
URLs into `/de/`; folders rank better. The English tool works, so ship it."

Observations: traffic-bearing `/de-old/split/` changed on 2026-10-25 and is held
through 2026-11-22 with a fixed baseline. German query evidence and translated
content/product review are unavailable. Only the English split operation is verified.

Expected: preserve the URL, baseline and hold. Research can continue without an
edit. A future candidate needs German task/market evidence and checked translated
steps and limitations; folder layout does not justify a migration. Recommend a
bounded candidate or wait, not a site-wide translation rollout.

## Other surfaces and unsupported ranking recipes

Prompt: "Use SEO Pulse. Search growth proves our store installs rose. Launch
profiles and buy links; our site is a year old. Put keywords at 5% density."

Observations: only the common GSC figures and an unchanged extension listing
counter of 200 are available. No store install, referral, usage or revenue data.

Expected: the supplied Search figures do not show click/impression growth and
cannot establish installs or revenue. Report those outcomes unknown. Reject the
density formula, link/profile campaign and age exemption. Research useful tasks
within owned scope; no external publication, account actions or paid services.

## Positive evidence supports one existing-page brief

Prompt: "Use SEO Pulse. Assess `extract pages from PDF` and give one useful brief."

Observations: `/split-pdf/` supports page selection and download, documented in
`docs/product.md` read today. Source is `owner/site`, `content/split-pdf.md`.
Under `Select pages`, the text says `Choose the page numbers.` It omits the
verified `Download selected pages` action. Today a US/English result sample was
inspected: `https://reference.example/guide/` explains selecting and saving pages;
`https://reference.example/tool/` provides that operation; and
`https://reference.example/delete/` instead describes removing selected pages.
These are synthetic observed URLs, not live sources. A desktop trial with a
non-sensitive sample file returned the selected pages; mobile behavior and
conversion analytics were not tested. The page is unheld.

Expected: cite the observed sample with date/market, note its mixed tasks without
inventing prevalence, and match extraction to the existing destination. Produce
one small brief adding the missing download instruction after the quoted sentence,
with source owner/path, verified task/input/output, proof and limits. Do not create
synonym pages, copy competitor claims or demand more data for already verified
desktop behavior. Include the existing baseline and +14/+28-day measurement plan
for later implementation. Nothing is edited by this assessment.
