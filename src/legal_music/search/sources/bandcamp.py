"""Bandcamp source adapter (DuckDuckGo site: search + page inspection)."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ...models import SearchResult, SongStatus
from ..backends import BandcampSearchBackend
from ..base import SourceAdapter


class BandcampSource(SourceAdapter):
    name = "Bandcamp"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = BandcampSearchBackend(self.session, self.delay)

    def search(self, song: str, variant: str) -> list[str]:
        """Search Bandcamp via backend."""
        return self.backend.search(variant, self.max_results)

    def inspect(self, song: str, page_url: str) -> SearchResult:
        try:
            r = self.fetch(page_url)
            html = r.text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links(page_url, html)
            if "freeDownloadPage" in html or '"hasAudio":true' in html:
                download_note = "Bandcamp page found with free/name-your-price download metadata."
            else:
                download_note = "Bandcamp page found with download option."
            if direct_links:
                return self.make_result(
                    song, page_url, html, direct_links[0], SongStatus.DOWNLOADED,
                    "Direct audio link found on Bandcamp page."
                )
            # Bandcamp free download indicators
            if any(kw in text for kw in ["buy digital", "download", "name your price", "free download"]):
                return self.make_result(
                    song, page_url, html, None, SongStatus.PAGE_FOUND,
                    download_note
                )
            return self.make_result(
                song, page_url, html, None, SongStatus.PAGE_FOUND,
                "Bandcamp page found (download not confirmed)."
            )
        except Exception as e:
            status_code = None
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
            if status_code in (403, 429):
                return SearchResult.blocked(song, self.name, page_url)
            return SearchResult.error(song, self.name, f"Bandcamp error: {e}")
