"""Async wrapper for parallel song search/download.

Runs up to MAX_CONCURRENT_SONGS songs simultaneously using asyncio +
ThreadPoolExecutor (so the existing sync SearchEngine is re-used as-is,
preserving all existing functionality).

SQLite-based cache is checked first: if a song was already found in a
previous run, the result is returned instantly without hitting any source.

Per-source timeout is capped at SOURCE_TIMEOUT_SECS (4 s) when using this
engine, matching the Task 1 requirement.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .config import AppConfig
from .db_cache import SQLiteCache
from .logging_utils import Printer
from .models import SearchResult, SongStatus
from .search.engine import SearchEngine
from .utils import default_data_dir

MAX_CONCURRENT_SONGS = 10
SOURCE_TIMEOUT_SECS = 4        # per-source HTTP timeout cap for async use
DB_CACHE_PATH = default_data_dir() / "cache" / "search_results.db"

logger = logging.getLogger(__name__)


def _make_async_cfg(cfg: AppConfig) -> AppConfig:
    """Clone config with reduced source timeout for async use."""
    import copy
    acfg = copy.deepcopy(cfg)
    acfg.timeout = min(acfg.timeout, SOURCE_TIMEOUT_SECS)
    return acfg


class AsyncSearchRunner:
    """Searches up to MAX_CONCURRENT_SONGS songs in parallel.

    Usage::

        runner = AsyncSearchRunner(cfg)
        results = await runner.search_many(songs, on_result=callback)
        runner.close()

    or as an async context manager::

        async with AsyncSearchRunner(cfg) as runner:
            results = await runner.search_many(songs)
    """

    def __init__(
        self,
        cfg: AppConfig,
        printer: Printer | None = None,
        max_concurrent: int = MAX_CONCURRENT_SONGS,
        db_path: Path | None = None,
    ) -> None:
        self.cfg = _make_async_cfg(cfg)
        self.printer = printer or Printer()
        self.max_concurrent = max_concurrent
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="lm-search")
        self._db = SQLiteCache(db_path or DB_CACHE_PATH)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_one(self, song: str) -> SearchResult:
        """Search a single song asynchronously.

        Checks the SQLite cache first; falls back to a threaded SearchEngine
        call if no valid cached result exists.
        """
        # --- SQLite fast path ---
        cached = self._db.get_song(song)
        if cached is not None:
            logger.debug("SQLite cache hit: %s", song)
            return self._deserialize(song, cached)

        # --- Full search in thread ---
        loop = asyncio.get_event_loop()
        cfg = self.cfg  # thread-safe read-only

        def _run() -> SearchResult:
            engine = SearchEngine(cfg, printer=self.printer)
            return engine.search_song(song)

        try:
            result = await loop.run_in_executor(self._executor, _run)
        except Exception as exc:
            logger.error("Error searching %r: %s", song, exc)
            result = SearchResult.error(song, "", f"Async engine error: {exc}")

        # Cache successful results
        if result.status in {SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND}:
            self._db.set_song(song, self._serialize(result), result.status.value)

        return result

    async def search_many(
        self,
        songs: list[str],
        on_result: Callable[[str, SearchResult], None] | None = None,
    ) -> list[SearchResult]:
        """Search *songs* in parallel (up to max_concurrent at a time).

        *on_result* is called with (song, result) as each song completes,
        allowing the caller to display progress without waiting for all songs.
        Results are returned in the same order as *songs*.
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        slot: list[SearchResult | None] = [None] * len(songs)

        async def _one(idx: int, song: str) -> None:
            async with semaphore:
                result = await self.search_one(song)
                slot[idx] = result
                if on_result is not None:
                    try:
                        on_result(song, result)
                    except Exception:
                        pass

        await asyncio.gather(*(_one(i, s) for i, s in enumerate(songs)))
        return [r for r in slot if r is not None]

    def db_stats(self) -> dict[str, int]:
        """Return SQLite cache statistics."""
        return self._db.stats()

    def close(self) -> None:
        self._executor.shutdown(wait=False)
        self._db.close()

    # ------------------------------------------------------------------
    # Async context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AsyncSearchRunner":
        return self

    async def __aexit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize(result: SearchResult) -> dict[str, object]:
        d = dict(result.__dict__)
        d["status"] = result.status.value
        d["result_tier"] = result.result_tier.value
        return d

    @staticmethod
    def _deserialize(song: str, data: dict[str, object]) -> SearchResult:
        from .models import ResultTier
        try:
            status = SongStatus(data.get("status", SongStatus.NOT_FOUND.value))
            tier = ResultTier(data.get("result_tier", ResultTier.TIER_4_LOW_CONFIDENCE.value))
            payload = dict(data)
            payload["status"] = status
            payload["result_tier"] = tier
            result = SearchResult(**payload)
            result.cache_hit = True
            result.cache_hits = result.cache_hits + 1
            return result
        except Exception:
            return SearchResult.not_found(song)
