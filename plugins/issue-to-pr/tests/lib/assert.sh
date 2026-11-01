#!/usr/bin/env bash

assert_eq() { # expected actual [msg]
  if [ "$1" != "$2" ]; then
    printf '  ASSERT FAILED: %s\n    expected: [%s]\n    actual:   [%s]\n' \
      "${3:-assert_eq}" "$1" "$2" >&2
    exit 1
  fi
}

assert_contains() { # haystack needle [msg]
  case "$1" in
    *"$2"*) : ;;
    *)
      printf '  ASSERT FAILED: %s\n    string:  [%s]\n    missing: [%s]\n' \
        "${3:-assert_contains}" "$1" "$2" >&2
      exit 1
      ;;
  esac
}

assert_not_contains() { # haystack needle [msg]
  case "$1" in
    *"$2"*)
      printf '  ASSERT FAILED: %s\n    string:      [%s]\n    should lack: [%s]\n' \
        "${3:-assert_not_contains}" "$1" "$2" >&2
      exit 1
      ;;
    *) : ;;
  esac
}

assert_key() {
  local out=$1 key=$2 exp=$3 msg=${4:-assert_key}
  local line val found=0
  while IFS= read -r line; do
    case "$line" in "$key="*) found=1; break ;; esac
  done <<<"$out"
  if [ "$found" = 0 ]; then
    printf '  ASSERT FAILED: %s\n    key not found: %s\n    output:\n%s\n' "$msg" "$key" "$out" >&2
    exit 1
  fi
  val=${line#*=}
  if [ "$val" != "$exp" ]; then
    printf '  ASSERT FAILED: %s\n    key: %s\n    expected: [%s]\n    actual:   [%s]\n' \
      "$msg" "$key" "$exp" "$val" >&2
    exit 1
  fi
}

assert_key_present() {
  local line found=0
  while IFS= read -r line; do
    case "$line" in "$2="*) found=1; break ;; esac
  done <<<"$1"
  if [ "$found" = 0 ]; then
    printf '  ASSERT FAILED: %s\n    key not present: %s\n    output:\n%s\n' \
      "${3:-assert_key_present}" "$2" "$1" >&2
    exit 1
  fi
}

assert_rc() {
  if [ "${RC:-unset}" != "$1" ]; then
    printf '  ASSERT FAILED: %s\n    expected rc: %s\n    actual rc:   %s\n    stdout:\n%s\n    stderr:\n%s\n' \
      "${2:-assert_rc}" "$1" "${RC:-unset}" "${OUT:-}" "${ERR:-}" >&2
    exit 1
  fi
}

fail() { # msg
  printf '  FAIL: %s\n' "$*" >&2
  exit 1
}

run_script() {
  local script=$1
  shift
  local errf="$TEST_TMPDIR/.stderr"
  OUT=$(bash "$ITP_SCRIPTS/$script" "$@" 2>"$errf")
  RC=$?
  ERR=$(<"$errf")
  export OUT ERR RC
}


use_fake_gh() {
  export PATH="$FAKE_GH_DIR:$PATH"
  export FAKE_GH_SCENARIO="$1"
  export FAKE_GH_LOG="$TEST_TMPDIR/gh-invocations.log"
  : >"$FAKE_GH_LOG"
}

gh_log() {
  cat "$FAKE_GH_LOG" 2>/dev/null || true
}

assert_gh_called() {
  assert_contains "$(gh_log)" "$1" "${2:-gh should have been called with: $1}"
}

assert_gh_not_called() {
  assert_not_contains "$(gh_log)" "$1" "${2:-gh should NOT have been called with: $1}"
}

init_repo() {
  local dir=${1:-$TEST_TMPDIR/repo}
  mkdir -p "$dir"
  git -C "$dir" init -q -b main
  git -C "$dir" config user.email test@example.com
  git -C "$dir" config user.name "Test"
  git -C "$dir" config commit.gpgsign false
  printf 'seed\n' >"$dir/README.md"
  git -C "$dir" add README.md
  git -C "$dir" commit -qm "seed"
  printf '%s' "$dir"
}

legacy_run_dir_of() {
  printf '%s/.claude/issue-to-pr/run-%s' "$1" "$(printf '%s' "$2" | sed 's/-/--/g; s|/|-s|g')"
}

run_dir_of() { # root branch -> the active legacy run, or shared Git metadata.
  local legacy
  legacy=$(legacy_run_dir_of "$1" "$2")
  if [ -e "$legacy" ] || [ -L "$legacy" ]; then printf '%s' "$legacy"; return 0; fi
  printf '%s/issue-to-pr/%s' "$(git -C "$1" rev-parse --path-format=absolute --git-common-dir)" "$(basename "$legacy")"
}

receipt_file() { printf '%s/receipt.json' "$(run_dir_of "$1" "$2")"; }

write_receipt() { # root branch sha [gates]
  local root=$1 branch=$2 sha=$3 gates=${4:-test} dir
  dir=$(run_dir_of "$root" "$branch")
  mkdir -p "$dir"
  printf '{"branch":"%s","head_sha":"%s","gates":"%s","created_at":"%s"}\n' \
    "$branch" "$sha" "$gates" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$dir/receipt.json"
}

init_repo_with_remote() {
  local dir="$TEST_TMPDIR/repo" remote="$TEST_TMPDIR/remote.git" b
  git init -q --bare "$remote"
  init_repo "$dir" >/dev/null
  git -C "$dir" remote add origin "$remote"
  git -C "$dir" push -q -u origin main
  for b in "$@"; do
    git -C "$dir" branch "$b" main
    git -C "$dir" push -q origin "$b"
    git -C "$dir" branch -q -D "$b"
  done
  printf '%s' "$dir"
}
