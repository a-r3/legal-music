#!/usr/bin/env bash
# Run a single playlist
# Usage: ./scripts/run_playlist.sh <playlist.txt> [--dry-run]
set -euo pipefail

PLAYLIST="${1:-}"
if [[ -z "$PLAYLIST" ]]; then
    echo "Usage: $0 <playlist.txt> [--dry-run]"
    exit 1
fi

DRY=""
if [[ "${2:-}" == "--dry-run" ]]; then
    DRY="dry"
fi

CMD="${DRY:-dl}"
legal-music "$CMD" "$PLAYLIST"
