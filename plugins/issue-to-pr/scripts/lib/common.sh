#!/usr/bin/env bash

_ITP_OUT_KEYS=()
_ITP_OUT_VALS=()

emit() {
  _ITP_OUT_KEYS+=("$1")
  _ITP_OUT_VALS+=("${2-}")
}

flush_output() {
  local i
  for ((i = 0; i < ${#_ITP_OUT_KEYS[@]}; i++)); do
    printf '%s=%s\n' "${_ITP_OUT_KEYS[$i]}" "${_ITP_OUT_VALS[$i]}"
  done
}

stop() { # reason [hint]: exit 2, nothing irreversible happened
  emit STOP_REASON "$1"
  shift
  flush_output
  [ "$#" -gt 0 ] && printf '%s\n' "$*" >&2
  exit 2
}

degrade() { # reason [hint]: exit 4, the call itself was wrong
  emit DEGRADED_REASON "$1"
  shift
  flush_output
  [ "$#" -gt 0 ] && printf '%s\n' "$*" >&2
  exit 4
}

done_ok() {
  flush_output
  exit 0
}

warn() { printf '%s\n' "$*" >&2; }

repo_root() { # the one place every worktree of this clone agrees on
  local r
  r=$(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -1)
  if [ -n "$r" ] && [ -e "$r/.git" ]; then printf '%s' "$r"; return 0; fi
  # a bare clone has no main checkout; its worktrees share the common dir instead
  git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || printf ''
}

assert_numeric_issue() { # the issue number ends up in a path cleanup rm -rf's
  case "$1" in
    '' | *[!0-9]*) degrade invalid-issue "${2:-script}: issue must be a number, got '$1'" ;;
  esac
}

state_dir() { printf '%s/.claude/issue-to-pr' "$1"; }

ensure_state_dir() { # default ignore for the state root; preserve project-owned rules
  local dir=$1 gi="$1/.gitignore" tmp
  mkdir -p "$dir" 2>/dev/null || return 1
  [ -e "$gi" ] && return 0
  tmp="$gi.tmp.$$"
  if ! printf '%s\n' \
    '# issue-to-pr keeps its runtime state here: config, gate receipts, logs.' \
    '# The star is first so anything you add below can still be un-ignored with a ! rule.' \
    '*' 2>/dev/null >"$tmp" || ! mv "$tmp" "$gi" 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null
    return 1
  fi
  return 0
}

runtime_dir() { # Git metadata is shared by the main checkout, linked worktrees, and bare clones.
  local common
  common=$(git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 1
  printf '%s/issue-to-pr' "$common"
}

legacy_branch_dir() {
  printf '%s/run-%s' "$(state_dir "$1")" "$(printf '%s' "$2" | sed 's/-/--/g; s|/|-s|g')"
}

branch_dir() { # Reuse active legacy runs until cleanup; new runs stay outside the source tree.
  local legacy runtime
  legacy=$(legacy_branch_dir "$1" "$2")
  if [ -e "$legacy" ] || [ -L "$legacy" ]; then printf '%s' "$legacy"; return 0; fi
  runtime=$(runtime_dir "$1") || return 1
  printf '%s/%s' "$runtime" "${legacy##*/}"
}

assert_run_dir_safe() { # checkout branch [ref]: refuse redirected or versioned run state
  local dir tracked runtime legacy
  local query=(ls-files)
  legacy=$(legacy_branch_dir "$1" "$2")
  runtime=$(runtime_dir "$1") || stop state-unreadable "issue-to-pr: cannot locate Git metadata in $1"
  if [ -L "$1/.claude" ] || [ -L "$(state_dir "$1")" ] ||
    [ -L "$legacy" ] || [ -L "$runtime" ] ||
    [ -L "$runtime/${legacy##*/}" ]; then
    stop unsafe-state-dir "issue-to-pr: a state path in $1 is a symlink; refusing writes or cleanup outside its owned directory."
  fi
  dir=".claude/issue-to-pr/${legacy##*/}"
  [ -z "${3:-}" ] || query=(ls-tree -r --name-only "$3")
  tracked=$(git -C "$1" "${query[@]}" -- "$dir") ||
    stop state-unreadable "issue-to-pr: cannot inspect tracked run state in $1 ${3:-index}"
  if [ -n "$tracked" ]; then
    warn "$tracked"
    stop tracked-run-state "issue-to-pr: run state is tracked in $1 ${3:-index}. Offer targeted git rm --cached -- <paths> after approval; keep the working files and history."
  fi
}

ensure_run_dir() { # root branch: protect the existing run namespace before any artifact write
  local dir gi
  assert_run_dir_safe "$1" "$2"
  dir=$(branch_dir "$1" "$2") || return 1
  if [ "$dir" != "$(legacy_branch_dir "$1" "$2")" ]; then
    mkdir -p "$dir" 2>/dev/null
    return $?
  fi
  gi="$dir/.gitignore"
  ensure_state_dir "$(state_dir "$1")" || return 1
  mkdir -p "$dir" 2>/dev/null || return 1
  [ ! -L "$gi" ] || return 1
  # The lower-level rule wins over parent exceptions without editing project ignore rules.
  [ -f "$gi" ] && [ "$(tail -n 1 "$gi")" = '*' ] && return 0
  printf '\n*\n' >>"$gi" 2>/dev/null
}

receipt_path() { printf '%s/receipt.json' "$(branch_dir "$1" "$2")"; }

json_escape() {
  local s=${1-}
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/\\r}
  s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

receipt_write() { # root branch head_sha gates
  local dir
  dir=$(branch_dir "$1" "$2")
  ensure_run_dir "$1" "$2" || return 1
  [ ! -L "$dir/receipt.json" ] || return 1
  printf '{"branch":"%s","head_sha":"%s","gates":"%s","created_at":"%s"}\n' \
    "$(json_escape "$2")" "$(json_escape "$3")" "$(json_escape "$4")" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$dir/receipt.json"
}

json_str_field() { # file key -> the string value, or empty
  grep -oE "\"$2\":\"[^\"]*\"" "$1" 2>/dev/null | head -1 | sed -E "s/.*\"$2\":\"([^\"]*)\".*/\1/"
}

config_line() { # root key -> the value of one top-level frontmatter line, or empty
  # a trailing " #..." comment is punctuation, not value: left in, it reaches the globs as a junk
  # pattern. No file or no key is no value (rc 0); an unreadable file or a key with an empty value
  # (a YAML block list) is rc 1, so the caller can fail closed instead of reading "nothing set".
  local f value
  f="$(state_dir "$1")/config.md"
  [ -f "$f" ] || return 0
  value=$(sed -n "s/^$2:[[:space:]]*/=/p" "$f" 2>/dev/null) || return 1
  [ -n "$value" ] || return 0
  value=${value%%$'\n'*}
  value=${value%$'\r'}
  value=$(printf '%s' "${value#=}" | sed -E 's/[[:space:]]+#.*$//')
  [ -n "$value" ] || return 1
  printf '%s' "$value"
}

cr_status() { # sha -> CodeRabbit's commit status on it as state<TAB>description, empty if none; rc 1 unreadable
  gh api "repos/{owner}/{repo}/commits/$1/status" \
    --jq 'first(.statuses[] | select(.context == "CodeRabbit") | "\(.state)\t\(.description // "")") // empty'
}

open_threads() { # PR node id -> each unresolved review thread as id<TAB>author<TAB>path<TAB>url; rc 1 unreadable
  # shellcheck disable=SC2016 # $id and $endCursor are GraphQL variables
  gh api graphql --paginate -f id="$1" \
    -f query='query($id:ID!,$endCursor:String){node(id:$id){... on PullRequest{reviewThreads(first:100,after:$endCursor){pageInfo{hasNextPage endCursor} nodes{id isResolved path comments(first:1){nodes{author{login} url}}}}}}}' \
    --jq '.data.node.reviewThreads.nodes[] | select(.isResolved | not) | [.id, (.comments.nodes[0].author.login // ""), (.path // ""), (.comments.nodes[0].url // "")] | @tsv'
}

tier_rank() { # trivial|standard|complex|none -> 1|2|3|0, anything else -> empty
  case "$1" in trivial) printf 1 ;; standard) printf 2 ;; complex) printf 3 ;; none) printf 0 ;; *) printf '' ;; esac
}
