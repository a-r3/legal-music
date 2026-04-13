"""Bandcamp source adapter (DuckDuckGo site: search + page inspection)."""
from __future__ import annotations

from urllib.parse import quote

from bs4 import BeautifulSoup

from ...models import SearchResult, SongStatus
from ..base import SourceAdapter


class BandcampSource(SourceAdapter):
    name = "Bandcamp"

    def search(self, song: str, variant: str) -> list[str]:
        query = f"site:bandcamp.com {variant}"
        try:
            r = self.fetch(f"https://html.duckduckgo.com/html/?q={quote(query)}")
            soup = BeautifulSoup(r.text, "html.parser")
            links: list[str] = []
            for a in soup.select("a.result__a"):
                href = str(a.get("href", ""))
                if "bandcamp.com" in href and href not in links:
                    links.append(href)
                if len(links) >= self.max_results:
                    break
            return links
        except Exception:
            return []

    def inspect(self, song: str, page_url: str) -> SearchResult:
        try:
            r = self.fetch(page_url)
            html = r.text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links(page_url, html)
            if direct_links:
                return self.make_result(
                    song, page_url, html, direct_links[0], SongStatus.PAGE_FOUND,
                    "Direct audio link found on Bandcamp page."
                )
            # Bandcamp free download indicators
            if any(kw in text for kw in ["buy digital", "download", "name your price", "free download"]):
                return self.make_result(
                    song, page_url, html, None, SongStatus.PAGE_FOUND,
                    "Bandcamp page found with download option."
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
