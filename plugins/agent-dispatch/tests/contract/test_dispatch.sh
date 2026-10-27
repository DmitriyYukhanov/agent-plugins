#!/usr/bin/env bash
# Contract tests for dispatch.sh. Fixtures: a fake gh serving files from $FIX, fake claude and
# codex acting out FAKE_CLI_MODE, and a test clock (date, sleep) so four hours pass in seconds.
# shellcheck disable=SC2016,SC2034,SC2088,SC2153
# SC2034: OUT/ERR/RC are read by assert_rc() in the sourced assert.sh, a file shellcheck does not
# follow from here. SC2088: the log path assertion shows a literal `~`, on purpose. SC2153: a
# sourced dispatch.sh's own $LOCK, misread as a typo of another test's unrelated local $lock.
# SC2016: notify hook bodies and nested "$BASH" -c scripts expand when they run, not here.

setup_env() { # [host] -> HOME, $FIX, PATH with the fakes, one configured repo octo/widgets
  export HOME="$TEST_TMPDIR/home" FIX="$TEST_TMPDIR/fix"
  mkdir -p "$HOME/.agent-dispatch" "$FIX" "$TEST_TMPDIR/checkout"
  REAL_SLEEP=$(command -v sleep)
  export REAL_SLEEP
  export PATH="$AD_FIXTURES/bin:$AD_FIXTURES/fake-gh:$AD_FIXTURES/fake-cli:$PATH"
  export FAKE_GH_FIX="$FIX" FAKE_CLI_LOG="$FIX/cli.log" FAKE_CLOCK="$FIX/clock"
  printf '1000\n' >"$FAKE_CLOCK"
  printf 'octo\n' >"$FIX/user"
  printf 'octo/widgets\n' >"$FIX/repo"
  printf '# path | host | auto-merge\n%s | %s | trivial\n' "$TEST_TMPDIR/checkout" "${1:-claude}" \
    >"$HOME/.agent-dispatch/repos.conf"
}

fake_intake() {
  [ "$1" = "$AD_SCRIPTS/seo_intake.py" ] || return 9
  [ "$2" = --policy ] && [ "$3" = "$HOME/.agent-dispatch/seo-incidents.json" ] || return 9
  [ "$4" = --repository ] && [ "$5" = octo/widgets ] && [ "$6" = --admit ] || return 9
  printf '4\tagent\n' >"$FIX/issues"
  printf 'agent\n' >"$FIX/labels-4"
  printf 'agent\tocto\n' >"$FIX/events-4"
  printf 'SEO_INTAKE=admitted ISSUE=4\n'
}

# shellcheck disable=SC2329 # Python functions are exported to the dispatch subprocess.
test_intake_runs_before_the_existing_owner_queue_pick() {
  setup_env
  printf '{}\n' >"$HOME/.agent-dispatch/seo-incidents.json"
  python() { fake_intake "$@"; }
  python3() { fake_intake "$@"; }
  export -f python python3 fake_intake
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_contains "$OUT" 'SEO_INTAKE=admitted ISSUE=4'
  assert_key "$OUT" ISSUE octo/widgets#4
  assert_key "$OUT" TICK 'done'
}

# shellcheck disable=SC2329 # Python functions are exported to the dispatch subprocess.
test_intake_errors_do_not_block_the_owner_queue() {
  setup_env
  open_issue 4 agent
  printf '{}\n' >"$HOME/.agent-dispatch/seo-incidents.json"
  python() { return 9; }
  python3() { return 9; }
  export -f python python3
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" SEO_INTAKE error
  assert_key "$OUT" ISSUE octo/widgets#4
  assert_key "$OUT" TICK 'done'
}

assert_gh_called_with() { assert_contains "$(cat "$FIX/gh.log" 2>/dev/null)" "gh $1" "gh was not called with: $1"; }
on_windows_host() { case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) return 0 ;; esac; return 1; }

dispatch() { # [accelerated test poll interval] -> OUT ERR RC
  if [ "$#" -gt 0 ]; then
    OUT=$("$BASH" -c 'source "$1"; POLL_SECONDS=$2; main' _ "$AD_SCRIPTS/dispatch.sh" "$1" 2>"$TEST_TMPDIR/.err")
  else
    OUT=$("$BASH" "$AD_SCRIPTS/dispatch.sh" 2>"$TEST_TMPDIR/.err")
  fi
  RC=$?
  ERR=$(cat "$TEST_TMPDIR/.err")
}

open_issue() { # n labels,csv [actor] -> an open issue, its labels, and who last applied the
  # label pick() cares about here: agent:waiting or agent:review if the issue carries one
  # (the reply path checks that one), else agent (the queue path's own check).
  local lbl
  printf '%s\t%s\n' "$1" "$2" >>"$FIX/issues"
  printf '%s\n' "$2" | tr ',' '\n' >"$FIX/labels-$1"
  case ",$2," in
    *,agent:waiting,*) lbl=agent:waiting ;;
    *,agent:review,*) lbl=agent:review ;;
    *) lbl=agent ;;
  esac
  printf '%s\t%s\n' "$lbl" "${3:-octo}" >"$FIX/events-$1"
}

comment() { # n id login [marker] -> one projected comment on thread n
  printf '%s\t%s\t%s\n' "$2" "$3" "${4:-}" >>"$FIX/comments-$1"
}

cli_log() { cat "$FIX/cli.log" 2>/dev/null; }

test_marker_is_issue_to_prs_copy() {
  cmp "$AD_SCRIPTS/marker.sh" "$AD_SCRIPTS/../../issue-to-pr/scripts/lib/marker.sh" ||
    fail "agent-dispatch's marker.sh has drifted from issue-to-pr's copy"
}

test_queue_launches_the_oldest_issue_the_owner_labelled() {
  setup_env
  open_issue 9 agent
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_rc 0
  assert_key "$OUT" ISSUE "octo/widgets#4"
  assert_key "$OUT" PICK queue
  assert_key "$OUT" TICK "done"
  assert_key "$OUT" OUTCOME agent:review
  assert_eq "claude -p --dangerously-skip-permissions --output-format stream-json --verbose /issue-to-pr:run 4 --headless --auto-merge trivial" \
    "$(cli_log)"
  assert_gh_called_with "issue edit 4 -R octo/widgets --add-label agent:running --remove-label agent,agent:waiting,agent:review,agent:failed"
  [ -e "$FIX/posted-4" ] && fail "a run that parked itself needs no dispatcher comment"
  [ -d "$HOME/.agent-dispatch/lock" ] && fail "the lock outlived the run"
  if on_windows_host; then assert_key "$OUT" LAUNCHER job; else assert_key "$OUT" LAUNCHER group; fi
}

test_an_agent_label_someone_else_applied_is_skipped() {
  setup_env
  open_issue 4 agent mallory
  printf 'agent\tocto\nagent\tmallory\n' >"$FIX/events-4"
  dispatch
  assert_key "$OUT" TICK idle
  [ -z "$(cli_log)" ] || fail "launched on a label the owner did not apply"
}

test_an_unverifiable_label_actor_is_skipped() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-events-4"
  dispatch
  assert_key "$OUT" TICK idle
}

test_live_states_are_skipped_and_a_failed_retry_is_picked() {
  setup_env
  open_issue 3 agent,agent:running
  open_issue 5 agent,agent:waiting
  open_issue 6 agent,agent:review
  open_issue 8 agent,agent:failed
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#8"
  assert_gh_called_with "issue edit 8 -R octo/widgets --add-label agent:running --remove-label agent,agent:waiting,agent:review,agent:failed"
  assert_eq "agent:review" "$(cat "$FIX/labels-8")" "the start edit cleared agent and agent:failed"
}

test_an_owner_reply_on_the_issue_goes_before_the_queue() {
  setup_env
  open_issue 2 agent
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting step=3 issue-read=100 -->'
  comment 7 102 octo
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#7"
  assert_key "$OUT" PICK reply
}

test_a_reply_on_a_parked_label_someone_else_applied_is_skipped() {
  setup_env
  open_issue 7 agent:waiting
  printf 'agent:waiting\tmallory\n' >"$FIX/events-7"
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo
  dispatch
  assert_key "$OUT" TICK idle
  [ -z "$(cli_log)" ] || fail "launched on a parked label a stranger applied, despite a valid owner reply"
}

test_r1_a_four_column_row_with_an_empty_marker_is_a_plain_reply() {
  # Real MARKER_JQ output has 4 columns (id, login, marker, body). IFS=$'\t' read collapses the
  # marker/body tab pair on a plain reply, so this pins the parameter-expansion split instead.
  setup_env
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting step=3 issue-read=100 -->'
  printf '%s\t%s\t\t%s\n' 102 octo 'looks good' >>"$FIX/comments-7"
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#7"
  assert_key "$OUT" PICK reply
}

test_an_owner_reply_on_the_pr_resumes_the_issue() {
  setup_env
  open_issue 7 agent:review
  comment 7 101 octo '<!-- issue-to-pr state=review step=7 tier=standard pr=12 head=abc issue-read=100 pr-read=200 -->'
  comment 12 200 octo
  comment 12 201 octo
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#7"
  assert_key "$OUT" PICK reply
}

test_read_marked_and_foreign_comments_are_not_replies() {
  setup_env
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo '<!-- issue-to-pr -->'
  comment 7 103 mallory
  dispatch
  assert_key "$OUT" TICK idle
}

test_a_reply_posted_while_the_run_was_parking_is_picked() {
  setup_env
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 102 octo
  comment 7 103 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#7"
}

test_replies_on_both_threads_start_one_run() {
  setup_env
  open_issue 7 agent:review
  comment 7 101 octo '<!-- issue-to-pr state=review pr=12 issue-read=100 pr-read=200 -->'
  comment 7 102 octo
  comment 12 201 octo
  dispatch
  assert_key "$OUT" TICK "done"
  assert_eq 1 "$(cli_log | grep -c .)" "one tick, one run"
}

test_a_state_comment_by_anyone_else_or_malformed_authorizes_nothing() {
  setup_env
  open_issue 7 agent:waiting
  comment 7 100 mallory '<!-- issue-to-pr state=waiting issue-read=1 -->'
  comment 7 101 octo '<!-- issue-to-pr state=bogus issue-read=1 -->'
  comment 7 102 octo '<!-- issue-to-pr state=waiting issue-read=x1 -->'
  comment 7 103 octo
  dispatch
  assert_key "$OUT" TICK idle
}

test_a_run_that_leaves_agent_running_is_failed_with_its_log_path() {
  setup_env
  open_issue 4 agent
  export FAKE_CLI_MODE=exit:0
  dispatch
  assert_rc 0
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/posted-4")" '<!-- issue-to-pr state=failed -->'
  assert_contains "$(cat "$FIX/posted-4")" '~/.agent-dispatch/logs/octo_widgets_4_20260101T000000Z.log'
  assert_eq "agent:failed" "$(cat "$FIX/labels-4")"
  [ -e "$HOME/.agent-dispatch/paused" ] && fail "a clean exit is not a CLI error"
  return 0
}

test_a_failed_run_carries_the_pr_from_a_prior_review_state() {
  # Amendment #2: reconcile reads the issue's own current state; if it names a PR, the failure
  # marker carries it too, so issue-to-pr's headless_guard can still find the run's PR.
  setup_env
  open_issue 4 agent
  comment 4 100 octo '<!-- issue-to-pr state=review step=7 tier=standard pr=12 head=abc issue-read=90 pr-read=91 -->'
  export FAKE_CLI_MODE=exit:0
  dispatch
  assert_rc 0
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/posted-4")" '<!-- issue-to-pr state=failed pr=12 -->'
}

test_a_cli_error_pauses_dispatching() {
  setup_env
  open_issue 4 agent
  export FAKE_CLI_MODE=exit:1
  dispatch
  assert_key "$OUT" PAUSED true
  [ -e "$HOME/.agent-dispatch/paused" ] || fail "paused was not created"
  assert_contains "$(cat "$FIX/posted-4")" "paused"
}

test_claude_reporting_an_error_with_exit_0_pauses_too() {
  setup_env
  open_issue 4 agent
  export FAKE_CLI_MODE=is-error
  dispatch
  assert_key "$OUT" RC 0
  assert_key "$OUT" PAUSED true
}

test_a_paused_tick_launches_nothing() {
  setup_env
  open_issue 4 agent
  : >"$HOME/.agent-dispatch/paused"
  dispatch
  assert_key "$OUT" TICK paused
  [ -z "$(cli_log)" ] || fail "launched while paused"
  assert_not_contains "$(cat "$FIX/gh.log" 2>/dev/null)" "issue edit"
}

test_a_failed_running_flip_launches_nothing() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-edit"
  dispatch
  assert_rc 1
  assert_key "$OUT" REASON flip
  [ -z "$(cli_log)" ] || fail "launched without the running label"
  [ -d "$HOME/.agent-dispatch/lock" ] || fail "an uncertain flip must keep its recovery record"
  rm "$FIX/fail-edit"
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_rc 0
  assert_eq agent:failed "$(cat "$FIX/labels-4")" "a recorded prelaunch failure must wait for owner retry"
  [ -z "$(cli_log)" ] || fail "recovery relaunched the failed attempt from its old queue label"
  printf 'agent\nagent:failed\n' >"$FIX/labels-4"
  printf 'agent\tocto\n' >>"$FIX/events-4"
  dispatch
  assert_rc 0
  assert_eq agent:review "$(cat "$FIX/labels-4")"
  assert_key "$OUT" TICK 'done'
  assert_eq 1 "$(wc -l <"$FIX/cli.log" | tr -d ' ')" "a rejected flip must launch only on retry"
}

test_a_malformed_config_line_stops_the_tick() {
  local line
  setup_env
  for line in "$TEST_TMPDIR/checkout | claude" "$TEST_TMPDIR/checkout | gpt | trivial" \
    "$TEST_TMPDIR/checkout | claude | yolo" "$TEST_TMPDIR/nowhere | claude | trivial" \
    "$TEST_TMPDIR/checkout | claude | trivial | extra"; do
    printf '# repos\n%s\n' "$line" >"$HOME/.agent-dispatch/repos.conf"
    dispatch
    assert_rc 1 "accepted: $line"
    assert_key "$OUT" REASON config
    assert_contains "$ERR" "$line"
  done
  printf '%s | claude | trivial\n' "$TEST_TMPDIR/checkout" >"$HOME/.agent-dispatch/repos.conf"
  : >"$FIX/repo"
  dispatch
  assert_rc 1
  assert_key "$OUT" REASON config "a checkout gh cannot name is a config error"
}

test_a_failed_repo_lookup_stops_the_tick_and_retries() {
  local repo
  setup_env
  mkdir -p "$TEST_TMPDIR/other-checkout"
  printf '%s | claude | trivial\n' "$TEST_TMPDIR/other-checkout" >>"$HOME/.agent-dispatch/repos.conf"
  open_issue 4 agent
  for repo in '' octo/widgets; do
    printf '%s\n' "$repo" >"$FIX/repo"
    # Keep any output, but exit nonzero as a failed gh lookup would.
    # shellcheck disable=SC2317,SC2329 # exported to the child dispatch process
    gh() { cat "$FIX/repo"; return 1; }
    export -f gh
    dispatch
    assert_rc 1
    assert_key "$OUT" REASON github
    assert_key "$OUT" TICK error
    assert_contains "$ERR" "$TEST_TMPDIR/checkout"
    [ -z "$(cli_log)" ] || fail "launched despite a failed repository lookup"
    [ -e "$HOME/.agent-dispatch/paused" ] && fail "a lookup failure must not pause dispatching"
  done
  unset -f gh
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_rc 0
  assert_key "$OUT" ISSUE "octo/widgets#4"
  assert_key "$OUT" TICK "done"
}

test_codex_runs_the_skill_through_exec_with_the_sandbox_bypassed() {
  setup_env codex
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" TICK "done"
  assert_eq "codex exec --dangerously-bypass-approvals-and-sandbox --json -C $TEST_TMPDIR/checkout \$issue-to-pr:run 4 --headless --auto-merge trivial" \
    "$(cli_log)"
}

test_jq_projections_shape_the_tsv() {
  command -v jq >/dev/null 2>&1 || { printf 'jq not installed; skipped\n'; return 0; }
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  # A Windows jq writes CRLF line endings; dispatch.sh strips \r wherever it reads a jq TSV
  # (pick's own JQ_ISSUES read, and every row() split), so these comparisons do the same. The
  # literal \r\n inside a body is MARKER_JQ's own @tsv escaping of a real line break in the
  # comment, not the platform artifact, so it is untouched by the strip.
  assert_eq "$(printf '4\tagent,agent:failed')" \
    "$(printf '%s' '[{"number":4,"labels":[{"name":"agent"},{"name":"agent:failed"}]}]' | jq -r "$JQ_ISSUES" | tr -d '\r')"
  local bs="\\" tab=$'\t' nl=$'\n' expected
  expected="7${tab}octo${tab}<!-- issue-to-pr state=waiting issue-read=6 -->${tab}which one?${bs}r${bs}n${bs}r${bs}n<!-- issue-to-pr state=waiting issue-read=6 -->${nl}8${tab}octo${tab}${tab}mit"
  assert_eq "$expected" \
    "$(printf '%s' '[{"id":7,"user":{"login":"octo"},"body":"Which one?\r\n\r\n<!-- issue-to-pr state=waiting issue-read=6 -->"},{"id":8,"user":{"login":"octo"},"body":"MIT"}]' | jq -r "$MARKER_JQ" | tr -d '\r')"
  # The events projection keeps every agent* label application (owner_approved picks the ones it
  # needs) and every rename, and nothing else; a rename has no label.
  assert_eq "$(printf 'labeled\tagent\tmallory\t2026-09-26T09:00:00Z\nlabeled\tagent:waiting\tocto\t2026-09-26T09:20:00Z\nrenamed\t\tocto\t2026-09-26T09:30:00Z')" \
    "$(printf '%s' '[{"event":"labeled","label":{"name":"agent"},"actor":{"login":"mallory"},"created_at":"2026-09-26T09:00:00Z"},{"event":"labeled","label":{"name":"bug"},"actor":{"login":"octo"},"created_at":"2026-09-26T09:10:00Z"},{"event":"labeled","label":{"name":"agent:waiting"},"actor":{"login":"octo"},"created_at":"2026-09-26T09:20:00Z"},{"event":"unlabeled","label":{"name":"agent"},"actor":{"login":"octo"},"created_at":"2026-09-26T09:25:00Z"},{"event":"renamed","actor":{"login":"octo"},"created_at":"2026-09-26T09:30:00Z","rename":{"from":"a","to":"b"}}]' | jq -r "$JQ_LABEL_EVENTS" | tr -d '\r')"
  # GraphQL edit history: the count first, then one row per version, newest first; a deleted
  # editor projects as empty, which owner_approved reads as not the owner.
  assert_eq "0" \
    "$(printf '%s' '{"data":{"repository":{"issue":{"userContentEdits":{"totalCount":0,"nodes":[]}}}}}' | jq -r "$JQ_EDITS" | tr -d '\r')"
  assert_eq "$(printf '2\n2026-09-26T11:00:00Z\tmallory\n2026-09-26T09:00:00Z\t')" \
    "$(printf '%s' '{"data":{"repository":{"issue":{"userContentEdits":{"totalCount":2,"nodes":[{"editedAt":"2026-09-26T11:00:00Z","editor":{"login":"mallory"}},{"editedAt":"2026-09-26T09:00:00Z","editor":null}]}}}}}' | jq -r "$JQ_EDITS" | tr -d '\r')"
}

wait_for() { # file -> waits up to 20 s for it to be non-empty
  local _i=0
  while [ ! -s "$1" ] && [ "$_i" -lt 100 ]; do
    "$REAL_SLEEP" 0.2
    _i=$((_i + 1))
  done
  [ -s "$1" ] || fail "$1 never appeared"
}

dead_pid() { # -> a pid that has already exited
  local p
  "$BASH" -c 'exit 0' &
  p=$!
  wait "$p"
  printf '%s' "$p"
}

dead_tick_lock() { # [log] -> the lock a tick that died left for octo/widgets#4
  local lock="$HOME/.agent-dispatch/lock"
  mkdir -p "$lock"
  printf 'octo/widgets\n' >"$lock/repo"
  printf '4\n' >"$lock/issue"
  dead_pid >"$lock/tick"
  write_boot_record "$lock"
  if [ -n "${1:-}" ]; then printf '%s\n' "$1" >"$lock/log"; fi
}

write_boot_record() { # directory -> bind controlled process records to this real boot
  (source "$AD_SCRIPTS/dispatch.sh"; boot_id >"$1/boot")
}

assert_dead() { # pid what
  local _i=0
  while kill -0 "$1" 2>/dev/null && [ "$_i" -lt 25 ]; do
    "$REAL_SLEEP" 0.2
    _i=$((_i + 1))
  done
  if kill -0 "$1" 2>/dev/null; then fail "$2 (pid $1) is still alive"; fi
}

kill_stray_run() { # safety net for a launching test: a broken stop must not strand the fake
  # CLI's real gate process (a 600s sleep) or, on Windows, the job.ps1 launcher, even when the
  # test itself fails. Chained with the runner's own EXIT trap, which this replaces.
  local leader='' child=''
  if [ -s "$FIX/hang.pids" ]; then read -r leader child <"$FIX/hang.pids"; fi
  [ -n "$leader" ] && kill -KILL "$leader" 2>/dev/null
  [ -n "$child" ] && kill -KILL "$child" 2>/dev/null
  if on_windows_host && [ -f "$HOME/.agent-dispatch/lock/run" ]; then
    taskkill //F //PID "$(cat "$HOME/.agent-dispatch/lock/run" 2>/dev/null)" >/dev/null 2>&1
  fi
  cd / 2>/dev/null
  rm -rf "$TEST_TMPDIR"
}

test_the_deadline_stops_the_run_and_fails_it() {
  local leader child start
  setup_env
  trap kill_stray_run EXIT
  notify_hook
  open_issue 4 agent
  export FAKE_CLI_MODE=hang FAKE_SLEEP_STEP=3600 FAKE_SLEEP_REAL=1
  start=$SECONDS
  dispatch 3600
  # SECONDS is bash's own real-time clock, untouched by the fake date/sleep fixtures: a stop that
  # does nothing would still "pass" once the real 600s sleep ends on its own, just 500x too slow.
  [ "$((SECONDS - start))" -lt 120 ] || fail "the tick took $((SECONDS - start))s; the stop did nothing and it waited out the real 600s sleep"
  assert_rc 0
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/posted-4")" "4-hour deadline"
  assert_contains "$(cat "$FIX/notified")" "[failed][octo/widgets][4][it ran past the 4-hour deadline.]"
  [ -e "$HOME/.agent-dispatch/paused" ] && fail "a deadline is not a CLI error"
  read -r leader child <"$FIX/hang.pids" || fail "the fake run never started"
  assert_dead "$child" "the run's gate"
  assert_dead "$leader" "the run"
}

test_a_live_ticks_lock_is_left_alone() {
  setup_env
  open_issue 4 agent
  mkdir -p "$HOME/.agent-dispatch/lock"
  printf '%s\n' "$$" >"$HOME/.agent-dispatch/lock/tick"
  write_boot_record "$HOME/.agent-dispatch/lock"
  dispatch
  assert_key "$OUT" TICK busy
  [ -f "$HOME/.agent-dispatch/lock/tick" ] || fail "a live tick's lock was touched"
  [ -z "$(cli_log)" ] || fail "launched next to a live tick"
}

test_a_dead_ticks_lock_without_a_run_is_reconciled() {
  local lock
  setup_env
  lock="$HOME/.agent-dispatch/lock"
  open_issue 4 agent:running
  dead_tick_lock "$HOME/.agent-dispatch/logs/octo_widgets_4_20260101T000000Z.log"
  : >"$FIX/issues"
  dispatch
  assert_rc 0
  assert_key "$OUT" RECOVERED "octo/widgets#4"
  assert_key "$OUT" TICK idle
  assert_contains "$(cat "$FIX/posted-4")" "stopped before the run finished"
  [ -d "$lock" ] && fail "the recovered lock was kept"
  return 0
}

test_a_dead_ticks_run_is_stopped_and_reconciled() {
  local leader child
  setup_env
  trap kill_stray_run EXIT
  open_issue 4 agent:running
  export FAKE_CLI_MODE=hang
  (
    # shellcheck source=../../scripts/dispatch.sh
    source "$AD_SCRIPTS/dispatch.sh"
    mkdir -p "$AD_HOME/logs"
    dead_tick_lock "$AD_HOME/logs/run.log"
    write_run_script "$TEST_TMPDIR/checkout" claude 4 trivial "$AD_HOME/logs/run.log"
    launch >/dev/null
  )
  wait_for "$FIX/hang.pids"
  read -r leader child <"$FIX/hang.pids"
  dispatch
  assert_rc 0
  assert_key "$OUT" RECOVERED "octo/widgets#4"
  assert_dead "$child" "the dead tick's gate"
  assert_dead "$leader" "the dead tick's run"
  assert_eq "agent:failed" "$(cat "$FIX/labels-4")"
}

test_recovery_keeps_the_lock_while_github_is_unreachable() {
  local lock
  setup_env
  lock="$HOME/.agent-dispatch/lock"
  open_issue 4 agent:running
  dead_tick_lock
  : >"$FIX/fail-labels-4"
  dispatch
  assert_rc 1
  assert_key "$OUT" REASON recover
  [ -d "$lock" ] || fail "the lock is the only record of the run; it must survive a failed reconcile"
}

test_a_failed_issue_listing_is_an_error_not_idle() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-issues"
  dispatch
  assert_rc 1
  assert_key "$OUT" REASON github
  assert_key "$OUT" TICK error
  [ -z "$(cli_log)" ] || fail "launched without a listing"
}

# F1: an edit to the title or body by anyone but the owner, after the owner's latest application
# of the label that makes the issue eligible, holds it until the owner labels it again.
labelled_at() { # n label actor time -> the issue's event history holds only that application
  printf '%s\t%s\t%s\n' "$2" "$3" "$4" >"$FIX/events-$1"
}
body_edited() { # n time login [time login]... -> the body's edit history, newest first, as the
  # userContentEdits projection prints it: totalCount, then `editedAt\teditor` rows
  local n=$1
  shift
  {
    printf '%s\n' "$(($# / 2))"
    while [ "$#" -gt 1 ]; do
      printf '%s\t%s\n' "$1" "$2"
      shift 2
    done
  } >"$FIX/graphql-$n"
}

test_a_body_a_stranger_edited_after_the_label_is_skipped() {
  setup_env
  open_issue 4 agent
  labelled_at 4 agent octo 2026-09-26T10:00:00Z
  body_edited 4 2026-09-26T11:00:00Z mallory
  dispatch
  assert_key "$OUT" TICK idle
  [ -z "$(cli_log)" ] || fail "ran a body a stranger rewrote after the owner's label"
  assert_gh_called_with "api graphql"
}

test_a_body_the_owner_edited_after_the_label_is_picked() {
  setup_env
  open_issue 4 agent
  labelled_at 4 agent octo 2026-09-26T10:00:00Z
  body_edited 4 2026-09-26T11:00:00Z octo
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#4"
}

test_a_title_a_stranger_renamed_after_the_label_is_skipped() {
  setup_env
  open_issue 4 agent
  printf 'agent\tocto\t2026-09-26T10:00:00Z\nrenamed\tmallory\t2026-09-26T11:00:00Z\n' >"$FIX/events-4"
  dispatch
  assert_key "$OUT" TICK idle
  [ -z "$(cli_log)" ] || fail "ran a title a stranger renamed after the owner's label"
}

test_edits_before_the_label_are_approved_by_it() {
  setup_env
  open_issue 4 agent
  printf 'agent\tocto\t2026-09-26T08:00:00Z\nrenamed\tmallory\t2026-09-26T09:00:00Z\nagent\tocto\t2026-09-26T10:00:00Z\n' \
    >"$FIX/events-4"
  body_edited 4 2026-09-26T09:30:00Z mallory
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#4"
}

# The reply path's content approval is the owner's latest `agent` label, not the park the run itself
# applied: an edit by someone else after it, mid-run included, holds the issue.
reply_issue_7() { # a parked issue 7 with a pending owner reply
  open_issue 7 "$1"
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo
}

test_a_reply_on_an_issue_a_stranger_edited_since_the_agent_label_is_skipped() {
  setup_env
  reply_issue_7 agent:waiting
  printf 'agent\tocto\t2026-09-26T08:00:00Z\nagent:waiting\tocto\t2026-09-26T10:00:00Z\n' >"$FIX/events-7"
  body_edited 7 2026-09-26T09:00:00Z mallory
  dispatch
  assert_key "$OUT" TICK idle "an edit while the run worked is not covered by its park"
  body_edited 7 2026-09-26T11:00:00Z mallory
  dispatch
  assert_key "$OUT" TICK idle
  rm "$FIX/graphql-7"
  printf 'agent\tocto\t2026-09-26T08:00:00Z\nrenamed\tmallory\t2026-09-26T09:00:00Z\nagent:waiting\tocto\t2026-09-26T10:00:00Z\n' \
    >"$FIX/events-7"
  dispatch
  assert_key "$OUT" TICK idle
  printf 'agent\tocto\t2026-09-26T08:00:00Z\nagent:waiting\tocto\t2026-09-26T10:00:00Z\n' >"$FIX/events-7"
  body_edited 7 2026-09-26T07:00:00Z mallory
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#7" "an edit before the agent label is covered by it"
  assert_key "$OUT" PICK reply
}

test_the_owner_relabelling_agent_re_approves_a_parked_issue() {
  setup_env
  reply_issue_7 agent,agent:waiting
  printf 'agent\tocto\t2026-09-26T08:00:00Z\nagent:waiting\tocto\t2026-09-26T10:00:00Z\nagent\tocto\t2026-09-26T12:00:00Z\n' \
    >"$FIX/events-7"
  body_edited 7 2026-09-26T09:00:00Z mallory
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#7"
  assert_key "$OUT" PICK reply
  assert_eq 1 "$(cli_log | grep -c .)" "one tick, one run: the queue path skips a parked issue"
}

test_a_parked_label_someone_else_applied_still_blocks_the_reply() {
  setup_env
  reply_issue_7 agent:waiting
  printf 'agent\tocto\t2026-09-26T08:00:00Z\nagent:waiting\tmallory\t2026-09-26T10:00:00Z\n' >"$FIX/events-7"
  dispatch
  assert_key "$OUT" TICK idle
}

test_an_unreadable_edit_history_is_skipped() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-graphql-4"
  dispatch
  assert_key "$OUT" TICK idle
  [ -z "$(cli_log)" ] || fail "ran an issue whose edits could not be checked"
}

# F7: a reply run that parks again with the cursors it started from, while the reply that started
# it is still above them, would be picked again every tick; it fails instead.
test_a_reply_run_that_parks_without_reading_the_reply_fails() {
  setup_env
  notify_hook
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo
  export FAKE_CLI_MODE=flip:agent:waiting
  dispatch
  assert_rc 0
  assert_key "$OUT" PICK reply
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/posted-7" 2>/dev/null)" "parked again without reading your reply"
  assert_contains "$(cat "$FIX/posted-7")" '<!-- issue-to-pr state=failed -->'
  assert_eq "[failed][octo/widgets][7][the run parked again without reading your reply.]" "$(cat "$FIX/notified")"
  assert_eq "agent:failed" "$(cat "$FIX/labels-7")"
  [ -e "$HOME/.agent-dispatch/paused" ] && fail "an unread reply is not a CLI error"
  return 0
}

test_a_review_run_that_parks_without_reading_the_pr_reply_fails_with_its_pr() {
  setup_env
  open_issue 7 agent:review
  comment 7 101 octo '<!-- issue-to-pr state=review step=7 pr=12 issue-read=100 pr-read=200 -->'
  comment 12 201 octo
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/posted-7" 2>/dev/null)" '<!-- issue-to-pr state=failed pr=12 -->'
  assert_eq "agent:failed" "$(cat "$FIX/labels-7")"
}

test_a_reply_run_that_moved_its_cursor_stays_parked() {
  # The run read 102 and parked at a new cursor; 104 arrived while it ran and waits for the next tick.
  setup_env
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo
  export FAKE_CLI_MODE=flip:agent:waiting \
    FAKE_CLI_COMMENTS='103\tocto\t<!-- issue-to-pr state=waiting issue-read=102 -->\n104\tocto\t\n'
  dispatch
  assert_key "$OUT" OUTCOME agent:waiting
  [ -e "$FIX/posted-7" ] && fail "a run that read the reply needs no dispatcher comment"
  assert_eq "agent:waiting" "$(cat "$FIX/labels-7")"
}

# F2: the launcher's id reaches the lock before the CLI can start; a launch without it is kept.
test_a_dead_ticks_launch_without_a_run_id_keeps_the_lock() {
  local lock
  setup_env
  lock="$HOME/.agent-dispatch/lock"
  open_issue 4 agent:running
  dead_tick_lock
  : >"$lock/launched"
  dispatch
  assert_rc 1
  assert_key "$OUT" REASON recover
  [ -d "$lock" ] || fail "the launcher may still be starting; its lock must survive"
  [ -e "$FIX/posted-4" ] && fail "reconciled a run that may still be starting"
  return 0
}

run_job() { # bash.exe script -> job.ps1's exit code
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$AD_SCRIPTS/job.ps1")" \
    "$(cygpath -w "$1")" "$(cygpath -w "$2")" </dev/null >/dev/null 2>&1
}

test_the_windows_launcher_records_its_own_pid_before_bash_starts() {
  on_windows_host || { printf 'job.ps1 only runs on Windows; skipped\n'; return 0; }
  local d="$TEST_TMPDIR/lock"
  mkdir -p "$d"
  # Query the saved native PID while Bash runs; process-list formatting is irrelevant here.
  printf 'launcher=$(cat %q)\npowershell.exe -NoProfile -Command "[Diagnostics.Process]::GetProcessById($launcher).ProcessName" > %q\n' \
    "$d/run" "$d/seen" >"$d/run.sh"
  run_job "$BASH" "$d/run.sh"
  assert_eq 0 "$?" "exit code"
  assert_eq powershell "$(tr -d '\r' <"$d/seen" | tr '[:upper:]' '[:lower:]')" "run did not name the live launcher while bash ran"
}

test_launcher_exit_codes_name_their_cause() {
  setup_env
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  mkdir -p "$LOCK"
  write_run_script "$TEST_TMPDIR/gone" claude 4 trivial "$TEST_TMPDIR/run.log"
  "$BASH" "$LOCK/run.sh"
  assert_eq 97 "$?" "exit code"
  run_cause 97 claude "$TEST_TMPDIR/run.log" "$TEST_TMPDIR/gone"
  assert_eq "the checkout $TEST_TMPDIR/gone is missing" "$CAUSE"
  assert_eq 0 "$CLIERR" "a missing checkout is not a CLI error"
  # shellcheck disable=SC2317,SC2329 # replaces the sourced dispatch.sh's own, which run_cause calls
  on_windows() { return 0; }
  run_cause 96 claude "$TEST_TMPDIR/run.log" "$TEST_TMPDIR/checkout"
  assert_eq "the Windows launcher could not start the run" "$CAUSE"
  assert_eq 2 "$CLIERR" "every launch would fail the same way: pause"
  run_cause 3 codex "$TEST_TMPDIR/run.log" "$TEST_TMPDIR/checkout"
  assert_eq "the codex CLI exited with code 3" "$CAUSE"
  assert_eq 1 "$CLIERR"
}

test_a_turn_ended_on_background_work_names_that_cause() {
  local log="$TEST_TMPDIR/run.log"
  setup_env
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  # Claude's stream: the final result, then the host stopping a task nobody waited for.
  printf '%s\n' '{"type":"system","subtype":"task_notification","task_id":"a1","status":"completed"}' \
    '{"type":"result","subtype":"success","is_error":false,"stop_reason":"end_turn"}' \
    '{"type":"system","subtype":"task_notification","task_id":"b2","status":"stopped"}' >"$log"
  run_cause 0 claude "$log" "$TEST_TMPDIR/checkout"
  assert_contains "$CAUSE" "background work was still running"
  assert_eq 0 "$CLIERR" "a run that ended too early is not a CLI error: no pause"
  # A task stopped before the end of the turn is the run's own business.
  printf '%s\n' '{"type":"system","subtype":"task_notification","task_id":"b2","status":"stopped"}' \
    '{"type":"result","subtype":"success","is_error":false,"stop_reason":"end_turn"}' >"$log"
  run_cause 0 claude "$log" "$TEST_TMPDIR/checkout"
  assert_eq "it ended without leaving a state" "$CAUSE"
}

test_a_launcher_failure_pauses_without_blaming_a_logout() {
  setup_env
  open_issue 4 agent:running
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  mkdir -p "$AD_HOME/logs"
  mkdir -p "$LOCK"
  OUT=$(reconcile octo/widgets 4 "the Windows launcher could not start the run" "$AD_HOME/logs/x.log" 2)
  assert_key "$OUT" PAUSED true
  [ -e "$HOME/.agent-dispatch/paused" ] || fail "paused was not created"
  assert_contains "$(cat "$FIX/posted-4")" "paused"
  assert_not_contains "$(cat "$FIX/posted-4")" "logged out"
}

# F3: "could not check" is never "stopped".
test_an_unreadable_process_list_is_not_a_stopped_run() {
  setup_env
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  # shellcheck disable=SC2317,SC2329 # replaces the sourced dispatch.sh's own, which gone calls
  on_windows() { return 0; }
  mkdir -p "$TEST_TMPDIR/bin"
  printf '#!/bin/sh\nexit 1\n' >"$TEST_TMPDIR/bin/tasklist"
  chmod +x "$TEST_TMPDIR/bin/tasklist"
  PATH="$TEST_TMPDIR/bin:$PATH"
  if gone 4242; then fail "a failed tasklist was read as a stopped run"; fi
  printf '#!/bin/sh\necho "INFO: No tasks are running which match the specified criteria."\n' >"$TEST_TMPDIR/bin/tasklist"
  gone 4242 || fail "tasklist's own no-match answer is a stopped run"
}

test_a_run_that_outlives_its_stop_keeps_the_lock() {
  setup_env
  trap kill_stray_run EXIT
  open_issue 4 agent
  export FAKE_CLI_MODE=hang FAKE_SLEEP_STEP=3600 FAKE_SLEEP_REAL=0.1
  # A stop that does nothing stands in for one that did not take: the tick must not block on wait.
  # shellcheck disable=SC2016 # $1 belongs to the nested shell
  OUT=$("$BASH" -c 'source "$1"; POLL_SECONDS=3600; stop_run() { :; }; main' _ "$AD_SCRIPTS/dispatch.sh" 2>"$TEST_TMPDIR/.err")
  RC=$?
  ERR=$(cat "$TEST_TMPDIR/.err")
  assert_rc 1
  assert_key "$OUT" REASON recover
  [ -d "$HOME/.agent-dispatch/lock" ] || fail "a run still alive after its stop keeps the lock"
  assert_contains "$(cat "$HOME/.agent-dispatch/lock/cause" 2>/dev/null)" "4-hour deadline" \
    "the kept lock must tell recovery why the run was stopped"
  [ -e "$FIX/posted-4" ] && fail "reconciled a run that is still alive"
  return 0
}

# A launched marker with no run id means "still starting" only briefly: job.ps1 records its pid
# before it starts bash, so a launcher silent for over a minute never ran the CLI.
test_a_dead_ticks_stale_launch_without_a_run_id_is_reconciled() {
  local lock
  setup_env
  lock="$HOME/.agent-dispatch/lock"
  open_issue 4 agent:running
  dead_tick_lock
  : >"$lock/launched"
  touch -t 202001010000 "$lock/launched"
  : >"$FIX/issues"
  dispatch
  assert_rc 0
  assert_key "$OUT" RECOVERED "octo/widgets#4"
  assert_eq "agent:failed" "$(cat "$FIX/labels-4")"
  [ -d "$lock" ] && fail "a stale launch kept the lock"
  return 0
}

test_the_launcher_exits_96_without_bash_and_passes_the_scripts_code_through() {
  on_windows_host || { printf 'job.ps1 only runs on Windows; skipped\n'; return 0; }
  mkdir -p "$TEST_TMPDIR/lock"
  printf 'exit 5\n' >"$TEST_TMPDIR/lock/run.sh"
  run_job "$TEST_TMPDIR/no-bash.exe" "$TEST_TMPDIR/lock/run.sh"
  assert_eq 96 "$?" "a bash.exe that cannot start is the launcher's failure"
  # No lock directory next to the script: job.ps1 cannot record its pid, so bash must never start.
  run_job "$BASH" "$TEST_TMPDIR/nowhere/run.sh"
  assert_eq 96 "$?" "a pid it cannot record is the launcher's failure"
  run_job "$BASH" "$TEST_TMPDIR/lock/run.sh"
  assert_eq 5 "$?" "the script's own exit code passes through"
}

test_a_strangers_edit_is_not_laundered_by_a_later_owner_edit() {
  setup_env
  open_issue 4 agent
  labelled_at 4 agent octo 2026-09-26T10:00:00Z
  body_edited 4 2026-09-26T12:00:00Z octo 2026-09-26T11:00:00Z mallory 2026-09-26T09:00:00Z octo
  dispatch
  assert_key "$OUT" TICK idle
  [ -z "$(cli_log)" ] || fail "a later owner edit laundered a stranger's edit after the label"
}

test_an_edit_history_longer_than_one_page_after_the_label_is_held() {
  local i
  setup_env
  open_issue 4 agent
  labelled_at 4 agent octo 2026-09-26T10:00:00Z
  # 51 edits, the 50 newest all the owner's and all after the label: the 51st is unread.
  { printf '51\n'; i=10; while [ "$i" -lt 60 ]; do printf '2026-09-26T11:%s:00Z\tocto\n' "$i"; i=$((i + 1)); done; } \
    >"$FIX/graphql-4"
  dispatch
  assert_key "$OUT" TICK idle "an unread edit after the approval is unverifiable"
  # The same page reaching back past the label proves the rest is older.
  printf '2026-09-26T09:00:00Z\tmallory\n' >>"$FIX/graphql-4"
  { printf '52\n'; tail -n +2 "$FIX/graphql-4"; } >"$FIX/.g" && mv "$FIX/.g" "$FIX/graphql-4"
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" ISSUE "octo/widgets#4"
}

test_an_unread_reply_fails_without_pausing_even_when_the_cli_errored() {
  setup_env
  open_issue 7 agent:waiting
  comment 7 100 octo
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo
  export FAKE_CLI_MODE=flip:agent:waiting FAKE_CLI_EXIT=1
  dispatch
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/posted-7" 2>/dev/null)" "parked again without reading your reply"
  assert_not_contains "$(cat "$FIX/posted-7")" "logged out"
  [ -e "$HOME/.agent-dispatch/paused" ] && fail "an unread reply is not a CLI error, whatever the exit code"
  return 0
}

notify_hook() { # [body] -> ~/.agent-dispatch/notify.sh: records its arguments as [a][b]..., then runs body
  printf '%s\n%s\n' 'printf "[%s]" "$@" >>"$FIX/notified"; echo >>"$FIX/notified"' "${1:-}" \
    >"$HOME/.agent-dispatch/notify.sh"
}

test_a_parked_run_tells_the_owner() {
  setup_env
  notify_hook
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_rc 0
  assert_key "$OUT" OUTCOME agent:review
  assert_key "$OUT" NOTIFY sent
  assert_eq "[review][octo/widgets][4][]" "$(cat "$FIX/notified")"
}

test_a_cli_error_tells_the_owner_the_cause_and_the_pause() {
  setup_env
  notify_hook
  open_issue 4 agent
  export FAKE_CLI_MODE=exit:1
  dispatch
  assert_key "$OUT" OUTCOME agent:failed
  assert_contains "$(cat "$FIX/notified")" "[failed][octo/widgets][4][the claude CLI exited with code 1."
  assert_contains "$(cat "$FIX/notified")" "paused until you delete ~/.agent-dispatch/paused"
}

test_a_recovered_dead_tick_tells_the_owner() {
  setup_env
  notify_hook
  open_issue 4 agent:running
  dead_tick_lock
  : >"$FIX/issues"
  dispatch
  assert_key "$OUT" RECOVERED "octo/widgets#4"
  assert_contains "$(cat "$FIX/notified")" "[failed][octo/widgets][4][the dispatcher stopped before the run finished"
}

test_a_merged_run_and_a_missing_hook_stay_silent() {
  setup_env
  notify_hook
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:
  dispatch
  assert_key "$OUT" TICK "done"
  [ -e "$FIX/notified" ] && fail "a closed issue needs no notification"
  rm -f "$HOME/.agent-dispatch/notify.sh"
  open_issue 5 agent
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" OUTCOME agent:review
  assert_not_contains "$OUT" "NOTIFY=" "no hook, nothing to report"
}

test_a_failing_hook_never_changes_the_ticks_result() {
  setup_env
  notify_hook 'printf "OUTCOME=bogus\nTICK=bogus\n"; exit 3'
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:waiting
  dispatch
  assert_rc 0
  assert_key "$OUT" OUTCOME agent:waiting
  assert_key "$OUT" NOTIFY failed
  assert_key "$OUT" NOTIFY_RC 3
  assert_not_contains "$OUT" "bogus" "the hook's output must stay out of the KEY=value lines"
  assert_eq "TICK=done" "$(printf '%s\n' "$OUT" | tail -1)"
  [ -d "$HOME/.agent-dispatch/lock" ] && fail "the lock outlived the tick"
  return 0
}

test_a_hanging_hook_is_stopped_with_its_children() {
  local child
  setup_env
  # The child stands in for a curl with no timeout: left alive, it would hold the scheduler's slot.
  # 0.5 s a fake second leaves the Windows launcher time to start before the cap.
  notify_hook '"$REAL_SLEEP" 120 & printf "%s\n" "$!" >"$FIX/hook-child"; wait'
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:review FAKE_SLEEP_REAL=0.5
  dispatch
  assert_rc 0
  assert_key "$OUT" NOTIFY timeout
  assert_key "$OUT" TICK "done"
  read -r child <"$FIX/hook-child" || fail "the hook never started its child"
  assert_dead "$child" "the hook's child"
  [ -d "$HOME/.agent-dispatch/.notify" ] && fail "the stopped hook's directory was kept"
  return 0
}

test_a_hook_that_exits_leaves_no_child_behind() {
  local child
  setup_env
  notify_hook '"$REAL_SLEEP" 120 & printf "%s\n" "$!" >"$FIX/hook-child"'
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:review
  dispatch
  assert_key "$OUT" NOTIFY sent
  read -r child <"$FIX/hook-child" || fail "the hook never started its child"
  assert_dead "$child" "the finished hook's child"
}

test_recovery_stops_a_hook_the_dead_tick_left_running() {
  local hook
  setup_env
  open_issue 4 agent:running
  (
    # shellcheck source=../../scripts/dispatch.sh
    source "$AD_SCRIPTS/dispatch.sh"
    mkdir -p "$AD_HOME/.notify"
    printf 'printf "%%s\\n" "$$" >"%s"\nexec "%s" 120\n' "$FIX/hook-pid" "$REAL_SLEEP" >"$AD_HOME/.notify/run.sh"
    launch "$AD_HOME/.notify"
  )
  wait_for "$FIX/hook-pid"
  read -r hook <"$FIX/hook-pid"
  dead_tick_lock
  : >"$FIX/issues"
  dispatch
  assert_key "$OUT" RECOVERED "octo/widgets#4"
  assert_dead "$hook" "the dead tick's hook"
  [ -d "$HOME/.agent-dispatch/.notify" ] && fail "the stopped hook's record would be signalled again"
  return 0
}

test_recovery_stops_a_hook_launcher_before_its_windows_pid_is_written() {
  on_windows_host || { printf 'job.ps1 only runs on Windows; skipped\n'; return 0; }
  local pending d
  setup_env
  trap kill_stray_run EXIT
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  HERE="$TEST_TMPDIR/launcher"
  mkdir -p "$HERE" "$AD_HOME/.notify"
  # Delay the real launcher before it publishes its Windows PID. The stopped tick must not
  # leave it able to start a hook after recovery reuses the notification directory.
  {
    printf '[IO.File]::WriteAllText("%s", "started")\n' "$(cygpath -w "$FIX/starting")"
    printf 'while (!(Test-Path -LiteralPath "%s")) { Start-Sleep -Milliseconds 20 }\n' \
      "$(cygpath -w "$FIX/release-launcher")"
    cat "$AD_SCRIPTS/job.ps1"
  } >"$HERE/job.ps1"
  d="$AD_HOME/.notify"
  printf 'exec %q 120\n' "$REAL_SLEEP" >"$d/run.sh"
  launch "$d"
  pending=$RUN_PID
  printf '%s\n' "$pending" >"$FIX/hang.pids"
  wait_for "$FIX/starting"
  [ ! -e "$d/run" ] || fail "the test launcher did not pause before PID publication"
  stop_hook
  assert_dead "$pending" "the hook launcher awaiting PID publication"
  [ -d "$d" ] && fail "the stopped launcher kept its directory"
  return 0
}

test_a_parked_state_is_found_behind_a_requeued_agent_label() {
  setup_env
  notify_hook
  # The owner labelled it `agent` again as the run parked, and gh lists that label first.
  printf 'agent\nagent:review\n' >"$FIX/labels-4"
  : >"$FIX/fail-comments-4" # settled labels do not need another comments fetch
  OUT=$("$BASH" -c 'source "$1/dispatch.sh"; reconcile octo/widgets 4 unused "" 0' _ "$AD_SCRIPTS" \
    2>"$TEST_TMPDIR/.err")
  assert_key "$OUT" OUTCOME agent
  assert_eq "[review][octo/widgets][4][]" "$(cat "$FIX/notified")"
}

test_a_hook_with_no_published_pid_keeps_its_directory() {
  setup_env
  notify_hook
  # shellcheck source=../../scripts/dispatch.sh
  source "$AD_SCRIPTS/dispatch.sh"
  mkdir -p "$AD_HOME/.notify"
  write_boot_record "$AD_HOME/.notify"
  : >"$AD_HOME/.notify/launched"
  printf 'original hook\n' >"$AD_HOME/.notify/run.sh"
  OUT=$(notify review octo/widgets 4 '')
  assert_key "$OUT" NOTIFY failed
  assert_eq 'original hook' "$(cat "$AD_HOME/.notify/run.sh")"
  [ -e "$FIX/notified" ] && fail "started another hook before the old launcher was resolved"
  return 0
}


test_done_supersedes_waiting_but_a_new_waiting_state_can_resume() {
  setup_env
  open_issue 7 agent:waiting
  comment 7 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 7 102 octo '<!-- issue-to-pr state=done step=9 pr=12 -->'
  comment 7 103 octo
  dispatch
  assert_key "$OUT" TICK idle "done must suppress replies to an old waiting state"
  comment 7 104 mallory '<!-- issue-to-pr state=waiting issue-read=100 -->'
  dispatch
  assert_key "$OUT" TICK idle "a foreign state must not supersede done"
  comment 7 105 octo '<!-- issue-to-pr state=waiting issue-read=104 -->'
  comment 7 106 octo
  dispatch
  assert_key "$OUT" PICK reply "a newer owner waiting state starts a new cycle"
}

test_done_after_launch_clears_running_but_stale_done_does_not() {
  setup_env
  open_issue 4 agent
  comment 4 100 octo '<!-- issue-to-pr state=done step=9 pr=12 -->'
  export FAKE_CLI_MODE=flip:agent:running FAKE_CLI_COMMENTS='101\tocto\t<!-- issue-to-pr state=done step=9 pr=13 -->\n'
  dispatch
  assert_key "$OUT" OUTCOME "done" "a crash after posting done must not become failed"
  assert_eq '' "$(cat "$FIX/labels-4")"
  [ ! -e "$FIX/posted-4" ] || fail "done needs no dispatcher failure comment"
  : >"$FIX/issues"
  open_issue 5 agent
  comment 5 100 octo '<!-- issue-to-pr state=done step=9 pr=12 -->'
  export FAKE_CLI_MODE=exit:0 FAKE_CLI_COMMENTS=''
  dispatch
  assert_key "$OUT" OUTCOME agent:failed "a previous cycle's done must not hide a new crash"
  assert_contains "$(cat "$FIX/posted-5")" 'state=failed pr=12'
}


test_an_incomplete_done_cannot_hide_a_run_failure() {
  setup_env
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:running FAKE_CLI_COMMENTS='101\tocto\t<!-- issue-to-pr state=done -->\n'
  dispatch
  assert_key "$OUT" OUTCOME agent:failed "only a complete done proves completion"
  assert_contains "$(cat "$FIX/posted-4")" 'state=failed'
}

test_a_running_flip_applied_before_error_is_recovered() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-after-edit-agent:running"
  dispatch
  assert_rc 1
  [ -z "$(cli_log)" ] || fail "launched after an uncertain running flip"
  [ -d "$HOME/.agent-dispatch/lock" ] || fail "lost the remotely applied running flip"
  rm "$FIX/fail-after-edit-agent:running"
  dispatch
  assert_rc 0
  assert_key "$OUT" RECOVERED octo/widgets#4
  assert_eq agent:failed "$(cat "$FIX/labels-4")"
  [ -z "$(cli_log)" ] || fail "recovery launched the uncertain run"
}

test_a_failure_comment_is_not_repeated_after_a_failed_label_edit() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-edit-agent:failed"
  dispatch
  assert_rc 1
  dispatch
  assert_rc 1
  rm "$FIX/fail-edit-agent:failed"
  dispatch
  assert_rc 0
  assert_eq 1 "$(grep -c 'state=failed' "$FIX/posted-4")" "failure POST repeated on retry"
  assert_eq agent:failed "$(cat "$FIX/labels-4")"
}

test_an_unread_reply_failure_finishes_after_a_label_error() {
  setup_env
  open_issue 7 agent:waiting
  comment 7 101 octo '<!-- issue-to-pr state=waiting step=3 issue-read=100 -->'
  comment 7 102 octo
  export FAKE_CLI_MODE=flip:agent:waiting FAKE_CLI_EXIT=3
  : >"$FIX/fail-edit-agent:failed"
  dispatch
  assert_rc 1
  rm "$FIX/fail-edit-agent:failed"
  dispatch
  assert_rc 0
  assert_eq agent:failed "$(cat "$FIX/labels-7")"
  assert_eq 1 "$(grep -c 'state=failed' "$FIX/posted-7")"
  assert_contains "$(cat "$FIX/posted-7")" 'parked again without reading your reply'
  [ -e "$HOME/.agent-dispatch/paused" ] && fail "an unread reply is not a CLI outage"
  return 0
}

test_previous_boot_ids_are_neither_checked_nor_signalled() {
  setup_env
  open_issue 4 agent:running
  dead_tick_lock
  printf '%s\n' "$$" >"$HOME/.agent-dispatch/lock/tick"
  printf '424242\n' >"$HOME/.agent-dispatch/lock/run"
  printf '111\n' >"$HOME/.agent-dispatch/lock/boot"
  : >"$FIX/issues"
  OUT=$("$BASH" -c '
    source "$1"
    boot_id() { printf "222\n"; }
    stop_run() { printf "signalled\n" >>"$FIX/signals"; }
    gone() { printf "checked\n" >>"$FIX/signals"; return 0; }
    main
  ' _ "$AD_SCRIPTS/dispatch.sh" 2>"$TEST_TMPDIR/.err")
  RC=$? ERR=$(cat "$TEST_TMPDIR/.err")
  assert_rc 0
  assert_key "$OUT" RECOVERED octo/widgets#4
  [ -e "$FIX/signals" ] && fail "used a process ID from a previous boot"
  return 0
}

test_previous_boot_hook_ids_are_never_signalled() {
  setup_env
  source "$AD_SCRIPTS/dispatch.sh"
  BOOT_ID=222
  mkdir -p "$AD_HOME/.notify"
  printf '111\n' >"$AD_HOME/.notify/boot"
  printf '424242\n' >"$AD_HOME/.notify/run"
  # shellcheck disable=SC2317,SC2329
  stop_run() { printf 'signalled\n' >>"$FIX/signals"; }
  # shellcheck disable=SC2317,SC2329
  gone() { return 0; }
  stop_hook || fail "an earlier boot cannot leave a hook alive"
  [ -e "$FIX/signals" ] && fail "signalled an earlier boot's hook ID"
  [ -d "$AD_HOME/.notify" ] && fail "kept an earlier boot's hook record"
  return 0
}

test_recovery_cannot_see_an_ownerless_lock_during_publication() {
  setup_env
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:review
  OUT=$("$BASH" -c '
    source "$1"
    mkdir() {
      command mkdir "$@" || return
      if [ "$1" = "$LOCK" ]; then (recover); fi
    }
    main
  ' _ "$AD_SCRIPTS/dispatch.sh" 2>"$TEST_TMPDIR/.err")
  RC=$? ERR=$(cat "$TEST_TMPDIR/.err")
  assert_rc 0
  assert_key "$OUT" OUTCOME agent:review
  assert_eq '' "$ERR" "recovery removed a lock before its owner record existed"
}

test_wall_clock_jumps_do_not_exhaust_the_poll_budget() {
  setup_env
  source "$AD_SCRIPTS/dispatch.sh"
  open_issue 4 agent
  PICK_I=0 PICK_N=4 PICK_WHY=queue
  read_config
  OWNER=octo
  DEADLINE_SECONDS=60 POLL_SECONDS=20
  # Keep the controlled run alive for three polls, without spawning a real worker.
  # shellcheck disable=SC2317,SC2329
  launch() { RUN_PID=424242; }
  # shellcheck disable=SC2317,SC2329
  kill() { [ ! -e "$FIX/stopped" ]; }
  # shellcheck disable=SC2317,SC2329
  stop_run() { touch "$FIX/stopped"; }
  # shellcheck disable=SC2317,SC2329
  wait() { return 0; }
  # shellcheck disable=SC2317,SC2329
  sleep() {
    printf '1000000\n' >"$FAKE_CLOCK"
    printf 'poll\n' >>"$FIX/polls"
  }
  OUT=$(run_issue)
  assert_eq 3 "$(wc -l <"$FIX/polls" | tr -d ' ')" "wall clock jump used the poll budget"
  assert_key "$OUT" TICK 'done'
}

test_publication_preserves_a_competing_lock_without_nesting() {
  setup_env
  source "$AD_SCRIPTS/dispatch.sh"
  read_config
  PICK_I=0 PICK_N=4 PICK_WHY=queue
  mkdir -p "$LOCK"
  printf 'original-owner\n' >"$LOCK/tick"
  OUT=$(run_issue)
  assert_key "$OUT" TICK busy
  assert_eq original-owner "$(cat "$LOCK/tick")"
  [ -d "$LOCK/lock" ] && fail "publication nested its candidate in the winner's lock"
  [ -n "$(find "$AD_HOME" -name '.claim.*' -print)" ] && fail "a losing candidate was kept"
  [ -z "$(cli_log)" ] || fail "a competing tick launched another run"
}

test_unknown_boot_records_are_preserved_without_signals() {
  local invalid
  setup_env
  open_issue 4 agent:running
  for invalid in '' '------------------------------------'; do
    mkdir -p "$HOME/.agent-dispatch/lock"
    printf '424242\n' >"$HOME/.agent-dispatch/lock/run"
    printf '%s\n' "$invalid" >"$HOME/.agent-dispatch/lock/boot"
    OUT=$("$BASH" -c '
      source "$1"
      boot_id() { printf "222\n"; }
      stop_run() { printf "signalled\n" >>"$FIX/signals"; }
      gone() { return 0; }
      main
    ' _ "$AD_SCRIPTS/dispatch.sh" 2>"$TEST_TMPDIR/.err")
    RC=$? ERR=$(cat "$TEST_TMPDIR/.err")
    assert_rc 1
    assert_key "$OUT" REASON recover
    [ -e "$FIX/signals" ] && fail "an unknown boot authorized a signal"
    [ -d "$HOME/.agent-dispatch/lock" ] || fail "unknown process records were discarded"
  done
}

test_fresh_done_clears_a_failure_label_applied_before_error() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-after-edit-agent:failed"
  dispatch
  assert_rc 1
  assert_eq agent:failed "$(cat "$FIX/labels-4")"
  rm "$FIX/fail-after-edit-agent:failed"
  comment 4 2000 octo '<!-- issue-to-pr state=done step=9 tier=standard pr=12 issue-read=1900 pr-read=1800 -->'
  dispatch
  assert_rc 0
  assert_key "$OUT" OUTCOME 'done'
  [ -s "$FIX/labels-4" ] && fail "a fresh completion retained the dispatcher's failure label"
  assert_eq 1 "$(grep -c 'state=failed' "$FIX/posted-4")" "completion reposted failure"
}

test_an_unrelated_cli_failed_state_does_not_replace_the_dispatcher_comment() {
  setup_env
  open_issue 4 agent
  export FAKE_CLI_MODE=flip:agent:running FAKE_CLI_COMMENTS='101\tocto\t<!-- issue-to-pr state=failed step=3 -->\n'
  : >"$FIX/fail-comment"
  dispatch
  assert_rc 1
  [ -e "$FIX/posted-4" ] && fail "a rejected comment was posted"
  rm "$FIX/fail-comment"
  dispatch
  assert_rc 0
  [ -s "$FIX/posted-4" ] || fail "another failed state suppressed the dispatcher diagnostic"
  assert_eq 1 "$(grep -c 'state=failed' "$FIX/posted-4")"
  assert_eq agent:failed "$(cat "$FIX/labels-4")"
}

test_a_running_flip_with_only_removals_applied_is_reconciled() {
  setup_env
  open_issue 4 agent
  : >"$FIX/fail-remove-only-agent:running"
  dispatch
  assert_rc 1
  [ -s "$FIX/labels-4" ] && fail "fixture did not apply just the removals"
  [ -z "$(cli_log)" ] || fail "launched after a partial running flip"
  rm "$FIX/fail-remove-only-agent:running"
  dispatch
  assert_rc 0
  assert_key "$OUT" RECOVERED octo/widgets#4
  assert_eq agent:failed "$(cat "$FIX/labels-4")" "partial flip lost the issue"
  [ -s "$FIX/posted-4" ] || fail "partial flip lost its diagnostic"
  [ -z "$(cli_log)" ] || fail "recovery renewed approval after a partial flip"
}

test_rejected_reply_flips_clear_parked_labels_before_owner_retry() {
  local base_tmp="$TEST_TMPDIR" base_path=$PATH state
  for state in waiting review; do
    TEST_TMPDIR="$base_tmp/$state"
    PATH=$base_path
    mkdir -p "$TEST_TMPDIR"
    setup_env
    open_issue 4 "agent:$state"
    comment 4 101 octo "<!-- issue-to-pr state=$state issue-read=100 -->"
    comment 4 102 octo
    : >"$FIX/fail-edit"
    dispatch
    assert_rc 1
    rm "$FIX/fail-edit"
    dispatch
    assert_rc 0
    assert_eq agent:failed "$(cat "$FIX/labels-4")" "recovery left a parked $state label"
    [ -z "$(cli_log)" ] || fail "recovery launched without owner retry"
    printf 'agent\nagent:failed\n' >"$FIX/labels-4"
    printf 'agent\tocto\n' >>"$FIX/events-4"
    export FAKE_CLI_MODE=flip:agent:review
    dispatch
    assert_rc 0
    assert_eq agent:review "$(cat "$FIX/labels-4")"
    assert_eq 1 "$(wc -l <"$FIX/cli.log" | tr -d ' ')" "owner retry must start one run"
  done
  TEST_TMPDIR=$base_tmp
}

test_done_clears_parked_labels_after_a_rejected_reply_flip() {
  setup_env
  open_issue 4 agent:waiting
  comment 4 101 octo '<!-- issue-to-pr state=waiting issue-read=100 -->'
  comment 4 102 octo
  : >"$FIX/fail-edit"
  dispatch
  assert_rc 1
  rm "$FIX/fail-edit"
  comment 4 2000 octo '<!-- issue-to-pr state=done step=9 pr=12 -->'
  dispatch
  assert_rc 0
  assert_key "$OUT" OUTCOME 'done'
  [ -s "$FIX/labels-4" ] && fail "completion retained the parked label"
  [ -z "$(cli_log)" ] || fail "completion launched another run"
}

test_a_tick_interrupted_during_the_running_flip_keeps_failure_intent() {
  setup_env
  open_issue 4 agent
  OUT=$("$BASH" -c '
    source "$1"
    gh() {
      case "$*" in "issue edit "*"--add-label agent:running"*)
        : >"$FIX/labels-4"
        exit 47 # removal applied, dispatcher stopped before the request returned
        ;;
      esac
      command gh "$@"
    }
    main
  ' _ "$AD_SCRIPTS/dispatch.sh" 2>"$TEST_TMPDIR/.err")
  RC=$? ERR=$(cat "$TEST_TMPDIR/.err")
  assert_rc 47
  [ -s "$FIX/labels-4" ] && fail "the interrupted edit did not remove queue labels"
  dispatch
  assert_rc 0
  assert_eq agent:failed "$(cat "$FIX/labels-4")" "interruption lost the approved issue"
  [ -s "$FIX/posted-4" ] || fail "interruption lost its diagnostic"
  [ -z "$(cli_log)" ] || fail "recovery launched without renewed owner approval"
}

test_failure_after_launch_preserves_a_fresh_owner_queue_label() {
  setup_env
  open_issue 4 agent,agent:running
  source "$AD_SCRIPTS/dispatch.sh"
  mkdir -p "$LOCK"
  : >"$LOCK/launched"
  OUT=$(reconcile octo/widgets 4 stopped "$AD_HOME/logs/run.log" 0)
  assert_eq $'agent\nagent:failed' "$(cat "$FIX/labels-4")" "a fresh owner retry label was discarded"
}
