#!/usr/bin/env bash

stage_repo() {
  REPO=$(init_repo)
  REPO=$(git -C "$REPO" rev-parse --show-toplevel)
  cd "$REPO" || fail 'cannot enter repo'
  git config core.autocrlf false
  PLAN="$TEST_TMPDIR/planned.txt" REASONS="$TEST_TMPDIR/reasons.tsv"
  : >"$REASONS"
}

stage_report() {
  local file
  file=$(printf '%s\n' "$OUT" | sed -n 's/^STAGING_REPORT=//p')
  cat "$file"
}

test_stage_report_omits_empty_groups_and_indicators() {
  stage_repo
  printf 'changed\n' >README.md
  printf 'README.md\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- README.md
  assert_rc 0
  local report
  report=$(stage_report)
  assert_contains "$report" '| source | 1 | 8 |'
  assert_contains "$report" '<code>README.md</code> | source | 8 |'
  assert_not_contains "$report" '| tests | 0 |'
  assert_not_contains "$report" 'binaries 0 files'
  assert_not_contains "$report" 'none |'
}

test_stage_cannot_hide_undeclared_gitlinks_with_git_configuration() {
  stage_repo
  git update-index --add --cacheinfo "160000,$(git rev-parse HEAD),hidden"
  git config diff.ignoreSubmodules all
  printf 'changed\n' >README.md
  printf 'README.md\n' >"$PLAN"
  local action
  for action in review commit; do
    run_script stage.sh "$action" --plan "$PLAN" --message 'fix: copy' -- README.md
    assert_rc 2
    assert_key "$OUT" STOP_REASON index-mismatch
    assert_eq hidden "$(git diff --cached --name-only --ignore-submodules=none)"
    assert_eq seed "$(git log -1 --format=%s)"
  done
}

test_stage_rejects_deleted_directory_declarations_before_staging_children() {
  stage_repo
  mkdir dir
  printf 'a\n' >dir/a.txt
  printf 'b\n' >dir/b.txt
  git add -- dir/a.txt dir/b.txt
  git commit -qm files
  rm -- dir/a.txt dir/b.txt
  rmdir -- dir
  printf 'dir\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- dir
  assert_rc 4
  assert_key "$OUT" DEGRADED_REASON directory-path
  assert_eq '' "$(git diff --cached --name-only)"
}

test_stage_binary_content_cannot_be_hidden_by_diff_attributes() {
  stage_repo
  printf 'blob diff\n' >.gitattributes
  git add -- .gitattributes
  git commit -qm attributes
  printf '\0bytes' >blob
  printf 'blob\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- blob
  assert_rc 2
  assert_contains "$(stage_report)" 'binary'
  assert_eq '' "$(git diff --cached --name-only)"
  printf 'blob\tInclude the binary fixture for the regression test.\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- blob
  assert_rc 0
  assert_contains "$(stage_report)" 'binaries 1 files / 6 bytes'
}

test_stage_deleted_binaries_still_need_a_reason_with_zero_committed_bytes() {
  stage_repo
  printf 'blob diff\n' >.gitattributes
  printf '\0bytes' >blob
  git add -- .gitattributes blob
  git commit -qm binary
  rm -- blob
  printf 'blob\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- blob
  assert_rc 2
  assert_contains "$(stage_report)" 'binaries 1 files / 0 bytes'
  assert_eq '' "$(git diff --cached --name-only)"
  [ ! -e blob ] || fail 'unstaging restored the working file'
  printf 'blob\tRemove the obsolete binary fixture.\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- blob
  assert_rc 0
  assert_contains "$(stage_report)" '| binaries | 1 | 0 |'
}

test_stage_supports_directory_symlinks_as_exact_files() {
  stage_repo
  mkdir target
  printf 'unrelated\n' >target/child.txt
  if ! MSYS=winsymlinks:nativestrict ln -s target link || [ ! -L link ]; then
    printf 'SKIP: native symlink creation is unavailable\n'
    return 0
  fi
  git config core.symlinks true
  printf 'link\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- link
  assert_rc 0
  assert_eq 120000 "$(git ls-files --stage -- link | cut -d' ' -f1)"
  assert_eq target "$(git cat-file blob :link)"
  run_script stage.sh commit --plan "$PLAN" --message 'feat: add directory link' -- link
  assert_rc 0
  assert_eq target "$(git show HEAD:link)"
  assert_eq '' "$(git ls-files -- target)"
  assert_eq unrelated "$(cat target/child.txt)"
}

test_stage_accepts_crlf_manifests_but_rejects_embedded_cr() {
  stage_repo
  printf '\0bytes' >blob
  printf 'other\n' >other.txt
  printf 'blob\r\nother.txt\r\n' >"$PLAN"
  printf 'blob\tInclude the binary fixture.\r\nother.txt\tInclude the companion text.\r\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- blob other.txt
  assert_rc 0
  printf 'bad\rname\n' >"$PLAN"
  local before
  before=$(git write-tree)
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- blob other.txt
  assert_rc 4
  assert_eq "$before" "$(git write-tree)"
}

test_stage_case_variants_cannot_bypass_runtime_policy() {
  stage_repo
  mkdir -p .CLAUDE/issue-to-pr/run-other
  printf 'private\n' >.CLAUDE/issue-to-pr/run-other/ledger.md
  printf '.CLAUDE/issue-to-pr/run-other/ledger.md\n' >"$PLAN"
  git add -- .CLAUDE/issue-to-pr/run-other/ledger.md
  run_script stage.sh commit --plan "$PLAN" --message 'fix: copy' -- .CLAUDE/issue-to-pr/run-other/ledger.md
  assert_rc 2
  assert_key "$OUT" STOP_REASON generated-run-state
  assert_eq seed "$(git log -1 --format=%s)"
  git restore --staged -- .CLAUDE/issue-to-pr/run-other/ledger.md
  mkdir -p DIST
  printf 'generated\n' >DIST/output.LOG
  printf 'DIST/output.LOG\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- DIST/output.LOG
  assert_rc 2
  assert_contains "$(stage_report)" 'generated, do-not-commit'
  assert_eq '' "$(git diff --cached --name-only)"
}

test_stage_commits_only_declared_files_and_reports_index_bytes() {
  stage_repo
  printf 'changed\n' >README.md
  printf 'unrelated\n' >other.txt
  printf 'README.md\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- README.md
  assert_rc 0
  printf 'different working bytes\n' >README.md
  run_script stage.sh commit --plan "$PLAN" --message 'fix: copy' -- README.md
  assert_rc 0
  assert_eq 'fix: copy' "$(git log -1 --format=%s)"
  assert_eq changed "$(git show HEAD:README.md)"
  assert_contains "$(stage_report)" '| source | 1 | 8 |'
  assert_eq unrelated "$(cat other.txt)"
}

test_stage_refuses_undeclared_index_entries_before_mutation_and_commit() {
  stage_repo
  printf 'changed\n' >README.md
  printf 'extra\n' >extra.txt
  git add -- extra.txt
  printf 'README.md\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- README.md
  assert_rc 2
  assert_key "$OUT" STOP_REASON index-mismatch
  assert_contains "$ERR" extra.txt
  assert_eq extra.txt "$(git diff --cached --name-only)"
  git restore --staged -- extra.txt
  run_script stage.sh review --plan "$PLAN" -- README.md
  assert_rc 0
  git add -- extra.txt
  run_script stage.sh commit --plan "$PLAN" --message 'fix: copy' -- README.md
  assert_rc 2
  assert_eq seed "$(git log -1 --format=%s)"
}

test_stage_unstages_only_unexplained_flags_and_retry_keeps_files() {
  stage_repo
  mkdir -p tests/snapshots dist
  printf 'new copy\n' >README.md
  printf '\211PNG\0data' >tests/snapshots/footer.png
  printf 'output\n' >dist/result.log
  printf 'README.md\ntests/snapshots/footer.png\ndist/result.log\n' >"$PLAN"
  printf 'tests/snapshots/footer.png\tRefresh the footer snapshot after its copy changes.\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- README.md tests/snapshots/footer.png dist/result.log
  assert_rc 2
  assert_key "$OUT" STOP_REASON unexplained-files
  assert_eq $'README.md\ntests/snapshots/footer.png' "$(git diff --cached --name-only)"
  assert_eq output "$(cat dist/result.log)"
  printf 'dist/result.log\tInclude the generated fixture for the regression test.\n' >>"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- README.md tests/snapshots/footer.png dist/result.log
  assert_rc 0
  local report
  report=$(stage_report)
  assert_contains "$report" '| fixtures/snapshots | 1 | 9 |'
  assert_contains "$report" 'binaries 1 files / 9 bytes'
  assert_contains "$report" 'binary'
  assert_contains "$report" 'generated'
  assert_contains "$report" 'do-not-commit'
  assert_contains "$report" 'Refresh the footer snapshot'
}

test_stage_unplanned_and_extensionless_binary_files_need_reasons() {
  stage_repo
  printf '\0bytes' >blob
  : >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- blob
  assert_rc 2
  assert_contains "$(stage_report)" 'unplanned'
  assert_contains "$(stage_report)" 'binary'
  assert_eq '' "$(git diff --cached --name-only)"
}

test_stage_literal_paths_and_rename_deletion_are_exact() {
  stage_repo
  printf 'literal\n' >'a[1].txt'
  printf 'keep\n' >a1.txt
  printf 'dash\n' >-option.txt
  printf 'space\n' >'space name.txt'
  printf 'a[1].txt\n-option.txt\nspace name.txt\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- 'a[1].txt' -option.txt 'space name.txt'
  assert_rc 0
  assert_not_contains "$(git diff --cached --name-only)" a1.txt
  git commit -qm files
  mv README.md renamed.md
  printf 'README.md\nrenamed.md\n' >"$PLAN"
  run_script stage.sh commit --plan "$PLAN" --message 'fix: rename' -- README.md renamed.md
  assert_rc 2
  run_script stage.sh review --plan "$PLAN" -- README.md renamed.md
  assert_rc 0
  assert_contains "$(stage_report)" '<code>README.md</code> | source | 0 |'
  run_script stage.sh commit --plan "$PLAN" --message 'fix: rename' -- README.md renamed.md
  assert_rc 0
}

test_stage_rejects_invalid_declarations_and_reasons_without_mutation() {
  stage_repo
  printf 'edit\n' >README.md
  printf 'README.md\n' >"$PLAN"
  local path
  for path in . ../README.md ./README.md /README.md $'bad\tpath'; do
    run_script stage.sh review --plan "$PLAN" -- "$path"
    assert_rc 4
    assert_eq '' "$(git diff --cached --name-only)"
  done
  printf 'README.md\t \n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- README.md
  assert_rc 4
  printf 'README.md\treason\nREADME.md\tsecond\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- README.md
  assert_rc 4
  printf 'other.txt\treason\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- README.md
  assert_rc 4
  assert_eq '' "$(git diff --cached --name-only)"
}

test_stage_flags_every_member_of_an_oversized_group() {
  stage_repo
  # Text content isolates the size rule from binary detection.
  head -c 10485761 /dev/zero | tr '\0' x >large.txt
  printf 'small\n' >small.txt
  printf 'large.txt\nsmall.txt\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- large.txt small.txt
  assert_rc 2
  assert_contains "$(stage_report)" '| source | 2 | 10485767 |'
  assert_contains "$(stage_report)" 'large-group'
  assert_eq '' "$(git diff --cached --name-only)"
}

test_stage_flags_config_lockfiles_tests_and_nested_patterns() {
  stage_repo
  mkdir -p config tests node_modules/pkg .claude
  local path
  for path in config/app.json package-lock.json tests/check.sh node_modules/pkg/file.js .claude/settings.json .env.example; do
    printf 'text\n' >"$path"
    printf '%s\n' "$path" >>"$PLAN"
    printf '%s\tInclude the declared configuration or test input.\n' "$path" >>"$REASONS"
  done
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- config/app.json package-lock.json tests/check.sh node_modules/pkg/file.js .claude/settings.json .env.example
  assert_rc 0
  local report
  report=$(stage_report)
  assert_contains "$report" '| config | 3 | 15 |'
  assert_contains "$report" '| lockfiles | 1 | 5 |'
  assert_contains "$report" '| tests | 1 | 5 |'
  assert_contains "$report" 'do-not-commit'
}

test_stage_never_accepts_generated_run_state_with_a_reason() {
  stage_repo
  mkdir -p .claude/issue-to-pr/run-main
  printf 'private\n' >.claude/issue-to-pr/run-main/ledger.md
  printf '.claude/issue-to-pr/run-main/ledger.md\n' >"$PLAN"
  printf '.claude/issue-to-pr/run-main/ledger.md\tA reason must not bypass run-state safety.\n' >"$REASONS"
  run_script stage.sh review --plan "$PLAN" --reasons "$REASONS" -- .claude/issue-to-pr/run-main/ledger.md
  assert_rc 2
  assert_key "$OUT" STOP_REASON generated-run-state
  assert_eq '' "$(git diff --cached --name-only)"
}

test_stage_reports_in_main_checkout_for_a_linked_worktree() {
  stage_repo
  git worktree add -qb feat/stage "$TEST_TMPDIR/linked"
  cd "$TEST_TMPDIR/linked" || fail 'cannot enter linked checkout'
  printf 'edit\n' >README.md
  printf 'README.md\n' >"$PLAN"
  run_script stage.sh review --plan "$PLAN" -- README.md
  assert_rc 0
  assert_key "$OUT" STAGING_REPORT "$(run_dir_of "$REPO" feat/stage)/staging-report.md"
  [ ! -e .claude ] || fail 'report was written into linked checkout'
}
