"""Configuration loading, validation, and defaults."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_BACKOFF,
    DEFAULT_DELAY,
    DEFAULT_MAX_RESULTS,
    DEFAULT_RETRY_COUNT,
    MIN_BEST_SEEN_SCORE,
    MIN_DOWNLOADABLE_SCORE,
    MIN_PAGE_SCORE,
)
from .utils import default_data_dir, default_output_dir, default_playlists_dir


@dataclass
class SourceConfig:
    name: str
    enabled: bool = True


@dataclass
class AppConfig:
    # Directories
    playlists_dir: Path = field(default_factory=default_playlists_dir)
    output_dir: Path = field(default_factory=default_output_dir)
    logs_dir: Path = field(default_factory=lambda: default_data_dir() / "logs")

    # Network
    delay: float = DEFAULT_DELAY
    max_results: int = DEFAULT_MAX_RESULTS
    timeout: int = 30
    retry_count: int = DEFAULT_RETRY_COUNT
    backoff: float = DEFAULT_BACKOFF

    # Scoring
    min_downloadable_score: float = MIN_DOWNLOADABLE_SCORE
    min_page_score: float = MIN_PAGE_SCORE
    min_best_seen_score: float = MIN_BEST_SEEN_SCORE

    # Sources (ordered by priority)
    sources: list[SourceConfig] = field(
        default_factory=lambda: [
            SourceConfig("Internet Archive"),
            SourceConfig("Bandcamp"),
            SourceConfig("Jamendo"),
            SourceConfig("Pixabay Music"),
        ]
    )

    # Reports
    csv_report: bool = True
    xlsx_report: bool = True

    def enabled_source_names(self) -> list[str]:
        return [s.name for s in self.sources if s.enabled]

    def to_dict(self) -> dict[str, Any]:
        return {
            "playlists_dir": str(self.playlists_dir),
            "output_dir": str(self.output_dir),
            "logs_dir": str(self.logs_dir),
            "delay": self.delay,
            "max_results": self.max_results,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "backoff": self.backoff,
            "min_downloadable_score": self.min_downloadable_score,
            "min_page_score": self.min_page_score,
            "min_best_seen_score": self.min_best_seen_score,
            "sources": [{"name": s.name, "enabled": s.enabled} for s in self.sources],
            "csv_report": self.csv_report,
            "xlsx_report": self.xlsx_report,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        sources = [
            SourceConfig(name=s["name"], enabled=s.get("enabled", True))
            for s in data.get("sources", [])
        ]
        return cls(
            playlists_dir=Path(data.get("playlists_dir", str(default_playlists_dir()))),
            output_dir=Path(data.get("output_dir", str(default_output_dir()))),
            logs_dir=Path(data.get("logs_dir", str(default_data_dir() / "logs"))),
            delay=float(data.get("delay", DEFAULT_DELAY)),
            max_results=int(data.get("max_results", DEFAULT_MAX_RESULTS)),
            timeout=int(data.get("timeout", 30)),
            retry_count=int(data.get("retry_count", DEFAULT_RETRY_COUNT)),
            backoff=float(data.get("backoff", DEFAULT_BACKOFF)),
            min_downloadable_score=float(data.get("min_downloadable_score", MIN_DOWNLOADABLE_SCORE)),
            min_page_score=float(data.get("min_page_score", MIN_PAGE_SCORE)),
            min_best_seen_score=float(data.get("min_best_seen_score", MIN_BEST_SEEN_SCORE)),
            sources=sources or cls.__dataclass_fields__["sources"].default_factory(),
            csv_report=bool(data.get("csv_report", True)),
            xlsx_report=bool(data.get("xlsx_report", True)),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> AppConfig:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def validate(self) -> list[str]:
        """Return list of validation error strings (empty = valid)."""
        errors = []
        if self.delay < 0:
            errors.append("delay must be >= 0")
        if self.max_results < 1:
            errors.append("max_results must be >= 1")
        if self.timeout < 1:
            errors.append("timeout must be >= 1")
        if self.retry_count < 0:
            errors.append("retry_count must be >= 0")
        if not (0.0 <= self.min_downloadable_score <= 1.0):
            errors.append("min_downloadable_score must be between 0.0 and 1.0")
        if not (0.0 <= self.min_page_score <= 1.0):
            errors.append("min_page_score must be between 0.0 and 1.0")
        if not self.sources:
            errors.append("at least one source must be configured")
        return errors
