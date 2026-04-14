"""String utilities: normalization, tokenization, parsing."""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

from .constants import MIX_NOISE_WORDS, NOISE_WORDS, STOP_WORDS

_FEATURE_RE = re.compile(r"\b(feat\.?|featuring|ft\.?)\b", re.IGNORECASE)
_PROD_RE = re.compile(r"\b(prod\.?|produced by)\b", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"\s*(?:-|–|—|:|\||·|•|_)\s*")
_BRACKETED_RE = re.compile(r"(\([^)]*\)|\[[^\]]*\]|\{[^}]*\})")

# Cyrillic to Latin transliteration table
_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '',
    'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}

# Azerbaijani/Turkish specific characters
_TURKIC_TO_LATIN = {
    'ə': 'a', 'Ə': 'A', 'ı': 'i', 'İ': 'I', 'ş': 's', 'Ş': 'S',
    'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U', 'ö': 'o', 'Ö': 'O',
    'ç': 'c', 'Ç': 'C',
}


def transliterate_cyrillic_turkic(text: str) -> str:
    """Transliterate Cyrillic and Turkic characters to Latin equivalents.
    
    Useful for improving search results on sources that have Latin-indexed
    versions of content originally in Cyrillic or Turkic scripts.
    
    Returns the transliterated text, or the original if no transliteration needed.
    """
    result = []
    for char in text:
        # Try Cyrillic first
        if char in _CYRILLIC_TO_LATIN:
            result.append(_CYRILLIC_TO_LATIN[char])
        # Then Turkic
        elif char in _TURKIC_TO_LATIN:
            result.append(_TURKIC_TO_LATIN[char])
        # Keep other characters as-is
        else:
            result.append(char)
    return ''.join(result)


def _has_cyrillic_or_turkic(text: str) -> bool:
    """Check if text contains Cyrillic or Turkic characters."""
    for char in text:
        if char in _CYRILLIC_TO_LATIN or char in _TURKIC_TO_LATIN:
            return True
    return False


def _simple_tokens(text: str) -> list[str]:
    base = strip_accents(text).casefold()
    base = re.sub(r"[^-\w\s]+", " ", base, flags=re.UNICODE)
    return [token for token in re.split(r"[\s\-]+", base) if token]


def strip_accents(text: str) -> str:
    """Return a Unicode-normalized accent-folded version of text."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_feature_suffix(text: str) -> str:
    return normalize_space(_FEATURE_RE.split(text, maxsplit=1)[0])


def strip_prod_suffix(text: str) -> str:
    return normalize_space(_PROD_RE.split(text, maxsplit=1)[0])


def strip_mix_suffix(text: str) -> str:
    """Remove trailing version/mix noise while preserving the core title."""
    cleaned = normalize_space(text)
    for pattern in [
        r"\s*[-–—]\s*(?:live|remaster(?:ed)?|remix|mix|version|edit|demo|acoustic)\b.*$",
        r"\s*\((?:[^)]*?(?:live|remaster(?:ed)?|remix|mix|version|edit|demo|acoustic|mono|stereo).*)\)$",
        r"\s*\[(?:[^\]]*?(?:live|remaster(?:ed)?|remix|mix|version|edit|demo|acoustic|mono|stereo).*)\]$",
    ]:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    suffix_tokens = re.split(r"\s+", cleaned)
    while suffix_tokens and suffix_tokens[-1].casefold().strip("._-") in MIX_NOISE_WORDS:
        suffix_tokens.pop()
    return normalize_space(" ".join(suffix_tokens))


def strip_bracket_noise(text: str) -> str:
    """Remove bracketed segments that mostly contain edition/noise words."""
    def _repl(match: re.Match[str]) -> str:
        segment = match.group(0)
        tokens = _simple_tokens(segment)
        if tokens and all(token in NOISE_WORDS or token in MIX_NOISE_WORDS for token in tokens):
            return " "
        lower = segment.casefold()
        if any(word in lower for word in ("official", "lyrics", "remaster", "live", "video", "audio")):
            return " "
        return segment

    return normalize_space(_BRACKETED_RE.sub(_repl, text))


def normalize_song(name: str) -> str:
    """Normalize a song name for comparison."""
    value = strip_accents(name).casefold().strip()
    value = strip_bracket_noise(value)
    value = re.sub(r"[\u2013\u2014]", "-", value)
    value = strip_feature_suffix(value)
    value = strip_prod_suffix(value)
    value = re.sub(r"[()\[\]{}_]+", " ", value)
    value = re.sub(r"[^-\w\s]+", " ", value, flags=re.UNICODE)
    tokens = []
    for token in re.split(r"\s+", value):
        token = token.strip("-_ ")
        if token and token not in NOISE_WORDS:
            tokens.append(token)
    return normalize_space(" ".join(tokens))


def tokenize(text: str) -> list[str]:
    """Split normalized text into meaningful tokens."""
    return [
        t
        for t in re.split(r"[\s\-]+", normalize_song(text))
        if t and t not in STOP_WORDS
    ]


def parse_artist_title(song: str) -> tuple[str, str]:
    """Split 'Artist - Title' into (artist, title). Returns ('', title) if no separator."""
    raw = normalize_space(song)
    raw = strip_prod_suffix(raw)
    raw = strip_bracket_noise(raw)

    if " by " in raw.casefold():
        title, artist = re.split(r"\s+by\s+", raw, maxsplit=1, flags=re.IGNORECASE)
        return normalize_space(artist), normalize_space(title)

    parts = [part.strip() for part in _SEPARATOR_RE.split(raw) if part.strip()]
    if len(parts) >= 2:
        left, right = parts[0], " - ".join(parts[1:])
        left_norm = tokenize(left)
        right_norm = tokenize(right)
        if len(left_norm) <= 5 and len(right_norm) >= 1:
            return (
                normalize_space(strip_feature_suffix(left)),
                normalize_space(strip_feature_suffix(right)),
            )

    return "", normalize_space(strip_feature_suffix(raw))


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
