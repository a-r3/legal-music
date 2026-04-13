"""Search subsystem for legal-music."""
from .engine import SearchEngine
from .filters import dedupe_songs
from .queries import build_query_variants
from .scoring import score_candidate

__all__ = [
    "SearchEngine",
    "dedupe_songs",
    "build_query_variants",
    "score_candidate",
]
