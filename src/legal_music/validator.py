"""Post-download metadata validation and file renaming.

After every download:
1. Read ID3 tags with mutagen.
2. Compare title/artist against expected song name via fuzzywuzzy.
3. If similarity < threshold  →  reject, delete file, log mismatch.
4. If similarity ≥ threshold  →  rename file to "Artist - Title.ext".

Mismatches are appended to output/mismatch_log.txt.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    from mutagen import File as MutagenFile  # type: ignore[import]

    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False
    logger.warning("mutagen not installed — metadata validation disabled")

try:
    from fuzzywuzzy import fuzz  # type: ignore[import]

    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False
    logger.warning("fuzzywuzzy not installed — using simple word-overlap fallback")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD: float = 0.65
MISMATCH_LOG: Path = Path("output/mismatch_log.txt")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation and extra spaces."""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _similarity(a: str, b: str) -> float:
    """Return fuzzy similarity in [0, 1] between two strings."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if HAS_FUZZ:
        return fuzz.token_set_ratio(na, nb) / 100.0
    # Simple word-overlap fallback
    wa, wb = set(na.split()), set(nb.split())
    return len(wa & wb) / max(len(wa), len(wb))


def _log_mismatch(song: str, file_path: Path, reason: str) -> None:
    MISMATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with MISMATCH_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] MISMATCH: song={song!r} file={file_path.name} reason={reason}\n")


def _read_tags(file_path: Path) -> dict[str, str]:
    """Return a dict with 'title' and/or 'artist' from the file's tags."""
    if not HAS_MUTAGEN or not file_path.exists():
        return {}
    try:
        audio = MutagenFile(str(file_path), easy=True)
        if audio is None:
            return {}
        tags: dict[str, str] = {}
        for key in ("title", "artist", "albumartist"):
            val = audio.get(key)
            if val:
                tags[key] = str(val[0]) if isinstance(val, (list, tuple)) else str(val)
        return tags
    except Exception as exc:
        logger.debug("mutagen read failed for %s: %s", file_path, exc)
        return {}


def _safe_part(text: str) -> str:
    """Strip characters that are illegal in filenames."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip(" .")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_and_rename(
    file_path: Path,
    expected_song: str,
    dest_dir: Path | None = None,
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[bool, Path]:
    """Validate a downloaded audio file and rename it to "Artist - Title.ext".

    Parameters
    ----------
    file_path:
        Path to the downloaded file.
    expected_song:
        The search query / expected song name (e.g. "Dua Lipa - Levitating").
    dest_dir:
        Where to place the renamed file (defaults to file_path.parent).
    threshold:
        Fuzzy-similarity minimum (0–1).  Files below this are rejected.

    Returns
    -------
    (valid, path)
        valid=True  → file kept (path may have been renamed).
        valid=False → file deleted (path is the original, now-gone, path).
    """
    if not file_path.exists():
        return False, file_path

    tags = _read_tags(file_path)

    if not tags:
        # mutagen unavailable or no tags — skip validation, keep file
        return True, file_path

    tag_title = tags.get("title", "")
    tag_artist = tags.get("artist", "") or tags.get("albumartist", "")

    if not tag_title:
        # No title tag — cannot validate meaningfully
        return True, file_path

    candidate = f"{tag_artist} - {tag_title}" if tag_artist else tag_title
    sim = _similarity(expected_song, candidate)

    if sim < threshold:
        reason = (
            f"similarity={sim:.2f} < {threshold:.2f}  "
            f"expected={expected_song!r}  got={candidate!r}"
        )
        _log_mismatch(expected_song, file_path, reason)
        logger.info("Rejected mismatch: %s", reason)
        try:
            os.remove(file_path)
        except OSError as exc:
            logger.warning("Could not delete rejected file %s: %s", file_path, exc)
        return False, file_path

    # Similarity OK — rename to "Artist - Title.ext"
    if tag_artist and tag_title:
        ext = file_path.suffix or ".mp3"
        new_name = f"{_safe_part(tag_artist)} - {_safe_part(tag_title)}{ext}"
        target_dir = dest_dir if dest_dir is not None else file_path.parent
        new_path = target_dir / new_name

        # Avoid collisions with existing files (but don't rename onto itself)
        if new_path.exists() and new_path != file_path:
            stem = new_path.stem
            counter = 1
            while new_path.exists():
                new_path = target_dir / f"{stem}_{counter}{ext}"
                counter += 1

        if new_path != file_path:
            try:
                file_path.rename(new_path)
                logger.debug("Renamed: %s → %s", file_path.name, new_path.name)
                return True, new_path
            except OSError as exc:
                logger.warning("Rename failed (%s → %s): %s", file_path, new_path, exc)

    return True, file_path
