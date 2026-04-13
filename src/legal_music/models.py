"""Data models for legal-music."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SongStatus(str, Enum):
    DOWNLOADED = "downloaded"
    PAGE_FOUND = "page_found"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    DOWNLOAD_ERROR = "download_error"
    ERROR = "error"
    DUPLICATE = "duplicate"
    UNSUPPORTED = "unsupported"


@dataclass
class SearchResult:
    song: str
    source: str = ""
    page_url: str = ""
    direct_url: str | None = None
    status: SongStatus = SongStatus.NOT_FOUND
    note: str = ""
    score: float = 0.0
    matched_query: str = ""
    candidate_title: str = ""
    saved_file: str = ""

    @classmethod
    def not_found(cls, song: str) -> SearchResult:
        return cls(
            song=song,
            status=SongStatus.NOT_FOUND,
            note="No permitted source found.",
        )

    @classmethod
    def error(cls, song: str, source: str, note: str) -> SearchResult:
        return cls(
            song=song,
            source=source,
            status=SongStatus.ERROR,
            note=note,
        )

    @classmethod
    def blocked(cls, song: str, source: str, url: str, note: str = "") -> SearchResult:
        return cls(
            song=song,
            source=source,
            page_url=url,
            status=SongStatus.BLOCKED,
            note=note or "Request blocked (403/429).",
        )


@dataclass
class DuplicateEntry:
    raw_song: str
    matched_song: str
    reason: str


@dataclass
class RunStats:
    downloaded: int = 0
    page_found: int = 0
    blocked: int = 0
    not_found: int = 0
    download_error: int = 0
    errors: int = 0
    duplicates: int = 0
    total: int = 0

    def record(self, result: SearchResult) -> None:
        status = result.status
        if status == SongStatus.DOWNLOADED:
            self.downloaded += 1
        elif status == SongStatus.PAGE_FOUND:
            self.page_found += 1
        elif status == SongStatus.BLOCKED:
            self.blocked += 1
        elif status == SongStatus.NOT_FOUND:
            self.not_found += 1
        elif status == SongStatus.DOWNLOAD_ERROR:
            self.download_error += 1
        elif status == SongStatus.ERROR:
            self.errors += 1
