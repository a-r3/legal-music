"""Incompetech source adapter.

Kevin MacLeod's incompetech.com hosts thousands of royalty-free,
Creative Commons licensed music tracks, freely downloadable as MP3.

Search endpoint: https://incompetech.com/music/royalty-free/search/?keywords={query}
Download links follow the pattern: https://incompetech.com/music/royalty-free/mp3-royaltyfree/{title}.mp3
"""
from __future__ import annotations

import urllib.parse
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...models import SearchResult, SongStatus
from ..base import SourceAdapter
from ..scoring import score_candidate

_SEARCH_URL = "https://incompetech.com/music/royalty-free/search/"
_BASE_URL = "https://incompetech.com"


class IncompetechSource(SourceAdapter):
    name = "Incompetech"

    def search(self, song: str, variant: str) -> list[str]:
        """Search incompetech and return track page URLs."""
        params = {"keywords": variant, "type": "any"}
        url = f"{_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            r = self.fetch(url, timeout=self.timeout)
            soup = BeautifulSoup(r.text, "html.parser")

            urls: list[str] = []
            # Track links are typically inside div.royalty-free-music or similar containers
            for a in soup.find_all("a", href=True):
                href = str(a["href"])
                full = urljoin(_BASE_URL, href)
                if "/music/royalty-free/" in full and full not in urls:
                    # Filter out the search page itself and navigation
                    if "search" not in href and "?" not in href:
                        urls.append(full)
                if len(urls) >= self.max_results:
                    break

            return urls
        except Exception:
            return []

    def inspect(self, song: str, page_url: str) -> SearchResult:
        """Inspect an incompetech track page for the direct MP3 link."""
        try:
            r = self.fetch(page_url, timeout=self.timeout)
            html = r.text
            soup = BeautifulSoup(html, "html.parser")

            page_title = self.extract_page_title(html)
            score = score_candidate(song, page_title, page_url, source_name=self.name)

            # Look for direct MP3 download links
            mp3_url: str | None = None
            for a in soup.find_all("a", href=True):
                href = str(a["href"])
                if href.lower().endswith(".mp3"):
                    mp3_url = urljoin(page_url, href)
                    break

            # Also check audio/source tags
            if not mp3_url:
                direct_links = self.extract_direct_audio_links(page_url, html)
                mp3_links = [u for u in direct_links if u.lower().endswith(".mp3")]
                if mp3_links:
                    mp3_url = mp3_links[0]

            if mp3_url:
                return SearchResult(
                    song=song,
                    source=self.name,
                    page_url=page_url,
                    direct_url=mp3_url,
                    status=SongStatus.DOWNLOADED,
                    note="Direct MP3 found on Incompetech.",
                    score=score,
                    candidate_title=page_title,
                )

            return SearchResult(
                song=song,
                source=self.name,
                page_url=page_url,
                direct_url=None,
                status=SongStatus.PAGE_FOUND,
                note="Incompetech page found (no direct link detected).",
                score=score,
                candidate_title=page_title,
            )

        except Exception as exc:
            code = None
            if hasattr(exc, "response") and exc.response is not None:
                code = exc.response.status_code
            if code in (403, 429):
                return SearchResult.blocked(song, self.name, page_url)
            return SearchResult.error(song, self.name, f"Incompetech error: {exc}")
