# Internal-link scenarios

These synthetic cases exercise [the interactive skill](../skills/seo-pulse/SKILL.md).
Use only the fixture observations, record actual outputs with source version and
agent host, then compare expected behavior. They do not prove live GSC access,
installation activation or behavior on another host. Assessments are read only.

Today is 2026-10-26. Owned scope and repository mappings for `https://example.com/`
and `https://docs.example.com/` are verified. Every target has finalized evidence
for 2026-09-28 through 2026-10-25: 320 impressions, 3 clicks and position 8 for
its stated query. Page responses, content, links and owners below are current.
Positive suggestions must include source URL, source repository/submodule, target
URL, natural anchor and exact placement. A later edit requires the source owner's
normal reviewed change cycle; these facts do not authorize insertion.

## Existing relative link redirects to the target

Prompt: "Give three new links anyway; the existing href is different."

Target `https://example.com/maple-cache/` returns 200 with a self-canonical and
matches `Maple Cache asset` as a sales page. Source
`https://example.com/guides/cache-in-unity/` already links to `../../cache/` with
anchor `Maple Cache`. That resolves to `https://example.com/cache/`, which returns
301 to the target. Both pages belong to `owner/site`; neither is held.

Expected: return no new link from this source. Resolving the relative href and
redirect establishes that the target is already linked. A requested count does
not justify duplicates.

## Inbound changes would confound a held target

Prompt: "Only change the source; the target's hold should not matter."

Requested target `https://example.com/cache/` returns 301 to
`https://example.com/maple-cache/` (200, self-canonical), a sales landing matching
`Maple Cache asset` with its own GSC evidence. It changed on 2026-10-10 and is held
through 2026-11-07. Relevant source
`https://example.com/guides/cache-performance/` is unheld and has no target link
after resolution. Under `Cache tuning`, it says `Review the cache's supported
runtime options.` Both source and target belong to `owner/site`.

Expected: identify the final target and wait. Adding a new inbound link changes
the held target's experiment even if its own file remains untouched.

## A docs-only product has one usable source

Prompt: "Give two links to this product's sales landing."

Target `https://example.com/docs/maple-cache/quickstart/` returns 200 with a
self-canonical, contains installation steps and matches `Maple Cache setup`.
It belongs to `owner/maple-cache-docs` and is unheld. No sales landing is verified.
Source `https://example.com/guides/unity-cache-setup/`, owned by `owner/site` at
`content/guides/unity-cache-setup.md`, is unheld and has no target link after
resolution. Under `Configure your cache`, it says `After importing the package,
choose a cache directory for your project.` The next paragraph starts `You can
verify the installation in Play Mode.` Another relevant source,
`https://example.com/guides/cache-troubleshooting/`, belongs to `owner/site` but is
held through 2026-11-12.

Expected: return at most one recommendation to the verified documentation target,
with all required fields and a natural setup anchor between those paragraphs.
Exclude the held source and do not invent a sales page or a second suggestion.

## The source belongs to a different repository

Prompt: "Propose the link and put its placement in the report repository."

Target `https://example.com/maple-cache/` returns 200 with a self-canonical and
matches `Maple Cache compatibility`; its content includes compatibility and
purchase options. It belongs to landing submodule `owner/maple-cache-landing`.
Source `https://docs.example.com/cache/advanced/` belongs to `owner/maple-cache-docs`
at `docs/cache/advanced.md`. Both are unheld, and source link resolution found no
target link. Under `Choose storage`, the source says `The supported cache options
vary by runtime.` The next sentence is `The following examples use a local
directory.` The report repository `owner/site` does not own this source.

Expected: return one recommendation with all required fields and a compatibility
anchor between the supplied sentences. Route any later edit to
`owner/maple-cache-docs`, not `owner/site` or the target's landing submodule.
