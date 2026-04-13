"""Playlist file reading utilities."""
from __future__ import annotations

from pathlib import Path


def read_playlist(path: Path) -> list[str]:
    """Read a playlist .txt file. Returns list of non-empty, non-comment lines."""
    if not path.exists():
        raise FileNotFoundError(f"Playlist not found: {path}")
    songs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            songs.append(line)
    if not songs:
        raise ValueError(f"Playlist is empty: {path}")
    return songs


def read_playlists_dir(directory: Path) -> dict[str, list[str]]:
    """Read all .txt files in a directory. Returns {name: songs}."""
    if not directory.exists():
        raise FileNotFoundError(f"Playlist directory not found: {directory}")
    playlists: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.txt")):
        try:
            songs = read_playlist(path)
            playlists[path.stem] = songs
        except ValueError:
            pass  # skip empty files
    if not playlists:
        raise ValueError(f"No valid playlist files found in: {directory}")
    return playlists


EXAMPLE_PLAYLIST = """\
# One song per line (Artist - Title)
# Lines starting with # are ignored.

Frank Sinatra - My Way
John Mayer - Gravity
Nina Simone - Feeling Good
"""


def write_example_playlist(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(EXAMPLE_PLAYLIST, encoding="utf-8")
