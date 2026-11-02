#!/bin/zsh
# Headless /daily run started by WorkLog.app (Generate now). Writes dailies/last-run.json once per run.
# Env: WORKLOG_LOG_DIR (default ~/Library/Logs/work-log), WORKLOG_HOME (data dir),
#      WORKLOG_PATH / WORKLOG_EXTRA_PATH (see env.sh), WORKLOG_DAILY_TIMEOUT_SEC (tests).
set -u
# Dailies quote Slack text and PR titles, so everything this run creates is readable by the user only
umask 077

SCRIPTS_DIR="${0:A:h}"
source "$SCRIPTS_DIR/env.sh"

DATA_DIR="${WORKLOG_HOME:-$HOME/Library/Application Support/WorkLog}"
LOG_DIR="${WORKLOG_LOG_DIR:-$HOME/Library/Logs/work-log}"
DAILIES_DIR="$DATA_DIR/dailies"
# Separate from the collector's lock, so a daily can run while a collection runs
LOCK_DIR="$LOG_DIR/.daily-lock"
RUN_LOG="$LOG_DIR/daily.log"
LOG_RETENTION_DAYS=7
DAILY_TIMEOUT_SEC="${WORKLOG_DAILY_TIMEOUT_SEC:-900}"
CONTEXT_TIMEOUT_SEC=300
FOLDER_CHECK_TIMEOUT_SEC=120
# Twice the timeout: an older lock was left by a crash
STALE_LOCK_MIN=30
SIGALRM_EXIT=142
# The agent may only save and show; it never runs daily_context.py itself (see below)
DAILY_COMMANDS=("daily.py save" "daily.py show")
SLACK_TOOLS=(
  mcp__plugin_slack_slack__slack_search_public_and_private
  mcp__plugin_slack_slack__slack_read_thread
  mcp__plugin_slack_slack__slack_read_user_profile
  mcp__plugin_slack_slack__slack_read_channel
)
# Read-only tools of the Atlassian MCP server. The server name is daily.jiraMcpServer in settings.
JIRA_READ_TOOLS=(atlassianUserInfo getAccessibleAtlassianResources searchJiraIssuesUsingJql getJiraIssue)
# The name becomes part of an allow rule, so it must not carry wildcards or the `__` separator
JIRA_SERVER_NAME_RE='^[A-Za-z0-9_-]+$'
# dontAsk only denies what nothing allows, and the user's own allow rules still apply. These denials close the
# common ways out for a run that reads untrusted Slack and PR text; they are not a complete list.
DENIED_TOOLS=(WebFetch WebSearch "Bash(curl:*)" "Bash(wget:*)" "Bash(gh:*)" "Bash(git:*)" "Bash(nc:*)" "Bash(ssh:*)")

mkdir -p "$LOG_DIR" "$DATA_DIR"
chmod 700 "$LOG_DIR" "$DATA_DIR"
stamp=$(date +%Y-%m-%d-%H%M)
out="$LOG_DIR/daily-$stamp.json"
err="$LOG_DIR/daily-$stamp.err"

log() { echo "$stamp $1" >> "$RUN_LOG"; }

# find drops the fraction of a day, so +N matches files older than N+1 days
find "$LOG_DIR" -maxdepth 1 -type f \( -name 'daily-*.json' -o -name 'daily-*.err' \) -mtime +"$(( LOG_RETENTION_DAYS - 1 ))" -delete

if ! worklog_python_ok; then
  log "failed: Python 3.11 or newer is required as python3 on the run PATH (found: $(python3 -V 2>&1 | head -n 1))."
  exit 1
fi

started_iso=$(iso_now)
work_dir=""
# The app stops a run with SIGTERM to the process group and removes the lock itself
stopped=0
TRAPTERM() { stopped=1; exit 143; }
TRAPINT() { exit 130; }

record() {
  worklog_py "$SCRIPTS_DIR/daily.py" record-run --started-at "$started_iso" --ended-at "$(iso_now)" \
    --result "$1" --reason "${2:-}" 2>>"$err" || log "run record write failed"
}
fail() { log "failed: $1"; record failed "$1"; exit 1; }

# The Jira server comes first: an empty last line would be dropped by the command substitution
settings=("${(@f)$(worklog_py "$SCRIPTS_DIR/settings.py" show 2>>"$err" | python3 -I -c '
import json, sys
s = json.load(sys.stdin)
print(s["daily"]["jiraMcpServer"] or ""); print(s["provider"]); print(s["logFolder"])' 2>>"$err")}")
(( ${#settings} == 3 )) || fail "Invalid settings"
jira_server="${settings[1]}"
provider="${settings[2]}"
log_folder="${settings[3]}"

if [[ -n "$jira_server" ]] && { [[ ! "$jira_server" =~ $JIRA_SERVER_NAME_RE ]] || [[ "$jira_server" == *__* ]]; }; then
  fail "Invalid Jira MCP server name"
fi
log_folder_is_dedicated "$log_folder" || fail "Log folder must be a dedicated folder"
command -v "$provider" >/dev/null 2>&1 || fail "Provider not found"
# Allow rules match the literal command text, and a path with spaces would have to be quoted
if [[ "$provider" == claude && "$SCRIPTS_DIR" == *[[:space:]]* ]]; then
  fail "Skill path must not contain spaces"
fi
if ! perl -e 'alarm shift; exec @ARGV' "$FOLDER_CHECK_TIMEOUT_SEC" /bin/ls "$log_folder" >/dev/null 2>>"$err"; then
  fail "Log folder not accessible"
fi

find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" -exec rmdir {} \; 2>/dev/null
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "busy: another daily is being generated"
  record busy "Another daily is being generated"
  exit 0
fi
trap '(( stopped )) || rmdir "$LOCK_DIR" 2>/dev/null; [[ -n "$work_dir" ]] && rm -rf "$work_dir"' EXIT

# The provider gets a fresh, empty working directory, which is also the payload folder
work_dir="$(mktemp -d -t work-log-daily)" || fail "Cannot create a working directory"
work_dir="${work_dir:A}"
cd "$work_dir" || fail "Cannot enter the working directory"

# One date for the whole run, so a run that crosses midnight saves and checks the same day
today=$(date +%Y-%m-%d)
daily_file="$DAILIES_DIR/$today.json"
started_epoch=$(date +%s)

# The facts are collected here, before the agent starts. daily_context.py runs git in the folders of past sessions,
# so the agent must not be able to run it with inputs of its own. -E and -s keep PYTHON* variables and user site
# packages out; the working directory is still empty, so nothing planted there can be imported.
perl -e 'alarm shift; exec @ARGV' "$CONTEXT_TIMEOUT_SEC" \
  python3 -E -s "$SCRIPTS_DIR/daily_context.py" --today "$today" >"$work_dir/context.json" 2>>"$err"
context_code=$?
if (( context_code == SIGALRM_EXIT )); then
  fail "Timed out collecting the facts after ${CONTEXT_TIMEOUT_SEC}s"
elif (( context_code != 0 )); then
  fail "Could not collect the facts: $(tail -n 1 "$err")"
fi
mkdir -p "$DAILIES_DIR"
# macOS has no timeout command, so a perl alarm limits the run time
if [[ "$provider" == codex ]]; then
  perl -e 'alarm shift; exec @ARGV' "$DAILY_TIMEOUT_SEC" \
    codex exec --json --sandbox workspace-write --add-dir "$DAILIES_DIR" --skip-git-repo-check '$daily' >"$out" 2>>"$err"
else
  # dontAsk denies every tool call that neither these rules nor the user's own allow rules cover
  allowed=("Read(/$work_dir/**)" "Edit(/$work_dir/**)" "Skill(daily)" "${SLACK_TOOLS[@]}")
  for command in "${DAILY_COMMANDS[@]}"; do
    allowed+=("Bash(python3 $SCRIPTS_DIR/$command:*)")
  done
  if [[ -n "$jira_server" ]]; then
    for tool in "${JIRA_READ_TOOLS[@]}"; do
      allowed+=("mcp__${jira_server}__$tool")
    done
  fi
  context="WorkLog headless daily run for $today. Scripts folder: $SCRIPTS_DIR. Payload folder: $work_dir. The facts are already collected in $work_dir/context.json: read that file and do not run daily_context.py. Call daily.py as python3 $SCRIPTS_DIR/daily.py with that exact path, write the payload only in the payload folder, and save it with --trigger app."
  perl -e 'alarm shift; exec @ARGV' "$DAILY_TIMEOUT_SEC" \
    claude -p "/daily" --permission-mode dontAsk --allowedTools "${allowed[@]}" --disallowedTools "${DENIED_TOOLS[@]}" \
    --append-system-prompt "$context" \
    --no-session-persistence --output-format json >"$out" 2>>"$err"
fi
code=$?

is_error=$(python3 -I -c '
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from runlog import summarize
print(int(summarize(sys.argv[2], Path(sys.argv[3]))["isError"]))
' "$SCRIPTS_DIR" "$provider" "$out" 2>>"$err" || echo 1)
written=0
[[ -f "$daily_file" ]] && written=$(stat -f %m "$daily_file")

result=ok
reason=""
if (( code == SIGALRM_EXIT )); then
  result=timeout; reason="Timed out after ${DAILY_TIMEOUT_SEC}s"
elif (( code != 0 )); then
  result=failed; reason="Provider exited with code $code"
elif (( is_error )); then
  result=failed; reason="Provider reported an error"
elif (( written < started_epoch )); then
  result=noOutput; reason="No daily was saved during this run"
fi

log "$result${reason:+: $reason} ($out)"
record "$result" "$reason"
[[ $result == ok ]]
