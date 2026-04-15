"""CCMixter source adapter.

CCMixter (https://ccmixter.org) is a community remixing site with thousands
of Creative Commons licensed tracks, freely downloadable.

Uses the official CCMixter query API:
  https://ccmixter.org/api/query?search_type=any&search_text={query}&format=json&limit=N
"""
from __future__ import annotations

import urllib.parse

from ...models import SearchResult, SongStatus
from ..base import SourceAdapter
from ..scoring import score_candidate

_SEARCH_API = "https://ccmixter.org/api/query"
_BASE_URL = "https://ccmixter.org"


class CCMixterSource(SourceAdapter):
    name = "CCMixter"

    def search(self, song: str, variant: str) -> list[str]:
        """Query CCMixter API and return upload/file page URLs."""
        params = {
            "search_type": "any",
            "search_text": variant,
            "format": "json",
            "limit": str(self.max_results),
            "f": "json",
        }
        url = f"{_SEARCH_API}?{urllib.parse.urlencode(params)}"
        try:
            r = self.fetch(url, timeout=self.timeout)
            data = r.json()
            urls: list[str] = []
            if isinstance(data, list):
                for item in data[: self.max_results]:
                    upload_url = item.get("upload_url") or item.get("url")
                    if upload_url:
                        if not upload_url.startswith("http"):
                            upload_url = _BASE_URL + upload_url
                        urls.append(upload_url)
            return urls
        except Exception:
            return []

    def inspect(self, song: str, page_url: str) -> SearchResult:
        """Inspect a CCMixter upload page for a direct MP3 download link."""
        try:
            r = self.fetch(page_url, timeout=self.timeout)
            html = r.text

            direct_links = self.extract_direct_audio_links(page_url, html)
            page_title = self.extract_page_title(html)
            score = score_candidate(song, page_title, page_url, source_name=self.name)

            if direct_links:
                # Prefer the first MP3
                mp3_links = [u for u in direct_links if u.lower().endswith(".mp3")]
                chosen = mp3_links[0] if mp3_links else direct_links[0]
                return SearchResult(
                    song=song,
                    source=self.name,
                    page_url=page_url,
                    direct_url=chosen,
                    status=SongStatus.DOWNLOADED,
                    note="Direct MP3 found on CCMixter.",
                    score=score,
                    candidate_title=page_title,
                )

            return SearchResult(
                song=song,
                source=self.name,
                page_url=page_url,
                direct_url=None,
                status=SongStatus.PAGE_FOUND,
                note="CCMixter page found (no direct link detected).",
                score=score,
                candidate_title=page_title,
            )

        except Exception as exc:
            code = None
            if hasattr(exc, "response") and exc.response is not None:
                code = exc.response.status_code
            if code in (403, 429):
                return SearchResult.blocked(song, self.name, page_url)
            return SearchResult.error(song, self.name, f"CCMixter error: {exc}")
