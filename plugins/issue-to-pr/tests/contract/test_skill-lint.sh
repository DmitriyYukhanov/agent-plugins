#!/usr/bin/env bash

skill_md() { printf '%s' "$ITP_SCRIPTS/../skills/run/SKILL.md"; }
setup_md() { printf '%s' "$ITP_SCRIPTS/../skills/setup/SKILL.md"; }
references_dir() { printf '%s' "$ITP_SCRIPTS/../skills/run/references"; }
companions_md() { printf '%s' "$(references_dir)/companions.md"; }
plugin_readme() { printf '%s' "$ITP_SCRIPTS/../README.md"; }
repo_readme() { printf '%s' "$ITP_SCRIPTS/../../../README.md"; }
plugin_manifest() { printf '%s' "$ITP_SCRIPTS/../.claude-plugin/plugin.json"; }
marketplace_manifest() { printf '%s' "$ITP_SCRIPTS/../../../.claude-plugin/marketplace.json"; }

skill_step() { # word-in-the-heading
  local heads head='^([*][*][0-9]+([.][0-9]+)?[.] |## Step [0-9])'
  heads=$(grep -cE "$head.*$1" "$(skill_md)")
  [ "$heads" -eq 1 ] || fail "SKILL.md has $heads step headings naming $1; there must be exactly one.
    Zero means it was renamed or removed. Two is how one step becomes two, which is how a single
    contact moment becomes a pair that each still reads like the original."
  awk -v w="$1" -v h="$head" '$0 ~ h {f = index($0, w) > 0} f' "$(skill_md)"
}

description_in() { # manifest [anchor-line]
  local line
  if [ -n "${2:-}" ]; then
    line=$(grep -A1 -F -- "$2" "$1" | grep '"description"' | head -1)
  else
    line=$(grep '"description"' "$1" | head -1)
  fi
  line=${line#*\"description\": \"}
  line=${line%\",}
  printf '%s' "${line%\"}"
}

test_every_reference_is_cited_and_every_citation_exists() {
  local on_disk cited
  on_disk=$(basename -a "$(references_dir)"/*.md | sort -u)
  cited=$(grep -o 'R/[A-Za-z0-9._-]*\.md' "$(skill_md)" | cut -d/ -f2 | sort -u)
  [ -n "$on_disk" ] || fail "no references on disk; this check would be vacuous"
  [ "$on_disk" = "$cited" ] || fail "the reference files on disk and the R/*.md the spine cites disagree.
    on disk: $(printf '%s' "$on_disk" | tr '\n' ' ')
    cited:   $(printf '%s' "$cited" | tr '\n' ' ')"
}

test_skill_names_every_script_that_ships() {
  local spine script found=0
  spine=$(cat "$(skill_md)")
  for script in "$ITP_SCRIPTS"/*.sh; do
    assert_contains "$spine" "${script##*/}" "SKILL spine must invoke ${script##*/}, or the script should not ship"
    found=$((found + 1))
  done
  [ "$found" -gt 0 ] || fail "no scripts found under $ITP_SCRIPTS; the glob did not expand"
}

test_skill_never_writes_a_resolved_value_as_a_shell_variable() {
  local hits
  hits=$(grep -n '\$[A-Z][A-Z_]\{2,\}' "$(skill_md)" || true)
  [ -z "$hits" ] || fail "SKILL.md names a shell variable where it must substitute the value.
    Every Bash call is a fresh shell, so the name expands to nothing. Use <ANGLE_BRACKETS>.
$hits"
}

test_skill_grill_reshapes_the_checkpoint_without_adding_a_moment() {
  local spine checkpoint ask_contract file content
  spine=$(cat "$(skill_md)")
  [ -n "$spine" ] || fail "SKILL.md came back empty; this check would be vacuous"
  grep -q 'argument-hint:.*--grill' "$(skill_md)" || fail "argument-hint must advertise --grill"

  for file in "$(skill_md)" "$(setup_md)" "$(references_dir)"/*.md \
              "$(plugin_readme)" "$(repo_readme)"; do
    content=$(cat "$file")
    [ -n "$content" ] || fail "$file came back empty; this check would be vacuous"
    assert_not_contains "$content" 'drill' "$file still mentions drill, which the plugin no longer has"
  done

  checkpoint=$(skill_step Checkpoint)
  assert_contains "$checkpoint" 'grilling' "the checkpoint must run the grill when --grill asked for it"
  assert_contains "$checkpoint" 'batched question' "the checkpoint lost its batched question"
  assert_contains "$checkpoint" 'replaces' \
    "the checkpoint must say the grill REPLACES the batched question; one that grills and THEN asks spends two contacts"

  ask_contract=$(printf '%s\n' "$spine" | grep -A3 -i 'ask contract:')
  [ -n "$ask_contract" ] || fail "the spine no longer states the ask contract"
  case "$ask_contract" in
    *four*) fail "the ask contract promises a fourth moment again: $ask_contract" ;;
  esac
}

test_review_convergence_simplifies_before_more_fixes() {
  local rule
  rule=$(awk '/^[*][*]Convergence:/ { f = 1 } f && /^## / { exit } f' "$(references_dir)/judgment.md")
  [ -n "$rule" ] || fail "judgment.md must define review convergence beside escalation"
  assert_contains "$rule" 'distinct confirmed bugs' "duplicate or rejected findings must not inflate the count"
  assert_contains "$rule" 'first pass' "the first pass must establish the comparison baseline"
  assert_contains "$rule" 'one or more' "a clean pass must not trigger simplification on zero equals zero"
  assert_contains "$rule" 'at least as many' "equal or increasing bug counts must trigger convergence"
  assert_contains "$rule" 'previous pass' "compare consecutive passes, not the whole run"
  assert_contains "$rule" 'before applying' "simplification must precede another round of patches"
  assert_contains "$rule" 'deleting the feature' "each open fix must weigh deletion"
  assert_contains "$rule" 'agreed behavior' "deletion must preserve the authorized scope"
  assert_contains "$rule" 'Ledger both counts' "convergence must leave its comparison evidence"
  assert_contains "$rule" 'choice and rationale' "the ledger must record deletion-versus-fix judgment"
  assert_contains "$rule" 'pass cap' "simplification must preserve the review budget"
  assert_contains "$rule" 'no review pass' "simplification must not restart the review loop"
}

test_confirmed_review_fixes_start_with_a_failing_regression() {
  local review pr
  review=$(skill_step Review)
  assert_contains "$review" 'every confirmed finding' "all confirmed findings need regression coverage"
  assert_contains "$review" 'local reviewers, the second model and review bots' "the rule must cover every reviewer source"
  assert_contains "$review" 'fails without the fix' "a green-only test cannot prove the reported defect"
  assert_contains "$review" 'before applying' "the regression must run before the affected code changes"
  assert_contains "$review" 'fix, simplification or deletion' "deletion must not bypass regression evidence"
  assert_contains "$review" 'demonstrate the defect' "an infrastructure failure is not a failing regression"
  assert_contains "$review" 'ledger the finding and reason' "missing automated coverage needs a concrete explanation"
  pr=$(skill_step 'PR and report')
  assert_contains "$pr" "as Step 6 verifies a reviewer's" "bot findings must retain evidence verification before a fix"
  assert_contains "$pr" "Step 6's regression rule" "bot fixes must follow the same test-first path"
  assert_contains "$pr" 'it opens no review pass' "bot findings must not extend the convergence loop"
}

test_report_names_fixes_without_regression_tests_at_every_tier() {
  local report
  report=$(skill_step 'PR and report')
  assert_contains "$report" 'findings fixed without regression tests' "the report must expose missing regression coverage"
  assert_contains "$report" 'when any' "exceptions must be reported when present without requiring an empty section"
  assert_contains "$report" 'with reasons' "each missing regression must have a reason"
  assert_contains "$report" 'report and PR body at every tier' "short reports and the PR body must retain the exceptions"
}

test_report_reconciles_the_applicable_flow_after_bot_fixes() {
  local report companions
  report=$(skill_step 'PR and report')
  companions=$(cat "$(companions_md)")
  assert_contains "$report" 'Final flow reconciliation' "the report must reconcile the flow before asking to merge"
  assert_contains "$report" 'current HEAD and changed behavior' "evidence must cover the reported change"
  case "$report" in
    *'that bot as unchecked.'*'Final flow reconciliation'*'Then report,'*) : ;;
    *) fail "reconcile after bot handling and before the final report" ;;
  esac
  assert_contains "$report" 'do not request merge approval or self-merge' "incomplete flow must not reach either merge path"
  assert_contains "$report" 'When the flow is complete, ask when to merge' "the terminal instruction must respect reconciliation"
  assert_contains "$companions" 'available and its runtime requirements are met' "an available companion must not be silently replaced"
}

test_the_second_model_review_only_reports() {
  local row step
  row=$(grep -i 'second-model review' "$(companions_md)")
  [ -n "$row" ] || fail "companions.md lost the Step 6 second-model review row"
  # --fresh skips the resume-thread question, --wait keeps the result in this turn
  assert_contains "$row" 'codex:rescue --fresh --wait' "the second-model row must name the invocation it prefers"
  assert_not_contains "$row" 'cross-review' "cross-review applies its own fixes and prompts about a dirty tree; Step 6 lets
    only the parent apply fixes and has no contact moment for that prompt"
  assert_contains "$row" 'asked for a read-only review' "without an explicit read-only ask the rescue forwarder runs Codex
    with --write"
  assert_contains "$row" 'git diff --name-only <BASE>' "the second model must be handed the changed files"
  assert_contains "$row" 'git ls-files --others --exclude-standard' "the second model must be handed the untracked files
    too: Step 6 runs before anything is committed"
  assert_contains "$row" 'a blocked review, not a clean one' "a failed or backgrounded Codex call returns nothing, which
    must not read as a clean review"
  assert_contains "$row" 'git hash-object --stdin' "the tree is already dirty in Step 6, so only a hash of the diff and the
    untracked files shows whether Codex edited it"
  assert_contains "$row" 'git ls-files --others --exclude-standard;' "the hash must cover untracked paths, not only their
    contents, or a rename slips through"
  step=$(skill_step Review)
  assert_contains "$step" 'second' "the spine must say when the second model runs"
  assert_contains "$step" "On \`complex\`" "the second-model review must retain its complex-tier trigger"
  assert_contains "$step" 'R/companions.md' "the second-model review must retain its host capability guidance"
}

test_the_headless_second_opinion_never_prompts() {
  local row
  row=$(grep -i 'second opinion' "$(companions_md)")
  [ -n "$row" ] || fail "companions.md lost the Step 3 second-opinion row"
  assert_contains "$row" 'codex:rescue --fresh --wait' "headless has nobody to answer the resume-thread question"
  assert_contains "$row" 'read-only' "without an explicit read-only ask the rescue forwarder runs Codex with --write"
  assert_contains "$row" 'is no second opinion' "empty output must not read as the second model agreeing"
  assert_not_contains "$row" 'cross-review' "cross-review hands undecided items and a dirty-tree prompt to a user headless
    does not have"
}

test_a_host_builtin_is_never_offered_as_an_install() {
  local setup companions offenders
  setup=$(cat "$(setup_md)")
  companions=$(cat "$(companions_md)")
  assert_contains "$setup" 'gh auth status' "setup.md did not load; this check would be vacuous"
  assert_contains "$companions" 'Inline fallback'     "companions.md did not load; this check would be vacuous"
  offenders=$(printf '%s
%s
' "$setup" "$companions" |
    grep -nE '(plugin (install|add)|marketplace add)' |
    grep -E 'code-review|simplify|verify|deep-research' || true)
  [ -z "$offenders" ] || fail "an install command is offered for a capability the host ships:
$offenders"
}

test_setup_checks_the_hard_requirements_and_installs_nothing() {
  local setup
  setup=$(cat "$(setup_md)")
  assert_contains "$setup" 'gh auth status' "setup must verify the one hard dependency the run has"
  assert_contains "$setup" 'gh auth refresh -s project' \
    "board mode needs the project scope; setup must print the command that adds it"
  assert_contains "$setup" 'never run' \
    "setup prints install commands for a human to run; it must say it installs nothing itself"
}

test_manifests_agree_on_what_the_plugin_does() {
  local plugin market
  plugin=$(description_in "$(plugin_manifest)")
  market=$(description_in "$(marketplace_manifest)" '"name": "issue-to-pr"')
  [ -n "$plugin" ] || fail "no description found in plugin.json; this check would be vacuous"
  [ -n "$market" ] || fail "no issue-to-pr description found in marketplace.json; check vacuous"
  case "$plugin$market" in
    *'"description"'*) fail "the key survived the strip, so both sides are raw lines; check vacuous" ;;
  esac
  [ "$plugin" = "$market" ] || fail "the manifests describe the plugin differently.
    plugin.json is the only copy Claude Code reads, so byte equality is the rule.
    plugin.json:      $plugin
    marketplace.json: $market"
}

test_headless_is_one_flag_that_reshapes_two_contacts_and_adds_none() {
  local hl merge
  grep -q 'argument-hint:.*--headless' "$(skill_md)" || fail "argument-hint must advertise --headless"
  grep -q 'argument-hint:.*--auto-merge' "$(skill_md)" || fail "argument-hint must advertise --auto-merge"
  hl=$(cat "$(references_dir)/headless.md") || fail "R/headless.md missing"
  assert_contains "$hl" 'agent:waiting' "headless.md must name the label a posted question sets"
  assert_contains "$hl" 'agent:review'  "headless.md must name the label an unmerged PR sets"
  assert_contains "$hl" 'An **owner reply** is a comment by the owner' \
    "headless.md must say only the owner's comment continues a run"
  assert_contains "$hl" 'finish.sh merge <N> --branch <b> --auto' \
    "the self-merge must pass --auto so the script checks the tier and human paths"
  assert_contains "$hl" 'git status --porcelain' "a headless deploy must refuse a dirty main checkout"
  merge=$(skill_step Merge)
  assert_contains "$merge" 'Approval is never inferred' "the attended merge gate lost its closing rule"
  case "$hl" in *"fourth"* | *"four moments"*) fail "headless.md adds a contact moment" ;; esac
  case "$hl" in *"gh pr merge"*) fail "headless.md names a merge path other than finish.sh" ;; esac
}

test_attended_steps_read_as_in_the_previous_release() {
  local heads
  heads=$(grep -oE '^\*\*[0-9]+\. [A-Za-z ]+|^## Step [0-9]+ — [A-Za-z ]+' "$(skill_md)" | sed 's/\*\*//; s/ *$//')
  assert_eq "$(printf '%s\n' \
    '0. Resolve' \
    '1. Worktree' \
    '2. Design' \
    '3. Checkpoint' \
    '4. Build' \
    '5. Gates' \
    '6. Review and harden' \
    '7. PR and report' \
    '## Step 8 — Merge on approval' \
    '## Step 9 — Cleanup')" "$heads" \
    "the step names changed; headless was meant to add a path, not reshape a step"

  local ask checkpoint
  ask=$(awk '
    /^- \*\*Ask contract:\*\*/ { f = 1 }
    f && /^- / && !/^- \*\*Ask contract:\*\*/ { exit }
    f { print }
  ' "$(skill_md)")
  assert_contains "$ask" "three moments" \
    "the Hard-rules Ask contract bullet was reshaped away from its three fixed moments"
  assert_contains "$ask" "ONE batched question if the ledger has open items" \
    "the Hard-rules Ask contract bullet no longer names the single batched question"
  checkpoint=$(skill_step Checkpoint)
  assert_contains "$checkpoint" "the only mid-run question" \
    "Step 3 no longer closes on it being the only mid-run question"
}

test_headless_state_lives_in_marked_comments_on_the_issue() {
  local hl hard
  hl=$(cat "$(references_dir)/headless.md") || fail "R/headless.md missing"
  [ -n "$hl" ] || fail "R/headless.md came back empty; this check would be vacuous"
  assert_contains "$hl" '<!-- issue-to-pr state=waiting step=3 tier=standard pr=12 head=<sha> issue-read=<id> pr-read=<id> -->' \
    "the state marker's exact grammar is what agent-dispatch parses"
  assert_contains "$hl" 'ends with one marker line' "every posted comment must say its marker is the last line"
  assert_contains "$hl" 'a missing cursor counts as 0' "an absent issue-read/pr-read cursor must be pinned to 0"
  assert_contains "$hl" '--add-label agent:running --remove-label agent,agent:waiting,agent:review,agent:failed' \
    "a run starts with one label edit, the same one the dispatcher makes"
  assert_contains "$hl" 'Post the state comment first' \
    "the label must move after the comment, or a dispatcher reads an old cursor"
  assert_contains "$hl" 'Nothing wakes you between turns' \
    "a headless host exits when the turn ends; a background job's notice never arrives"
  assert_contains "$hl" 'in the foreground' "pending background work must be waited for, not left behind"
  assert_contains "$hl" 're-read both threads' "the run must look for a late reply before it parks"
  assert_not_contains "$hl" 'next prompt' "the reply no longer arrives as a prompt: every run starts fresh from GitHub"
  assert_not_contains "$hl" 'comment on the PR' "state comments live on the issue, never on the PR"
  assert_contains "$hl" 'no earlier owner state comment' \
    "the self-merge policy must hold back a run on an issue with any earlier state, not just a resumed one"
  assert_contains "$hl" '| Current state |' "re-entry is one transition table; the first matching row decides"
  assert_contains "$hl" 'a change request or a question among the replies' \
    "a change request among several replies must win over a later merge word"
  assert_contains "$hl" 'no rebuild' "a failed state after the merge must not rebuild the merged work"
  assert_contains "$hl" 'step=9 pr=<pr>' "a post-merge failure must name the merged PR so a later run finds it"
  hard=$(awk '/^- \*\*Merge is gated/ { f = 1 } f && /^- / && !/^- \*\*Merge is gated/ { exit } f { print }' "$(skill_md)")
  assert_contains "$hard" 'owner reply' "the merge Hard rule must name the owner reply as the headless go-ahead"
  assert_contains "$hard" 'never self-merges' "the merge Hard rule must hold a resumed run back from self-merging"
}


# shellcheck disable=SC2016 # Markdown code spans are literal contract text.
test_headless_done_follows_verified_completion_and_allows_a_fresh_owner_queue() {
  local hl after
  hl=$(cat "$(references_dir)/headless.md")
  after=$(sed -n '/^## After Step 9/,$p' "$(references_dir)/headless.md")
  assert_contains "$after" '<!-- issue-to-pr state=done step=9 pr=<pr> -->'
  assert_contains "$after" '`after_merge` succeeds' "done requires the post-merge action to succeed"
  assert_contains "$after" 'Post the state comment first' "the label clears only after done is durable"
  assert_contains "$hl" 'strictly later than completion' "a reopened issue needs fresh owner authorization"
  assert_contains "$hl" 'Without `done`, completion is unproven' "missing worktree is not a completion receipt"
  assert_contains "$hl" 'ignoring the completed cycle' "a new queue must not resume its old merged PR"
}
