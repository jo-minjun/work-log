# Sourced by run.sh and save_rate_limits.sh. The app starts them without a login shell, so PATH is set here.
# WORKLOG_PATH replaces PATH entirely (tests). WORKLOG_EXTRA_PATH, which install.sh puts in the app's
# Info.plist from where python3, claude and codex live in the user's shell, goes in front of the defaults.
WORKLOG_DEFAULT_PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
if [[ -n "${WORKLOG_PATH:-}" ]]; then
  export PATH="$WORKLOG_PATH"
else
  export PATH="${WORKLOG_EXTRA_PATH:+$WORKLOG_EXTRA_PATH:}$WORKLOG_DEFAULT_PATH"
fi

# The Command Line Tools python3 is 3.9; the scripts need 3.11 (fromisoformat reads "...Z" session timestamps).
worklog_python_ok() {
  python3 -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null
}

# Runs one of the scripts in isolated mode (-I): neither the working directory nor PYTHON* variables reach
# sys.path, so files a provider wrote there cannot be imported. The script's own folder is added back.
worklog_py() {
  python3 -I -c 'import os, runpy, sys
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0], run_name="__main__")' "$@"
}
