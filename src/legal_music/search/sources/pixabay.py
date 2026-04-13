"""Pixabay Music source adapter (DuckDuckGo site: search + page inspection)."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ...models import SearchResult, SongStatus
from ..backends import PixabayMusicBackend
from ..base import SourceAdapter


class PixabaySource(SourceAdapter):
    name = "Pixabay Music"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = PixabayMusicBackend(self.session, self.delay)

    def search(self, song: str, variant: str) -> list[str]:
        """Search Pixabay Music via backend."""
        return self.backend.search(variant, self.max_results)

    def inspect(self, song: str, page_url: str) -> SearchResult:
        try:
            r = self.fetch(page_url)
            html = r.text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links(page_url, html)
            if "download" in html.lower() and "pixabay" in html.lower():
                page_note = "Pixabay Music page found with download indicators."
            else:
                page_note = "Pixabay Music page found."
            if direct_links:
                return self.make_result(
                    song, page_url, html, direct_links[0], SongStatus.DOWNLOADED,
                    "Direct audio link found on Pixabay Music page."
                )
            if any(kw in text for kw in ["free download", "download", "royalty free", "royalty-free", "music"]):
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
            return SearchResult.error(song, self.name, f"Pixabay error: {e}")
