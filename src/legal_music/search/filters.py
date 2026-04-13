"""Duplicate detection for song lists."""
from __future__ import annotations

import difflib

from ..utils import normalize_song, tokenize


def dedupe_songs(
    songs: list[str],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """
    Remove near-duplicate entries from a song list.

    Returns:
        (unique_songs, removed_list)
        where removed_list contains (raw_song, matched_song, reason) tuples.
    """
    unique: list[str] = []
    seen: list[tuple[str, str, frozenset[str]]] = []
    removed: list[tuple[str, str, str]] = []

    for song in songs:
        norm = normalize_song(song)
        tokens = frozenset(tokenize(song))
        if not norm:
            continue

        duplicate_of: tuple[str, str] | None = None
        for existing_song, existing_norm, existing_tokens in seen:
            if norm == existing_norm:
                duplicate_of = (existing_song, "exact")
                break
            ratio = difflib.SequenceMatcher(None, norm, existing_norm).ratio()
            token_overlap = (
                len(tokens & existing_tokens) / max(1, len(tokens | existing_tokens))
                if (tokens or existing_tokens)
                else 0.0
            )
            if ratio >= 0.94:
                duplicate_of = (existing_song, f"near:{ratio:.2f}")
                break
            if token_overlap >= 0.88 and min(len(tokens), len(existing_tokens)) >= 2:
                duplicate_of = (existing_song, f"token:{token_overlap:.2f}")
                break

        if duplicate_of:
            removed.append((song, duplicate_of[0], duplicate_of[1]))
        else:
            unique.append(song)
            seen.append((song, norm, tokens))

    return unique, removed
