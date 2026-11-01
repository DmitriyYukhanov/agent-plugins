#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=${BASH_SOURCE[0]%/*}
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

# review stages whole declared files; commit audits the index without restaging.
action=${1:-}
case "$action" in review | commit) shift ;; *) degrade bad-arguments 'stage: expected review or commit' ;; esac
plan='' reasons='' message=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --plan | --reasons | --message)
      [ "$#" -ge 2 ] || degrade bad-arguments "stage: $1 needs a value"
      case "$1" in --plan) plan=$2 ;; --reasons) reasons=$2 ;; --message) message=$2 ;; esac
      shift 2 ;;
    --) shift; break ;;
    *) degrade bad-arguments "stage: unknown option $1; put literal paths after --" ;;
  esac
done
[[ "$#" -gt 0 && -r "$plan" ]] || degrade bad-arguments 'stage: supply --plan <path-list> and -- <files...>'
if [ "$action" = commit ]; then
  [[ -n "${message//[[:space:]]/}" && "$message" != *$'\n'* && "$message" != *$'\r'* ]] ||
    degrade bad-arguments 'stage: commit needs a one-line --message subject'
fi
paths=("$@") planned=() reason_paths=() reason_texts=()
# Policy patterns ignore case; exact-path membership still uses literal test comparisons.
shopt -s nocasematch

has_path() {
  local wanted=$1 candidate
  shift
  for candidate in "$@"; do [ "$wanted" != "$candidate" ] || return 0; done
  return 1
}

validate_path() {
  case "$1" in
    '' | /* | [A-Za-z]:* | *\\* | . | .. | ./* | */./* | */. | ../* | */../* | */.. | *//* | */ | .git | .git/* | */.git/* | *$'\n'* | *$'\r'* | *$'\t'*)
      degrade invalid-path "stage: use canonical repository-relative file paths without CR, LF or tabs: $1" ;;
  esac
}

# Resolve manifests before changing directory; their paths may be checkout-relative.
plan_text=$(cat -- "$plan") || degrade unreadable-plan "stage: cannot read $plan"
reason_text=''
if [ -n "$reasons" ]; then
  reason_text=$(cat -- "$reasons") || degrade unreadable-reasons "stage: cannot read $reasons"
fi
checkout=$(git rev-parse --show-toplevel 2>/dev/null) || degrade not-a-git-repo 'stage: not inside a Git checkout'
cd "$checkout"
branch=$(git symbolic-ref --short HEAD 2>/dev/null) || degrade detached-head 'stage: check out the task branch first'
git rev-parse --verify HEAD >/dev/null 2>&1 || degrade unborn-head 'stage: an initial commit is required'
root=$(repo_root)
seen=()
for path in "${paths[@]}"; do
  validate_path "$path"
  has_path "$path" "${seen[@]}" && degrade duplicate-path "stage: duplicate declaration: $path"
  seen+=("$path")
  case "$path" in .claude/issue-to-pr/run-* | .claude/issue-to-pr/branch-*)
    stop generated-run-state "stage: generated run state cannot be committed: $path" ;;
  esac
  [[ ! -d "$path" || -L "$path" ]] || degrade directory-path "stage: declare each file, not a directory: $path"
  if [ ! -e "$path" ] && [ ! -L "$path" ]; then
    object_type=$(git cat-file -t ":$path" 2>/dev/null || git cat-file -t "HEAD:$path" 2>/dev/null) ||
      degrade missing-path "stage: file does not exist and is not tracked: $path"
    [ "$object_type" = blob ] || degrade directory-path "stage: declare an exact tracked file, not a tree or gitlink: $path"
  fi
done
while IFS= read -r path; do
  path=${path%$'\r'}
  [ -n "$path" ] || continue
  validate_path "$path"
  has_path "$path" "${planned[@]}" && degrade duplicate-plan-path "stage: duplicate planned path: $path"
  planned+=("$path")
done <<<"$plan_text"
while IFS= read -r row; do
  row=${row%$'\r'}
  [ -n "$row" ] || continue
  [[ "$row" == *$'\t'* ]] || degrade invalid-reason 'stage: reasons must be path<TAB>one-line explanation'
  path=${row%%$'\t'*} reason=${row#*$'\t'}
  validate_path "$path"
  [[ "$reason" != *$'\t'* && "$reason" != *$'\r'* && -n "${reason//[[:space:]]/}" ]] ||
    degrade invalid-reason "stage: blank or multiline reason for $path"
  has_path "$path" "${paths[@]}" || degrade unknown-reason-path "stage: reason names an undeclared file: $path"
  has_path "$path" "${reason_paths[@]}" && degrade duplicate-reason "stage: duplicate reason for $path"
  reason_paths+=("$path") reason_texts+=("$reason")
done <<<"$reason_text"

ensure_run_dir "$root" "$branch" || degrade state-unwritable 'stage: cannot initialize the run directory'
run_dir=$(branch_dir "$root" "$branch")
stage_tmp=$(mktemp -d "$run_dir/stage.XXXXXX") || degrade state-unwritable 'stage: cannot create temporary report files'
trap 'rm -f -- "$stage_tmp/paths" "$stage_tmp/unmerged" "$stage_tmp/numstat" "$stage_tmp/report"; rmdir -- "$stage_tmp"' EXIT
git ls-files --unmerged >"$stage_tmp/unmerged" || stop index-unreadable 'stage: cannot inspect the index'
[ ! -s "$stage_tmp/unmerged" ] || stop unmerged-index 'stage: resolve index conflicts before staging'

read_index() {
  git diff --cached --name-only --no-renames --ignore-submodules=none -z >"$stage_tmp/paths" || stop index-unreadable 'stage: cannot inspect staged paths'
  indexed=()
  while IFS= read -r -d '' path; do indexed+=("$path"); done <"$stage_tmp/paths"
}
check_extras() {
  for path in "${indexed[@]}"; do
    has_path "$path" "${paths[@]}" || stop index-mismatch "stage: index contains undeclared file $path; preserve it or unstage that exact path, then retry with the intended list."
  done
}
if [ "$action" = review ]; then
  read_index
  check_extras
  git --literal-pathspecs add -- "${paths[@]}" || stop staging-failed 'stage: explicit staging failed; inspect the index before retrying'
fi
tree=$(git write-tree) || stop index-unreadable 'stage: cannot read the staged tree'
read_index
check_extras
for path in "${paths[@]}"; do
  has_path "$path" "${indexed[@]}" || stop index-mismatch "stage: declared file has no staged change: $path; stage it or correct the declaration."
done
git diff --cached --numstat --no-renames --ignore-submodules=none -z >"$stage_tmp/numstat" || stop index-unreadable 'stage: cannot inspect binary changes'
binary_paths=()
while IFS= read -r -d '' row; do
  [[ "$row" != -$'\t'-$'\t'* ]] || binary_paths+=("${row#*$'\t'*$'\t'}")
done <"$stage_tmp/numstat"

groups=(source tests fixtures/snapshots generated binaries lockfiles config)
counts=(0 0 0 0 0 0 0) totals=(0 0 0 0 0 0 0)
file_groups=() sizes=() flags=() explanations=()
new_count=0 new_bytes=0 binary_count=0 binary_bytes=0 total_bytes=0
for path in "${paths[@]}"; do
  size=0 is_new=0 is_binary=0 is_deleted=0 flag=''
  if oid=$(git rev-parse --verify ":$path" 2>/dev/null); then
    git cat-file -e "HEAD:$path" 2>/dev/null || is_new=1
  else
    oid=$(git rev-parse --verify "HEAD:$path") || stop unsupported-index-entry "stage: cannot inspect deleted path: $path"
    is_deleted=1
  fi
  blob_size=$(git cat-file -s "$oid") || stop unsupported-index-entry "stage: cannot measure blob: $path"
  [ "$is_deleted" = 1 ] || size=$blob_size
  non_nul_size=$(git cat-file blob "$oid" | LC_ALL=C tr -d '\000' | wc -c) ||
    stop unsupported-index-entry "stage: cannot inspect blob: $path"
  [ "$non_nul_size" -eq "$blob_size" ] || is_binary=1
  has_path "$path" "${binary_paths[@]}" && is_binary=1
  case "$path" in *.png | *.jpg | *.jpeg | *.gif | *.webp | *.ico | *.pdf | *.zip | *.gz | *.woff* | *.ttf | *.mp4 | *.mp3 | *.exe | *.dll) is_binary=1 ;; esac
  wrapped="/$path/"
  group=0
  case "$wrapped" in
    */dist/* | */build/* | */coverage/* | */node_modules/* | */test-results/*) group=3 ;;
    */fixtures/* | */__fixtures__/* | */snapshots/* | */__snapshots__/* | *-snapshots/*) group=2 ;;
    */package-lock.json/ | */yarn.lock/ | */pnpm-lock.yaml/ | */cargo.lock/ | */poetry.lock/ | */uv.lock/ | */gemfile.lock/ | */composer.lock/ | */go.sum/) group=5 ;;
    */config/* | */.github/* | */.claude/* | */.env*/ | */.*rc/ | */*.config.*/ | */*.json/ | */*.yaml/ | */*.yml/ | */*.toml/ | */*.ini/) group=6 ;;
    */tests/* | */test/* | */*.test.*/ | */*.spec.*/) group=1 ;;
    *) [ "$is_binary" = 0 ] || group=4 ;;
  esac
  has_path "$path" "${planned[@]}" || flag='unplanned'
  [ "$is_binary" = 0 ] || { flag="${flag:+$flag, }binary"; binary_count=$((binary_count + 1)); binary_bytes=$((binary_bytes + size)); }
  [ "$group" != 3 ] || flag="${flag:+$flag, }generated"
  case "$wrapped" in */*.log/ | */.env*/ | */dist/* | */node_modules/* | */.claude/* | */test-results/*) flag="${flag:+$flag, }do-not-commit" ;; esac
  counts[group]=$((counts[group] + 1)) totals[group]=$((totals[group] + size)) total_bytes=$((total_bytes + size))
  new_count=$((new_count + is_new)) new_bytes=$((new_bytes + is_new * size))
  file_groups+=("$group") sizes+=("$size") flags+=("$flag")
  reason=''
  for ((i = 0; i < ${#reason_paths[@]}; i++)); do
    [ "$path" != "${reason_paths[$i]}" ] || reason=${reason_texts[$i]}
  done
  explanations+=("$reason")
done

html_text() {
  local text=$1
  text=${text//&/\&amp;} text=${text//</\&lt;} text=${text//>/\&gt;} text=${text//|/\&#124;}
  printf '%s' "$text"
}
missing=()
{
  printf "## What's in the commit\n\n%d files, %d indexed bytes.\n\n" "${#paths[@]}" "$total_bytes"
  printf '| Group | Files | Bytes |\n| --- | ---: | ---: |\n'
  for ((i = 0; i < ${#groups[@]}; i++)); do
    [ "${counts[$i]}" -gt 0 ] || continue
    printf '| %s | %d | %d |\n' "${groups[$i]}" "${counts[$i]}" "${totals[$i]}"
  done
  [ "$binary_count" -eq 0 ] || printf '\nbinaries %d files / %d bytes.\n' "$binary_count" "$binary_bytes"
  [ "$new_count" -eq 0 ] || printf '\nnew files %d / %d bytes.\n' "$new_count" "$new_bytes"
  printf '\n| File | Group | Bytes | Review |\n| --- | --- | ---: | --- |\n'
  for ((i = 0; i < ${#paths[@]}; i++)); do
    group=${file_groups[$i]}
    [ "${totals[$group]}" -le 10485760 ] || flags[i]="${flags[$i]:+${flags[$i]}, }large-group"
    if [ -n "${flags[$i]}" ] && [ -z "${explanations[$i]}" ]; then missing+=("${paths[$i]}"); fi
    note=${flags[$i]}
    [ -z "${explanations[$i]}" ] || note="${note:+$note: }${explanations[$i]}"
    printf '| <code>%s</code> | %s | %d | %s |\n' "$(html_text "${paths[$i]}")" "${groups[$group]}" "${sizes[$i]}" "$(html_text "${note:--}")"
  done
} >"$stage_tmp/report"
[ "$(git write-tree)" = "$tree" ] || stop index-changed 'stage: index changed during review; repeat the audit'
report="$run_dir/staging-report.md"
[ ! -L "$report" ] || stop unsafe-report 'stage: report path is a symlink; refusing to overwrite it'
mv -- "$stage_tmp/report" "$report"
emit STAGING_REPORT "$report"
cat -- "$report" >&2
if [ "${#missing[@]}" -gt 0 ]; then
  git --literal-pathspecs restore --staged -- "${missing[@]}" || stop unstage-failed 'stage: cannot unstage unexplained files; inspect the index'
  stop unexplained-files 'stage: unexplained flagged files were unstaged; add exact-path reasons or remove them from the declaration, then review again.'
fi
if [ "$action" = commit ]; then
  [ "$(git write-tree)" = "$tree" ] || stop index-changed 'stage: index changed before commit; repeat the audit'
  git commit --message "$message" >&2 || stop commit-failed 'stage: commit failed; inspect hook output and retry the audit'
  [ "$(git rev-parse 'HEAD^{tree}')" = "$tree" ] || stop commit-tree-changed 'stage: a hook or concurrent writer changed the commit tree; review that commit before pushing.'
  emit COMMIT "$(git rev-parse HEAD)"
fi
done_ok
