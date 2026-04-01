#!/usr/bin/env bash
# =============================================================================
# PACT Common Preamble — platform detection for cross-OS compatibility.
# Source this at the top of every PACT hook script:
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   source "$SCRIPT_DIR/pact-common.sh"
# =============================================================================

# ── Python: resolve python3 vs python ──
if command -v python3 >/dev/null 2>&1; then
  PACT_PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PACT_PYTHON=python
else
  PACT_PYTHON=""
fi

# ── Temp directory: Windows uses %TEMP%, Unix uses /tmp ──
PACT_TEMP="${TEMP:-${TMP:-/tmp}}"

# ── Random bytes: /dev/urandom doesn't exist on Windows ──
pact_random_hex() {
  local bytes="${1:-2}"
  if [ -r /dev/urandom ]; then
    head -c "$bytes" /dev/urandom | od -An -tx1 | tr -d ' \n'
  elif [ -n "$PACT_PYTHON" ]; then
    $PACT_PYTHON -c "import os; print(os.urandom($bytes).hex(), end='')"
  else
    # Last resort: nanoseconds + PID
    echo "$(date +%N 2>/dev/null || echo $$)$$" | md5sum 2>/dev/null | head -c $(( bytes * 2 ))
  fi
}

# ── Date arithmetic: GNU date -d doesn't exist on macOS/Git Bash ──
# Usage: pact_date_to_epoch "2025-03-15"
# Returns epoch seconds, or 0 on failure.
pact_date_to_epoch() {
  local datestr="$1"
  if [ -n "$PACT_PYTHON" ]; then
    $PACT_PYTHON -c "
from datetime import datetime
try:
    dt = datetime.strptime('$datestr', '%Y-%m-%d')
    print(int(dt.timestamp()))
except:
    print(0)
" 2>/dev/null
  elif date -d "$datestr" +%s >/dev/null 2>&1; then
    date -d "$datestr" +%s
  else
    echo 0
  fi
}

# ── Process name lookup: ps -o comm= is GNU-specific ──
pact_parent_name() {
  ps -o comm= -p $PPID 2>/dev/null \
    || ps -p $PPID 2>/dev/null | awk 'NR==2 {print $NF}' \
    || echo "unknown"
}