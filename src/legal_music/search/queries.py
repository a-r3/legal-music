"""Query variant generation for multi-source legal music search."""
from __future__ import annotations

from dataclasses import dataclass

from ..utils import (
    _has_cyrillic_or_turkic,
    normalize_space,
    parse_artist_title,
    strip_bracket_noise,
    strip_feature_suffix,
    strip_mix_suffix,
    transliterate_cyrillic_turkic,
)


@dataclass(frozen=True)
class QueryVariant:
    query: str
    kind: str
    artist: str = ""
    title: str = ""
    is_fallback: bool = False


def _quoted(*parts: str) -> str:
    return " ".join(f'"{part}"' for part in parts if part)


def build_query_variants(song: str) -> list[QueryVariant]:
    """Build a compact set of high-value query variants.

    Supported variants are intentionally limited to the small set the engine
    actively reasons about across balanced and maximize modes:
    `artist_title`, `title_quoted`, `translit_artist_title`, `translit_raw`,
    `artist_title_quoted`, and `title_only`.
    """
    raw = normalize_space(song)
    artist, title = parse_artist_title(raw)
    title = normalize_space(strip_bracket_noise(title))
    artist = normalize_space(strip_feature_suffix(artist))
    title_core = normalize_space(strip_mix_suffix(strip_feature_suffix(title)))
    variants: list[QueryVariant] = []

    def add(query: str, kind: str, *, fallback: bool = False) -> None:
        query = normalize_space(query)
        if not query:
            return
        variants.append(
            QueryVariant(
                query=query,
                kind=kind,
                artist=artist,
                title=title_core or title,
                is_fallback=fallback,
            )
        )

    if artist and title:
        add(f"{artist} {title}", "artist_title")
        add(_quoted(artist, title), "artist_title_quoted")
        add(f"{title} {artist}", "title_artist", fallback=True)
    if title:
        add(title, "title_only", fallback=True)
        add(f'"{title}"', "title_quoted", fallback=True)
        add(f"{title} instrumental", "title_instrumental", fallback=True)

    # Add transliterated variants if the input contains Cyrillic or Turkic characters
    if _has_cyrillic_or_turkic(raw):
        translit_raw = transliterate_cyrillic_turkic(raw)
        if translit_raw and translit_raw.casefold() != raw.casefold():
            add(translit_raw, "translit_raw", fallback=True)
        
        # Transliterated artist/title if both are present
        if artist and title:
            translit_artist = transliterate_cyrillic_turkic(artist)
            translit_title = transliterate_cyrillic_turkic(title)
            translit_artist_title = normalize_space(f"{translit_artist} {translit_title}")
            if translit_artist_title and translit_artist_title.casefold() != f"{artist} {title}".casefold():
                add(translit_artist_title, "translit_artist_title", fallback=True)

    seen: set[str] = set()
    deduped: list[QueryVariant] = []
    for variant in variants:
        key = variant.query.casefold()
        if key not in seen:
            deduped.append(variant)
            seen.add(key)
    return deduped
