# Observe Actions reports

The existing dispatcher tick can verify reports and save local receipts. Enrollment is optional. Place a reviewed monitoring registry at ~/.agent-dispatch/monitoring.json to enable it. The dispatcher reads the observations arrays on the registry's existing site entries. Use Python 3.11 or newer and the same authenticated gh login as the dispatcher.

The observer uses read-only GitHub requests. It reads completed attempts on main from the named workflows. It checks repository and attempt identity, main ancestry, source pins, required jobs and the ZIP digest before interpreting a report. It stores a receipt for each verified attempt. Reported findings are observations. The owner queue and trusted SEO intake govern repair admission.

## Enrollment

Add an observations array to a site with a repository field. Use registry version 1 and at most four feeds. Review the following fields for each feed.

| Field | Value |
| --- | --- |
| workflow | Exact path, such as .github/workflows/deploy.yml |
| job, prerequisites | Exact report job name and optional list of required upstream jobs |
| events | Allowed Actions events |
| since | Earliest run creation time to consider, in UTC with a Z suffix |
| artifact, member | Exact artifact name and the single JSON member expected in its ZIP |
| source_pins | Map of repo-relative paths to reviewed Git blob or tree SHAs. Pin the workflow and every producer and scope input. The workflow must pin any external checker. |
| report_on_failure | Optional. Set to true only when the pinned technical job uploads valid evidence after a nonzero checker exit. Set upload_step to the exact upload step name. |
| format | technical-v1, indexing-observations or weekly-search-report |

For technical-v1, supply manifests in batch order. Each entry is the technical object returned by the reviewed checker's validate_config. Obtain these from the reviewed source and configuration. For a producer that wraps multiple batches, also set wrapped to true, checker_commit to the pinned checker revision and outside_scope to the reviewed exclusions. Pin the source inputs that determine the batches, including the documentation tree for a producer that enumerates it.

For indexing-observations, supply the property and exact urls list. For weekly-search-report, supply the property, scope and report_issue. The weekly observer compares the plan's report block with the current issue. A no-op plan checks that the configured block still exists. The receipt records planned write count and report-block digest.

If a workflow or scope changes, review the new producer and rebuild the relevant feed before updating its pins. A contract change has its own receipt namespace. Set since to the first run you want to consider under that contract.

## Receipts and retries

Receipts live under ~/.agent-dispatch/observations/. Each names the run and attempt, source revision, contract digest and outcome. Successful reports also record the artifact ID and digests. Technical receipts distinguish healthy, finding and unknown. A failed or incomplete collection cannot establish recovery. Google Search receipts remain observations.

The observer revisits the last seven days of run creation times, bounded by since. An attempt that finishes late or is rerun within that window is picked up on a later scan. A missed window is recorded in the feed's scan status. For a run outside the window, inspect the original Actions run and artifact separately. Unverified evidence is saved as a retry record and retried after 30 minutes after discovery, even when the run leaves the scan window. After 14 days, a failed retry closes as unknown with its reason. New evidence takes priority over retries. At most three attempts per feed are processed per tick. A short file lock and atomic receipt writes let the next scan resume after an interruption.

Test with an isolated registry and state directory before enrolling the real tick. Run the candidate script twice and compare the receipts. Inspect any retry records and confirm that the test used the intended GitHub runs.

    python -B scripts/seo_observe.py --registry /path/to/reviewed-registry.json --state /path/to/test-state

The dispatcher also runs the observer while waiting for a repair, using the existing polling loop. To suspend the observer, move the enrollment file out of the dispatcher directory. Receipts remain available for inspection.
