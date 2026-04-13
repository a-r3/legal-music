"""Abstract base class for source adapters."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..constants import AUDIO_EXTENSIONS, REQUEST_TIMEOUT
from ..models import SearchResult, SongStatus
from ..search.scoring import score_candidate


class SourceAdapter(ABC):
    """Base class for all legal music source adapters."""

    name: str = "Unknown"

    def __init__(
        self,
        session: requests.Session,
        delay: float = 1.2,
        max_results: int = 8,
        timeout: int = REQUEST_TIMEOUT,
        retry_count: int = 2,
        backoff: float = 2.0,
        verbose: bool = False,
    ) -> None:
        self.session = session
        self.delay = delay
        self.max_results = max_results
        self.timeout = timeout
        self.retry_count = retry_count
        self.backoff = backoff
        self.verbose = verbose

    @abstractmethod
    def search(self, song: str, variant: str) -> list[str]:
        """Return a list of candidate page URLs for this source."""
        ...

    @abstractmethod
    def inspect(self, song: str, page_url: str) -> SearchResult:
        """Inspect a candidate URL and return a SearchResult."""
        ...

    def fetch(self, url: str, timeout: int | None = None) -> requests.Response:
        """Fetch a URL with retry + backoff. Raises on final failure."""
        use_timeout = timeout if timeout is not None else self.timeout
        last_exc: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                r = self.session.get(url, timeout=use_timeout)
                r.raise_for_status()
                return r
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (403, 429):
                    raise  # Don't retry on block/rate-limit
                last_exc = e
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
            if attempt < self.retry_count:
                time.sleep(self.backoff * (attempt + 1))
        raise last_exc or RuntimeError(f"Failed to fetch {url}")

    def extract_direct_audio_links(self, page_url: str, html: str) -> list[str]:
        """Find direct audio file links in HTML."""
        soup = BeautifulSoup(html, "html.parser")
        results: list[str] = []
        for tag in soup.find_all(["audio", "source", "a"]):
            candidate = tag.get("src") or tag.get("href") or ""
            if not candidate:
                continue
            full_url = urljoin(page_url, candidate)
            if any(ext in full_url.lower() for ext in AUDIO_EXTENSIONS) and full_url not in results:
                results.append(full_url)
        return results

    def extract_page_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.text:
            return soup.title.text.strip()
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            return str(og["content"]).strip()
        h1 = soup.find("h1")
        return h1.get_text(" ", strip=True) if h1 else ""

    def make_result(
        self,
        song: str,
        page_url: str,
        html: str,
        direct_url: str | None,
        status: SongStatus,
        note: str,
    ) -> SearchResult:
        title = self.extract_page_title(html)
        return SearchResult(
            song=song,
            source=self.name,
            page_url=page_url,
            direct_url=direct_url,
            status=status,
            note=note,
            score=score_candidate(song, title, page_url, source_name=self.name),
            candidate_title=title,
        )
