#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=${BASH_SOURCE[0]%/*}
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/marker.sh
source "$SCRIPT_DIR/lib/marker.sh"

# finish.sh merge   <N> --branch <b> [--method squash|merge|rebase] [--auto <threshold> --tier <tier>]
# finish.sh cleanup <N> --branch <b> [--keep-branch]
# The two actions a run cannot take back: merging the PR and deleting its branch and worktree.
subcmd=${1:-}
shift || true
issue="" branch="" method=squash keep_branch=0 auto="" tier="" auto_given=0 tier_given=0
readonly WAIT_FOR_MERGE="Post a state=review comment on the issue that it waits for 'merge', label agent:review, and end the turn."
while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch) branch=${2:-}; shift 2 2>/dev/null || shift "$#" ;;
    --method) method=${2:-}; shift 2 2>/dev/null || shift "$#" ;;
    --keep-branch) keep_branch=1; shift ;;
    --auto) auto=${2:-}; auto_given=1; shift 2 2>/dev/null || shift "$#" ;;
    --tier) tier=${2:-}; tier_given=1; shift 2 2>/dev/null || shift "$#" ;;
    -*) degrade unknown-flag "finish: unknown flag '$1'. Ignoring it would let a mistyped --keep-branch delete the branch anyway" ;;
    *) [ -z "$issue" ] && issue=$1; shift ;;
  esac
done
[ -n "$branch" ] || degrade missing-branch "finish: --branch required"
case "$method" in squash | merge | rebase) : ;; *) degrade bad-method "finish: --method must be squash, merge or rebase, got '$method'" ;; esac
[ -n "$issue" ] || degrade missing-issue "finish: issue number required"
if [ "$auto_given" = 1 ] || [ "$tier_given" = 1 ]; then
  # presence, not value: an empty --auto would otherwise skip the guard and merge attended
  [ "$auto_given$tier_given" = 11 ] || degrade auto-needs-tier "finish: --auto and --tier go together: the threshold means nothing without the run's tier"
  [ -n "$(tier_rank "$auto")" ] || degrade bad-tier "finish: --auto must be trivial, standard, complex or none, got '$auto'"
  case "$tier" in trivial | standard | complex) : ;; *) degrade bad-tier "finish: --tier must be trivial, standard or complex, got '$tier'" ;; esac
fi
assert_numeric_issue "$issue" finish
root=$(repo_root)
[ -n "$root" ] || degrade not-a-git-repo "finish: not inside a git repository"

cmd_merge() {
  local pr head_sha decision base_ref pr_number pr_id cr threads receipt push_out merge_out default_ref base_rev globs pathspecs changed hit limits caps cap stats additions deletions files
  # reviewDecision alone is null on a base branch that does not require review, however many
  # reviews a PR has, so the reviews themselves decide and the field only confirms them
  pr=$(gh pr view "$branch" --json headRefOid,reviewDecision,latestReviews,baseRefName,number,id \
    --jq '"\(.headRefOid)\t\(if .reviewDecision == "CHANGES_REQUESTED" or any(.latestReviews[]?; .state == "CHANGES_REQUESTED") then "CHANGES_REQUESTED" else .reviewDecision // "" end)\t\(.baseRefName)\t\(.number)\t\(.id)"' 2>/dev/null) || pr=""
  # cut, not read: a tab is IFS whitespace, so read would fold an empty field into the next
  head_sha=$(printf '%s' "$pr" | cut -f1)
  decision=$(printf '%s' "$pr" | cut -f2)
  base_ref=$(printf '%s' "$pr" | cut -f3)
  pr_number=$(printf '%s' "$pr" | cut -f4)
  pr_id=$(printf '%s' "$pr" | cut -f5)
  case "$head_sha" in '' | null)
    stop pr-unreadable "issue-to-pr: could not read the PR for $branch. Check it exists and gh is authenticated, then hand back." ;;
  esac

  receipt=$(receipt_path "$root" "$branch")
  if [ ! -f "$receipt" ] || [ "$(json_str_field "$receipt" head_sha)" != "$head_sha" ]; then
    stop gates-unverified "issue-to-pr: no green gate receipt for ${head_sha:0:12}. Repeat run/SKILL.md Steps 5-7 on this head, then re-approve."
  fi
  case ",$(json_str_field "$receipt" gates)," in
    *,test,*) : ;;
    *) stop gates-unverified "issue-to-pr: the receipt for ${head_sha:0:12} covers '$(json_str_field "$receipt" gates)', not the test gate (a smoke or install run overwrites it). Run the full gate set on this head, then re-approve." ;;
  esac
  [ "$decision" != CHANGES_REQUESTED ] ||
    stop review-blocked "issue-to-pr: $branch has a review requesting changes. Address it, push, re-run the gates, and re-approve."
  # the review bots' findings: a CodeRabbit review still running on the head (a limit, skip or
  # pause reports success), then every unresolved thread. A status that never moves is the
  # livelock hand-back. ponytail: a thread opened between this read and the merge seconds later
  # slips through; GitHub's "require conversation resolution" rule closes that where a plan has it
  if ! cr=$(cr_status "$head_sha" 2>/dev/null) || ! threads=$(open_threads "$pr_id" 2>/dev/null); then
    stop threads-unprovable "issue-to-pr: could not read the reviews of PR #$pr_number, so none can be shown answered. Check gh is authenticated, then re-run."
  fi
  case "$cr" in pending*)
    stop bots-pending "issue-to-pr: CodeRabbit is still reviewing ${head_sha:0:12}. Run S/bots.sh wait $pr_number, triage what it posts as run/SKILL.md Step 7 says, then re-run the merge." ;;
  esac
  if [ -n "$threads" ]; then
    printf '%s\n' "$threads" | cut -f2,4 >&2 # author, url: the next move differs for a person
    stop review-threads-open "issue-to-pr: PR #$pr_number has unresolved review threads (above). Answer the bots' threads as run/SKILL.md Step 7 says (S/bots.sh reply); a person's thread is theirs to resolve, so report it and wait. A fix commit is a new head: repeat Steps 5-7 and re-approve."
  fi
  headless_guard "$pr_number"

  if [ -n "$auto" ]; then
    [ "$(tier_rank "$tier")" -le "$(tier_rank "$auto")" ] ||
      stop auto-tier "issue-to-pr: a $tier run does not merge unattended under an --auto-merge $auto threshold. $WAIT_FOR_MERGE"
    if git rev-parse --verify -q "origin/$base_ref^{commit}" >/dev/null; then base_rev="origin/$base_ref"
    elif git rev-parse --verify -q "$base_ref^{commit}" >/dev/null; then base_rev=$base_ref
    else stop auto-unprovable "issue-to-pr: neither origin/$base_ref nor $base_ref resolves here, so the human-path check cannot read the diff. Fetch the base and re-run."
    fi
    limits=$(config_line "$root" auto_merge_limits) ||
      stop auto-unprovable "issue-to-pr: auto_merge_limits must contain four positive integers. $WAIT_FOR_MERGE"
    if [ -n "$limits" ]; then
      read -ra caps <<<"$limits"
      [ "${#caps[@]}" -eq 4 ] ||
        stop auto-unprovable "issue-to-pr: auto_merge_limits needs changed-lines files factor growth. $WAIT_FOR_MERGE"
      for cap in "${caps[@]}"; do
        [[ "$cap" =~ ^[1-9][0-9]{0,8}$ ]] ||
          stop auto-unprovable "issue-to-pr: auto_merge_limits needs positive integers of at most nine digits. $WAIT_FOR_MERGE"
      done
      git fetch --no-tags --no-prune origin "$base_ref" >/dev/null 2>&1 ||
        stop auto-unprovable "issue-to-pr: could not refresh the PR base to measure its diff. $WAIT_FOR_MERGE"
      base_rev=$(git rev-parse --verify 'FETCH_HEAD^{commit}') ||
        stop auto-unprovable "issue-to-pr: fetched PR base is unreadable. $WAIT_FOR_MERGE"
      stats=$(git -C "$root" diff --no-renames --numstat "$base_rev...$branch" |
        awk -F '\t' '
          NF < 3 || $1 !~ /^[0-9]+$/ || $2 !~ /^[0-9]+$/ { bad=1; next }
          { additions+=$1; deletions+=$2; files++ }
          END { if (bad) exit 1; printf "%.0f %.0f %.0f\n", additions, deletions, files }
        ') || stop auto-unprovable "issue-to-pr: diff size is unreadable or contains binary files. $WAIT_FOR_MERGE"
      read -r additions deletions files <<<"$stats"
      emit DIFF_ADDITIONS "$additions"
      emit DIFF_DELETIONS "$deletions"
      emit DIFF_FILES "$files"
      if (( additions + deletions > caps[0] || files > caps[1] ||
            (additions > caps[2] * deletions && additions - deletions > caps[3]) )); then
        stop auto-diff-limit "issue-to-pr: +$additions -$deletions across $files files exceeds auto_merge_limits ($limits). $WAIT_FOR_MERGE"
      fi
    fi
    # the diff runs over the local branch: the fixture's constant sha never resolves, and the
    # receipt plus --match-head-commit already bind the merge to head_sha.
    globs=$(config_line "$root" human_paths) ||
      stop auto-unprovable "issue-to-pr: human_paths in .claude/issue-to-pr/config.md is unreadable or empty on its line; put the globs on that line or delete the key, then re-run."
    case "$globs" in *[\"\'[]* | -*)
      stop auto-unprovable "issue-to-pr: human_paths must be one line of bare space-separated globs, no quotes, no YAML list (got: $globs); fix the config and re-run." ;;
    esac
    pathspecs=()
    read -ra pathspecs <<<"$globs"   # read never globs, so the shell cannot expand them
    changed=$(git -C "$root" diff --no-renames --name-only "$base_rev...$branch" 2>/dev/null) ||
      stop auto-unprovable "issue-to-pr: could not read the diff $base_rev...$branch, so the merge cannot be proved safe. Fetch the base and re-run."
    [ -n "$changed" ] ||
      stop auto-diff-empty "issue-to-pr: the diff $base_rev...$branch is empty, so the human-path check has nothing to prove; a PR with no diff against its base does not merge unattended. $WAIT_FOR_MERGE"
    if [ "${#pathspecs[@]}" -gt 0 ]; then
      hit=$(git -C "$root" diff --no-renames --name-only "$base_rev...$branch" -- "${pathspecs[@]}" 2>/dev/null) ||
        stop auto-unprovable "issue-to-pr: git rejected human_paths as pathspecs ($globs); fix the config and re-run."
      [ -z "$hit" ] || {
        emit HUMAN_PATH "${hit%%$'\n'*}"
        stop auto-human-path "issue-to-pr: ${hit%%$'\n'*} matches human_paths; this PR waits for a human 'merge'. $WAIT_FOR_MERGE"
      }
    fi
  fi

  if ! push_out=$(git push origin "$branch" 2>&1); then
    emit PUSH_ERROR "$(printf '%s' "$push_out" | tr '\n' ' ')"
    stop push-rejected "issue-to-pr: git push was rejected. The remote branch moved under you: fetch, look at what landed, and re-approve rather than assuming the approval still covers the diff you showed."
  fi
  if ! merge_out=$(gh pr merge "$branch" "--$method" --match-head-commit "$head_sha" 2>&1); then
    emit MERGE_ERROR "$(printf '%s' "$merge_out" | tr '\n' ' ')"
    stop merge-failed "issue-to-pr: gh pr merge refused; report MERGE_ERROR verbatim. If it says this merge method is not allowed, re-run once with --method merge (then rebase). If checks are still pending, 'gh pr checks $branch --watch', then re-run. The same refusal a third time is a livelock: hand back."
  fi
  emit MERGED true
  emit MERGE_METHOD "$method"
  emit MERGED_INTO "$base_ref"
  default_ref=$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null || printf '')
  if [ -z "$base_ref" ] || [ -z "$default_ref" ]; then
    emit BASE_IS_DEFAULT unknown
  elif [ "$base_ref" != "$default_ref" ]; then
    emit BASE_IS_DEFAULT false
    emit WARN_NON_DEFAULT_BASE "merged into '$base_ref', not '$default_ref' - the issue stays open and this work has NOT reached the default branch"
  else
    emit BASE_IS_DEFAULT true
  fi
  done_ok
}

row() { # comment TSV line -> R_ID R_LOGIN R_MARKER R_BODY; rc 1 on a row with no numeric id
  local l=${1%$'\r'}
  R_ID=${l%%$'\t'*}
  l=${l#*$'\t'}
  R_LOGIN=${l%%$'\t'*}
  l=${l#*$'\t'}
  R_MARKER=${l%%$'\t'*}
  R_BODY=${l#*$'\t'}
  case "$R_ID" in '' | *[!0-9]*) return 1 ;; esac
}

headless_guard() { # pr-number: returns on an attended merge or the owner's word for head_sha
  local labels owner rows prows line sid=0 st="" spr="" shead="" wid=0 word=""
  labels=$(gh issue view "$issue" --json labels --jq '.labels[].name | ascii_downcase' 2>/dev/null) ||
    stop headless-unprovable "issue-to-pr: could not read the labels of issue #$issue, so whether this merge is headless is unknown. Check gh is authenticated, then re-run."
  # ponytail: headless = --auto, or any of agent:running|waiting|review (Step 0 and the dispatcher set one
  # before any work); a plain merge on an issue that lost all three merges attended-style
  # ponytail: same token: the agent posts as the owner's gh login, so this proves an unmarked comment by that login, not a human's hand;
  # a prompt-injected agent could post 'merge' itself or drop the agent:* labels. Upgrade path: a separate token for the agent.
  [ -n "$auto" ] || case $'\n'"${labels//$'\r'/}"$'\n' in
    *$'\n'agent:running$'\n'* | *$'\n'agent:waiting$'\n'* | *$'\n'agent:review$'\n'*) ;;
    *) return 0 ;;
  esac
  owner=$(gh api user --jq .login 2>/dev/null) || owner=""
  owner=${owner%$'\r'}
  [ -n "$owner" ] ||
    stop headless-unprovable "issue-to-pr: could not read the owner's login (gh api user), so no comment can authorize a headless merge of issue #$issue. Check gh is authenticated, then re-run."
  rows=$(gh api "repos/{owner}/{repo}/issues/$issue/comments" --paginate --jq "$MARKER_JQ" 2>/dev/null) ||
    stop headless-unprovable "issue-to-pr: could not read the comments on issue #$issue, so the run's state is unknown. Check gh is authenticated, then re-run."
  while IFS= read -r line; do
    row "$line" || continue
    [ "$R_LOGIN" = "$owner" ] || continue
    if ! parse_marker "$R_MARKER"; then
      [ -z "$R_MARKER" ] || [ "$R_MARKER" = '<!-- issue-to-pr -->' ] ||
        stop headless-unprovable "issue-to-pr: the owner's comment $R_ID on issue #$issue ends in a marker that does not parse ($R_MARKER), so the run's state is unknown. Fix or delete that comment, then re-run."
      continue
    fi
    sid=$R_ID st=$M_STATE spr=$M_PR shead=$M_HEAD
  done <<<"$rows"

  if [ -n "$auto" ]; then
    [ -z "$st" ] ||
      stop auto-prior-state "issue-to-pr: issue #$issue already stopped once, so this PR waits for the owner's 'merge'. $WAIT_FOR_MERGE"
    return 0
  fi
  if [ "$st" != review ] || [ -z "$1" ] || [ "$spr" != "$1" ] || [ "$shead" != "$head_sha" ]; then
    stop headless-unapproved "issue-to-pr: a headless merge needs a state=review report for PR #$1 at ${head_sha:0:12}, and the current state of issue #$issue is not that (state=${st:-none} pr=${spr:-none} head=${shead:0:12}). Post that report (pr=$1 head=$head_sha) on the issue, label agent:review, and end the turn. If this is an attended run, remove the agent:* labels from issue #$issue and re-run."
  fi
  prows=$(gh api "repos/{owner}/{repo}/issues/$1/comments" --paginate --jq "$MARKER_JQ" 2>/dev/null) ||
    stop headless-unprovable "issue-to-pr: could not read the conversation of PR #$1, so the owner's word on it is unknown. Check gh is authenticated, then re-run."
  while IFS= read -r line; do
    row "$line" || continue
    if [ "$R_LOGIN" = "$owner" ] && [ -z "$R_MARKER" ] && [ "$R_ID" -gt "$sid" ] && [ "$R_ID" -gt "$wid" ]; then
      wid=$R_ID word=$R_BODY
    fi
  done <<<"$rows"$'\n'"$prows"
  case "$word" in merge | мерж | Мерж | МЕРЖ) return 0 ;; esac # jq's ascii_downcase leaves Cyrillic as typed
  stop headless-unapproved "issue-to-pr: the owner's newest word after the report for ${head_sha:0:12} is not 'merge' (${word:-nothing yet}). Answer it in a new state=review comment (pr=$1 head=$head_sha) on the issue, label agent:review, and end the turn. If this is an attended run, remove the agent:* labels from issue #$issue and re-run."
}

registered_wt() { # the registered worktree on --branch, else the one ending in /issue-<N>, else empty
  local list by_branch
  list=$(git -C "$root" worktree list --porcelain 2>/dev/null) || return 1
  by_branch=$(printf '%s\n' "$list" | awk -v b="refs/heads/$branch" '/^worktree /{p=substr($0,10)} $1=="branch" && $2==b {print p; exit}')
  if [ -n "$by_branch" ]; then printf '%s\n' "$by_branch"; return 0; fi
  printf '%s\n' "$list" | sed -n 's/^worktree //p' | grep -E "/issue-$issue\$" | head -1 || true
}

remove_worktree() { # path -> REMOVED, LEFTOVER; stops on a dirty tree, never forces
  local wt=$1 status registered
  REMOVED=false
  LEFTOVER=""
  [ "$wt" != "$root" ] || { REMOVED=true; return 0; } # in-place cleanup keeps the main checkout
  if [ ! -e "$wt" ]; then
    git -C "$root" worktree prune 2>/dev/null
    REMOVED=true
    return 0
  fi
  if git -C "$root" worktree remove "$wt" 2>/dev/null; then
    REMOVED=true
    return 0
  fi
  registered=$(registered_wt) || stop worktree-list-failed "could not list registered worktrees - refusing cleanup"
  if [ -z "$registered" ]; then
    git -C "$root" worktree prune 2>/dev/null
    LEFTOVER=$wt
    return 0
  fi
  status=$(git -C "$wt" status --porcelain --untracked-files=all 2>/dev/null || printf '')
  if [ -n "$status" ]; then
    emit DIRTY_FILES "$(printf '%s' "$status" | tr '\n' ';')"
    stop dirty-tracked-files "worktree $wt has tracked or unexpected changes - not removing"
  fi
  LEFTOVER=$wt
}

cmd_cleanup() {
  local pr_state dependents wt_path wt_branch def deleted_local=false deleted_remote=false
  assert_run_dir_safe "$root" "$branch"
  if [ "$keep_branch" -eq 0 ]; then
    if git -C "$root" show-ref --verify --quiet "refs/heads/$branch"; then
      assert_run_dir_safe "$root" "$branch" "refs/heads/$branch"
    fi
    pr_state=$(gh pr view "$branch" --json state --jq .state 2>/dev/null || printf '')
    [ "$pr_state" = MERGED ] || stop pr-not-merged "PR for $branch is '${pr_state:-unknown}', not MERGED - refusing cleanup"
    dependents=$(gh pr list --base "$branch" --state open --json number --jq '[.[].number] | join(", ")' 2>/dev/null) ||
      stop dependents-unreadable "could not read whether an open PR is based on $branch - check on GitHub, then delete the branch by hand"
    [ -z "$dependents" ] || stop base-of-open-pr "$branch is the base of open PR(s) $dependents - retarget or merge them before deleting it"
  fi

  wt_path=$(registered_wt) || stop worktree-list-failed "could not list registered worktrees - refusing cleanup"
  if [ -n "$wt_path" ] && [ -e "$wt_path" ]; then
    wt_branch=$(git -C "$wt_path" symbolic-ref --quiet --short HEAD 2>/dev/null || printf '')
    [ "$wt_branch" = "$branch" ] ||
      stop worktree-branch-mismatch "worktree $wt_path is on '${wt_branch:-detached or unreadable}', expected '$branch' - refusing cleanup"
    assert_run_dir_safe "$wt_path" "$branch"
  fi
  [ -n "$wt_path" ] || wt_path="$(dirname "$root")/$(basename "$root")-worktrees/issue-$issue"
  cd "$root" 2>/dev/null || true
  remove_worktree "$wt_path"
  emit REMOVED "$REMOVED"
  if [ "$keep_branch" -eq 1 ]; then
    emit KEPT branch-and-pr
    [ -n "$LEFTOVER" ] && emit LEFTOVER_DIR "$LEFTOVER"
    done_ok
  fi

  if [ "$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || printf '')" = "$branch" ]; then
    def=$(git -C "$root" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')
    if [ -n "$def" ] && [ "$def" != "$branch" ]; then
      git -C "$root" switch "$def" >/dev/null 2>&1 || git -C "$root" checkout --detach >/dev/null 2>&1
    else
      git -C "$root" checkout --detach >/dev/null 2>&1
    fi
  fi
  assert_run_dir_safe "$root" "$branch"
  if git -C "$root" show-ref --verify --quiet "refs/heads/$branch" && git -C "$root" branch -D "$branch" >/dev/null 2>&1; then
    deleted_local=true
  fi
  if git -C "$root" push origin --delete "$branch" >/dev/null 2>&1; then
    deleted_remote=true
  fi
  rm -rf "$(branch_dir "$root" "$branch")" 2>/dev/null

  emit DELETED_LOCAL "$deleted_local"
  emit DELETED_REMOTE "$deleted_remote"
  [ -n "$LEFTOVER" ] && emit LEFTOVER_DIR "$LEFTOVER"
  done_ok
}

case "$subcmd" in
  merge) cmd_merge ;;
  cleanup) cmd_cleanup ;;
  *) degrade unknown-subcommand "finish: subcommand required (merge|cleanup), got '$subcmd'" ;;
esac
