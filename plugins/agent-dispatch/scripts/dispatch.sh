#!/usr/bin/env bash
# agent-dispatch: one tick. Recover a dead tick's run, then start at most one headless
# issue-to-pr run: an owner reply first, else the oldest issue the owner labelled `agent`.
# Prints KEY=value lines, TICK= last; exit 1 when the tick could not do its job.
# Bash 3.2 and up. gh --jq only projects fields; every decision is made here.
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=marker.sh
. "$HERE/marker.sh"

AD_HOME="$HOME/.agent-dispatch"
LOCK="$AD_HOME/lock"
DEADLINE_SECONDS=14400 # a hang guard: a trivial run takes minutes, a complex one a few hours at most
POLL_SECONDS=20
GRACE_SECONDS=10
NOTIFY_SECONDS=30 # the owner's hook sends one message; past this it is stopped
RUN_LABELS="agent,agent:waiting,agent:review,agent:failed"
OWNER= # Ruling R2: recover() may reconcile before main sets this; reconcile resolves it itself.
BOOT_ID=
PICK_WHY='' PICK_IREAD='' PICK_PREAD='' # a reply pick's cursors; empty when recover() reconciles

JQ_ISSUES='.[] | [.number, ([.labels[].name] | join(","))] | @tsv'
JQ_LABEL_EVENTS='.[] | select((.event == "labeled" and (.label.name | startswith("agent"))) or .event == "renamed") | [.event, (.label.name // ""), .actor.login, .created_at] | @tsv'
# shellcheck disable=SC2016 # $o $r $n are GraphQL variables, not shell ones
# The body's edit history, newest first (first: 50 is the newest page; last: would be the oldest).
GQL_EDITS='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){userContentEdits(first:50){totalCount nodes{editedAt editor{login}}}}}}'
JQ_EDITS='.data.repository.issue.userContentEdits | (.totalCount | tostring), (.nodes[] | [.editedAt // "", .editor.login // ""] | @tsv)'

# ponytail: one global lock; per-repo locks if parallel runs ever matter.

say() { printf '%s\n' "$*"; }
die() { # reason message -> TICK=error, exit 1
  printf 'agent-dispatch: %s\n' "$2" >&2
  say "REASON=$1"
  say "TICK=error"
  exit 1
}
on_windows() {
  case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) return 0 ;; esac
  return 1
}
boot_id() {
  case "$(uname -s)" in
    Linux) cat /proc/sys/kernel/random/boot_id ;;
    Darwin) /usr/sbin/sysctl -n kern.bootsessionuuid ;;
    MINGW* | MSYS* | CYGWIN*)
      powershell.exe -NoProfile -Command '(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime.ToUniversalTime().Ticks' | tr -d '\r'
      ;;
    *) return 1 ;;
  esac
}

valid_boot() {
  [[ "$1" =~ ^[0-9]+$ || "$1" =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]
}

load_boot() {
  [ -n "$BOOT_ID" ] || BOOT_ID=$(boot_id) || return 1
  valid_boot "$BOOT_ID"
}

record_boot() { # directory -> 0 current boot, 1 earlier boot, 2 unknown
  local saved
  saved=$(cat "$1/boot" 2>/dev/null) || return 2
  valid_boot "$saved" || return 2
  [ "$saved" = "$BOOT_ID" ] || return 1
}
trim() {
  local s=${1%$'\r'}
  s=${s#"${s%%[![:space:]]*}"}
  printf '%s' "${s%"${s##*[![:space:]]}"}"
}
has_label() { # csv label
  case ",$1," in *",$2,"*) return 0 ;; esac
  return 1
}

# Ruling R1: split a MARKER_JQ row by parameter expansion, never `IFS=$'\t' read`, which
# collapses a plain reply's consecutive marker/body tabs. Mirrors finish.sh's row().
row() { # comment TSV line -> R_ID R_LOGIN R_MARKER (the body column is not needed here); rc 1 on a row with no numeric id
  local l=${1%$'\r'}
  R_ID=${l%%$'\t'*}
  l=${l#*$'\t'}
  R_LOGIN=${l%%$'\t'*}
  l=${l#*$'\t'}
  R_MARKER=${l%%$'\t'*}
  case "$R_ID" in '' | *[!0-9]*) return 1 ;; esac
}

valid_line() { # path host tier rest
  if [ -n "$4" ] || [ ! -d "$1" ]; then return 1; fi
  case "$2" in claude | codex) ;; *) return 1 ;; esac
  case "$3" in trivial | standard | complex | none) ;; *) return 1 ;; esac
}

read_config() { # -> CONF_PATH CONF_HOST CONF_TIER CONF_REPO; dies on a malformed line
  local f="$AD_HOME/repos.conf" line p h t rest repo
  CONF_PATH=() CONF_HOST=() CONF_TIER=() CONF_REPO=()
  [ -f "$f" ] || die config "no $f: run the agent-dispatch setup skill"
  while IFS= read -r line || [ -n "$line" ]; do
    line=$(trim "$line")
    case "$line" in '' | '#'*) continue ;; esac
    IFS='|' read -r p h t rest <<<"$line"
    p=$(trim "$p")
    h=$(trim "${h:-}")
    t=$(trim "${t:-}")
    if ! valid_line "$p" "$h" "$t" "${rest:-}"; then
      die config "malformed line in $f (want: <checkout path> | claude|codex | trivial|standard|complex|none): $line"
    fi
    repo=$(cd "$p" && gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null) ||
      die github "could not look up the GitHub repo of $p; the next tick retries"
    [ -n "$repo" ] || die config "gh cannot name the GitHub repo of $p (line: $line)"
    CONF_PATH+=("$p")
    CONF_HOST+=("$h")
    CONF_TIER+=("$t")
    CONF_REPO+=("$(trim "$repo")")
  done <"$f"
}

current_state() { # comments-tsv -> M_* of the newest well-formed owner state comment; rc 1 when none
  local line s='' p='' i='' r='' id=0
  while IFS= read -r line; do
    row "$line" || continue
    [ "$R_LOGIN" = "$OWNER" ] || continue
    parse_marker "$R_MARKER" || continue
    s=$M_STATE p=$M_PR i=$M_IREAD r=$M_PREAD id=$R_ID
  done <<<"$1"
  [ -n "$s" ] || return 1
  M_STATE=$s M_PR=$p M_IREAD=$i M_PREAD=$r STATE_ID=$id
}

reply_in() { # comments-tsv cursor -> rc 0 on an unmarked owner comment above the cursor
  local line
  while IFS= read -r line; do
    row "$line" || continue
    if [ "$R_LOGIN" != "$OWNER" ] || [ -n "$R_MARKER" ]; then continue; fi
    if [ "$R_ID" -gt "${2:-0}" ] 2>/dev/null; then return 0; fi
  done <<<"$1"
  return 1
}

owner_replied() { # repo issue -> rc 0 when the issue's current state has an owner reply
  local c
  c=$(gh api "repos/$1/issues/$2/comments" --paginate --jq "$MARKER_JQ" 2>/dev/null) || return 1
  current_state "$c" || return 1
  case "$M_STATE" in waiting | review) ;; *) return 1 ;; esac
  reply_in "$c" "$M_IREAD" && return 0
  [ -n "$M_PR" ] || return 1
  c=$(gh api "repos/$1/issues/$M_PR/comments" --paginate --jq "$MARKER_JQ" 2>/dev/null) || return 1
  reply_in "$c" "$M_PREAD"
}

# ponytail: checked at pick time; an edit landing in the seconds before the run reads the issue
# still gets through. Closing that needs the run itself to re-check, which issue-to-pr does not.
owner_approved() { # repo issue label -> rc 0 when the owner applied that label last and nobody
  # else changed the title or the body since the owner last applied `agent` (the content approval:
  # on the reply path the parked label is the run's own, so it approves nothing); rc 1 when any of
  # it cannot be read
  local rows line ev lbl who at by='' since='' renamed='' total='' seen=0
  rows=$(gh api "repos/$1/issues/$2/events" --paginate --jq "$JQ_LABEL_EVENTS" 2>/dev/null) || return 1
  while IFS= read -r line; do # events come oldest first
    line=${line%$'\r'}
    ev=${line%%$'\t'*}
    line=${line#*$'\t'}
    lbl=${line%%$'\t'*}
    line=${line#*$'\t'}
    who=${line%%$'\t'*}
    at=${line#*$'\t'}
    case "$ev" in
      labeled)
        if [ "$lbl" = "$3" ]; then by=$who; fi
        if [ "$lbl" = agent ] && [ "$who" = "$OWNER" ]; then since=$at renamed=''; fi
        ;;
      renamed) if [ "$who" != "$OWNER" ]; then renamed=1; fi ;;
    esac
  done <<<"$rows"
  if [ "$by" != "$OWNER" ] || [ -n "$renamed" ]; then return 1; fi
  # Every body edit since the approval must be the owner's: the last editor alone would let a
  # later owner edit launder a stranger's. ISO-8601 UTC stamps order as strings; an edit in the
  # label's own second, or with no time or no editor, counts against it.
  rows=$(gh api graphql -f query="$GQL_EDITS" -f o="${1%%/*}" -f r="${1#*/}" -F n="$2" --jq "$JQ_EDITS" 2>/dev/null) || return 1
  at=''
  while IFS= read -r line; do
    line=${line%$'\r'}
    if [ -z "$total" ]; then
      total=${line:-0}
      continue
    fi
    [ -n "$line" ] || continue
    seen=$((seen + 1))
    at=${line%%$'\t'*}
    who=${line#*$'\t'}
    if [ -z "$at" ] || ! [ "$at" \< "$since" ]; then
      [ "$who" = "$OWNER" ] || return 1
    fi
  done <<<"$rows"
  case "$total" in *[!0-9]*) return 1 ;; esac
  # Past one page, the unread edits are older than the oldest read; they matter only when that one
  # is not already before the approval.
  if [ "$total" -gt "$seen" ] && { [ -z "$at" ] || ! [ "$at" \< "$since" ]; }; then return 1; fi
  return 0
}

pick() { # -> PICK_I PICK_N PICK_WHY; rc 1 when nothing is due
  local i=0 n labels why parked out
  local -a issues
  issues=()
  while [ "$i" -lt "${#CONF_REPO[@]}" ]; do
    out=$(gh issue list -R "${CONF_REPO[$i]}" --state open --search 'label:agent,agent:waiting,agent:review' \
      --limit 500 --json number,labels --jq "$JQ_ISSUES" 2>/dev/null) ||
      die github "could not list the open issues of ${CONF_REPO[$i]}"
    issues+=("$(printf '%s\n' "$out" | tr -d '\r' | sort -n)")
    i=$((i + 1))
  done
  for why in reply queue; do
    i=0
    while [ "$i" -lt "${#CONF_REPO[@]}" ]; do
      while IFS=$'\t' read -r n labels; do
        [ -n "$n" ] || continue
        if [ "$why" = reply ]; then
          if has_label "$labels" agent:waiting; then parked=agent:waiting
          elif has_label "$labels" agent:review; then parked=agent:review
          else continue; fi
          owner_approved "${CONF_REPO[$i]}" "$n" "$parked" || continue
          owner_replied "${CONF_REPO[$i]}" "$n" || continue
          PICK_IREAD=$M_IREAD PICK_PREAD=$M_PREAD
        else
          has_label "$labels" agent || continue
          if has_label "$labels" agent:running || has_label "$labels" agent:waiting ||
            has_label "$labels" agent:review; then continue; fi
          owner_approved "${CONF_REPO[$i]}" "$n" agent || continue
        fi
        PICK_I=$i PICK_N=$n PICK_WHY=$why
        return 0
      done <<<"${issues[$i]}"
      i=$((i + 1))
    done
  done
  return 1
}

admit_seo_incidents() {
  local policy="$AD_HOME/seo-incidents.json" python=python3 repo
  [ -f "$policy" ] || return 0
  if on_windows; then python=python; fi
  if ! command -v "$python" >/dev/null 2>&1; then
    say 'SEO_INTAKE=unavailable'
    return 0
  fi
  for repo in "${CONF_REPO[@]}"; do
    "$python" "$HERE/seo_intake.py" --policy "$policy" --repository "$repo" --admit ||
      say 'SEO_INTAKE=error'
  done
}

write_run_script() { # path host issue tier log -> $LOCK/run.sh
  local prompt="issue-to-pr:run $3 --headless --auto-merge $4"
  {
    printf 'cd %q || exit 97\n' "$1"
    if [ "$2" = claude ]; then
      printf 'exec claude -p --dangerously-skip-permissions --output-format stream-json --verbose %q' "/$prompt"
    else
      printf 'exec codex exec --dangerously-bypass-approvals-and-sandbox --json -C %q %q' "$1" "\$$prompt"
    fi
    printf ' </dev/null >%q 2>&1\n' "$5"
  } >"$LOCK/run.sh"
}

launch() { # [dir, default $LOCK] runs dir/run.sh -> RUN_PID (to wait on); the id that stops it goes to dir/run
  local d=${1:-$LOCK}
  load_boot && printf '%s\n' "$BOOT_ID" >"$d/boot" || return 96
  : >"$d/launched"
  if on_windows; then
    # job.ps1 holds the run in a job object: stopping it stops every process the run started,
    # Git Bash grandchildren and orphans included, which taskkill //T misses. It writes its own
    # Windows pid to dir/run before it starts bash.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/job.ps1")" \
      "$(cygpath -w "$BASH")" "$(cygpath -w "$d/run.sh")" </dev/null >/dev/null 2>&1 &
    RUN_PID=$!
  else
    set -m
    "$BASH" "$d/run.sh" </dev/null >/dev/null 2>&1 &
    RUN_PID=$!
    set +m
    printf '%s\n' "$RUN_PID" >"$d/run"
  fi
  printf '%s\n' "$RUN_PID" >"$d/pid"
}

run_id() { trim "$(cat "$LOCK/run" 2>/dev/null)"; }

# ponytail: 96 and 97 are the launcher's own codes; a CLI that itself exits 97 (or 96 on Windows)
# is reported as the launcher's failure.
run_cause() { # rc host log checkout -> CAUSE, CLIERR (0 no pause, 1 the CLI failed, 2 the launcher)
  CAUSE='' CLIERR=0
  if [ "$1" -eq 97 ]; then
    CAUSE="the checkout $4 is missing"
  elif [ "$1" -eq 96 ] && on_windows; then
    CAUSE="the Windows launcher could not start the run" CLIERR=2
  elif [ "$1" -ne 0 ]; then
    CAUSE="the $2 CLI exited with code $1" CLIERR=1
  elif [ "$2" = claude ] && grep '"type":"result"' "$3" 2>/dev/null | tail -1 | grep -q '"is_error":true'; then
    CAUSE="the claude CLI reported an error" CLIERR=1
  elif [ "$2" = claude ] && awk '/"type":"result"/ { r = NR } /"subtype":"task_notification"/ && /"status":"stopped"/ { s = NR }
      END { exit !(r && s > r) }' "$3" 2>/dev/null; then
    # claude -p exits when the turn ends and stops whatever the run left running in the background.
    CAUSE="it ended its turn while background work was still running, so that work was stopped"
  else
    CAUSE="it ended without leaving a state"
  fi
}

stop_run() { # run-id: the job launcher's Windows pid, or the run's process group
  [ -n "$1" ] || return 0
  if on_windows; then
    taskkill //F //FI "PID eq $1" //FI "IMAGENAME eq powershell.exe" >/dev/null 2>&1
  else
    kill -TERM -- "-$1" 2>/dev/null && sleep "$GRACE_SECONDS"
    kill -KILL -- "-$1" 2>/dev/null
  fi
  return 0
}

gone() { # run-id -> rc 0 once nothing of the run is left; rc 1 while it lives or cannot be checked
  local _ out
  for _ in 1 2 3 4 5; do
    if on_windows; then
      # tasklist exits 0 with an INFO line when nothing matches; a failure says nothing either way.
      out=$(tasklist //FI "PID eq $1" //FI "IMAGENAME eq powershell.exe" //NH 2>/dev/null) || return 1
      printf '%s\n' "$out" | grep -qi powershell || return 0
    else
      kill -0 -- "-$1" 2>/dev/null || return 0
    fi
    sleep 1
  done
  return 1
}

# ponytail: best effort, no retry and no record of what was sent; a tick that dies before it drops
# the lock has its hook stopped and notifies again from recover().
notify() { # waiting|review|failed repo issue detail -> NOTIFY=sent|failed|timeout; runs the owner's
  # ~/.agent-dispatch/notify.sh when there is one, and never changes the tick's own result
  local hook="$AD_HOME/notify.sh" d="$AD_HOME/.notify" waited=0 a rc
  [ -f "$hook" ] || return 0
  # Launched the way a run is, so a stop takes curl and the like with it: a child left behind would
  # hold the scheduler's single tick slot.
  if ! stop_hook; then say "NOTIFY=failed"; return 0; fi
  mkdir -p "$d" "$AD_HOME/logs"
  {
    for a in "$BASH" "$hook" "$@"; do
      if [ -n "$a" ]; then printf '%q ' "$a"; else printf "'' "; fi # an old bash's %q may drop ''
    done
    printf '</dev/null >>%q 2>&1\n' "$AD_HOME/logs/notify.log"
  } >"$d/run.sh"
  if ! launch "$d"; then say "NOTIFY=failed"; return 0; fi
  while kill -0 "$RUN_PID" 2>/dev/null; do
    if [ "$waited" -ge "$NOTIFY_SECONDS" ]; then
      stop_hook
      say "NOTIFY=timeout"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$RUN_PID"
  rc=$?
  stop_hook # its launcher has exited; also stop any children it left behind
  if [ "$rc" -eq 0 ]; then
    say "NOTIFY=sent"
  else
    say "NOTIFY=failed"
    say "NOTIFY_RC=$rc" # 96 on Windows: the launcher, not the hook
  fi
  return 0
}

stop_hook() { # stop the hook before reusing its directory, including a Windows launcher still starting
  local d="$AD_HOME/.notify" id pid boot_rc
  [ -d "$d" ] || return 0
  load_boot || return 1
  record_boot "$d"
  boot_rc=$?
  if [ "$boot_rc" -eq 1 ]; then rm -rf "$d"; return 0; fi
  if [ "$boot_rc" -eq 2 ] && { [ -s "$d/run" ] || [ -s "$d/pid" ] || [ -e "$d/launched" ]; }; then
    return 1 # unknown legacy process identity must not authorize a signal
  fi
  pid=$(trim "$(cat "$d/pid" 2>/dev/null)")
  id=$(trim "$(cat "$d/run" 2>/dev/null)")
  if [ -n "$id" ]; then
    if on_windows; then stop_run "$id"; else kill -KILL -- "-$id" 2>/dev/null; fi
    gone "$id" || return 1
  elif [ -n "$pid" ]; then
    # Bash knows this process before job.ps1 publishes its Windows PID. Never wait on a failed kill.
    kill -KILL "$pid" 2>/dev/null || { kill -0 "$pid" 2>/dev/null && return 1; }
    wait "$pid" 2>/dev/null # reaps our child; recovery is not its parent and returns immediately
    kill -0 "$pid" 2>/dev/null && return 1
  elif [ -e "$d/launched" ]; then
    # A crash between spawn and PID publication leaves an unresolved launcher. Its directory
    # must survive: a late startup could otherwise overwrite the next hook's process record.
    return 1
  fi
  rm -rf "$d"
}

# shellcheck disable=SC2016,SC2088 # the backticks are Markdown; the tilde is shown, not expanded
reconcile() { # repo issue cause log cli-error(0|1 CLI|2 launcher) -> OUTCOME [PAUSED] [NOTIFY]; rc 1 when GitHub failed
  local labels body="$AD_HOME/.comment.md" shown=$4 comments prmark='' cause=$3 from=agent:running clierr=$5 why='' state pending remove_labels=agent:running,agent:waiting,agent:review
  pending=$(cat "$LOCK/failure-from" 2>/dev/null)
  case "$pending" in agent:running | agent:waiting | agent:review)
    from=$pending
    cause=$(cat "$LOCK/cause") || return 1
    clierr=$(cat "$LOCK/clierr") || return 1
    ;; *) pending='' ;; esac
  if [ -z "$OWNER" ]; then # Ruling R2: recover() may call us before main() resolves OWNER
    OWNER=$(gh api user --jq .login 2>/dev/null | tr -d '\r')
    [ -n "$OWNER" ] || return 1
  fi
  labels=$(gh issue view "$2" -R "$1" --json labels --jq '.labels[].name' 2>/dev/null) || return 1
  labels=$(printf '%s\n' "$labels" | tr -d '\r')
  if [ -z "$pending" ] && ! printf '%s\n' "$labels" | grep -qx 'agent:running'; then
    # A reply run that parked again at the cursors it started from, with the reply that started it
    # still above them, would be picked again every tick: that one fails instead.
    from=$(printf '%s\n' "$labels" | grep -x -E 'agent:(waiting|review)' | head -1)
    if [ -z "$from" ] || [ "$PICK_WHY" != reply ] || ! owner_replied "$1" "$2" ||
      [ "$M_IREAD" != "$PICK_IREAD" ] || [ "$M_PREAD" != "$PICK_PREAD" ]; then
      say "OUTCOME=$(printf '%s\n' "$labels" | grep '^agent' | head -1)"
      state=$(printf '%s\n' "$labels" | grep -x -E 'agent:(waiting|review|failed)' | head -1)
      [ -z "$state" ] || notify "${state#agent:}" "$1" "$2" ''
      return 0
    fi
    cause="the run parked again without reading your reply" clierr=0 # whatever the CLI exited with
  fi
  comments=$(gh api "repos/$1/issues/$2/comments" --paginate --jq "$MARKER_JQ" 2>/dev/null) || return 1
  # Accept only a done posted during this launch; a reopened issue may carry an old done.
  state=$(cat "$LOCK/state-id" 2>/dev/null)
  case "$state" in
    '' | *[!0-9]*) ;;
    *) if current_state "$comments" && [ "$M_STATE" = "done" ] && [ "$STATE_ID" -gt "$state" ]; then
      gh issue edit "$2" -R "$1" --remove-label agent:running,agent:waiting,agent:review,agent:failed >/dev/null 2>&1 || return 1
      say 'OUTCOME=done'
      return 0
    fi ;;
  esac
  # Amendment #2: carry the run's PR, if the issue's own current state already named one, so a
  # retry (or a human) can still find it from the failure comment alone.
  if current_state "$comments" && [ -n "$M_PR" ]; then prmark=" pr=$M_PR"; fi
  case "$shown" in "$HOME"/*) shown="~${shown#"$HOME"}" ;; esac
  case "$clierr" in # a failure every next run would repeat pauses dispatching
    1) why='An error like this usually means the CLI is logged out or out of allowance, and the next issue would fail the same way.' ;;
    2) why='Every run on this machine would hit the same launcher failure.' ;;
  esac
  if [ -n "$why" ]; then
    : >"$AD_HOME/paused"
    say "PAUSED=true"
  fi
  {
    printf 'The dispatcher marked this run failed: %s. Its run log path on the dispatching machine is `%s`.\n' "$cause" "$shown"
    if [ -n "$why" ]; then
      printf '\nDispatching is paused for every repo until you delete `~/.agent-dispatch/paused`. %s\n' "$why"
    fi
    printf '\nTo retry, label the issue `agent` again.\n\n<!-- issue-to-pr state=failed%s -->\n' "$prmark"
  } >"$body"
  printf '%s\n' "$cause" >"$LOCK/cause" || return 1
  printf '%s\n' "$clierr" >"$LOCK/clierr" || return 1
  printf '%s\n' "$from" >"$LOCK/failure-from" || return 1
  if [ ! -f "$LOCK/failure-posted" ]; then
    gh issue comment "$2" -R "$1" --body-file "$body" >/dev/null 2>&1 || return 1
    : >"$LOCK/failure-posted" || return 1
  fi
  [ -e "$LOCK/launched" ] || remove_labels="agent,$remove_labels"
  gh issue edit "$2" -R "$1" --add-label agent:failed --remove-label "$remove_labels" >/dev/null 2>&1 || return 1
  say "OUTCOME=agent:failed"
  notify failed "$1" "$2" "$cause.${why:+ Dispatching is paused until you delete ~/.agent-dispatch/paused.}"
}

recover() { # a lock at tick start: a live tick (busy), or a dead one's run to stop and reconcile
  [ -d "$LOCK" ] || return 0
  local tick repo n run cause clierr boot_rc
  record_boot "$LOCK"
  boot_rc=$?
  if [ "$boot_rc" -eq 2 ] && { [ -s "$LOCK/tick" ] || [ -s "$LOCK/run" ] || [ -s "$LOCK/pid" ] || [ -e "$LOCK/launched" ]; }; then
    die recover "the lock has no readable boot identity; verify its processes before removing $LOCK"
  fi
  tick=$(cat "$LOCK/tick" 2>/dev/null)
  if [ "$boot_rc" -eq 0 ] && [ -n "$tick" ] && kill -0 "$tick" 2>/dev/null; then
    say "TICK=busy"
    exit 0
  fi
  repo=$(cat "$LOCK/repo" 2>/dev/null)
  n=$(cat "$LOCK/issue" 2>/dev/null)
  run=$(run_id)
  stop_hook # a notification the dead tick left in flight
  if [ "$boot_rc" -eq 0 ] && [ -n "$run" ]; then
    stop_run "$run"
    gone "$run" || die recover "the run of a dead tick ($repo#$n, id $run) is still alive; the next tick retries"
  elif [ "$boot_rc" -eq 0 ] && [ -e "$LOCK/launched" ] && [ -z "$(find "$LOCK/launched" -mmin +1 2>/dev/null)" ]; then
    # job.ps1 records its pid before it starts bash, so a launcher silent for over a minute never
    # ran the CLI: past that, the lock is reconciled like one with no run.
    die recover "the launcher of a dead tick's run ($repo#$n) has not recorded its id yet; the next tick retries"
  fi
  if [ -n "$repo" ] && [ -n "$n" ]; then
    cause=$(cat "$LOCK/cause" 2>/dev/null)
    clierr=$(cat "$LOCK/clierr" 2>/dev/null)
    reconcile "$repo" "$n" "${cause:-the dispatcher stopped before the run finished}" \
      "$(cat "$LOCK/log" 2>/dev/null)" "${clierr:-0}" ||
      die recover "could not reach GitHub to reconcile $repo#$n; the next tick retries"
    say "RECOVERED=$repo#$n"
  fi
  rm -rf "$LOCK"
}

run_issue() { # the picked issue: lock, flip, launch, wait, reconcile
  local repo=${CONF_REPO[$PICK_I]} path=${CONF_PATH[$PICK_I]} host=${CONF_HOST[$PICK_I]}
  local tier=${CONF_TIER[$PICK_I]} n=$PICK_N log rc cause='' clierr=0 active=0 waited=0 id comments stage
  say "ISSUE=$repo#$n"
  say "PICK=$PICK_WHY"
  load_boot || die boot "could not read the machine's boot identity"
  stage=$(mktemp -d "$AD_HOME/.claim.XXXXXX") || die lock "could not prepare the lock"
  log="$AD_HOME/logs/${repo//\//_}_${n}_$(date -u +%Y%m%dT%H%M%SZ).log"
  if ! {
    mkdir "$stage/lock" &&
    printf '%s\n' "$BOOT_ID" >"$stage/lock/boot" &&
    printf '%s\n' "$$" >"$stage/lock/tick" &&
    printf '%s\n' "$repo" >"$stage/lock/repo" &&
    printf '%s\n' "$n" >"$stage/lock/issue" &&
    printf '%s\n' "$log" >"$stage/lock/log"
  }; then
    rm -rf "$stage"
    die lock "could not prepare the lock's owner and recovery records"
  fi
  # A fixed basename into the parent rejects an existing nonempty lock instead of nesting.
  if ! mv "$stage/lock" "$AD_HOME/" 2>/dev/null; then
    rm -rf "$stage"
    say "TICK=busy"
    exit 0
  fi
  rmdir "$stage"
  comments=$(gh api "repos/$repo/issues/$n/comments" --paginate --jq "$MARKER_JQ" 2>/dev/null) ||
    die github "could not read the state before launching $repo#$n; the next tick retries"
  STATE_ID=0
  current_state "$comments" || true
  printf '%s\n' "$STATE_ID" >"$LOCK/state-id"
  if ! {
    printf 'the dispatcher stopped before the run was launched\n' >"$LOCK/cause" &&
      printf '0\n' >"$LOCK/clierr" &&
      printf 'agent:running\n' >"$LOCK/failure-from"
  }; then
    die lock "could not save the pending launch state; nothing was launched"
  fi
  if ! gh issue edit "$n" -R "$repo" --add-label agent:running --remove-label "$RUN_LABELS" >/dev/null 2>&1; then
    die flip "could not label $repo#$n agent:running; nothing was launched"
  fi
  rm -- "$LOCK/failure-from" || die launch "could not clear the pending launch state; nothing was launched"
  write_run_script "$path" "$host" "$n" "$tier" "$log"
  launch || die launch "could not record the run's boot identity; nothing was launched"
  if on_windows; then say "LAUNCHER=job"; else say "LAUNCHER=group"; fi
  while kill -0 "$RUN_PID" 2>/dev/null; do
    if [ "$active" -ge "$DEADLINE_SECONDS" ]; then
      stop_run "$(run_id)"
      cause="it ran past the $((DEADLINE_SECONDS / 3600))-hour deadline"
      printf '%s\n' "$cause" >"$LOCK/cause" # for recovery, if the stop does not take
      break
    fi
    sleep "$POLL_SECONDS"
    active=$((active + POLL_SECONDS))
  done
  while kill -0 "$RUN_PID" 2>/dev/null; do # a stop that did not take: never block on a bare wait
    [ "$waited" -lt $((GRACE_SECONDS + 20)) ] ||
      die recover "the run of $repo#$n outlived its stop; the next tick retries"
    sleep 1
    waited=$((waited + 1))
  done
  wait "$RUN_PID"
  rc=$?
  if [ -z "$cause" ]; then
    run_cause "$rc" "$host" "$log" "$path"
    cause=$CAUSE clierr=$CLIERR
  fi
  printf '%s\n' "$cause" >"$LOCK/cause"
  printf '%s\n' "$clierr" >"$LOCK/clierr"
  id=$(run_id) # empty only when job.ps1 failed before it started bash: nothing of the run exists
  if [ -n "$id" ]; then
    on_windows || kill -KILL -- "-$id" 2>/dev/null # whatever the exited run left behind
    gone "$id" || die recover "processes of $repo#$n are still alive (id $id); the next tick retries"
  fi
  reconcile "$repo" "$n" "$cause" "$log" "$clierr" ||
    die github "could not reach GitHub to reconcile $repo#$n; the next tick retries"
  rm -rf "$LOCK"
  say "RC=$rc"
  say "TICK=done"
}

main() {
  mkdir -p "$AD_HOME/logs"
  load_boot || die boot "could not read the machine's boot identity"
  recover
  if [ -e "$AD_HOME/paused" ]; then
    say "TICK=paused"
    exit 0
  fi
  read_config
  OWNER=$(gh api user --jq .login 2>/dev/null | tr -d '\r')
  [ -n "$OWNER" ] || die github "gh api user failed: check gh auth status and the network"
  admit_seo_incidents
  if ! pick; then
    say "TICK=idle"
    exit 0
  fi
  run_issue
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main; fi
