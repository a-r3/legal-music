"""Internet Archive source adapter (open API + page inspection)."""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...constants import AUDIO_EXTENSIONS
from ...models import SearchResult, SongStatus
from ..backends import InternetArchiveAPIBackend
from ..base import SourceAdapter

_IA_DETAILS = "https://archive.org/details/"


class InternetArchiveSource(SourceAdapter):
    name = "Internet Archive"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = InternetArchiveAPIBackend(self.session, self.delay)

    def search(self, song: str, variant: str) -> list[str]:
        """Use the Archive.org native API to find music items."""
        # Direct API search - no DuckDuckGo dependency
        return self.backend.search(variant, self.max_results)

    def inspect(self, song: str, page_url: str) -> SearchResult:
        try:
            r = self.fetch(page_url, timeout=self.timeout)
            html = r.text
            soup = BeautifulSoup(html, "html.parser")

            # Find direct audio download links
            direct_links: list[str] = []
            for a in soup.find_all("a", href=True):
                href = urljoin(page_url, str(a["href"]))
                if any(href.lower().endswith(ext) for ext in AUDIO_EXTENSIONS):
                    direct_links.append(href)

            # Also try <audio> / <source> tags
            direct_links.extend(self.extract_direct_audio_links(page_url, html))
            # Deduplicate
            seen: set[str] = set()
            unique_links = [u for u in direct_links if not (u in seen or seen.add(u))]  # type: ignore[func-returns-value]

            if unique_links:
                return self.make_result(
                    song, page_url, html, unique_links[0], SongStatus.DOWNLOADED,
                    f"Direct audio link found on Internet Archive ({len(unique_links)} file(s))."
                )
            return self.make_result(
                song, page_url, html, None, SongStatus.PAGE_FOUND,
                "Internet Archive page found (no direct link detected)."
            )
        except Exception as e:
            status_code = None
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
            if status_code in (403, 429):
                return SearchResult.blocked(song, self.name, page_url)
            return SearchResult.error(song, self.name, f"Archive error: {e}")

