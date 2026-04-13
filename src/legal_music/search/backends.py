"""Search backend abstraction for different search strategies."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils import normalize_space


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        normalized = normalize_space(url)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


class SearchBackend(ABC):
    """Abstract base for different search backend strategies."""

    name: str = "Unknown"
    timeout: int = 5

    def __init__(self, session: requests.Session, delay: float = 0.5) -> None:
        self.session = session
        self.delay = delay

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[str]:
        """Search and return a list of URLs."""
        ...

    def _get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response


class DuckDuckGoBackend(SearchBackend):
    """DuckDuckGo site: search fallback."""

    name = "DuckDuckGo"
    timeout = 4

    def search(self, query: str, max_results: int = 5) -> list[str]:
        q = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        response = self._get(q)
        soup = BeautifulSoup(response.text, "html.parser")
        links = [str(a.get("href", "")) for a in soup.select("a.result__a")]
        return _dedupe(links)[:max_results]


class InternetArchiveAPIBackend(SearchBackend):
    """Internet Archive open API (native search, no DuckDuckGo dependency)."""

    name = "Internet Archive API"
    timeout = 7

    def search(self, query: str, max_results: int = 5) -> list[str]:
        normalized = normalize_space(query)
        token_query = quote(f"mediatype:audio AND ({normalized})")
        params = (
            f"q={token_query}"
            f"&fl[]=identifier&fl[]=title&fl[]=creator"
            f"&rows={max_results * 2}"
            f"&output=json&sort[]=downloads+desc"
        )
        url = f"https://archive.org/advancedsearch.php?{params}"
        response = self._get(url)
        docs = response.json().get("response", {}).get("docs", [])
        urls = [
            f"https://archive.org/details/{doc['identifier']}"
            for doc in docs
            if "identifier" in doc
        ]
        return _dedupe(urls)[:max_results]


class JamendoAPIBackend(SearchBackend):
    """Jamendo source-aware search using website search plus fallback."""

    name = "Jamendo Search"
    timeout = 6

    def search(self, query: str, max_results: int = 5) -> list[str]:
        query = normalize_space(query)
        urls: list[str] = []
        patterns = [
            f"https://www.jamendo.com/search/tracks?q={quote(query)}",
            f"https://www.jamendo.com/search?q={quote(query)}",
        ]
        for url in patterns:
            try:
                response = self._get(url)
            except requests.RequestException:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(url, str(a["href"]))
                if re.search(r"/track/\d+", href) and href not in urls:
                    urls.append(href)
                if len(urls) >= max_results:
                    return urls[:max_results]
        if urls:
            return urls[:max_results]
        return DuckDuckGoBackend(self.session).search(f"site:jamendo.com/track {query}", max_results=max_results)


class BandcampSearchBackend(SearchBackend):
    """Bandcamp direct search with DuckDuckGo fallback."""

    name = "Bandcamp Search"
    timeout = 5

    def search(self, query: str, max_results: int = 5) -> list[str]:
        query = normalize_space(query)
        urls: list[str] = []
        direct = f"https://bandcamp.com/search?q={quote(query)}&item_type=t"
        try:
            response = self._get(direct)
            soup = BeautifulSoup(response.text, "html.parser")
            selectors = [
                "li.searchresult .itemurl",
                "li.searchresult a[href*='.bandcamp.com/track/']",
                "a.result-info-heading",
            ]
            for selector in selectors:
                for a in soup.select(selector):
                    href = str(a.get("href", "")).strip()
                    if ".bandcamp.com" in href and "/track/" in href:
                        urls.append(href)
        except requests.RequestException:
            pass

        if urls:
            return _dedupe(urls)[:max_results]
        return DuckDuckGoBackend(self.session).search(f"site:bandcamp.com/track {query}", max_results=max_results)


class PixabayMusicBackend(SearchBackend):
    """Pixabay music search with direct site query and DuckDuckGo fallback."""

    name = "Pixabay Search"
    timeout = 5

    def search(self, query: str, max_results: int = 5) -> list[str]:
        query = normalize_space(query)
        urls: list[str] = []
        patterns = [
            f"https://pixabay.com/music/search/{quote(query.replace(' ', '-'))}/",
            f"https://pixabay.com/music/search/?q={quote(query)}",
        ]
        for url in patterns:
            try:
                response = self._get(url)
            except requests.RequestException:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(url, str(a["href"]))
                path = unquote(urlparse(href).path)
                if "/music/" in path and "/download/" not in path and href not in urls:
                    urls.append(href)
                if len(urls) >= max_results:
                    return urls[:max_results]
        if urls:
            return urls[:max_results]
        return DuckDuckGoBackend(self.session).search(f"site:pixabay.com/music {query}", max_results=max_results)


class FreeMusicArchiveBackend(SearchBackend):
    """Free Music Archive search with direct site query first."""

    name = "Free Music Archive Search"
    timeout = 6

    def search(self, query: str, max_results: int = 5) -> list[str]:
        query = normalize_space(query)
        urls: list[str] = []
        patterns = [
            f"https://freemusicarchive.org/search/?quicksearch={quote(query)}",
            f"https://freemusicarchive.org/search?quicksearch={quote(query)}",
        ]
        for url in patterns:
            try:
                response = self._get(url)
            except requests.RequestException:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(url, str(a["href"]))
                path = unquote(urlparse(href).path)
                if "/music/" in path and href not in urls:
                    urls.append(href)
                if len(urls) >= max_results:
                    return urls[:max_results]
        if urls:
            return urls[:max_results]
        return DuckDuckGoBackend(self.session).search(
            f"site:freemusicarchive.org/music {query}",
            max_results=max_results,
        )
