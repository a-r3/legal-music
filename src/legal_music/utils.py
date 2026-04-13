"""String utilities: normalization, tokenization, parsing."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .constants import NOISE_WORDS, STOP_WORDS


def normalize_song(name: str) -> str:
    """Normalize a song name for comparison."""
    value = name.casefold().strip()
    # Remove bracketed noise like (Official Audio), [Lyrics], etc.
    value = re.sub(
        r"\((?:[^)]*?(?:official|lyrics?|live|remix|remaster(?:ed)?|audio|video|"
        r"hq|hd|karaoke|instrumental|feat\.?|featuring|ft\.?|prod\.?).*?)\)",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\[(?:[^\]]*?(?:official|lyrics?|live|remix|remaster(?:ed)?|audio|video|"
        r"hq|hd|karaoke|instrumental|feat\.?|featuring|ft\.?|prod\.?).*?)\]",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    # Normalize dashes
    value = re.sub(r"[\u2013\u2014]", "-", value)
    # Strip feat/prod suffixes
    value = re.sub(r"\b(feat\.?|featuring|ft\.?)\b.*$", "", value)
    value = re.sub(r"\b(prod\.?|produced by)\b.*$", "", value)
    # Remove remaining brackets and punctuation
    value = re.sub(r"[()\[\]{}_]+", " ", value)
    value = re.sub(r"[^-\w\s]+", " ", value, flags=re.UNICODE)
    # Remove noise words
    tokens = []
    for token in re.split(r"\s+", value):
        token = token.strip("-_ ")
        if token and token not in NOISE_WORDS:
            tokens.append(token)
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def tokenize(text: str) -> list[str]:
    """Split normalized text into meaningful tokens."""
    return [
        t
        for t in re.split(r"[\s\-]+", normalize_song(text))
        if t and t not in STOP_WORDS
    ]


def parse_artist_title(song: str) -> tuple[str, str]:
    """Split 'Artist - Title' into (artist, title). Returns ('', title) if no separator."""
    raw = re.sub(r"\s+", " ", song).strip()
    # Strip feat/prod first
    raw = re.sub(r"\s+(feat\.?|featuring|ft\.?)\s+.*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+(prod\.?|produced by)\s+.*$", "", raw, flags=re.IGNORECASE)
    for sep in [" - ", " — ", " – ", " _ "]:
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip()
    return "", raw.strip()


def safe_filename(name: str, max_len: int = 180) -> str:
    """Turn a song name into a safe filesystem name."""
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len]


def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def default_config_dir() -> Path:
    if os_name() == "windows":
        return Path.home() / "AppData" / "Roaming" / "legal-music"
    return Path.home() / ".config" / "legal-music"


def default_data_dir() -> Path:
    if os_name() == "windows":
        return Path.home() / "AppData" / "Local" / "legal-music"
    return Path.home() / ".local" / "share" / "legal-music"


def default_output_dir() -> Path:
    return default_data_dir() / "output"


def default_playlists_dir() -> Path:
    return default_data_dir() / "playlists"
