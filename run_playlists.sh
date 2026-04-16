#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAYLIST_DIR="$ROOT_DIR/playlists"
OUTPUT_DIR="$ROOT_DIR/output"
MODE="dry"
MAXIMIZE=0
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --download)
            MODE="download"
            shift
            ;;
        --maximize)
            MAXIMIZE=1
            shift
            ;;
        --config|-c)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for $1" >&2
                exit 1
            fi
            EXTRA_ARGS+=("$1" "$2")
            shift 2
            ;;
        --no-color|-v|--verbose|--delay|--max-results|--fast|-o|--output)
            if [[ "$1" == "--delay" || "$1" == "--max-results" || "$1" == "-o" || "$1" == "--output" ]]; then
                if [[ $# -lt 2 ]]; then
                    echo "Missing value for $1" >&2
                    exit 1
                fi
                EXTRA_ARGS+=("$1" "$2")
                shift 2
            else
                EXTRA_ARGS+=("$1")
                shift
            fi
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: ./run_playlists.sh [--download] [--maximize] [--verbose] [--no-color] [-c CONFIG]" >&2
            exit 1
            ;;
    esac
done

if [[ ! -d "$PLAYLIST_DIR" ]]; then
    echo "Playlist directory not found: $PLAYLIST_DIR" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

CMD=(python3 -m legal_music)
if [[ "$MODE" == "dry" ]]; then
    CMD+=(batch-dry "$PLAYLIST_DIR")
else
    CMD+=(batch-dl "$PLAYLIST_DIR")
fi

CMD+=(--output "$OUTPUT_DIR")
if [[ "$MAXIMIZE" -eq 1 ]]; then
    CMD+=(--maximize)
fi
CMD+=("${EXTRA_ARGS[@]}")

echo "Running ${MODE} for playlists in $PLAYLIST_DIR"
if [[ "$MAXIMIZE" -eq 1 ]]; then
    echo "Mode: maximize"
else
    echo "Mode: balanced"
fi

PYTHONPATH="$ROOT_DIR/src" "${CMD[@]}"

echo
echo "Per-playlist summary:"
find "$PLAYLIST_DIR" -maxdepth 1 -type f -name '*.txt' | sort | while read -r playlist; do
    name="$(basename "$playlist" .txt)"
    summary="$OUTPUT_DIR/$name/summary.json"
    if [[ -f "$summary" ]]; then
        python3 - "$summary" "$name" <<'PY'
import json, sys
summary_path, name = sys.argv[1], sys.argv[2]
with open(summary_path, encoding="utf-8") as fh:
    data = json.load(fh)
stats = data.get("stats", {})
elapsed = data.get("elapsed_seconds", 0.0)
print(
    f"{name} - processed={stats.get('total', 0)} "
    f"downloaded={stats.get('downloaded', 0)} "
    f"page_found={stats.get('page_found', 0)} "
    f"not_found={stats.get('not_found', 0)} "
    f"elapsed={elapsed:.1f}s"
)
PY
    fi
done
