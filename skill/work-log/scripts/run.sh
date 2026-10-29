#!/bin/zsh
# Headless /work-log collector started by WorkLog.app (schedule or manual). Appends one line to runs.jsonl per run.
# Env: WORKLOG_TRIGGER (schedule|manual, default manual), WORKLOG_LOG_DIR (default ~/Library/Logs/work-log),
#      WORKLOG_HOME (data dir), WORKLOG_PATH / WORKLOG_EXTRA_PATH (see env.sh).
set -u
# Logs hold raw transcripts and Slack text, so everything this run creates is readable by the user only
umask 077

SCRIPTS_DIR="${0:A:h}"
source "$SCRIPTS_DIR/env.sh"

DATA_DIR="${WORKLOG_HOME:-$HOME/Library/Application Support/WorkLog}"
LOG_DIR="${WORKLOG_LOG_DIR:-$HOME/Library/Logs/work-log}"
LOCK_DIR="$LOG_DIR/.lock"
RUN_LOG="$LOG_DIR/run.log"
RUNNER_LOG="$LOG_DIR/app-runner.log"
TRIGGER="${WORKLOG_TRIGGER:-manual}"
LOG_RETENTION_DAYS=7
LOG_TRIM_BYTES=1048576
LOG_TRIM_KEEP_LINES=1000
RUN_TIMEOUT_SEC=1800
# Gives the user time to answer the first-run folder access prompt
FOLDER_CHECK_TIMEOUT_SEC=120
STALE_LOCK_MIN=60
SIGALRM_EXIT=142
WARNINGS_REASON="Completed with warnings"
COLLECTOR_SCRIPTS=(settings state write_day extract_sessions suggestions)
SLACK_TOOLS=(
  mcp__plugin_slack_slack__slack_search_public_and_private
  mcp__plugin_slack_slack__slack_read_thread
  mcp__plugin_slack_slack__slack_read_user_profile
)

mkdir -p "$LOG_DIR" "$DATA_DIR"
chmod 700 "$LOG_DIR" "$DATA_DIR"
stamp=$(date +%Y-%m-%d-%H%M)
out="$LOG_DIR/$stamp.json"
err="$LOG_DIR/$stamp.err"

log() { echo "$stamp $1" >> "$RUN_LOG"; }
# ISO-8601 with a colon in the offset, seconds precision
iso_now() { date +%Y-%m-%dT%H:%M:%S%z | sed -E 's/([0-9]{2})$/:\1/'; }

# Keeps the last lines of a text log that grew past the size limit. It truncates in place because the app
# holds app-runner.log open in append mode as this script's output.
trim_log() {
  [[ -f "$1" ]] && (( $(stat -f %z "$1") > LOG_TRIM_BYTES )) || return 0
  local kept
  kept="$(tail -n "$LOG_TRIM_KEEP_LINES" "$1")"
  print -r -- "$kept" > "$1"
}

# find drops the fraction of a day, so +N matches files older than N+1 days
find "$LOG_DIR" -maxdepth 1 -type f \( -name '*.json' -o -name '*.err' \) -mtime +"$(( LOG_RETENTION_DAYS - 1 ))" -delete
trim_log "$RUN_LOG"
trim_log "$RUNNER_LOG"

# Without a usable python3 nothing can be recorded in runs.jsonl, so the reason goes to run.log only
if ! worklog_python_ok; then
  log "failed: Python 3.11 or newer is required as python3 on the run PATH (found: $(python3 -V 2>&1 | head -n 1)). Reinstall with install.sh after installing it."
  exit 1
fi

started_iso=$(iso_now)
provider=claude
log_folder=""
work_dir=""
# The app stops a run with SIGTERM to the process group, then removes the lock and records the stop itself.
# A new run may already hold the lock when this trap runs, so a stopped run removes only its working directory.
stopped=0
TRAPTERM() { stopped=1; exit 143; }
TRAPINT() { exit 130; }

# record RESULT REASON [OUTPUT_PATH]: appends the runs.jsonl line
record() {
  local args=(append --provider "$provider" --started-at "$started_iso" --ended-at "$(iso_now)"
              --trigger "$TRIGGER" --result "$1" --reason "$2" --runs "$DATA_DIR/runs.jsonl")
  [[ -n "${3:-}" ]] && args+=(--output "$3" --log-path "$3")
  worklog_py "$SCRIPTS_DIR/runlog.py" "${args[@]}" 2>>"$err" || { log "run record write failed"; return 1; }
}
fail() { log "failed: $1"; record failed "$1" "${2:-}"; exit 1; }

# The provider may change anything under the log folder, so it must not contain the home folder or WorkLog's data.
# The rejected set lives in this one function.
log_folder_is_dedicated() {
  local folder="${1:A}"
  [[ "$folder" != / && "$folder" != "${HOME:A}" && "${DATA_DIR:A}/" != "$folder/"* ]]
}

settings=("${(@f)$(worklog_py "$SCRIPTS_DIR/settings.py" show 2>>"$err" | python3 -I -c '
import json, sys
s = json.load(sys.stdin)
print(s["provider"]); print(s["logFolder"]); print(int(s["logFolderIsDefault"]))' 2>>"$err")}")
(( ${#settings} == 3 )) || fail "Invalid settings"
provider="${settings[1]}"
log_folder="${settings[2]}"
log_folder_is_default="${settings[3]}"

log_folder_is_dedicated "$log_folder" || fail "Log folder must be a dedicated folder"
# Only the default folder is created here; a missing folder the user chose fails the access check below
if (( log_folder_is_default )) && [[ ! -e "$log_folder" ]]; then
  mkdir -p -m 700 "$log_folder" 2>>"$err" || fail "Cannot create the log folder"
fi
command -v "$provider" >/dev/null 2>&1 || fail "Provider not found"
# Allow rules match the literal command text, and a path with spaces would have to be quoted
if [[ "$provider" == claude && "$SCRIPTS_DIR" == *[[:space:]]* ]]; then
  fail "Skill path must not contain spaces"
fi

# Background runs can be blocked by macOS privacy (TCC) from reading the log folder. Check before spending tokens.
if ! perl -e 'alarm shift; exec @ARGV' "$FOLDER_CHECK_TIMEOUT_SEC" /bin/ls "$log_folder" >/dev/null 2>>"$err"; then
  fail "Log folder not accessible"
fi

# Do not overlap with another run. A lock left by a crash is removed after a while.
find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" -exec rmdir {} \; 2>/dev/null
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "skipped: another run is in progress"
  record skipped "Another run is in progress" || exit 1
  exit 0
fi
trap '(( stopped )) || rmdir "$LOCK_DIR" 2>/dev/null; [[ -n "$work_dir" ]] && rm -rf "$work_dir"' EXIT

# The provider gets a fresh, empty working directory: what it writes there is thrown away with the directory
work_dir="$(mktemp -d -t work-log-run)" || fail "Cannot create a working directory"
work_dir="${work_dir:A}"
cd "$work_dir" || fail "Cannot enter the working directory"

started_epoch=$(date +%s)
# macOS has no timeout command, so a perl alarm limits the run time
if [[ "$provider" == codex ]]; then
  perl -e 'alarm shift; exec @ARGV' "$RUN_TIMEOUT_SEC" \
    codex exec --json --sandbox workspace-write --add-dir "$log_folder" --add-dir "$DATA_DIR" \
    --skip-git-repo-check '$work-log' >"$out" 2>>"$err"
else
  # dontAsk denies every tool call these rules do not cover, whatever the user's own permission settings say
  allowed=(Read "Skill(work-log)" "${SLACK_TOOLS[@]}")
  for script in "${COLLECTOR_SCRIPTS[@]}"; do
    allowed+=("Bash(python3 $SCRIPTS_DIR/$script.py:*)")
  done
  for dir in "$log_folder" "${log_folder:A}" "$work_dir"; do
    allowed+=("Edit(/$dir/**)")
  done
  allowed=("${(@u)allowed}")
  context="WorkLog headless run. Scripts folder: $SCRIPTS_DIR. Payload folder: $work_dir. Call every script as python3 $SCRIPTS_DIR/<name>.py with that exact path, and write JSON payload files only in the payload folder."
  perl -e 'alarm shift; exec @ARGV' "$RUN_TIMEOUT_SEC" \
    claude -p "/work-log" --permission-mode dontAsk --allowedTools "${allowed[@]}" \
    --append-system-prompt "$context" \
    --no-session-persistence --output-format json >"$out" 2>>"$err"
fi
code=$?

# The skill can stop by itself and still exit cleanly, so success means it actually wrote during this run
times=("${(@f)$(python3 -I -c '
import sys
sys.path.insert(0, sys.argv[1])
from state import DEFAULT_STATE_PATH, load_last_warned, load_last_written
for t in (load_last_written(DEFAULT_STATE_PATH), load_last_warned(DEFAULT_STATE_PATH)):
    print(int(t.timestamp()) if t else 0)
' "$SCRIPTS_DIR" 2>>"$err")}")
written="${times[1]:-0}"
warned="${times[2]:-0}"
is_error=$(python3 -I -c '
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from runlog import summarize
print(int(summarize(sys.argv[2], Path(sys.argv[3]))["isError"]))
' "$SCRIPTS_DIR" "$provider" "$out" 2>>"$err" || echo 1)

result=succeeded
reason=""
if (( code == SIGALRM_EXIT )); then
  result=failed; reason="Timed out after ${RUN_TIMEOUT_SEC}s"
elif (( code != 0 )); then
  result=failed; reason="Provider exited with code $code"
elif (( is_error )); then
  result=failed; reason="Provider reported an error"
elif (( written < started_epoch )); then
  result=failed; reason="Nothing was written during this run"
elif (( warned >= started_epoch )); then
  reason="$WARNINGS_REASON"
fi

log "$result${reason:+: $reason} ($out)"
record "$result" "$reason" "$out" && [[ $result == succeeded ]]
