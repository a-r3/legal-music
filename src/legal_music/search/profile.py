"""Lightweight song profiling for adaptive search."""
from __future__ import annotations

from dataclasses import dataclass

from ..utils import parse_artist_title, strip_accents, tokenize

CLASSICAL_HINTS = {
    "bach", "beethoven", "mozart", "chopin", "vivaldi", "tchaikovsky",
    "sonata", "concerto", "symphony", "prelude", "nocturne", "opus", "op",
    "orchestra", "movement", "suite",
}
INSTRUMENTAL_HINTS = {
    "instrumental", "ambient", "piano", "orchestral", "soundscape", "theme",
}
SOUNDTRACK_HINTS = {"soundtrack", "score", "ost", "theme"}
ELECTRONIC_HINTS = {"mix", "remix", "techno", "house", "edm", "synthwave", "ambient"}


@dataclass(frozen=True)
class SongProfile:
    artist: str
    title: str
    tokens: tuple[str, ...]
    is_classical: bool = False
    is_instrumental: bool = False
    is_soundtrack: bool = False
    is_electronic: bool = False
    has_accents: bool = False
    has_non_ascii: bool = False


def classify_song(song: str) -> SongProfile:
    artist, title = parse_artist_title(song)
    merged_tokens = tuple(tokenize(f"{artist} {title}".strip()))
    token_set = set(merged_tokens)
    lower_song = song.casefold()
    has_accents = strip_accents(song) != song
    has_non_ascii = any(ord(char) > 127 for char in song)

    is_classical = bool(token_set & CLASSICAL_HINTS)
    is_soundtrack = bool(token_set & SOUNDTRACK_HINTS)
    is_instrumental = is_classical or bool(token_set & INSTRUMENTAL_HINTS)
    is_electronic = bool(token_set & ELECTRONIC_HINTS)

    return SongProfile(
        artist=artist,
        title=title,
        tokens=merged_tokens,
        is_classical=is_classical,
        is_instrumental=is_instrumental,
        is_soundtrack=is_soundtrack or "ost" in lower_song,
        is_electronic=is_electronic,
        has_accents=has_accents,
        has_non_ascii=has_non_ascii,
    )
