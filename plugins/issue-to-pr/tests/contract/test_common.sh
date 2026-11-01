#!/usr/bin/env bash

test_common_stop_exits_2_with_the_keys_the_reason_and_the_hint() {
  local out err rc
  out=$(bash -c 'source "$1/lib/common.sh"; emit CTX yes; stop bad-thing "the human hint"' _ "$ITP_SCRIPTS" 2>"$TEST_TMPDIR/err")
  rc=$?
  err=$(<"$TEST_TMPDIR/err")
  assert_eq 2 "$rc" "stop exits 2"
  assert_key "$out" CTX yes
  assert_key "$out" STOP_REASON bad-thing
  assert_contains "$err" "the human hint"
}

test_common_degrade_exits_4() {
  bash -c 'source "$1/lib/common.sh"; degrade parse' _ "$ITP_SCRIPTS" >/dev/null 2>&1
  assert_eq 4 "$?" "degrade exits 4"
}

test_common_done_ok_exits_0_with_the_keys() {
  local out rc
  out=$(bash -c 'source "$1/lib/common.sh"; emit RESULT "good value"; done_ok' _ "$ITP_SCRIPTS" 2>/dev/null)
  rc=$?
  assert_eq 0 "$rc" "done_ok exits 0"
  assert_key "$out" RESULT "good value"
}

test_common_state_dir_ignores_itself_and_keeps_a_hand_edited_rule() {
  source "$ITP_SCRIPTS/lib/common.sh"
  local d first
  d="$TEST_TMPDIR/state"
  ensure_state_dir "$d" || fail "ensure_state_dir failed on a writable path"
  first=$(grep -v '^#' "$d/.gitignore" | grep -v '^[[:space:]]*$' | head -1)
  assert_eq '*' "$first" 'the FIRST rule must be a star: gitignore lets the last match decide'
  printf '%s\n' '*' '!keep-me.md' >"$d/.gitignore"
  ensure_state_dir "$d" || fail "ensure_state_dir failed on an existing directory"
  assert_contains "$(cat "$d/.gitignore")" 'keep-me.md' 'a hand-edited rule was overwritten'
}

test_common_branch_dir_never_gives_two_branches_one_directory() {
  source "$ITP_SCRIPTS/lib/common.sh"
  local root
  root=$(init_repo)
  [ "$(branch_dir "$root" a/-b)" != "$(branch_dir "$root" a-/b)" ] ||
    fail "two branch names share run state, which cleanup would delete"
  [ "$(branch_dir "$root" a/b)" != "$root/.claude/issue-to-pr/branch-a-sb" ] ||
    fail "new state overlaps another branch's legacy directory"
}


test_common_receipt_write_refuses_a_symlink_target() {
  source "$ITP_SCRIPTS/lib/common.sh"
  local root target receipt rc
  root=$(init_repo)
  target="$TEST_TMPDIR/outside.json"
  receipt="$(branch_dir "$root" main)/receipt.json"
  mkdir -p "$(dirname "$receipt")"
  printf 'keep\n' >"$target"
  MSYS=winsymlinks:nativestrict ln -s "$target" "$receipt" || fail "native symlink fixture unavailable"
  receipt_write "$root" main sha test
  rc=$?
  assert_eq 1 "$rc" "receipt write must refuse an external target"
  assert_eq keep "$(cat "$target")"
}
