#!/usr/bin/env bash
# agent-dispatch contract tests. Runs under bash 3.2 (macOS system bash) and up; every nested
# shell is "$BASH", so the interpreter that started this file runs every test.
# shellcheck disable=SC2016 # nested "$BASH" -c scripts use their own $1/$2
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PLUGIN_DIR=$(cd "$HERE/.." && pwd)
export AD_SCRIPTS="$PLUGIN_DIR/scripts" AD_FIXTURES="$HERE/fixtures"
ASSERT_LIB="$PLUGIN_DIR/../issue-to-pr/tests/lib/assert.sh"
[ -f "$ASSERT_LIB" ] || { printf 'missing %s\n' "$ASSERT_LIB" >&2; exit 1; }

lint_rc=0
if command -v shellcheck >/dev/null 2>&1; then
  printf '== shellcheck ==\n'
  if shellcheck -x -e SC1091 "$AD_SCRIPTS"/*.sh "$HERE"/run-tests.sh "$HERE"/contract/*.sh \
    "$AD_FIXTURES"/fake-gh/gh "$AD_FIXTURES"/fake-cli/claude "$AD_FIXTURES"/fake-cli/codex \
    "$AD_FIXTURES"/bin/date "$AD_FIXTURES"/bin/sleep; then
    printf 'shellcheck clean\n'
  else
    lint_rc=1
  fi
else
  printf '== shellcheck skipped (not installed) ==\n'
fi

printf '== contract tests ==\n'
total=0 fail=0 failures=
for tf in "$HERE"/contract/test_*.sh; do
  if ! functions=$("$BASH" --norc -c 'source "$1" || exit; source "$2" || exit; declare -F | awk "{print \$3}" | grep "^test_"' \
    _ "$ASSERT_LIB" "$tf"); then
    fail=$((fail + 1))
    failures="$failures
  ${tf##*/} :: discovery"
    printf '  FAIL %s :: discovery\n' "${tf##*/}"
    continue
  fi
  for fn in $functions; do
    total=$((total + 1))
    printf '  run  %s :: %s\n' "${tf##*/}" "$fn"
    if out=$("$BASH" --norc -c '
        set -uo pipefail
        TEST_TMPDIR=$(mktemp -d)
        export TEST_TMPDIR
        trap "cd / 2>/dev/null; rm -rf \"$TEST_TMPDIR\"" EXIT
        source "$1" || exit
        source "$2" || exit
        cd "$TEST_TMPDIR"
        "$3"
      ' _ "$ASSERT_LIB" "$tf" "$fn" 2>&1); then
      printf '  ok   %s :: %s\n' "${tf##*/}" "$fn"
    else
      fail=$((fail + 1))
      failures="$failures
  ${tf##*/} :: $fn"
      printf '  FAIL %s :: %s\n%s\n' "${tf##*/}" "$fn" "$out"
    fi
  done
done

printf '\ntests: %d  failed: %d%s\n' "$total" "$fail" "$failures"
[ "$total" -gt 0 ] || { printf 'no tests discovered\n'; exit 1; }
[ "$fail" -eq 0 ] && [ "$lint_rc" -eq 0 ]
