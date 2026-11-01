#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=${BASH_SOURCE[0]%/*}
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

# bots.sh wait    <PR> [--request-codex]   wait for the review bots on the PR head, one slice per call
# bots.sh threads <PR>                     the PR's unresolved review threads
# bots.sh reply   <thread-id> --body-file <f>   answer a thread, then resolve it
# Nothing here is irreversible; the merge gate in finish.sh is what holds.
subcmd=${1:-}
shift || true
target="" body_file="" request_codex=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --request-codex) request_codex=1; shift ;;
    --body-file) body_file=${2:-}; shift 2 2>/dev/null || shift "$#" ;;
    -*) degrade unknown-flag "bots: unknown flag '$1'" ;;
    *) [ -z "$target" ] && target=$1; shift ;;
  esac
done
[ -n "$target" ] || degrade missing-target "bots: $subcmd needs a PR number or a thread id"

readonly MARKER='<!-- issue-to-pr -->' CX='chatgpt-codex-connector[bot]'
# one call ends well inside a default two-minute tool call; the model calls again on WAIT_MORE
SLICE=${ITP_BOTS_SLICE:-90}
readonly POLL=30 GRACE=240 LIMIT=1200

now() { date +%s; }

pr_ctx() { # -> head, pr_branch, pr_id of PR $target, or stop
  head="" pr_branch="" pr_id=""
  assert_numeric_issue "$target" bots
  IFS=$'\t' read -r head pr_branch pr_id < <(gh pr view "$target" --json headRefOid,headRefName,id \
    --jq '"\(.headRefOid)\t\(.headRefName)\t\(.id)"' 2>/dev/null)
  if [ -z "$head" ] || [ -z "$pr_id" ]; then
    stop pr-unreadable "issue-to-pr: could not read PR #$target. Check it exists and gh is authenticated."
  fi
}

cmd_threads() {
  local threads t
  pr_ctx
  threads=$(open_threads "$pr_id" 2>/dev/null) ||
    stop threads-unprovable "issue-to-pr: could not read the review threads of PR #$target."
  while IFS= read -r t; do [ -z "$t" ] || emit THREAD "$t"; done <<<"$threads"
  done_ok
}

cmd_reply() {
  local body url
  [ -f "$body_file" ] || degrade missing-body "bots: reply needs --body-file <file>"
  body=$(cat "$body_file")$'\n\n'$MARKER
  # shellcheck disable=SC2016 # $t and $b are GraphQL variables
  url=$(gh api graphql -f t="$target" -f b="$body" \
    -f query='mutation($t:ID!,$b:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$t,body:$b}){comment{url}}}' \
    --jq '.data.addPullRequestReviewThreadReply.comment.url // empty' 2>/dev/null)
  # resolving without the answer would clear the merge gate with nothing said
  [ -n "$url" ] || stop reply-failed "issue-to-pr: the reply to $target did not post, so the thread stays open. Check gh auth and the thread id."
  emit REPLIED "$url"
  # shellcheck disable=SC2016 # $t is a GraphQL variable
  gh api graphql -f t="$target" -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' \
    --jq '.data.resolveReviewThread.thread.isResolved' 2>/dev/null | grep -qx true ||
    stop resolve-failed "issue-to-pr: replied to $target but could not resolve it. Resolve it on GitHub."
  done_ok
}

# One tick: CodeRabbit reports as a commit status; Codex only answers our own request comment, so
# everything about it is keyed to that comment's id. -> cr_state, cr_desc, cx; rc 1 unreadable.
snapshot() {
  local st reviews said seen
  st=$(cr_status "$head" 2>/dev/null) || return 1
  IFS=$'\t' read -r cr_state cr_desc <<<"$st"
  cx=""
  [ -n "$rid" ] || return 0
  reviews=$(gh api "repos/{owner}/{repo}/pulls/$target/reviews?per_page=100" --paginate \
    --jq '.[] | select(.user.login == "'"$CX"'" and .commit_id == "'"$head"'") | .id' 2>/dev/null) || return 1
  said=$(gh api "repos/{owner}/{repo}/issues/$target/comments?per_page=100" --paginate \
    --jq '.[] | select(.user.login == "'"$CX"'" and .id > '"$rid"') | .body' 2>/dev/null) || return 1
  seen=$(gh api "repos/{owner}/{repo}/issues/comments/$rid/reactions" \
    --jq '.[] | select(.user.login == "'"$CX"'") | .content' 2>/dev/null) || return 1
  # its other replies (an environment to set up, a quota) are read in triage, not classified here
  # reactions are whole words; a reply's text only counts for its verdict
  case "$reviews" in ?*) cx="done" ;; esac
  case "$said" in *"major issues"*) cx="done" ;; esac
  case " ${seen//$'\n'/ } " in
    *" +1 "*) cx="done" ;;
    *" eyes "*) [ -n "$cx" ] || cx="wait" ;;
  esac
}

cmd_wait() {
  local root state since rid="" h s i t n fails=0 slice_end cr cx cr_state cr_desc
  pr_ctx
  root=$(repo_root)
  [ -n "$root" ] || degrade not-a-git-repo "bots: not inside a git repository"
  state="$(branch_dir "$root" "$pr_branch")/bots"
  if ! ensure_run_dir "$root" "$pr_branch"; then
    degrade state-unwritable "bots: cannot write $state"
  fi
  [ ! -L "$state" ] || stop unsafe-state-dir "bots: $state is a symlink; refusing redirected wait state"
  since=$(now)
  # one budget per head, shared by every call, and the Codex request it already made
  if [ -f "$state" ] && read -r h s i <"$state" && [ "$h" = "$head" ]; then since=$s rid=$i; fi
  if [ "$request_codex" = 1 ] && [ -z "$rid" ]; then
    rid=$(gh api "repos/{owner}/{repo}/issues/$target/comments" -f body="@codex review"$'\n\n'"$MARKER" --jq .id 2>/dev/null) ||
      stop request-failed "issue-to-pr: could not post '@codex review' on PR #$target."
  fi
  printf '%s %s %s\n' "$head" "$since" "$rid" >"$state"
  slice_end=$(($(now) + SLICE))
  while :; do
    n=$(now)
    t=$((n - since))
    if snapshot; then
      fails=0
      # wait on a review running or still to come; a limit, skip or pause is reported as written
      if [ "$cr_state" = pending ] || { [ -z "$cr_desc" ] && [ "$t" -lt "$GRACE" ]; }; then cr="wait"; else cr=$cr_desc; fi
      if [ -n "$rid" ] && [ -z "$cx" ]; then
        if [ "$t" -lt "$GRACE" ]; then cx="wait"; else cx="no-review"; fi
      fi
      if [ "$t" -ge "$LIMIT" ]; then
        [ "$cr" != wait ] || cr=timeout
        [ "$cx" != wait ] || cx=timeout
      fi
      [ "$cr" = wait ] || [ "$cx" = wait ] || break
    else
      fails=$((fails + 1))
      [ "$fails" -lt 3 ] || stop bots-unreadable "issue-to-pr: could not read PR #$target from GitHub three times running. Report the bots as unchecked; the merge gate still reads the threads."
    fi
    if [ $((n + POLL)) -gt "$slice_end" ]; then
      emit WAIT_MORE true
      done_ok
    fi
    sleep "$POLL"
  done
  [ -z "$cr" ] || emit BOT_coderabbit "$cr"
  [ -z "$cx" ] || emit BOT_codex "$cx"
  [ -n "$cr$cx" ] || emit BOTS none
  done_ok
}

case "$subcmd" in
  wait) cmd_wait ;;
  threads) cmd_threads ;;
  reply) cmd_reply ;;
  *) degrade unknown-subcommand "bots: expected wait, threads or reply, got '$subcmd'" ;;
esac
