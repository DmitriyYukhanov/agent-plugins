# Observation format

Keep a JSON array of observations in the project's local work directory
alongside the captures. This example is synthetic.

```json
[
  {
    "run_id": "run-a",
    "product": "product-a",
    "prompt_set": "buyer-questions@1",
    "prompt_id": "Q1",
    "prompt": "Which tools export reports as CSV?",
    "task": "discovery",
    "engine": "engine-a",
    "surface": "consumer app",
    "model": null,
    "search_setting": "Web Search",
    "language": "en",
    "market": "GB",
    "repeat_id": "1",
    "repeat_number": 1,
    "timestamp": "2026-11-10T12:05:00+00:00",
    "status": "observed",
    "raw_ref": "raw/run-a/Q1-1.txt",
    "mention": true,
    "citations_complete": false,
    "citations": [
      {"url": "https://sources.example/report-exports", "ownership": "third_party"}
    ]
  }
]
```

## Import

- Use a stable `run_id` for each collection batch, prompt-set version and
  set of conditions. If an export mixes versions or conditions, give each
  series its own stable run ID. Reuse it on import. An observation's
  identity is `(run_id, prompt_id, repeat_id)`. Keep the original repeat ID
  for each attempt. A new, intentional repeat needs a new slot and capture.
  Never mint identities from import filenames or import time. If an export
  cannot identify a batch or attempt reliably, flag that gap before counting.
  Record the planned repeat number in `repeat_number` when the collection
  protocol establishes it. Use `null` if it is unknown.
- Import identical records for a slot once. If the evidence for a slot
  disagrees, retain both versions locally, report the conflicting identity
  and leave that slot out of metric totals until the evidence resolves it.
  Validate that a run uses consistent conditions and that a versioned prompt
  ID has the same exact text. Flag mismatches before comparing.
- Record the search setting shown for the actual answer. A preview or
  fallback mode gets its own run ID even if the selected mode stayed the same.
- Use `observed` for an answer, `failed` for an attempted collection with
  no answer and `not_run` for an unattempted prompt. An answer captured in
  full still counts if the interface shows an access warning.
  If an older export only says a slot is missing, leave it as a coverage
  gap unless the source establishes whether it was attempted. Keep
  unavailable annotations, raw references and timestamps as `null`. Use the
  timestamp and timezone from collection evidence. For `raw_ref`, use a local
  path or stable capture ID. Mark missing captures. If the source records
  competitors, retain those observations in the optional `competitors` field.
- An explicit `mention: false` means the answer was scored and the target
  was absent. Use `mention: null` for an unscored answer. An excerpt that
  omits the target supports a negative only if a full-answer scan confirms
  absence. Keep failed and unrun rows out of the denominators.
- Preserve the observed destination URLs exactly. Classify each URL against
  the verified project scope as `owned`, `third_party`, or `null` if
  ownership is unresolved. Use `citations: null` when the URL record is
  unavailable. Use `citations: []` with `citations_complete: true` only
  for a confirmed answer with no citations. Use a nonempty list with
  `citations_complete: false` when only some destinations were captured.
  Retain the citation as answer evidence and leave source-selection reasons unknown.

## Count and compare

- Report observed answers out of planned prompt/repeat slots, with counts
  for failures, unrun slots, conflicts and any unexplained gaps. Show which
  prompts and repeats were measured. When planned coverage is unknown,
  report the observed count and leave planned coverage unknown.
- For each metric, count positive answers over answers where that metric
  is known. A single confirmed URL of the relevant type establishes a
  positive, even from a partial list. A negative requires a complete list
  with enough ownership evidence to rule out that type. Show unknown counts
  and call partial citation counts confirmed minima over all observed answers.
  If the denominator is zero, show insufficient evidence for that metric.
- Count each exact URL once per series and preserve all contributing
  prompt IDs, engines and raw observation references. Flag links with
  unavailable captures as export-only evidence. Keep raw references local
  when publishing an authorized summary.
- Show series by run, product, prompt-set version, engine, app/API surface,
  model, search setting and language/market. Keep other documented changes
  to collection conditions visible. Pair runs on the same prompt ID and
  planned repeat number. Keep each original repeat ID in the provenance.
  Use slots with one observation and a measured value on each side for
  that metric. Report missing or ambiguous pairs as gaps.
  Label same-prompt comparisons across engines as descriptive and show each
  side's conditions. Keep incompatible runs separate. If a model or setting
  is unknown, say so and leave equivalence unverified.
