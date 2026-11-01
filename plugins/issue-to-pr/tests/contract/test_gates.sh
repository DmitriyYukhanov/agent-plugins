#!/usr/bin/env bash

gates_repo() { # cwd moves into a fresh repo checked out on feat/issue-6-x
  REPO=$(init_repo "$TEST_TMPDIR/gr")
  git -C "$REPO" switch -qc feat/issue-6-x
  cd "$REPO" || fail "could not enter the test repo"
}

test_gates_all_green_leaves_a_receipt_bound_to_head() {
  gates_repo
  run_script gates.sh typecheck true test true
  assert_rc 0
  assert_key "$OUT" GATE_TYPECHECK_EXIT 0
  assert_key "$OUT" GATE_TEST_EXIT 0
  assert_contains "$(cat "$(receipt_file "$REPO" feat/issue-6-x)")" "$(git -C "$REPO" rev-parse HEAD)"
}

test_gates_stop_at_the_first_red_gate_with_its_tail_and_no_receipt() {
  gates_repo
  run_script gates.sh boom 'echo boomtext; exit 7' never true
  assert_rc 1
  assert_key "$OUT" GATE_BOOM_EXIT 7
  assert_not_contains "$OUT" GATE_NEVER_EXIT
  assert_contains "$ERR" boomtext
  [ ! -e "$(receipt_file "$REPO" feat/issue-6-x)" ] || fail "a red gate left a receipt"
}

test_gates_receipt_names_the_sanitized_key_so_a_gate_name_cannot_forge_the_test_gate() {
  gates_repo
  run_script gates.sh 'smoke,test' true
  assert_rc 0
  assert_contains "$(cat "$(receipt_file "$REPO" feat/issue-6-x)")" '"gates":"smoke_test"' \
    "a comma in the receipt would read as a second entry, and the merge accepts one named test"
}

test_gates_refuse_an_empty_command_before_running_anything() {
  gates_repo
  run_script gates.sh test true typecheck ' '
  assert_rc 4
  assert_not_contains "$OUT" GATE_TEST_EXIT
  [ ! -e "$(receipt_file "$REPO" feat/issue-6-x)" ] ||
    fail "bash -c on nothing exits 0, and that receipt would let the merge through"
}

test_gates_refuse_a_variable_name_passed_instead_of_the_command() {
  gates_repo
  # shellcheck disable=SC2016  # not expanding is the mistake this test is about
  run_script gates.sh test '$test_cmd'
  assert_rc 4
  [ ! -e "$(receipt_file "$REPO" feat/issue-6-x)" ] ||
    fail "bash -c on a bare variable name runs nothing and exits 0: a receipt the merge would accept"
}

test_gates_refuse_an_odd_argument_count() {
  gates_repo
  run_script gates.sh test true
  assert_rc 0
  local previous
  previous=$(cat "$(receipt_file "$REPO" feat/issue-6-x)")
  run_script gates.sh test true stray
  assert_rc 4
  assert_not_contains "$OUT" GATE_TEST_EXIT
  assert_eq "$previous" "$(cat "$(receipt_file "$REPO" feat/issue-6-x)")"
}

test_gates_refuse_a_detached_head() {
  gates_repo
  git -C "$REPO" checkout -q --detach
  run_script gates.sh test true
  assert_rc 4
  [ ! -e "$(run_dir_of "$REPO" HEAD)" ] || fail "a detached checkout wrote run-HEAD/, which no merge looks under"
}

gates_worktree() { # name -> cwd moves into a worktree of REPO on feat/issue-6-x, set as WT
  REPO=$(init_repo "$TEST_TMPDIR/$1")
  WT="$REPO-worktrees/issue-6"
  git -C "$REPO" worktree add -q "$WT" -b feat/issue-6-x main
  cd "$WT" || fail "could not enter the worktree"
}

test_gates_log_lands_in_shared_metadata_and_nothing_in_the_worktree() {
  local repo wt
  gates_worktree repo
  repo=$REPO wt=$WT
  run_script gates.sh hello 'echo hi-there'
  assert_rc 0
  [ ! -e "$wt/.claude" ] || fail "a gate run left state inside the worktree, which git worktree remove then refuses"
  assert_contains "$(cat "$(run_dir_of "$repo" feat/issue-6-x)"/logs/hello.log)" hi-there
  [ ! -e "$repo/.claude" ] || fail "a gate run created source-tree state"
}

test_gates_run_from_a_relocated_plugin_path_with_spaces() {
  # An installed plugin lives outside the project; neither host's environment is required.
  mkdir -p "$TEST_TMPDIR/plugin cache"
  cp -R "$ITP_SCRIPTS/.." "$TEST_TMPDIR/plugin cache/issue-to-pr"
  ITP_SCRIPTS="$TEST_TMPDIR/plugin cache/issue-to-pr/scripts"
  gates_worktree "repo with spaces"
  run_script gates.sh hello 'echo hi-there'
  assert_rc 0
  assert_contains "$(cat "$(run_dir_of "$REPO" feat/issue-6-x)"/logs/hello.log)" hi-there
}

test_gates_say_so_when_the_receipt_cannot_be_written() {
  gates_repo
  mkdir -p "$(receipt_file "$REPO" feat/issue-6-x)"
  run_script gates.sh test true
  assert_rc 0
  assert_not_contains "$OUT" GATES_RECEIPT
  assert_contains "$ERR" "the merge will refuse this head"
}

test_gates_refuse_a_name_that_sanitizes_to_nothing() {
  gates_repo
  run_script gates.sh '***' true
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON unnamed-gate
  [ ! -e "$(receipt_file "$REPO" feat/issue-6-x)" ] ||
    fail "the gate would have run and then been missing from the receipt the merge reads"
}


test_gates_replace_the_previous_log_for_the_same_gate() {
  gates_repo
  run_script gates.sh 'Unit tests' 'echo previous-output'
  assert_rc 0
  local first second count
  first=$(printf '%s\n' "$OUT" | sed -n 's/^GATE_UNIT_TESTS_LOG=//p')
  run_script gates.sh 'Unit tests' 'echo latest-output'
  assert_rc 0
  second=$(printf '%s\n' "$OUT" | sed -n 's/^GATE_UNIT_TESTS_LOG=//p')
  assert_eq "$first" "$second" "same gate must replace its previous log"
  assert_eq unit_tests.log "$(basename "$second")"
  assert_eq latest-output "$(cat "$second")"
  count=$(find "$(dirname "$second")" -type f | wc -l | tr -d ' ')
  assert_eq 1 "$count"
}


test_gates_refuse_redirected_logs_before_running_the_gate() {
  gates_repo
  local run logs outside
  run=$(run_dir_of "$REPO" feat/issue-6-x)
  logs="$run/logs" outside="$TEST_TMPDIR/outside"
  mkdir -p "$run" "$outside"
  printf 'keep\n' >"$outside/test.log"
  MSYS=winsymlinks:nativestrict ln -s "$outside" "$logs" || fail "native symlink fixture unavailable"
  run_script gates.sh test 'echo overwritten'
  assert_rc 2
  assert_key "$OUT" STOP_REASON unsafe-state-dir
  assert_eq keep "$(cat "$outside/test.log")"
}

test_gates_refuse_a_redirected_log_file_before_running_the_gate() {
  gates_repo
  local logs outside
  logs="$(run_dir_of "$REPO" feat/issue-6-x)/logs" outside="$TEST_TMPDIR/outside"
  mkdir -p "$logs" "$outside"
  printf 'keep\n' >"$outside/test.log"
  MSYS=winsymlinks:nativestrict ln -s "$outside/test.log" "$logs/test.log" || fail "native symlink fixture unavailable"
  run_script gates.sh test 'echo overwritten'
  assert_rc 2
  assert_key "$OUT" STOP_REASON unsafe-state-dir
  assert_eq keep "$(cat "$outside/test.log")"
}


test_gates_a_failed_rerun_revokes_the_previous_green_receipt() {
  gates_repo
  run_script gates.sh test true
  assert_rc 0
  [ -f "$(receipt_file "$REPO" feat/issue-6-x)" ] || fail "green gate did not create a receipt"
  run_script gates.sh test 'echo latest-failure; exit 7'
  assert_rc 1
  assert_key "$OUT" GATE_TEST_EXIT 7
  assert_contains "$ERR" latest-failure
  [ ! -e "$(receipt_file "$REPO" feat/issue-6-x)" ] || fail "failed rerun kept the prior green receipt"
}
