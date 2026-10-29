#!/bin/zsh
# Statusline tap: saves rate_limits from the statusline JSON on stdin to claude-rate-limits.json.
# Prints nothing and always exits 0 so it never changes or breaks the user's statusline.
# Usage in a statusline command: input=$(cat); echo "$input" | /path/to/save_rate_limits.sh
# Env: WORKLOG_HOME (data dir), WORKLOG_PATH / WORKLOG_EXTRA_PATH (see env.sh)
source "${0:A:h}/env.sh"

worklog_py "${0:A:h}/rate_limits.py" >/dev/null 2>&1
exit 0
