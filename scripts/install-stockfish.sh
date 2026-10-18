#!/usr/bin/env bash
# Install OS-managed binaries outside the checkout (Ubuntu/Debian/Droplets).
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
    echo "This installer requires Ubuntu/Debian. Install Stockfish with your OS package manager." >&2
    exit 1
fi

privilege=()
if [[ "$(id -u)" != "0" ]]; then
    if ! command -v sudo >/dev/null 2>&1; then
        echo "Run as root or install sudo before running this installer." >&2
        exit 1
    fi
    privilege=(sudo)
fi

"${privilege[@]}" apt-get update
"${privilege[@]}" apt-get install -y --no-install-recommends stockfish
echo "Installed Stockfish outside Git. Check it with: python -m chess_analyzer --check-engine"