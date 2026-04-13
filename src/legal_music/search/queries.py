"""Query variant generation for multi-source search."""
from __future__ import annotations

import re

from ..utils import normalize_song, parse_artist_title


def build_query_variants(song: str) -> list[str]:
    """Return a list of query strings (most specific first)."""
    raw = re.sub(r"\s+", " ", song).strip()
    artist, title = parse_artist_title(raw)
    norm = normalize_song(raw)
    title_norm = normalize_song(title)
    artist_norm = normalize_song(artist)

    variants: list[str] = [raw]
    if norm and norm != raw:
        variants.append(norm)
    if artist and title:
        variants.extend(
            [
                f'"{artist}" "{title}"',
                f"{artist} {title}",
                title,
            ]
        )
        if artist_norm and title_norm:
            variants.extend(
                [
                    f'"{artist_norm}" "{title_norm}"',
                    f"{artist_norm} {title_norm}",
                    title_norm,
                ]
            )
    else:
        if title:
            variants.append(title)

    # Deduplicate, preserving order
    seen: set[str] = set()
    out: list[str] = []
    for item in variants:
        item = re.sub(r"\s+", " ", item).strip()
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out
