"""SQLite-based persistent cache for search results.

Supplements the existing JSON cache with a faster, thread-safe SQLite store.
Results are keyed by song name (case-insensitive) and expire after ttl_days.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    """Thread-safe SQLite cache for song search results and query URL lists.

    Cache entries expire after `ttl_days` days (default: 30).
    """

    def __init__(self, db_path: Path, ttl_days: int = 30) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_days * 86400
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._setup()

    def _setup(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS query_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS song_cache (
                song TEXT PRIMARY KEY,
                result TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_query_created
                ON query_cache(created_at);
            CREATE INDEX IF NOT EXISTS idx_song_created
                ON song_cache(created_at);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query-level cache  (source + query -> list of URLs)
    # ------------------------------------------------------------------

    def get_query(self, key: str) -> list[str] | None:
        """Return cached URL list for a query key, or None if missing/expired."""
        row = self._conn.execute(
            "SELECT value, created_at FROM query_cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, created_at = row
        if time.time() - created_at > self.ttl_seconds:
            self._conn.execute("DELETE FROM query_cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(value)

    def set_query(self, key: str, urls: list[str]) -> None:
        """Store URL list for a query key."""
        self._conn.execute(
            "INSERT OR REPLACE INTO query_cache (key, value, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(urls), time.time()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Song-level cache  (song name -> full SearchResult dict)
    # ------------------------------------------------------------------

    def get_song(self, song: str) -> dict[str, Any] | None:
        """Return cached final result dict for a song, or None if missing/expired."""
        row = self._conn.execute(
            "SELECT result, created_at FROM song_cache WHERE song = ?",
            (song.casefold(),),
        ).fetchone()
        if row is None:
            return None
        result_json, created_at = row
        if time.time() - created_at > self.ttl_seconds:
            self._conn.execute(
                "DELETE FROM song_cache WHERE song = ?", (song.casefold(),)
            )
            self._conn.commit()
            return None
        return json.loads(result_json)

    def set_song(self, song: str, result: dict[str, Any], status: str) -> None:
        """Cache the final result dict for a song (only useful statuses)."""
        self._conn.execute(
            "INSERT OR REPLACE INTO song_cache "
            "(song, result, status, created_at) VALUES (?, ?, ?, ?)",
            (song.casefold(), json.dumps(result), status, time.time()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Return row counts for each table."""
        q_count = self._conn.execute(
            "SELECT COUNT(*) FROM query_cache"
        ).fetchone()[0]
        s_count = self._conn.execute(
            "SELECT COUNT(*) FROM song_cache"
        ).fetchone()[0]
        return {"query_cache_entries": q_count, "song_cache_entries": s_count}

    def total_downloaded(self) -> int:
        """Return how many songs are cached as 'downloaded'."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM song_cache WHERE status = 'downloaded'"
        ).fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()
