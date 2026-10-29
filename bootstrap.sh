#!/bin/zsh
# Installs or upgrades work-log without a manual clone: keeps a clone in one folder and runs its install.sh.
# Usage: curl -fsSL https://raw.githubusercontent.com/jo-minjun/work-log/main/bootstrap.sh | zsh -s -- [install.sh options]
# Env: WORKLOG_INSTALL_DIR (default ~/.local/share/work-log), WORKLOG_REPO_URL (default the GitHub repo)
set -euo pipefail

# Everything runs from main, so a download cut off midway runs nothing
main() {
  local dir="${WORKLOG_INSTALL_DIR:-$HOME/.local/share/work-log}"
  local url="${WORKLOG_REPO_URL:-https://github.com/jo-minjun/work-log.git}"

  # /usr/bin/git and /usr/bin/swift exist without the Command Line Tools and only open the install prompt
  if ! xcode-select -p >/dev/null 2>&1; then
    echo "error: WorkLog is built from source and needs the Command Line Tools. Run 'xcode-select --install', then re-run." >&2
    exit 1
  fi

  if [[ -d "$dir/.git" && "$(git -C "$dir" remote get-url origin 2>/dev/null)" == "$url" ]]; then
    echo "==> Updating $dir"
    git -C "$dir" pull --ff-only --quiet || {
      echo "error: could not update $dir. Remove local changes there, or delete the folder, and re-run." >&2
      exit 1
    }
  elif [[ -e "$dir" ]]; then
    echo "error: $dir exists and is not a clone of $url; move it away or set WORKLOG_INSTALL_DIR, and re-run. Nothing was changed." >&2
    exit 1
  else
    echo "==> Cloning into $dir"
    mkdir -p "${dir:h}"
    git clone --quiet "$url" "$dir"
  fi

  exec "$dir/install.sh" "$@"
}

main "$@"
