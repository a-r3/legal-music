"""Jamendo source adapter (direct search + page inspection)."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ...models import SearchResult, SongStatus
from ..backends import JamendoAPIBackend
from ..base import SourceAdapter


class JamendoSource(SourceAdapter):
    name = "Jamendo"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = JamendoAPIBackend(self.session, self.delay)

    def search(self, song: str, variant: str) -> list[str]:
        """Search Jamendo via backend."""
        return self.backend.search(variant, self.max_results)

    def inspect(self, song: str, page_url: str) -> SearchResult:
        try:
            r = self.fetch(page_url)
            html = r.text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links(page_url, html)
            if 'download' in html.lower() and 'track' in html.lower():
                page_note = "Jamendo page found with download indicators."
            else:
                page_note = "Jamendo page found."
            if direct_links:
                return self.make_result(
                    song, page_url, html, direct_links[0], SongStatus.DOWNLOADED,
                    "Direct audio link found on Jamendo page."
                )
            if any(kw in text for kw in ["free download", "download", "royalty free", "royalty-free"]):
                return self.make_result(
                    song, page_url, html, None, SongStatus.PAGE_FOUND,
                    page_note
                )
            return self.make_result(
                song, page_url, html, None, SongStatus.PAGE_FOUND,
                page_note
            )
        except Exception as e:
            status_code = None
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
            if status_code in (403, 429):
                return SearchResult.blocked(song, self.name, page_url)
            return SearchResult.error(song, self.name, f"Jamendo error: {e}")
