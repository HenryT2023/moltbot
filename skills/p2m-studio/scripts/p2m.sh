#!/bin/bash
# P2M Studio - moltbot skill entry point
# Calls the Python pipeline from HenryBot/p2m_studio
set -e

# Source env vars (GEMINI_API_KEY etc.)
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc" 2>/dev/null || true

# Ensure homebrew bins are in PATH (ffmpeg on Mac Mini)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use Python 3.11 on macmini, fallback to python3
if [ -x "/opt/homebrew/bin/python3.11" ]; then
    PYTHON="/opt/homebrew/bin/python3.11"
else
    PYTHON="python3"
fi

cd "$SKILL_DIR"
export PYTHONPATH="$SKILL_DIR:$PYTHONPATH"
exec "$PYTHON" cli.py "$@"
