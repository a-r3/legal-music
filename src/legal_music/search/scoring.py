"""Candidate relevance scoring."""
from __future__ import annotations

import difflib
from urllib.parse import unquote, urlparse

from ..utils import normalize_song, parse_artist_title, tokenize


def score_candidate(song: str, candidate_title: str, page_url: str) -> float:
    """Return a relevance score in [0, 1] for a candidate page."""
    artist, title = parse_artist_title(song)

    song_norm = normalize_song(song)
    cand_norm = normalize_song(candidate_title or "")
    url_text = unquote(urlparse(page_url).path).replace("/", " ")
    url_norm = normalize_song(url_text)

    song_tokens = set(tokenize(song))
    title_tokens = set(tokenize(title))
    artist_tokens = set(tokenize(artist))
    cand_tokens = set(tokenize(candidate_title + " " + url_text))

    seq1 = difflib.SequenceMatcher(None, song_norm, cand_norm).ratio() if cand_norm else 0.0
    seq2 = difflib.SequenceMatcher(None, song_norm, url_norm).ratio() if url_norm else 0.0

    token_all = len(song_tokens & cand_tokens) / max(1, len(song_tokens))
    token_title = (
        len(title_tokens & cand_tokens) / max(1, len(title_tokens)) if title_tokens else 0.0
    )
    token_artist = (
        len(artist_tokens & cand_tokens) / max(1, len(artist_tokens)) if artist_tokens else 0.0
    )

    score = max(seq1, seq2) * 0.40 + token_all * 0.25 + token_title * 0.25 + token_artist * 0.10

    # Bonus for strong title + artist match
    if token_title >= 0.70 and (not artist_tokens or token_artist >= 0.50):
        score += 0.15

    return min(score, 1.0)
