"""Free Music Archive source adapter."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ...models import SearchResult, SongStatus
from ..backends import FreeMusicArchiveBackend
from ..base import SourceAdapter


class FreeMusicArchiveSource(SourceAdapter):
    name = "Free Music Archive"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = FreeMusicArchiveBackend(self.session, self.delay)

    def search(self, song: str, variant: str) -> list[str]:
        return self.backend.search(variant, self.max_results)

    def inspect(self, song: str, page_url: str) -> SearchResult:
        try:
            response = self.fetch(page_url)
            html = response.text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links(page_url, html)
            if direct_links:
                return self.make_result(
                    song,
                    page_url,
                    html,
                    direct_links[0],
                    SongStatus.DOWNLOADED,
                    "Direct audio link found on Free Music Archive page.",
                )
            if any(keyword in text for keyword in ["download", "free music archive", "track", "album"]):
                return self.make_result(
                    song,
                    page_url,
                    html,
                    None,
                    SongStatus.PAGE_FOUND,
                    "Free Music Archive page found with probable download access.",
                )
            return self.make_result(
                song,
                page_url,
                html,
                None,
                SongStatus.PAGE_FOUND,
                "Free Music Archive page found.",
            )
        except Exception as exc:
            status_code = None
            if hasattr(exc, "response") and exc.response is not None:
                status_code = exc.response.status_code
            if status_code in (403, 429):
                return SearchResult.blocked(song, self.name, page_url)
            return SearchResult.error(song, self.name, f"Free Music Archive error: {exc}")
