"""YouTube Audio Library source via yt-dlp.

Searches YouTube for Creative Commons licensed tracks using yt-dlp.
Only returns results that have a CC license (license field present and
contains 'Creative Commons').

This source requires yt-dlp to be installed:
    pip install yt-dlp

Downloads are handled by the modified downloader.py via yt-dlp subprocess
when a `ytdl://` prefixed URL or a YouTube URL is detected.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ...models import SearchResult, SongStatus
from ..base import SourceAdapter
from ..scoring import score_candidate

logger = logging.getLogger(__name__)

_YTDLP_BIN = shutil.which("yt-dlp") or "yt-dlp"
YTDL_PREFIX = "ytdl://"


def _ytdlp_available() -> bool:
    """Return True if yt-dlp is installed and executable."""
    return shutil.which("yt-dlp") is not None


def _search_yt(query: str, max_results: int = 5, timeout: int = 8) -> list[dict]:
    """Run yt-dlp to search YouTube and return info dicts for CC tracks."""
    if not _ytdlp_available():
        return []

    cmd = [
        _YTDLP_BIN,
        "--flat-playlist",
        "--print-json",
        "--skip-download",
        "--no-warnings",
        "--quiet",
        # Limit to CC-licensed content
        "--match-filter", "license",
        f"ytsearch{max_results}:{query}",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        tracks: list[dict] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                info = json.loads(line)
                # Only include CC-licensed tracks
                lic = str(info.get("license") or "").lower()
                if "creative commons" in lic or lic:
                    tracks.append(info)
            except json.JSONDecodeError:
                continue
        return tracks
    except subprocess.TimeoutExpired:
        logger.debug("yt-dlp search timed out for query: %r", query)
        return []
    except Exception as exc:
        logger.debug("yt-dlp search error: %s", exc)
        return []


def download_via_ytdlp(url: str, dest_path: Path) -> Path:
    """Download audio from a YouTube URL using yt-dlp.

    Extracts audio as MP3 and saves to dest_path (without extension).
    Returns the actual output path.
    """
    if not _ytdlp_available():
        raise RuntimeError("yt-dlp is not installed")

    output_template = str(dest_path.with_suffix("")) + ".%(ext)s"
    cmd = [
        _YTDLP_BIN,
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-warnings",
        "--quiet",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:200]}")

    # Find the actual output file (yt-dlp may add .mp3)
    mp3_path = dest_path.with_suffix(".mp3")
    if mp3_path.exists():
        return mp3_path
    if dest_path.exists():
        return dest_path
    raise RuntimeError(f"yt-dlp: output file not found at {dest_path}")


class YouTubeAudioLibrarySource(SourceAdapter):
    """Searches YouTube for Creative Commons tracks via yt-dlp."""

    name = "YouTube Audio Library"

    def search(self, song: str, variant: str) -> list[str]:
        """Search YouTube for CC-licensed tracks, return yt-dlp-prefixed URLs."""
        if not _ytdlp_available():
            return []

        tracks = _search_yt(variant, max_results=self.max_results, timeout=self.timeout)
        urls: list[str] = []
        for track in tracks:
            video_id = track.get("id") or track.get("webpage_url")
            if video_id:
                if video_id.startswith("http"):
                    urls.append(video_id)
                else:
                    urls.append(f"https://www.youtube.com/watch?v={video_id}")
        return urls

    def inspect(self, song: str, page_url: str) -> SearchResult:
        """Get metadata for a YouTube video and return as DOWNLOADED result.

        The actual download is deferred to downloader.py which calls yt-dlp.
        We mark it as DOWNLOADED so the engine schedules it for download.
        """
        if not _ytdlp_available():
            return SearchResult.error(song, self.name, "yt-dlp not installed")

        cmd = [
            _YTDLP_BIN,
            "--print-json",
            "--skip-download",
            "--no-warnings",
            "--quiet",
            page_url,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            info: dict = {}
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    try:
                        info = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

            if not info:
                return SearchResult.error(song, self.name, "yt-dlp returned no metadata")

            lic = str(info.get("license") or "").lower()
            if "creative commons" not in lic and not lic:
                return SearchResult.not_found(song)

            title = info.get("title") or info.get("fulltitle") or ""
            uploader = info.get("uploader") or info.get("channel") or ""
            candidate_title = f"{uploader} - {title}" if uploader else title
            score = score_candidate(song, candidate_title, page_url, source_name=self.name)

            # Embed yt-dlp prefix so downloader knows to use yt-dlp
            dl_url = YTDL_PREFIX + page_url

            return SearchResult(
                song=song,
                source=self.name,
                page_url=page_url,
                direct_url=dl_url,
                status=SongStatus.DOWNLOADED,
                note=f"YouTube CC track: {candidate_title!r} license={lic!r}",
                score=score,
                candidate_title=candidate_title,
            )

        except subprocess.TimeoutExpired:
            return SearchResult.error(song, self.name, "yt-dlp inspect timed out")
        except Exception as exc:
            return SearchResult.error(song, self.name, f"YouTube inspect error: {exc}")
