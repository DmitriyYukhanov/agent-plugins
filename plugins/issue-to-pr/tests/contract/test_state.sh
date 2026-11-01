#!/usr/bin/env bash

state_repo() {
  REPO=$(init_repo "$TEST_TMPDIR/state repo")
  REPO=$(git -C "$REPO" rev-parse --show-toplevel)
  git -C "$REPO" switch -qc feat/issue-6-x
  cd "$REPO" || fail "could not enter repo"
}

write_run_artifacts() {
  local d=$1
  mkdir -p "$d/plans" "$d/logs"
  printf 'plan\n' >"$d/plans/design.md"
  printf 'decision\n' >"$d/ledger.md"
  printf 'resume\n' >"$d/resume.md"
  printf 'log\n' >"$d/logs/test.log"
  printf '{}\n' >"$d/receipt.json"
  printf 'body\n' >"$d/pr-body.md"
}

assert_only_project_files_stage() {
  local repo=$1
  printf 'change\n' >>"$repo/README.md"
  assert_eq ' M README.md' "$(git -C "$repo" status --short --untracked-files=all)"
  # Deliberately broad staging in a disposable repo proves ignores protect normal commits.
  git -C "$repo" add --all
  assert_eq README.md "$(git -C "$repo" diff --cached --name-only)"
}

test_state_fresh_run_is_ignored_before_any_gate() {
  state_repo
  run_script state.sh
  assert_rc 0
  local expected
  expected="$(git rev-parse --path-format=absolute --git-common-dir)/issue-to-pr/run-feat-sissue--6--x"
  assert_key "$OUT" RUN_DIR "$expected"
  [ -d "$expected" ] || fail "metadata run directory missing"
  [ ! -e "$REPO/.claude" ] || fail "new run created source-tree state"
  [ ! -e "$expected/.gitignore" ] || fail "metadata run created an unnecessary ignore file"
  write_run_artifacts "$(run_dir_of "$REPO" feat/issue-6-x)"
  assert_only_project_files_stage "$REPO"
}

test_state_worktree_run_protects_both_checkouts_before_gates() {
  state_repo
  git -C "$REPO" switch -q main
  local wt="$TEST_TMPDIR/linked tree"
  git -C "$REPO" worktree add -q "$wt" feat/issue-6-x
  cd "$wt" || fail "could not enter worktree"
  run_script state.sh
  assert_rc 0
  assert_key "$OUT" RUN_DIR "$(run_dir_of "$REPO" feat/issue-6-x)"
  write_run_artifacts "$(run_dir_of "$REPO" feat/issue-6-x)"
  [ ! -e "$wt/.claude" ] || fail "bootstrap wrote into the worktree"
  assert_only_project_files_stage "$REPO"
  assert_only_project_files_stage "$wt"
}

test_state_keeps_custom_ignore_and_versioned_configuration() {
  state_repo
  local state="$REPO/.claude/issue-to-pr" original
  mkdir -p "$state"
  printf '# custom rules\n!run-*/' >"$state/.gitignore"
  original=$(cat "$state/.gitignore")
  printf 'config\n' >"$state/config.md"
  printf 'instructions\n' >"$REPO/.claude/CLAUDE.md"
  git add .claude/issue-to-pr/.gitignore .claude/issue-to-pr/config.md .claude/CLAUDE.md
  git commit -qm config
  run_script state.sh
  assert_rc 0
  write_run_artifacts "$(run_dir_of "$REPO" feat/issue-6-x)"
  run_script state.sh
  assert_rc 0
  assert_eq "$original" "$(cat "$state/.gitignore")" "custom ignore changed"
  assert_eq '' "$(git status --short --untracked-files=all)"
  printf 'edit\n' >>"$state/config.md"
  printf 'edit\n' >>"$REPO/.claude/CLAUDE.md"
  git add --all
  assert_eq $'.claude/CLAUDE.md\n.claude/issue-to-pr/config.md' "$(git diff --cached --name-only)"
}

test_state_preserves_an_empty_tracked_ignore() {
  state_repo
  mkdir -p .claude/issue-to-pr
  : >.claude/issue-to-pr/.gitignore
  git add .claude/issue-to-pr/.gitignore
  git commit -qm ignore
  run_script state.sh
  assert_rc 0
  write_run_artifacts "$(run_dir_of "$REPO" feat/issue-6-x)"
  assert_eq '' "$(git status --short --untracked-files=all)"
}

test_state_refuses_tracked_run_files_without_touching_them() {
  state_repo
  local d
  d=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
  mkdir -p "$d"
  printf 'keep\n' >"$d/ledger.md"
  git add .claude/issue-to-pr
  git commit -qm ledger
  run_script state.sh
  assert_rc 2
  assert_key "$OUT" STOP_REASON tracked-run-state
  assert_contains "$ERR" '.claude/issue-to-pr/run-feat-sissue--6--x/ledger.md'
  assert_eq keep "$(cat "$d/ledger.md")"
  assert_eq '' "$(git status --short)"
}

test_state_reports_legacy_tracked_candidates_without_removing_them() {
  state_repo
  mkdir -p .claude/issue-to-pr
  printf 'legacy\n' >.claude/issue-to-pr/ledger-5.md
  git add .claude/issue-to-pr/ledger-5.md
  git commit -qm legacy
  run_script state.sh
  assert_rc 0
  assert_contains "$ERR" '.claude/issue-to-pr/ledger-5.md'
  assert_eq legacy "$(cat .claude/issue-to-pr/ledger-5.md)"
  assert_eq '' "$(git status --short --untracked-files=all)"
}

test_state_refuses_detached_head() {
  state_repo
  git checkout -q --detach
  run_script state.sh
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON detached-head
  [ ! -e .claude ] || fail "detached bootstrap wrote state"
}

test_state_repairs_existing_run_ignore_once() {
  state_repo
  local d first
  d=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
  mkdir -p "$d"
  printf '# custom parent\n!run-*/\n' >"$REPO/.claude/issue-to-pr/.gitignore"
  git add .claude/issue-to-pr/.gitignore
  git commit -qm ignore
  printf '# existing rule\n!ledger.md' >"$d/.gitignore"
  run_script state.sh
  assert_rc 0
  first=$(cat "$d/.gitignore")
  assert_contains "$first" '!ledger.md'
  write_run_artifacts "$d"
  run_script state.sh
  assert_rc 0
  assert_eq "$first" "$(cat "$d/.gitignore")" "initialization is not idempotent"
  assert_eq '' "$(git status --short --untracked-files=all)"
}

test_state_refuses_run_files_tracked_only_in_worktree() {
  state_repo
  git switch -q main
  local wt="$TEST_TMPDIR/linked tree" rel='.claude/issue-to-pr/run-feat-sissue--6--x'
  git worktree add -q "$wt" feat/issue-6-x
  cd "$wt" || fail "could not enter worktree"
  mkdir -p "$rel"
  printf 'keep\n' >"$rel/ledger.md"
  git add "$rel/ledger.md"
  git commit -qm ledger
  run_script state.sh
  assert_rc 2
  assert_key "$OUT" STOP_REASON tracked-run-state
  assert_eq keep "$(cat "$rel/ledger.md")"
  [ ! -e "$REPO/.claude" ] || fail "bootstrap wrote state before checking the worktree index"
}

test_state_refuses_symlinked_state_ancestors_before_writing() {
  state_repo
  local rel link outside n=0
  for rel in .claude .claude/issue-to-pr; do
    n=$((n + 1))
    outside="$TEST_TMPDIR/outside-$n" link="$REPO/$rel"
    mkdir -p "$outside" "$(dirname "$link")"
    MSYS=winsymlinks:nativestrict ln -s "$outside" "$link" || fail "native symlink fixture unavailable"
    [ -L "$link" ] || fail "the symlink fixture is not a symlink"
    printf 'keep\n' >"$outside/sentinel"
    run_script state.sh
    assert_rc 2
    assert_key "$OUT" STOP_REASON unsafe-state-dir
    assert_eq sentinel "$(ls -A "$outside")" "bootstrap wrote through the symlink"
    assert_eq keep "$(cat "$outside/sentinel")"
    rm "$link"
  done
}

test_state_reuses_legacy_active_run_and_preserves_config() {
  state_repo
  local legacy="$REPO/.claude/issue-to-pr/run-feat-sissue--6--x"
  mkdir -p "$legacy"
  printf 'existing receipt\n' >"$legacy/receipt.json"
  printf 'human_paths: protected/**\n' >"$REPO/.claude/issue-to-pr/config.md"
  run_script state.sh
  assert_rc 0
  assert_key "$OUT" RUN_DIR "$legacy"
  assert_eq 'existing receipt' "$(cat "$legacy/receipt.json")"
  assert_eq 'human_paths: protected/**' "$(cat "$REPO/.claude/issue-to-pr/config.md")"
  [ ! -e "$REPO/.git/issue-to-pr" ] || fail "legacy run was duplicated"
}

test_state_bare_clone_worktrees_share_git_metadata() {
  local seed bare one two common
  seed=$(init_repo "$TEST_TMPDIR/seed")
  bare="$TEST_TMPDIR/bare.git" one="$TEST_TMPDIR/one" two="$TEST_TMPDIR/two"
  git clone -q --bare "$seed" "$bare"
  git -C "$bare" worktree add -qb feat/one "$one" main
  git -C "$bare" worktree add -qb feat/two "$two" main
  common=$(git -C "$one" rev-parse --path-format=absolute --git-common-dir)
  cd "$one" || fail "could not enter first worktree"
  run_script state.sh
  assert_rc 0
  assert_key "$OUT" RUN_DIR "$common/issue-to-pr/run-feat-sone"
  cd "$two" || fail "could not enter second worktree"
  run_script state.sh
  assert_rc 0
  assert_key "$OUT" RUN_DIR "$common/issue-to-pr/run-feat-stwo"
  [ ! -e "$one/.claude" ] && [ ! -e "$two/.claude" ] && [ ! -e "$bare/.claude" ] ||
    fail "bare clone bootstrap created source-tree state"
}

test_state_refuses_symlinked_metadata_paths_before_writing() {
  state_repo
  local common rel link outside n=0
  common=$(git rev-parse --path-format=absolute --git-common-dir)
  for rel in issue-to-pr issue-to-pr/run-feat-sissue--6--x; do
    n=$((n + 1))
    outside="$TEST_TMPDIR/outside-$n" link="$common/$rel"
    mkdir -p "$outside" "$(dirname "$link")"
    MSYS=winsymlinks:nativestrict ln -s "$outside" "$link" || fail "native symlink fixture unavailable"
    printf 'keep\n' >"$outside/sentinel"
    run_script state.sh
    assert_rc 2
    assert_key "$OUT" STOP_REASON unsafe-state-dir
    assert_eq sentinel "$(ls -A "$outside")"
    assert_eq keep "$(cat "$outside/sentinel")"
    rm "$link"
  done
}
