#!/usr/bin/env bash
# Uninstall legal-music
set -euo pipefail

if command -v pipx &>/dev/null; then
    echo "Removing via pipx..."
    pipx uninstall legal-music 2>/dev/null && echo "pipx uninstall done." || echo "Not installed via pipx."
fi

pip uninstall -y legal-music 2>/dev/null && echo "pip uninstall done." || echo "Not installed via pip."

echo "Uninstall complete."
