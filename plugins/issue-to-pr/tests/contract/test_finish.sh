#!/usr/bin/env bash

SHA_OK="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

enter() { cd "$1" || fail "could not enter $1"; }

mk_worktree() { # repo branch -> worktree at repo-worktrees/issue-6 with one pushed commit
  local repo=$1 branch=$2 wt="$TEST_TMPDIR/repo-worktrees/issue-6"
  git -C "$repo" worktree add "$wt" -b "$branch" main >/dev/null 2>&1
  printf 'work\n' >"$wt/work.txt"
  git -C "$wt" add work.txt
  git -C "$wt" commit -qm work
  git -C "$wt" push -q -u origin "$branch" 2>/dev/null || true
  printf '%s' "$wt"
}

merge_setup() { # scenario [receipt-gates] -> cwd in the worktree, receipt for SHA_OK written
  REPO=$(init_repo_with_remote)
  WT=$(mk_worktree "$REPO" feat/issue-6-x)
  enter "$WT"
  use_fake_gh "$1"
  write_receipt "$REPO" feat/issue-6-x "$SHA_OK" "${2:-test}"
}

cleanup_setup() { # scenario -> cwd in the main checkout, worktree on feat/issue-6-x
  REPO=$(init_repo_with_remote)
  WT=$(mk_worktree "$REPO" feat/issue-6-x)
  enter "$REPO"
  use_fake_gh "$1"
}

branch_survives() { git -C "$REPO" show-ref --verify --quiet refs/heads/feat/issue-6-x; }

test_merge_squashes_the_head_the_receipt_covers() {
  merge_setup happy
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" MERGED true
  assert_key "$OUT" BASE_IS_DEFAULT true
  assert_gh_called "pr merge feat/issue-6-x --squash --match-head-commit $SHA_OK"
}

test_merge_reports_a_non_default_base() {
  merge_setup stacked-base
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" MERGED_INTO feat/issue-5-parent
  assert_key "$OUT" BASE_IS_DEFAULT false
}

test_merge_says_unknown_when_the_default_branch_is_unreadable() {
  merge_setup default-branch-unreadable
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" BASE_IS_DEFAULT unknown
}

test_merge_refuses_a_head_no_receipt_covers() {
  local repo wt
  repo=$(init_repo_with_remote)
  wt=$(mk_worktree "$repo" feat/issue-6-x)
  enter "$wt"
  use_fake_gh happy
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON gates-unverified
  write_receipt "$repo" feat/issue-6-x bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_gh_not_called "pr merge" "merged with no receipt, or one for another head"
}

test_merge_refuses_a_receipt_without_the_test_gate() {
  merge_setup happy smoke
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_gh_not_called "pr merge" "a smoke or install run overwrites the receipt; neither ran the tests on this head"
}

test_merge_refuses_a_method_gh_would_read_as_a_bypass() {
  merge_setup happy
  run_script finish.sh merge 6 --branch feat/issue-6-x --method admin
  assert_rc 4
  assert_gh_not_called "pr merge" "--method admin reached gh as --admin, which bypasses branch protection"
}

test_merge_pushes_the_branch_not_whatever_the_cwd_is_on() {
  merge_setup happy
  enter "$REPO" # the main checkout, on main, with a local commit origin does not have
  printf 'local only\n' >"$REPO/local.txt"
  git -C "$REPO" add local.txt
  git -C "$REPO" commit -qm "local only"
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 0
  [ "$(git -C "$REPO" rev-parse origin/main)" != "$(git -C "$REPO" rev-parse main)" ] ||
    fail "a bare git push published the main checkout's own branch"
}

test_merge_refuses_a_review_requesting_changes() {
  merge_setup review-changes-requested
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON review-blocked
  assert_gh_not_called "pr merge"
}

test_merge_refuses_when_the_pr_cannot_be_read() {
  merge_setup pr-unreadable
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_gh_not_called "pr merge"
}

test_merge_surfaces_gh_own_refusal_and_claims_nothing() {
  merge_setup protected
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_contains "$OUT" "Protected branch update failed"
  assert_not_contains "$OUT" "MERGED=true"
}

test_merge_stops_when_the_push_is_rejected() {
  merge_setup happy
  git -C "$WT" remote set-url origin "$TEST_TMPDIR/does-not-exist.git"
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_gh_not_called "pr merge"
}

test_cleanup_removes_the_tree_both_branches_and_the_run_dir() {
  cleanup_setup pr-merged
  write_receipt "$REPO" feat/issue-6-x "$SHA_OK"
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" REMOVED true
  assert_key "$OUT" DELETED_LOCAL true
  assert_key "$OUT" DELETED_REMOTE true
  [ ! -d "$WT" ] || fail "the worktree survived cleanup"
  ! branch_survives || fail "the local branch survived cleanup"
  ! git -C "$REPO" ls-remote --exit-code --heads origin feat/issue-6-x >/dev/null 2>&1 ||
    fail "the remote branch survived cleanup"
  [ ! -e "$(run_dir_of "$REPO" feat/issue-6-x)" ] || fail "the run directory survived cleanup"
}

# A PR number must not hide the worktree checked out on --branch.
test_cleanup_finds_the_tree_by_branch_when_the_number_is_wrong() {
  cleanup_setup pr-merged
  run_script finish.sh cleanup 999 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" REMOVED true
  assert_key "$OUT" DELETED_LOCAL true
  [ ! -d "$WT" ] || fail "the worktree on --branch survived a cleanup keyed on the wrong number"
  ! branch_survives || fail "the local branch survived cleanup"
}

test_cleanup_prefers_the_branch_to_an_unrelated_numbered_tree() {
  cleanup_setup pr-merged
  local other="$TEST_TMPDIR/repo-worktrees/issue-999"
  git -C "$REPO" worktree add "$other" -b another-task main >/dev/null 2>&1
  run_script finish.sh cleanup 999 --branch feat/issue-6-x
  assert_rc 0
  [ ! -d "$WT" ] || fail "the requested worktree survived cleanup"
  ! branch_survives || fail "the requested branch survived cleanup"
  [ -d "$other" ] || fail "cleanup removed the unrelated worktree"
  git -C "$other" symbolic-ref --quiet --short HEAD | grep -qx another-task ||
    fail "cleanup changed the unrelated worktree's branch"
}

test_cleanup_refuses_an_unmerged_pr() {
  cleanup_setup pr-open
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON pr-not-merged
  branch_survives || fail "cleanup deleted the branch of an open PR"
  [ -d "$WT" ] || fail "cleanup removed the worktree of an open PR"
}

test_cleanup_refuses_a_branch_an_open_pr_is_based_on_or_cannot_check() {
  cleanup_setup has-dependent-pr
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON base-of-open-pr
  branch_survives || fail "cleanup deleted a branch an open PR is based on"
  use_fake_gh dependents-unreadable
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  branch_survives || fail "cleanup deleted the branch without knowing whether a PR depends on it"
}

test_cleanup_refuses_a_dirty_worktree() {
  cleanup_setup pr-merged
  printf 'changed\n' >>"$WT/README.md"
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON dirty-tracked-files
  [ -d "$WT" ] || fail "a dirty worktree was removed"
  branch_survives || fail "the branch of a dirty worktree was deleted"
}

test_cleanup_preserves_tracked_run_state_before_removing_anything() {
  cleanup_setup pr-merged
  local d
  d=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
  mkdir -p "$d"
  printf 'keep\n' >"$d/ledger.md"
  git add .claude/issue-to-pr
  git commit -qm ledger
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON tracked-run-state
  assert_eq keep "$(cat "$d/ledger.md")"
  [ -d "$WT" ] || fail "cleanup removed the worktree before checking tracked state"
  branch_survives || fail "cleanup removed the branch before checking tracked state"
}

test_cleanup_preserves_a_tracked_file_at_the_run_directory_path() {
  cleanup_setup pr-merged
  local d
  d=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
  mkdir -p "$(dirname "$d")"
  printf 'keep\n' >"$d"
  git add .claude/issue-to-pr
  git commit -qm collision
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON tracked-run-state
  assert_eq keep "$(cat "$d")"
  branch_survives || fail "cleanup removed the branch despite tracked state"
}

test_cleanup_rechecks_tracked_run_state_after_switching_in_place() {
  cleanup_setup pr-merged
  local d
  d=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
  mkdir -p "$d"
  printf 'keep\n' >"$d/ledger.md"
  git add .claude/issue-to-pr
  git commit -qm ledger
  git worktree remove "$WT"
  git switch -q feat/issue-6-x
  git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON tracked-run-state
  assert_eq keep "$(cat "$d/ledger.md")"
  assert_eq '' "$(git status --short)"
  branch_survives || fail "cleanup deleted the branch before checking the new index"
}

test_cleanup_preserves_tracked_run_state_on_a_branch_without_a_worktree() {
  cleanup_setup pr-merged
  local d
  d=$(legacy_run_dir_of "$WT" feat/issue-6-x)
  mkdir -p "$d"
  printf 'keep\n' >"$d/ledger.md"
  git -C "$WT" add .claude/issue-to-pr
  git -C "$WT" commit -qm ledger
  git -C "$WT" push -q origin feat/issue-6-x
  git worktree remove "$WT"
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON tracked-run-state
  branch_survives || fail "cleanup removed the branch containing tracked run state"
  assert_eq keep "$(MSYS_NO_PATHCONV=1 git show feat/issue-6-x:.claude/issue-to-pr/run-feat-sissue--6--x/ledger.md)"
  git ls-remote --exit-code --heads origin feat/issue-6-x >/dev/null || fail "cleanup removed the remote branch"
}

test_cleanup_refuses_symlinks_before_removing_external_state() {
  cleanup_setup pr-merged
  local rel link outside d n=0
  for rel in .claude .claude/issue-to-pr .claude/issue-to-pr/run-feat-sissue--6--x; do
    n=$((n + 1))
    outside="$TEST_TMPDIR/outside-$n" link="$REPO/$rel"
    mkdir -p "$outside" "$(dirname "$link")"
    MSYS=winsymlinks:nativestrict ln -s "$outside" "$link" || fail "native symlink fixture unavailable"
    [ -L "$link" ] || fail "the symlink fixture is not a symlink"
    d=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
    mkdir -p "$d"
    printf 'keep\n' >"$d/ledger.md"
    run_script finish.sh cleanup 6 --branch feat/issue-6-x
    assert_rc 2
    assert_key "$OUT" STOP_REASON unsafe-state-dir
    assert_eq keep "$(cat "$d/ledger.md")"
    [ -d "$WT" ] || fail "cleanup removed the worktree before checking symlinks"
    branch_survives || fail "cleanup removed the branch before checking symlinks"
    rm "$link"
  done
}

test_cleanup_stops_when_worktree_listing_fails() {
  cleanup_setup pr-merged
  write_receipt "$REPO" feat/issue-6-x "$SHA_OK"
  local attempt
  git() {
    case "$*" in
      *"worktree list --porcelain")
        local count=0
        [ ! -f "$TEST_TMPDIR/list-count" ] || read -r count <"$TEST_TMPDIR/list-count"
        count=$((count + 1))
        printf '%s\n' "$count" >"$TEST_TMPDIR/list-count"
        [ "$count" != "$FAIL_LIST_AT" ] || return 1 ;;
      *"worktree remove "*) [ "$FAIL_LIST_AT" != 3 ] || return 1 ;;
    esac
    command git "$@"
  }
  export -f git
  for attempt in 2 3; do
    export FAIL_LIST_AT=$attempt
    rm -f "$TEST_TMPDIR/list-count"
    if [ "$attempt" = 2 ]; then git -C "$WT" switch -qc another-task
    else git -C "$WT" switch -q feat/issue-6-x; fi
    run_script finish.sh cleanup 6 --branch feat/issue-6-x
    assert_rc 2
    assert_key "$OUT" STOP_REASON worktree-list-failed
    [ -f "$WT/work.txt" ] || fail "an unreadable worktree list allowed removal"
    branch_survives || fail "an unreadable worktree list allowed local branch deletion"
    git -C "$REPO" ls-remote --exit-code --heads origin feat/issue-6-x >/dev/null 2>&1 ||
      fail "an unreadable worktree list allowed remote branch deletion"
    [ -f "$(receipt_file "$REPO" feat/issue-6-x)" ] || fail "an unreadable list deleted run state"
  done
}

test_cleanup_refuses_a_worktree_on_another_branch_or_detached_head() {
  local mode
  cleanup_setup pr-merged
  write_receipt "$REPO" feat/issue-6-x "$SHA_OK"
  git -C "$WT" switch -qc another-task
  for mode in another-task detached; do
    [ "$mode" != detached ] || git -C "$WT" checkout -q --detach
    run_script finish.sh cleanup 6 --branch feat/issue-6-x
    assert_rc 2
    assert_key "$OUT" STOP_REASON worktree-branch-mismatch
    run_script finish.sh cleanup 6 --branch feat/issue-6-x --keep-branch
    assert_rc 2
    assert_key "$OUT" STOP_REASON worktree-branch-mismatch
    [ -f "$WT/work.txt" ] || fail "cleanup removed another task's worktree"
    branch_survives || fail "refused cleanup deleted the requested branch"
    git -C "$REPO" ls-remote --exit-code --heads origin feat/issue-6-x >/dev/null 2>&1 ||
      fail "refused cleanup deleted the remote branch"
    [ -f "$(receipt_file "$REPO" feat/issue-6-x)" ] || fail "refused cleanup deleted run state"
  done
}

test_cleanup_reports_an_unregistered_leftover_dir_instead_of_deleting_it() {
  cleanup_setup pr-merged
  git -C "$REPO" worktree remove "$WT"
  mkdir -p "$WT"
  printf 'stale\n' >"$WT/leftover"
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key_present "$OUT" LEFTOVER_DIR
  assert_key "$OUT" DELETED_LOCAL true
  [ -d "$WT" ] || fail "an unregistered directory must be reported, not deleted"
}

test_cleanup_keep_branch_removes_the_tree_and_touches_nothing_else() {
  cleanup_setup happy # PR still open: --keep-branch is exempt from the merged precondition
  run_script finish.sh cleanup 6 --branch feat/issue-6-x --keep-branch
  assert_rc 0
  assert_key "$OUT" REMOVED true
  [ ! -d "$WT" ] || fail "--keep-branch did not remove the worktree"
  branch_survives || fail "--keep-branch deleted the branch"
  assert_gh_not_called "pr list"
}

test_cleanup_in_place_deletes_the_checked_out_branch() {
  local repo
  repo=$(init_repo_with_remote)
  enter "$repo"
  git -C "$repo" switch -qc feat/issue-6-x main
  git -C "$repo" push -q -u origin feat/issue-6-x 2>/dev/null || true
  use_fake_gh pr-merged
  run_script finish.sh cleanup 6 --branch feat/issue-6-x --keep-branch
  assert_rc 0
  assert_key "$OUT" REMOVED true
  assert_not_contains "$OUT" "LEFTOVER_DIR="
  assert_eq feat/issue-6-x "$(git -C "$repo" symbolic-ref --quiet --short HEAD)"
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" REMOVED true
  assert_not_contains "$OUT" "LEFTOVER_DIR="
  assert_key "$OUT" DELETED_LOCAL true
  [ -d "$repo/.git" ] || fail "in-place cleanup removed the main checkout"
}

test_a_traversing_issue_token_deletes_nothing() {
  cleanup_setup pr-merged
  run_script finish.sh cleanup '6/../../../.git' --branch feat/issue-6-x
  assert_rc 4
  [ -d "$REPO/.git" ] || fail "a traversing issue token reached rm"
  branch_survives || fail "a rejected call still deleted the branch"
}

test_a_missing_branch_value_does_not_hang() {
  local rc
  timeout 15 bash "$ITP_SCRIPTS/finish.sh" merge 6 --branch >/dev/null 2>&1
  rc=$?
  [ "$rc" != 124 ] || fail "finish.sh hung on --branch with no value"
  assert_eq 4 "$rc" "should degrade, not hang"
}

test_cleanup_refuses_a_mistyped_flag_rather_than_deleting_the_branch() {
  cleanup_setup pr-merged
  run_script finish.sh cleanup 6 --branch feat/issue-6-x --keep-branchs
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON unknown-flag
  branch_survives || fail "a typo in --keep-branch deleted the branch it was meant to save"
}

write_config() { # root key value
  mkdir -p "$1/.claude/issue-to-pr"
  printf -- '---\n%s: %s\n---\n' "$2" "$3" >"$1/.claude/issue-to-pr/config.md"
}

assert_human_path_blocks_merge() { # msg
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-human-path
  assert_contains "$ERR" "on the issue" "the auto-human-path policy stop must point at the issue, not the PR"
  assert_gh_not_called "pr merge" "$1"
}

test_auto_merge_refuses_a_tier_above_the_threshold() {
  merge_setup happy
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier standard
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-tier
  assert_contains "$ERR" "on the issue" "the auto-tier policy stop must point at the issue, not the PR"
  assert_gh_not_called "pr merge" "a standard run merged under a trivial threshold"
}

test_auto_merge_none_never_merges() {
  merge_setup happy
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto none --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-tier
  assert_gh_not_called "pr merge" "--auto none merged"
}

test_auto_merge_refuses_a_diff_touching_a_human_path() {
  merge_setup happy
  write_config "$REPO" human_paths "migrations/* work.txt"
  assert_human_path_blocks_merge "a diff touching a human path merged unattended"
  assert_key "$OUT" HUMAN_PATH work.txt
}

test_auto_merge_refuses_a_deleted_human_path() {
  merge_setup happy
  mkdir -p "$REPO/migrations"
  printf 'a\n' >"$REPO/migrations/a.sql" && printf 'b\n' >"$REPO/migrations/b.sql"
  git -C "$REPO" add migrations/a.sql migrations/b.sql
  git -C "$REPO" commit -qm "add migrations"
  git -C "$REPO" push -q origin main
  git -C "$WT" rebase -q origin/main
  git -C "$WT" rm -q migrations/a.sql
  git -C "$WT" commit -qm "drop a migration" && git -C "$WT" push -q -f origin feat/issue-6-x
  write_config "$REPO" human_paths "migrations/*"
  assert_human_path_blocks_merge "a deleted human path merged unattended"
}

test_auto_merge_refuses_a_human_path_with_a_space() {
  merge_setup happy
  mkdir -p "$WT/my dir" && printf 'x\n' >"$WT/my dir/x.txt"
  git -C "$WT" add "my dir/x.txt" && git -C "$WT" commit -qm "spaced path"
  git -C "$WT" push -q origin feat/issue-6-x
  write_config "$REPO" human_paths "my?dir/*"
  assert_human_path_blocks_merge "a human path with a space merged unattended"
  assert_key "$OUT" HUMAN_PATH "my dir/x.txt"
}

test_auto_merge_refuses_when_the_base_does_not_resolve() {
  merge_setup happy
  git -C "$WT" update-ref -d refs/remotes/origin/main
  git -C "$REPO" branch -q -D main 2>/dev/null || git -C "$REPO" checkout -q --detach
  git -C "$REPO" branch -q -D main 2>/dev/null || true
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-unprovable
  assert_gh_not_called "pr merge"
}

test_auto_merge_merges_a_clean_run_at_or_under_the_threshold() {
  merge_setup happy
  write_config "$REPO" human_paths "migrations/*"
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
  assert_rc 0
  assert_key "$OUT" MERGED true
  assert_gh_called "pr merge feat/issue-6-x --squash --match-head-commit $SHA_OK"
}

test_auto_merge_without_human_paths_configured_still_merges() {
  merge_setup happy
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_auto_and_tier_are_a_pair() {
  merge_setup happy
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON auto-needs-tier
  run_script finish.sh merge 6 --branch feat/issue-6-x --tier trivial
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON auto-needs-tier
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto huge --tier trivial
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON bad-tier
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto "" --tier ""
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON bad-tier
  run_script finish.sh merge 6 --branch feat/issue-6-x --tier trivial --auto
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON bad-tier
  assert_gh_not_called "pr merge" "a malformed --auto call merged"
}

test_merge_without_auto_is_unchanged() {
  merge_setup happy
  write_config "$REPO" human_paths "work.txt"
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_auto_merge_refuses_a_renamed_human_path() {
  merge_setup happy
  mkdir -p "$REPO/migrations"
  printf 'a\n' >"$REPO/migrations/a.sql"
  git -C "$REPO" add migrations/a.sql
  git -C "$REPO" commit -qm "add a migration"
  git -C "$REPO" push -q origin main
  git -C "$WT" rebase -q origin/main
  mkdir -p "$WT/db"
  git -C "$WT" mv migrations/a.sql db/a.sql
  git -C "$WT" commit -qm "move the migration out of migrations/"
  git -C "$WT" push -q -f origin feat/issue-6-x
  write_config "$REPO" human_paths "migrations/*"
  assert_human_path_blocks_merge "a rename out of a human path merged unattended"
}

test_auto_merge_refuses_a_non_ascii_human_path() {
  merge_setup happy
  mkdir -p "$WT/migrations"
  printf 'x\n' >"$WT/migrations/café.sql"
  git -C "$WT" add "migrations/café.sql"
  git -C "$WT" commit -qm "add an accented migration"
  write_config "$REPO" human_paths "migrations/*"
  assert_human_path_blocks_merge "a C-quoted non-ASCII human path merged unattended"
}

test_human_paths_value_may_be_commented() {
  merge_setup happy
  write_config "$REPO" human_paths 'work.txt   # never unattended'
  assert_human_path_blocks_merge "a trailing comment defeated the glob"
}

test_human_paths_in_a_crlf_config_still_match() {
  merge_setup happy
  mkdir -p "$REPO/.claude/issue-to-pr"
  printf -- '---\r\nhuman_paths: work.txt\r\n---\r\n' >"$REPO/.claude/issue-to-pr/config.md"
  assert_human_path_blocks_merge "a CR on the last glob defeated it"
}

test_human_paths_match_from_a_subdirectory_of_the_checkout() {
  merge_setup happy
  write_config "$REPO" human_paths work.txt
  mkdir -p "$WT/sub" && enter "$WT/sub"
  assert_human_path_blocks_merge "the guard read human_paths relative to a subdirectory"
}

test_human_paths_with_quotes_is_refused() {
  merge_setup happy
  write_config "$REPO" human_paths '"work.txt"'
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-unprovable
  assert_gh_not_called "pr merge" "a quoted human_paths value merged unattended"
}

test_human_paths_as_a_yaml_list_is_refused() {
  local v
  merge_setup happy
  mkdir -p "$REPO/.claude/issue-to-pr"
  for v in '' '[work.txt]' '- work.txt'; do
    printf -- '---\nhuman_paths: %s\n  - work.txt\n---\n' "$v" >"$REPO/.claude/issue-to-pr/config.md"
    run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
    assert_rc 2
    assert_key "$OUT" STOP_REASON auto-unprovable
    assert_gh_not_called "pr merge" "human_paths '$v' as a YAML list merged unattended"
  done
}

test_auto_merge_refuses_a_c_quoted_human_path() {
  merge_setup happy
  # Git objects hold names Windows cannot create; Git matches raw pathspecs before quoting output.
  local blob subtree tree commit name
  blob=$(printf 'x\n' | git -C "$WT" hash-object -w --stdin)
  for name in 'a"b.sql' $'a\tb.sql' $'a\nb.sql'; do
    subtree=$(printf '100644 blob %s\t%s\0' "$blob" "$name" | git -C "$WT" mktree -z)
    tree=$({ git -C "$WT" ls-tree HEAD | grep -v $'\tmigrations$'; printf '040000 tree %s\tmigrations\n' "$subtree"; } | git -C "$WT" mktree)
    commit=$(git -C "$WT" commit-tree "$tree" -p HEAD -m "quoted path")
    git -C "$WT" update-ref refs/heads/feat/issue-6-x "$commit"
    write_config "$REPO" human_paths "migrations/*"
    assert_human_path_blocks_merge "a C-quoted human path merged unattended"
    assert_key "$OUT" HUMAN_PATH "$(git -C "$WT" diff --name-only origin/main...HEAD -- migrations/)"
  done
}

test_auto_merge_refuses_an_empty_diff() {
  local repo wt
  repo=$(init_repo_with_remote)
  wt="$TEST_TMPDIR/repo-worktrees/issue-6"
  git -C "$repo" worktree add "$wt" -b feat/issue-6-x main >/dev/null 2>&1
  git -C "$wt" push -q -u origin feat/issue-6-x 2>/dev/null || true
  enter "$wt"
  use_fake_gh happy
  write_receipt "$repo" feat/issue-6-x "$SHA_OK"
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-diff-empty
  assert_contains "$ERR" "on the issue" "the auto-diff-empty policy stop must point at the issue, not the PR"
  assert_gh_not_called "pr merge" "a branch with no diff against its base merged unattended"
}

test_auto_merge_refuses_when_the_diff_cannot_be_read() {
  merge_setup happy
  git -C "$WT" checkout -q --detach
  git -C "$REPO" branch -q -D feat/issue-6-x
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-unprovable
  assert_gh_not_called "pr merge" "an unreadable diff merged unattended"
}

headless_setup() { # [labels] -> merge_setup happy, fixtures in FAKE_GH_FIX, issue 6 labelled
  merge_setup happy
  export FAKE_GH_FIX="$TEST_TMPDIR/fix"
  mkdir -p "$FAKE_GH_FIX"
  printf '%s\n' "${1-agent:running}" >"$FAKE_GH_FIX/labels-6"
}

comment() { # thread id login marker body -> one row of that thread's comments
  printf '%s\t%s\t%s\t%s\n' "$2" "$3" "$4" "$5" >>"$FAKE_GH_FIX/comments-$1"
}

report() { # state pr head -> a state marker line
  printf '<!-- issue-to-pr state=%s step=7 tier=trivial pr=%s head=%s issue-read=90 -->' "$1" "$2" "$3"
}

assert_headless_stop() { # reason msg
  assert_rc 2
  assert_key "$OUT" STOP_REASON "$1"
  assert_gh_not_called "pr merge" "$2"
}

run_auto() { run_script finish.sh merge 6 --branch feat/issue-6-x --auto trivial --tier trivial; }
run_plain() { run_script finish.sh merge 6 --branch feat/issue-6-x; }

test_attended_merge_reads_the_labels_and_nothing_else() {
  headless_setup bug
  comment 6 100 octo "$(report waiting 12 "$SHA_OK")" "stopped"
  run_plain
  assert_rc 0
  assert_key "$OUT" MERGED true
  assert_eq 1 "$(grep -c '^gh issue view' "$FAKE_GH_LOG")" "attended reads the labels once"
  assert_gh_not_called "/comments" "an attended merge read the comments"
  assert_gh_not_called "gh api user" "an attended merge looked up the owner"
}

threads_setup() { # thread rows -> merge_setup happy with those unresolved threads
  merge_setup happy
  export FAKE_GH_FIX="$TEST_TMPDIR/fix"
  mkdir -p "$FAKE_GH_FIX"
  printf '%s\n' "$1" >"$FAKE_GH_FIX/threads"
}

test_merge_refuses_unresolved_review_threads() {
  threads_setup $'T1\tcoderabbitai\ta.sh\thttps://github.com/o/r/pull/12#discussion_r7'
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON review-threads-open
  assert_contains "$ERR" "discussion_r7"
  assert_gh_not_called "pr merge" "merged over an unanswered finding"
}

test_merge_refuses_when_the_threads_cannot_be_read() {
  threads_setup ""
  : >"$FAKE_GH_FIX/fail-threads"
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 2
  assert_key "$OUT" STOP_REASON threads-unprovable
  assert_gh_not_called "pr merge"
}

test_merge_waits_for_a_coderabbit_review_in_progress_and_nothing_else() {
  threads_setup ""
  printf 'pending\tReview in progress\n' >"$FAKE_GH_FIX/status"
  run_plain
  assert_rc 2
  assert_key "$OUT" STOP_REASON bots-pending
  assert_gh_not_called "pr merge" "merged while CodeRabbit was still reviewing"
  printf 'success\tReview rate limited\n' >"$FAKE_GH_FIX/status"
  run_plain
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_headless_auto_merge_waits_once_the_run_has_stopped() {
  headless_setup
  comment 6 100 octo "$(report waiting "" "")" "question"
  run_auto
  assert_headless_stop auto-prior-state "an unattended merge went through after the run had stopped once"
  assert_contains "$ERR" "on the issue" "the auto-prior-state stop must point at the issue"
}

test_headless_auto_merge_reads_the_history_whatever_the_labels() {
  headless_setup bug
  comment 6 100 octo "$(report waiting 12 "$SHA_OK")" "stopped"
  run_auto
  assert_headless_stop auto-prior-state "--auto merged on an issue that already stopped, because it lost its agent:* label"
}

test_headless_auto_merge_ignores_a_stranger_state() {
  headless_setup
  comment 6 100 mallory "$(report waiting 12 "$SHA_OK")" "fake stop"
  run_auto
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_headless_auto_merge_with_no_state_merges() {
  headless_setup
  comment 6 100 octo "" "just a note"
  run_auto
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_headless_plain_merge_needs_a_report() {
  headless_setup
  comment 12 105 octo "" "merge"
  run_plain
  assert_headless_stop headless-unapproved "a headless merge went through with no review report"
}

test_headless_plain_merge_refuses_a_report_for_another_head() {
  headless_setup
  comment 6 101 octo "$(report review 12 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb)" "report"
  comment 6 102 octo "" "merge"
  run_plain
  assert_headless_stop headless-unapproved "a merge word for another head merged this one"
}

test_headless_plain_merge_refuses_a_report_for_another_pr() {
  headless_setup
  comment 6 101 octo "$(report review 13 "$SHA_OK")" "report"
  comment 6 102 octo "" "merge"
  run_plain
  assert_headless_stop headless-unapproved "a merge word for PR 13 merged PR 12"
}

test_headless_plain_merge_refuses_a_word_older_than_the_report() {
  headless_setup
  comment 6 100 octo "" "merge"
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  run_plain
  assert_headless_stop headless-unapproved "a merge said before the report authorized it"
}

test_headless_plain_merge_takes_the_owner_word_on_the_pr() {
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 12 102 octo "" "merge"
  comment 12 103 mallory "" "wait"
  comment 6 104 octo "<!-- issue-to-pr -->" "a note of the run's own"
  run_plain
  assert_rc 0
  assert_key "$OUT" MERGED true
  assert_gh_called "pr merge feat/issue-6-x --squash --match-head-commit $SHA_OK"
  assert_gh_called "issues/6/comments --paginate" "the issue thread must be read past its first page"
  assert_gh_called "issues/12/comments --paginate" "the PR thread must be read past its first page"
}

test_headless_plain_merge_heeds_the_owner_newest_word() {
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 12 102 octo "" "merge"
  comment 6 103 octo "" "wait, change the title"
  run_plain
  assert_headless_stop headless-unapproved "a later owner word did not revoke the merge"
}

test_headless_plain_merge_reads_the_newest_state_not_the_oldest() {
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 6 102 octo "$(report failed 12 "$SHA_OK")" "failed"
  comment 6 103 octo "" "merge"
  run_plain
  assert_headless_stop headless-unapproved "a merge went through on a state the run had already left"
  assert_contains "$ERR" "head=$SHA_OK" "the stop must give the full head sha the report needs"
  assert_contains "$ERR" "remove the agent:* labels from issue #6" "the stop must name the attended way out"
}

test_headless_plain_merge_takes_only_the_exact_word() {
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 6 102 octo "" "don't merge"
  run_plain
  assert_headless_stop headless-unapproved "a word containing merge was read as merge"
  assert_contains "$ERR" "head=$SHA_OK" "the stop must give the full head sha the report needs"
  assert_contains "$ERR" "remove the agent:* labels from issue #6" "the stop must name the attended way out"
}

test_headless_plain_merge_takes_a_capitalised_russian_word() {
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 12 102 octo "" "Мерж"
  run_plain
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_headless_plain_merge_stops_on_a_malformed_owner_marker() {
  local m
  headless_setup
  for m in '<!-- issue-to-pr state=Review -->' '<!-- issue-to-pr state=failed pr=#12 -->' '<!-- issue-to-pr state = failed -->'; do
    : >"$FAKE_GH_FIX/comments-6"
    comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
    comment 6 102 octo "" "merge"
    comment 6 103 octo "$m" "a state the guard cannot read"
    run_plain
    assert_headless_stop headless-unprovable "a malformed newer owner marker let an older review merge ($m)"
    assert_contains "$ERR" "delete that comment" "the stop must name the way out"
  done
}

test_headless_plain_merge_takes_a_plain_marker_note_between_report_and_word() {
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 6 102 octo "<!-- issue-to-pr -->" "a note of the run's own"
  comment 6 103 octo "" "merge"
  run_plain
  assert_rc 0
  assert_key "$OUT" MERGED true
}

test_headless_is_any_live_agent_label() {
  headless_setup agent:review
  comment 12 105 octo "" "merge"
  run_plain
  assert_headless_stop headless-unapproved "an agent:review issue merged as if attended"
}

test_headless_merge_fails_closed_when_github_cannot_be_read() {
  local f
  headless_setup
  comment 6 101 octo "$(report review 12 "$SHA_OK")" "report"
  comment 12 102 octo "" "мерж"
  for f in comments-6 comments-12 user labels-6; do
    rm -f "$FAKE_GH_FIX"/fail-*
    : >"$FAKE_GH_FIX/fail-$f"
    run_plain
    assert_headless_stop headless-unprovable "a merge went through with $f unreadable"
  done
  rm -f "$FAKE_GH_FIX"/fail-*
  run_plain # the control: the same threads, all readable, merge on the Russian word
  assert_rc 0
  assert_key "$OUT" MERGED true
}


size_diff() { # additions deletions files
  local additions=$1 deletions=$2 files=$3 count=0 i
  merge_setup happy
  write_config "$REPO" auto_merge_limits '200 5 2 50'
  if [ "$deletions" -gt 0 ]; then
    seq "$deletions" >"$REPO/removed.txt"
    git -C "$REPO" add removed.txt
    git -C "$REPO" commit -qm baseline
    git -C "$REPO" push -q origin main
    git -C "$WT" rebase -q origin/main
    git -C "$WT" rm -q removed.txt
    count=$((count + 1))
  fi
  if [ "$additions" -gt 0 ]; then
    seq "$additions" >"$WT/work.txt"
    git -C "$WT" add work.txt
    count=$((count + 1))
  else
    git -C "$WT" rm -q work.txt
  fi
  for ((i = count; i < files; i++)); do
    : >"$WT/empty-$i.txt"
    git -C "$WT" add "empty-$i.txt"
  done
  git -C "$WT" commit -qm sized-diff
  git -C "$WT" push -q -f origin feat/issue-6-x
}

test_limits_allow_exact_line_and_file_boundaries() {
  size_diff 100 100 5
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
  assert_rc 0
  assert_key "$OUT" MERGED true
  assert_key "$OUT" DIFF_ADDITIONS 100
  assert_key "$OUT" DIFF_DELETIONS 100
  assert_key "$OUT" DIFF_FILES 5
}

test_limits_hold_large_or_addition_heavy_changes_using_primary_config() {
  local numbers
  for numbers in '101 100 2' '10 10 6' '101 50 2' '51 0 1'; do
    (
      TEST_TMPDIR=$(mktemp -d "$TEST_TMPDIR/size-case.XXXXXX")
      # The numeric fixture triples above intentionally split into arguments.
      # shellcheck disable=SC2086
      size_diff $numbers
      write_config "$WT" auto_merge_limits '10000 100 100 10000'
      run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
      assert_rc 2
      assert_key "$OUT" STOP_REASON auto-diff-limit
      assert_gh_not_called 'pr merge'
    ) || fail "unexpected merge for fixture $numbers"
  done
}

test_limits_allow_a_small_new_file() {
  size_diff 15 0 1
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
  assert_rc 0
}

test_limits_allow_growth_at_the_boundary() {
  size_diff 99 49 2
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
  assert_rc 0
}

test_limits_require_manual_review_for_binary_changes() {
  merge_setup happy
  write_config "$REPO" auto_merge_limits '200 5 2 50'
  printf '\0binary\n' >"$WT/blob.bin"
  git -C "$WT" add blob.bin
  git -C "$WT" commit -qm binary
  run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
  assert_rc 2
  assert_key "$OUT" STOP_REASON auto-unprovable
  assert_gh_not_called 'pr merge'
}

test_limits_reject_malformed_configuration() {
  local value
  merge_setup happy
  for value in '' '200 5 2' '200 5 two 50' '200 5 0 50' '200 5 2 50 extra'; do
    write_config "$REPO" auto_merge_limits "$value"
    run_script finish.sh merge 6 --branch feat/issue-6-x --auto standard --tier trivial
    assert_rc 2
    assert_key "$OUT" STOP_REASON auto-unprovable
  done
  assert_gh_not_called 'pr merge'
}

test_limits_do_not_block_an_explicit_owner_merge() {
  size_diff 51 0 1
  run_script finish.sh merge 6 --branch feat/issue-6-x
  assert_rc 0
  assert_key "$OUT" MERGED true
}


test_cleanup_removes_only_the_owned_legacy_run() {
  cleanup_setup pr-merged
  local owned other
  owned=$(legacy_run_dir_of "$REPO" feat/issue-6-x)
  other=$(legacy_run_dir_of "$REPO" feat/other)
  mkdir -p "$owned" "$other"
  printf 'owned\n' >"$owned/receipt.json"
  printf 'keep\n' >"$other/receipt.json"
  run_script finish.sh cleanup 6 --branch feat/issue-6-x
  assert_rc 0
  [ ! -e "$owned" ] || fail "the owned legacy run survived cleanup"
  assert_eq keep "$(cat "$other/receipt.json")"
}
