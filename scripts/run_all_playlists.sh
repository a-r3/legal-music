#!/usr/bin/env bash
# Run all playlists in a directory
# Usage: ./scripts/run_all_playlists.sh [playlists_dir] [--dry-run]
set -euo pipefail

PLAYLISTS_DIR="${1:-playlists}"
DRY=""
if [[ "${2:-}" == "--dry-run" ]]; then
    DRY="batch-dry"
fi

CMD="${DRY:-batch-dl}"
legal-music "$CMD" "$PLAYLISTS_DIR"
