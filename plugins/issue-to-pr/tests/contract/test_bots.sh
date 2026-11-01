#!/usr/bin/env bash

bots_setup() { # -> cwd in a fresh repo, fake gh and a fake clock at 0, empty fixtures
  REPO=$(init_repo "$(mktemp -d "$TEST_TMPDIR/repo.XXXXXX")")
  cd "$REPO" || fail "could not enter $REPO"
  use_fake_gh happy
  export FAKE_GH_FIX="$TEST_TMPDIR/fix"
  rm -rf "$FAKE_GH_FIX" && mkdir -p "$FAKE_GH_FIX"
  FAKE_CLOCK_DIR=$(cd "${FAKE_GH_DIR:?}/../fake-clock" && pwd)
  export FAKE_CLOCK_DIR PATH="$FAKE_CLOCK_DIR:$PATH"
  export FAKE_NOW="$TEST_TMPDIR/now"
  printf '0\n' >"$FAKE_NOW"
  export ITP_BOTS_SLICE=100000 # one call per wait; slicing has its own test
}

fx() { printf '%s\n' "$2" >"$FAKE_GH_FIX/$1"; } # fixture[@t] body
clock() { cat "$FAKE_NOW"; }
posted() { grep -c -- "$1" "$FAKE_GH_LOG" || true; }
waits() { # the model re-runs the call while it says WAIT_MORE
  local n=0
  run_script bots.sh wait 12 "$@"
  while [ "$RC" = 0 ] && [ "$n" -lt 40 ] && printf '%s' "$OUT" | grep -qx 'WAIT_MORE=true'; do
    n=$((n + 1))
    run_script bots.sh wait 12 "$@"
  done
}

test_no_bots_waits_out_the_grace_window_and_posts_nothing() {
  bots_setup
  waits
  assert_rc 0
  assert_key "$OUT" BOTS none
  [ "$(clock)" -ge 240 ] || fail "gave up before the grace window: $(clock)"
  assert_eq 0 "$(posted '-f body=')" "posted a comment with no bot to ask"
}

test_coderabbit_is_waited_on_until_its_status_says_completed() {
  bots_setup
  fx status@0 $'pending\tReview queued'
  fx status@60 $'pending\tReview in progress'
  fx status@300 $'success\tReview completed'
  waits
  assert_key "$OUT" BOT_coderabbit "Review completed"
  [ "$(clock)" -ge 300 ] || fail "left before the review finished: $(clock)"
  bots_setup
  fx status@0 $'pending\t'
  fx status@400 $'success\tReview completed'
  waits
  assert_key "$OUT" BOT_coderabbit "Review completed"
}

test_a_limit_a_skip_or_a_pause_is_reported_at_once_and_never_worked_around() {
  local st
  for st in 'Review rate limited' 'Review skipped: draft pull request' 'Review paused'; do
    bots_setup
    fx status@0 "success	$st"
    waits
    assert_key "$OUT" BOT_coderabbit "$st"
    assert_eq 0 "$(clock)" "waited on a final state: $st"
    assert_eq 0 "$(posted '-f body=')" "asked CodeRabbit again on the owner's behalf"
  done
}

test_a_review_that_never_ends_times_out_inside_the_budget() {
  bots_setup
  fx status $'pending\tReview in progress'
  waits
  assert_key "$OUT" BOT_coderabbit timeout
  if [ "$(clock)" -lt 1200 ] || [ "$(clock)" -ge 1300 ]; then fail "budget is 20 minutes, ran to $(clock)"; fi
}

test_one_call_fits_a_two_minute_tool_call_and_the_next_keeps_the_budget() {
  bots_setup
  fx status $'pending\tReview in progress'
  ITP_BOTS_SLICE=90 run_script bots.sh wait 12 --request-codex
  assert_key "$OUT" WAIT_MORE true
  [ "$(clock)" -le 100 ] || fail "one call ran $(clock) seconds"
  waits --request-codex
  [ "$(clock)" -lt 1300 ] || fail "a later call restarted the budget: $(clock)"
  assert_eq 1 "$(posted '@codex review')" "re-asked Codex on a later call"
}

test_codex_is_asked_once_with_the_marker_and_done_on_a_review_of_the_head() {
  bots_setup
  fx reactions@10 eyes
  fx reviews@120 77
  waits --request-codex
  assert_key "$OUT" BOT_codex "done"
  assert_eq 1 "$(posted '@codex review')"
  assert_contains "$(gh_log)" "<!-- issue-to-pr -->" "the request carries no marker, so headless reads it as the owner"
}

test_codex_answers_decide_its_outcome() {
  local c
  for c in "Codex Review: Didn't find any major issues.|done" \
    'To use Codex here, create an environment for this repo.|no-review' '+1 reaction|done' 'silence|no-review' \
    'Keep your eyes on it, +1 to that.|no-review'; do
    bots_setup
    case "${c%%|*}" in
      '+1 reaction') fx reactions@20 +1 ;;
      silence) : ;;
      *) fx comments-12@30 "${c%%|*}" ;;
    esac
    waits --request-codex
    assert_key "$OUT" BOT_codex "${c#*|}"
  done
}

test_github_unreadable_three_times_stops() {
  local f
  for f in status reviews; do
    bots_setup
    : >"$FAKE_GH_FIX/fail-$f"
    waits --request-codex
    assert_rc 2
    assert_key "$OUT" STOP_REASON bots-unreadable
  done
}

test_threads_lists_the_open_threads() {
  bots_setup
  fx threads $'T1\tcoderabbitai\ta.sh\thttps://x/1\nT2\tcoderabbitai\tb.sh\thttps://x/2'
  run_script bots.sh threads 12
  assert_rc 0
  assert_contains "$OUT" "THREAD=T2	coderabbitai	b.sh	https://x/2"
}

test_reply_answers_then_resolves_and_never_resolves_unanswered() {
  bots_setup
  printf 'Fixed in abc123.\n' >"$TEST_TMPDIR/body"
  run_script bots.sh reply T1 --body-file "$TEST_TMPDIR/body"
  assert_rc 0
  assert_gh_called "addPullRequestReviewThreadReply"
  assert_gh_called "resolveReviewThread"
  assert_contains "$(gh_log)" "<!-- issue-to-pr -->" "the reply carries no marker"
  bots_setup
  : >"$FAKE_GH_FIX/fail-reply"
  run_script bots.sh reply T1 --body-file "$TEST_TMPDIR/body"
  assert_rc 2
  assert_key "$OUT" STOP_REASON reply-failed
  assert_gh_not_called "resolveReviewThread" "resolved a thread nobody answered"
}

test_bad_calls_degrade() {
  bots_setup
  run_script bots.sh wait
  assert_rc 4
  run_script bots.sh wait 12 --bogus
  assert_rc 4
  run_script bots.sh nope 12
  assert_rc 4
  run_script bots.sh reply T1
  assert_rc 4
}


test_wait_refuses_a_symlinked_budget_file() {
  bots_setup
  local state outside
  state="$(run_dir_of "$REPO" feat/issue-6-x)/bots" outside="$TEST_TMPDIR/outside"
  mkdir -p "$(dirname "$state")"
  printf 'keep\n' >"$outside"
  MSYS=winsymlinks:nativestrict ln -s "$outside" "$state" || fail "native symlink fixture unavailable"
  fx status@0 $'success\tReview completed'
  run_script bots.sh wait 12
  assert_rc 2
  assert_key "$OUT" STOP_REASON unsafe-state-dir
  assert_eq keep "$(cat "$outside")"
}
