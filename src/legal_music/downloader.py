"""File downloading utilities.

Supports:
- Direct HTTP downloads (requests)
- yt-dlp downloads for YouTube/ytdl:// URLs
- Post-download metadata validation and rename via validator.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from .constants import AUDIO_EXTENSIONS, DOWNLOAD_TIMEOUT, HEADERS
from .utils import safe_filename

logger = logging.getLogger(__name__)

# Lazy imports for optional deps
_validator_imported = False
_validate_fn = None

YTDL_PREFIX = "ytdl://"


def _try_import_validator():
    global _validator_imported, _validate_fn
    if not _validator_imported:
        try:
            from .validator import validate_and_rename
            _validate_fn = validate_and_rename
        except ImportError:
            _validate_fn = None
        _validator_imported = True
    return _validate_fn


def guess_extension(response: requests.Response, url: str) -> str:
    ct = (response.headers.get("Content-Type") or "").lower()
    ul = url.lower()
    for ext in AUDIO_EXTENSIONS:
        if ext.lstrip(".") in ul or ext.lstrip(".") in ct:
            return ext
    if "mp4" in ct or "m4a" in ct:
        return ".m4a"
    return ".mp3"


def _download_via_ytdlp(url: str, song_name: str, dest_dir: Path) -> Path:
    """Download a YouTube URL using yt-dlp subprocess."""
    from .search.sources.ytdlp_source import download_via_ytdlp

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(song_name)
    dest = dest_dir / filename  # extension added by yt-dlp
    return download_via_ytdlp(url, dest)


def download_file(
    url: str,
    song_name: str,
    dest_dir: Path,
    session: requests.Session | None = None,
    *,
    validate: bool = True,
) -> Path:
    """Download an audio file to dest_dir and return the saved path.

    If *url* starts with ``ytdl://`` the download is delegated to yt-dlp.
    After a successful HTTP download, metadata is validated with mutagen/
    fuzzywuzzy (if available).  Files that don't match *song_name* are
    rejected and a FileNotFoundError is raised so the caller can try the
    next candidate.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  yt-dlp path                                                         #
    # ------------------------------------------------------------------ #
    if url.startswith(YTDL_PREFIX):
        real_url = url[len(YTDL_PREFIX):]
        saved = _download_via_ytdlp(real_url, song_name, dest_dir)
        if validate:
            fn = _try_import_validator()
            if fn is not None:
                valid, new_path = fn(saved, song_name, dest_dir)
                if not valid:
                    raise FileNotFoundError(
                        f"Metadata mismatch for {song_name!r}; file rejected"
                    )
                saved = new_path
        return saved

    # ------------------------------------------------------------------ #
    #  Standard HTTP path                                                  #
    # ------------------------------------------------------------------ #
    headers = dict(HEADERS)
    if session:
        r = session.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
    else:
        r = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()

    ext = guess_extension(r, url)
    filename = f"{safe_filename(song_name)}{ext}"
    dest = dest_dir / filename

    # Avoid overwriting: append counter if needed
    counter = 1
    while dest.exists():
        filename = f"{safe_filename(song_name)}_{counter}{ext}"
        dest = dest_dir / filename
        counter += 1

    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=131072):
            if chunk:
                f.write(chunk)

    # ------------------------------------------------------------------ #
    #  Metadata validation + rename                                        #
    # ------------------------------------------------------------------ #
    if validate:
        fn = _try_import_validator()
        if fn is not None:
            valid, new_path = fn(dest, song_name, dest_dir)
            if not valid:
                raise FileNotFoundError(
                    f"Metadata mismatch for {song_name!r}; file rejected"
                )
            dest = new_path

    return dest
