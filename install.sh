#!/bin/zsh
# Builds WorkLog.app, installs it under a prefix, and links the skill.
# Usage: ./install.sh [--prefix DIR] [--no-open]
set -euo pipefail

PREFIX="$HOME/Applications"
OPEN_APP=1
BUNDLE_ID="dev.worklog.WorkLog"
QUIT_WAIT_SEC=10

while (( $# > 0 )); do
  case "$1" in
    --prefix)
      (( $# >= 2 )) || { echo "error: --prefix needs a directory" >&2; exit 2; }
      PREFIX="$2"; shift 2 ;;
    --no-open) OPEN_APP=0; shift ;;
    -h|--help) echo "Usage: $0 [--prefix DIR] [--no-open]"; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done
# The app is replaced with rm -rf under the prefix, so a prefix that is empty, the root or an option is refused
if [[ -z "$PREFIX" || "$PREFIX" == / || "$PREFIX" == -* ]]; then
  echo "error: --prefix must be a directory path (got '$PREFIX')" >&2
  exit 2
fi

REPO_ROOT="${0:A:h}"
SKILL_DIR="$REPO_ROOT/skill/work-log"
TEMPLATE="$REPO_ROOT/app/Resources/Info.plist.template"
# Codex reads user skills from ~/.agents/skills and Claude Code from ~/.claude/skills; both link straight to the repo
LINKS=("$HOME/.agents/skills/work-log" "$HOME/.claude/skills/work-log")
APP="$PREFIX/WorkLog.app"
LOCK_DIR="${WORKLOG_LOG_DIR:-$HOME/Library/Logs/work-log}/.lock"

[[ -d "$SKILL_DIR" ]] || { echo "error: skill directory not found: $SKILL_DIR" >&2; exit 1; }
[[ -f "$TEMPLATE" ]] || { echo "error: template not found: $TEMPLATE" >&2; exit 1; }

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  value="${value//\'/&apos;}"
  print -r -- "$value"
}

# `is running` fails for an app LaunchServices has never seen, which also means it is not running
app_is_running() {
  [[ "$(osascript -e "application id \"$BUNDLE_ID\" is running" 2>/dev/null)" == true ]]
}

stop_if_collecting() {
  if app_is_running && [[ -d "$LOCK_DIR" ]]; then
    echo "error: a collection is running in WorkLog. Wait for it to finish, then re-run. Nothing was changed." >&2
    exit 1
  fi
}

echo "==> Checking tools"
# The app starts run.sh without a login shell, so the folders of these tools in this shell are recorded for it
EXTRA_PATH=""
for tool in python3 claude codex; do
  found="$(command -v "$tool" 2>/dev/null || true)"
  [[ "$found" == /* ]] || continue
  dir="${found:h}"
  [[ ":$EXTRA_PATH:" == *":$dir:"* ]] || EXTRA_PATH="${EXTRA_PATH:+$EXTRA_PATH:}$dir"
done
echo "Run PATH starts with: ${EXTRA_PATH:-(defaults only)}"
run_env=(env -u WORKLOG_PATH WORKLOG_EXTRA_PATH="$EXTRA_PATH" zsh -fc)
if ! "${run_env[@]}" 'source "$1"; worklog_python_ok' _ "$SKILL_DIR/scripts/env.sh"; then
  found="$("${run_env[@]}" 'source "$1"; python3 -V 2>&1 | head -n 1' _ "$SKILL_DIR/scripts/env.sh" || true)"
  echo "error: WorkLog needs Python 3.11 or newer as python3 (found: ${found:-none})." >&2
  echo "       The Command Line Tools python3 is 3.9. Install a newer one (for example with Homebrew or mise) and re-run." >&2
  exit 1
fi
echo "Requires Python 3.11 or newer as python3: found $("${run_env[@]}" 'source "$1"; python3 -V' _ "$SKILL_DIR/scripts/env.sh")"

echo "==> Checking skill links"
# Every link is checked before anything is changed, so a refusal leaves both places as they were
typeset -A LINK_ACTIONS
for link in "${LINKS[@]}"; do
  if [[ -L "$link" ]]; then
    [[ "$(readlink "$link")" == "$SKILL_DIR" ]] && LINK_ACTIONS[$link]=keep || LINK_ACTIONS[$link]=replace
  elif [[ -e "$link" ]]; then
    echo "error: $link exists and is not a symlink; move it away and re-run. Nothing was changed." >&2
    exit 1
  else
    LINK_ACTIONS[$link]=create
  fi
done

if [[ -e "$APP" ]]; then
  existing_id="$(plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist" 2>/dev/null || true)"
  if [[ "$existing_id" != "$BUNDLE_ID" ]]; then
    echo "error: $APP is not WorkLog (bundle id: ${existing_id:-unknown}); move it away and re-run. Nothing was changed." >&2
    exit 1
  fi
fi
stop_if_collecting

echo "==> Building (release)"
swift build -c release --package-path "$REPO_ROOT/app"
BIN="$(swift build -c release --package-path "$REPO_ROOT/app" --show-bin-path)/WorkLog"
[[ -x "$BIN" ]] || { echo "error: built binary not found: $BIN" >&2; exit 1; }

echo "==> Assembling bundle"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
STAGED_APP="$STAGE/WorkLog.app"
mkdir -p "$STAGED_APP/Contents/MacOS"
cp "$BIN" "$STAGED_APP/Contents/MacOS/WorkLog"

PLIST="$(<"$TEMPLATE")"
PLIST="${PLIST//__SKILL_PATH__/$(xml_escape "$SKILL_DIR")}"
PLIST="${PLIST//__EXTRA_PATH__/$(xml_escape "$EXTRA_PATH")}"
print -r -- "$PLIST" > "$STAGED_APP/Contents/Info.plist"
plutil -lint "$STAGED_APP/Contents/Info.plist" >/dev/null

echo "==> Signing (ad hoc)"
codesign --force --sign - "$STAGED_APP"

# A collection may have started during the build, so check again right before the app is replaced
stop_if_collecting
if app_is_running; then
  echo "==> Quitting the running WorkLog"
  osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null
  for _ in {1..$QUIT_WAIT_SEC}; do
    app_is_running || break
    sleep 1
  done
  if app_is_running; then
    echo "error: WorkLog did not quit within ${QUIT_WAIT_SEC}s; quit it and re-run. Nothing was changed." >&2
    exit 1
  fi
fi

echo "==> Installing to $APP"
mkdir -p "$PREFIX"
rm -rf "$APP"
mv "$STAGED_APP" "$APP"

for link in "${LINKS[@]}"; do
  action="${LINK_ACTIONS[$link]}"
  echo "==> Skill link $link ($action)"
  [[ "$action" == replace ]] && echo "Previous link target: $(readlink "$link")"
  if [[ "$action" != keep ]]; then
    mkdir -p "${link:h}"
    ln -sfn "$SKILL_DIR" "$link"
  fi
done

if (( OPEN_APP )); then
  echo "==> Opening app"
  open "$APP"
else
  echo "==> Skipping launch (--no-open)"
fi
echo "Done."
