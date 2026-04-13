"""Search engine: orchestrates sources, queries, and candidate inspection."""
from __future__ import annotations

import time

import requests

from ..config import AppConfig
from ..constants import HEADERS
from ..logging_utils import Printer
from ..models import SearchResult, SongStatus
from ..search.queries import build_query_variants
from ..search.sources import (
    BandcampSource,
    InternetArchiveSource,
    JamendoSource,
    PixabaySource,
)
from .base import SourceAdapter

_SOURCE_REGISTRY: dict[str, type[SourceAdapter]] = {
    "Internet Archive": InternetArchiveSource,
    "Bandcamp": BandcampSource,
    "Jamendo": JamendoSource,
    "Pixabay Music": PixabaySource,
}


def build_session(cfg: AppConfig) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def build_sources(cfg: AppConfig, session: requests.Session) -> list[SourceAdapter]:
    sources: list[SourceAdapter] = []
    for src_cfg in cfg.sources:
        if not src_cfg.enabled:
            continue
        cls = _SOURCE_REGISTRY.get(src_cfg.name)
        if cls is None:
            continue
        sources.append(
            cls(
                session=session,
                delay=cfg.delay,
                max_results=cfg.max_results,
                timeout=cfg.timeout,
                retry_count=cfg.retry_count,
                backoff=cfg.backoff,
            )
        )
    return sources


class SearchEngine:
    def __init__(self, cfg: AppConfig, printer: Printer | None = None) -> None:
        self.cfg = cfg
        self.printer = printer or Printer()
        self.session = build_session(cfg)
        self.sources = build_sources(cfg, self.session)

    def search_song(self, song: str) -> SearchResult:
        """Search all enabled sources for a song. Returns the best result."""
        variants = build_query_variants(song)
        self.printer.vlog(f"variants: {', '.join(variants[:5])}")

        best_downloadable: SearchResult | None = None
        best_page: SearchResult | None = None
        best_seen: SearchResult | None = None
        seen_urls: set[str] = set()

        for variant in variants:
            for source in self.sources:
                self.printer.vlog(f"search: {source.name} | query={variant!r}")
                try:
                    urls = source.search(song, variant)
                except Exception as e:
                    self.printer.vlog(f"search error [{source.name}]: {e}")
                    urls = []

                self.printer.vlog(f"  found {len(urls)} candidate(s)")

                for url in urls:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    try:
                        result = source.inspect(song, url)
                        result.matched_query = variant
                    except Exception as e:
                        self.printer.vlog(f"inspect error [{source.name}] {url}: {e}")
                        continue

                    self.printer.vlog(
                        f"  candidate: score={result.score:.3f} status={result.status} "
                        f"title={result.candidate_title[:60]!r}"
                    )

                    if best_seen is None or result.score > best_seen.score:
                        best_seen = result

                    if result.status == SongStatus.DOWNLOADED and self._good_enough_download(result):
                        if best_downloadable is None or result.score > best_downloadable.score:
                            best_downloadable = result
                        # Early exit if we found a strong match
                        if result.score >= self.cfg.min_downloadable_score + 0.2:
                            return result

                    elif result.status == SongStatus.PAGE_FOUND and self._good_enough_page(result):
                        if best_page is None or result.score > best_page.score:
                            best_page = result

                    time.sleep(self.cfg.delay)

        # Return in priority order
        if best_downloadable:
            return best_downloadable
        if best_page:
            return best_page
        if best_seen and best_seen.score >= self.cfg.min_best_seen_score:
            best_seen.note += " (best relevance match)"
            return best_seen

        return SearchResult.not_found(song)

    def _good_enough_download(self, r: SearchResult) -> bool:
        return r.score >= self.cfg.min_downloadable_score

    def _good_enough_page(self, r: SearchResult) -> bool:
        return r.score >= self.cfg.min_page_score
