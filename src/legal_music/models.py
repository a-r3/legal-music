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


class ResultTier(str, Enum):
    TIER_1_DOWNLOADABLE = "tier_1_downloadable"
    TIER_2_STRONG_PAGE = "tier_2_strong_page"
    TIER_3_WEAK_PAGE = "tier_3_weak_page"
    TIER_4_LOW_CONFIDENCE = "tier_4_low_confidence"


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
    matched_query_kind: str = ""
    candidate_title: str = ""
    saved_file: str = ""
    fallback_used: bool = False
    resolved_phase: str = ""
    result_tier: ResultTier = ResultTier.TIER_4_LOW_CONFIDENCE
    best_seen_source: str = ""
    best_seen_score: float = 0.0
    best_seen_url: str = ""
    best_seen_tier: str = ""

    @classmethod
    def not_found(
        cls,
        song: str,
        *,
        best_seen: SearchResult | None = None,
    ) -> SearchResult:
        note = "No permitted source found."
        best_seen_source = ""
        best_seen_score = 0.0
        best_seen_url = ""
        best_seen_tier = ""
        if best_seen is not None:
            best_seen_source = best_seen.source
            best_seen_score = best_seen.score
            best_seen_url = best_seen.page_url
            best_seen_tier = best_seen.result_tier.value
            note = (
                "No permitted source found above threshold. "
                f"Best candidate: {best_seen.source} score={best_seen.score:.2f}"
            )
        return cls(
            song=song,
            status=SongStatus.NOT_FOUND,
            note=note,
            best_seen_source=best_seen_source,
            best_seen_score=best_seen_score,
            best_seen_url=best_seen_url,
            best_seen_tier=best_seen_tier,
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
    elapsed_seconds: float = 0.0
    avg_seconds_per_song: float = 0.0
    avg_seconds_per_success: float = 0.0
    phase_a_wins: int = 0
    phase_b_wins: int = 0

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
