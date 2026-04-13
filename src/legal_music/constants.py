"""Project-wide constants."""
from __future__ import annotations

VERSION = "2.0.0"
APP_NAME = "legal-music"
APP_DIR = "legal-music"

AUDIO_EXTENSIONS = (".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus")

NOISE_WORDS: frozenset[str] = frozenset(
    {
        "official",
        "audio",
        "video",
        "lyrics",
        "lyric",
        "live",
        "remix",
        "edit",
        "version",
        "remastered",
        "remaster",
        "hq",
        "hd",
        "full",
        "album",
        "topic",
        "track",
        "music",
        "feat",
        "featuring",
        "ft",
        "karaoke",
        "instrumental",
        "cover",
        "extended",
        "radio",
        "prod",
        "produced",
        "performance",
        "clip",
        "visualizer",
        "teaser",
        "clean",
        "explicit",
    }
)

STOP_WORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "by"}
)

REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120
DEFAULT_DELAY = 1.2
DEFAULT_MAX_RESULTS = 8
DEFAULT_RETRY_COUNT = 2
DEFAULT_BACKOFF = 2.0

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Score thresholds
MIN_DOWNLOADABLE_SCORE = 0.40
MIN_PAGE_SCORE = 0.52
MIN_BEST_SEEN_SCORE = 0.55
