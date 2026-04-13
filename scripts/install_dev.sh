#!/usr/bin/env bash
# Set up development environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

echo "Creating virtual environment..."
python3 -m venv .venv

echo "Installing in editable mode with dev tools..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

echo ""
echo "Done! Activate with:"
echo "  source .venv/bin/activate"
echo ""
echo "Then run:"
echo "  legal-music --help"
echo "  pytest"
echo "  ruff check ."
