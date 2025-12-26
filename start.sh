#!/bin/bash

# Ensure we are in the script directory (resolving symlinks)
cd "$(dirname "$(readlink -f "$0")")"

# Activate Venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: Virtual environment not found. Please run ./setup-dev.sh first."
    exit 1
fi

# Check if Brain is running (optional warning)
if ! pgrep -f "src/brain.py" > /dev/null; then
    # Try to start it via systemd just in case, non-blocking
    systemctl --user start omni-brain 2>/dev/null || true
fi

# Launch UI instantly
python3 src/omni.py
