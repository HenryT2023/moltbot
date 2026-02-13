#!/bin/bash
# P2M Studio - moltbot skill entry point
# Calls the Python pipeline from HenryBot/p2m_studio
set -e

# Source env vars (GEMINI_API_KEY etc.)
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc" 2>/dev/null || true

# Ensure homebrew bins are in PATH (ffmpeg on Mac Mini)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
P2M_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PYTHON="/usr/bin/python3"

# Check if running on Mac Mini (production)
if [ -d "$HOME/HenryBot/p2m_studio" ]; then
    P2M_ROOT="$HOME/HenryBot"
fi

cd "$P2M_ROOT"
exec "$PYTHON" -m p2m_studio.cli "$@"
