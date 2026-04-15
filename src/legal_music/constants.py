"""Project-wide constants."""
from __future__ import annotations

VERSION = "2.3.0"
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
        "mono",
        "stereo",
        "session",
        "sessions",
        "bonus",
        "deluxe",
        "anniversary",
        "recorded",
    }
)

MIX_NOISE_WORDS: frozenset[str] = frozenset(
    {
        "live",
        "remix",
        "edit",
        "version",
        "remastered",
        "remaster",
        "mix",
        "demo",
        "radio",
        "extended",
        "mono",
        "stereo",
        "session",
        "sessions",
        "bonus",
        "deluxe",
        "anniversary",
        "instrumental",
        "karaoke",
        "acoustic",
    }
)

STOP_WORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "by"}
)

REQUEST_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 120
DEFAULT_DELAY = 0.3
DEFAULT_MAX_RESULTS = 3
DEFAULT_RETRY_COUNT = 0
DEFAULT_BACKOFF = 1.0
DEFAULT_PER_SONG_TIMEOUT = 10
DEFAULT_QUERY_VARIANTS = 5
FAST_QUERY_VARIANTS = 2
MAXIMIZE_QUERY_VARIANTS = 8
DEFAULT_EARLY_EXIT_SCORE = 0.95
DEFAULT_FALLBACK_POLICY = "page_or_best_seen"
DEFAULT_DEGRADED_AFTER_TIMEOUTS = 4
DEFAULT_UNHEALTHY_AFTER_TIMEOUTS = 6
DEFAULT_BLOCKED_AFTER_FAILURES = 3

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
