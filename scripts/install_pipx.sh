#!/usr/bin/env bash
# Install legal-music with pipx (recommended for CLI use)
set -euo pipefail

if ! command -v pipx &>/dev/null; then
    echo "pipx not found. Installing..."
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    echo "Restart your shell or run: source ~/.bashrc"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Installing legal-music via pipx from: $REPO_ROOT"
pipx install --force "$REPO_ROOT"
echo ""
echo "Done! Run: legal-music --help"
