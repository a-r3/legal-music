"""Candidate relevance scoring."""
from __future__ import annotations

import difflib
from urllib.parse import unquote, urlparse

from ..utils import (
    normalize_song,
    normalize_space,
    parse_artist_title,
    strip_mix_suffix,
    tokenize,
)

SOURCE_CONFIDENCE = {
    "Internet Archive": 0.10,
    "Bandcamp": 0.02,
    "Free Music Archive": 0.06,
    "Jamendo": 0.07,
    "Pixabay Music": 0.06,
    "CCMixter": 0.07,
    "Incompetech": 0.07,
    "YouTube Audio Library": 0.05,
}

BANDCAMP_LOW_VALUE_WORDS = {
    "remix", "edit", "rework", "cover", "bootleg", "mashup", "flip", "vip", "version",
}


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _coverage(expected: set[str], actual: set[str]) -> float:
    if not expected:
        return 0.0
    return len(expected & actual) / len(expected)


def score_candidate(
    song: str,
    candidate_title: str,
    page_url: str,
    *,
    source_name: str = "",
) -> float:
    """Return a relevance score in [0, 1] for a candidate page."""
    artist, title = parse_artist_title(song)
    title_core = strip_mix_suffix(title)

    song_norm = normalize_song(song)
    title_norm = normalize_song(title_core or title)
    artist_norm = normalize_song(artist)
    cand_norm = normalize_song(candidate_title or "")
    cand_core = normalize_song(strip_mix_suffix(candidate_title or ""))
    url_text = normalize_space(unquote(urlparse(page_url).path).replace("/", " "))
    url_norm = normalize_song(url_text)

    song_tokens = set(tokenize(song))
    title_tokens = set(tokenize(title_core or title))
    artist_tokens = set(tokenize(artist))
    candidate_tokens = set(tokenize(f"{candidate_title} {url_text}"))

    whole_match = max(_ratio(song_norm, cand_norm), _ratio(song_norm, url_norm))
    title_match = max(_ratio(title_norm, cand_norm), _ratio(title_norm, cand_core), _ratio(title_norm, url_norm))
    artist_match = max(_ratio(artist_norm, cand_norm), _ratio(artist_norm, url_norm))
    token_all = _coverage(song_tokens, candidate_tokens)
    token_title = _coverage(title_tokens, candidate_tokens)
    token_artist = _coverage(artist_tokens, candidate_tokens) if artist_tokens else 0.0

    score = (
        whole_match * 0.22
        + title_match * 0.30
        + artist_match * 0.13
        + token_all * 0.12
        + token_title * 0.15
        + token_artist * 0.08
    )

    if title_norm and title_norm in {cand_norm, cand_core, url_norm}:
        score += 0.18
    elif title_match >= 0.92:
        score += 0.12
    elif title_match >= 0.82 and token_title >= 0.75:
        score += 0.08

    if artist_tokens:
        if token_artist >= 0.99 or artist_match >= 0.95:
            score += 0.08
        elif token_artist >= 0.66 and title_match >= 0.85:
            score += 0.05
        elif token_artist == 0.0 and token_title < 0.85:
            score -= 0.10

    if song_tokens and not (song_tokens & candidate_tokens):
        score -= 0.20
    if title_tokens and not (title_tokens & candidate_tokens):
        score -= 0.15

    if source_name == "Bandcamp":
        low_value_overlap = BANDCAMP_LOW_VALUE_WORDS & candidate_tokens
        requested_low_value = BANDCAMP_LOW_VALUE_WORDS & title_tokens
        if low_value_overlap and not requested_low_value:
            score -= 0.18
        if artist_tokens and token_artist < 0.45:
            score -= 0.14
        if title_match < 0.86:
            score -= 0.08
    elif source_name == "Internet Archive" and title_match >= 0.86:
        score += 0.03

    score += SOURCE_CONFIDENCE.get(source_name, 0.0)
    return max(0.0, min(score, 1.0))
