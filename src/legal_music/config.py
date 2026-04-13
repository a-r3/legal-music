"""Configuration loading, validation, and defaults."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_BLOCKED_AFTER_FAILURES,
    DEFAULT_DEGRADED_AFTER_TIMEOUTS,
    DEFAULT_EARLY_EXIT_SCORE,
    DEFAULT_FALLBACK_POLICY,
    DEFAULT_QUERY_VARIANTS,
    DEFAULT_UNHEALTHY_AFTER_TIMEOUTS,
    FAST_QUERY_VARIANTS,
    MAXIMIZE_QUERY_VARIANTS,
)
from .utils import default_data_dir, default_output_dir, default_playlists_dir

# ---------------------------------------------------------------------------
# Source presets
# ---------------------------------------------------------------------------

ALL_SOURCE_NAMES: list[str] = [
    "Internet Archive",
    "Free Music Archive",
    "Bandcamp",
    "Jamendo",
    "Pixabay Music",
]

SOURCE_PRESETS: dict[str, list[str]] = {
    "fast": ["Internet Archive"],
    "balanced": ["Internet Archive", "Free Music Archive", "Bandcamp"],
    "maximize": ["Internet Archive", "Free Music Archive", "Bandcamp", "Jamendo", "Pixabay Music"],
}


@dataclass
class SourceConfig:
    name: str
    enabled: bool = True
    max_variants: int | None = None
    min_downloadable_score: float | None = None
    min_page_score: float | None = None


@dataclass
class AppConfig:
    # Directories
    playlists_dir: Path = field(default_factory=default_playlists_dir)
    output_dir: Path = field(default_factory=default_output_dir)
    logs_dir: Path = field(default_factory=lambda: default_data_dir() / "logs")

    # Network / search balance
    delay: float = 0.25
    max_results: int = 5
    timeout: int = 10
    retry_count: int = 1
    backoff: float = 1.0
    per_song_timeout: int = 15
    phase_a_budget_ratio: float = 0.65

    # Scoring
    min_downloadable_score: float = 0.46
    min_page_score: float = 0.48
    min_best_seen_score: float = 0.42
    early_exit_score: float = DEFAULT_EARLY_EXIT_SCORE

    # Runtime behavior
    fast_mode: bool = False
    maximize_mode: bool = False
    reduce_variants: bool = False
    balanced_query_variants: int = DEFAULT_QUERY_VARIANTS
    fast_query_variants: int = FAST_QUERY_VARIANTS
    maximize_query_variants: int = MAXIMIZE_QUERY_VARIANTS
    fallback_policy: str = DEFAULT_FALLBACK_POLICY
    adaptive_source_ordering: bool = True
    adaptive_queries: bool = True
    cache_enabled: bool = True
    persistent_cache_enabled: bool = False
    cache_file: Path = field(default_factory=lambda: default_data_dir() / "cache" / "search_cache.json")

    # Health thresholds
    degraded_after_timeouts: int = DEFAULT_DEGRADED_AFTER_TIMEOUTS
    unhealthy_after_timeouts: int = DEFAULT_UNHEALTHY_AFTER_TIMEOUTS
    blocked_after_failures: int = DEFAULT_BLOCKED_AFTER_FAILURES

    # Source priority
    source_priority: list[str] = field(
        default_factory=lambda: [
            "Internet Archive",
            "Free Music Archive",
            "Bandcamp",
            "Jamendo",
            "Pixabay Music",
        ]
    )

    # Sources (ordered by priority)
    sources: list[SourceConfig] = field(
        default_factory=lambda: [
            SourceConfig("Internet Archive"),
            SourceConfig("Free Music Archive"),
            SourceConfig("Bandcamp"),
            SourceConfig("Jamendo", enabled=False),
            SourceConfig("Pixabay Music", enabled=False),
        ]
    )

    # Reports
    csv_report: bool = True
    xlsx_report: bool = True

    def enabled_source_names(self) -> list[str]:
        return [s.name for s in self.sources if s.enabled]

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        data = {
            "playlists_dir": str(self.playlists_dir),
            "output_dir": str(self.output_dir),
            "logs_dir": str(self.logs_dir),
            "delay": self.delay,
            "max_results": self.max_results,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "backoff": self.backoff,
            "per_song_timeout": self.per_song_timeout,
            "phase_a_budget_ratio": self.phase_a_budget_ratio,
            "min_downloadable_score": self.min_downloadable_score,
            "min_page_score": self.min_page_score,
            "min_best_seen_score": self.min_best_seen_score,
            "early_exit_score": self.early_exit_score,
            "balanced_query_variants": self.balanced_query_variants,
            "maximize_query_variants": self.maximize_query_variants,
            "cache_enabled": self.cache_enabled,
            "persistent_cache_enabled": self.persistent_cache_enabled,
            "cache_file": str(self.cache_file),
            "degraded_after_timeouts": self.degraded_after_timeouts,
            "unhealthy_after_timeouts": self.unhealthy_after_timeouts,
            "blocked_after_failures": self.blocked_after_failures,
            "source_priority": list(self.source_priority),
            "sources": [
                {
                    "name": s.name,
                    "enabled": s.enabled,
                    "max_variants": s.max_variants,
                    "min_downloadable_score": s.min_downloadable_score,
                    "min_page_score": s.min_page_score,
                }
                for s in self.sources
            ],
            "csv_report": self.csv_report,
            "xlsx_report": self.xlsx_report,
        }
        if not compact:
            data.update(
                {
                    "fast_mode": self.fast_mode,
                    "maximize_mode": self.maximize_mode,
                    "reduce_variants": self.reduce_variants,
                    "fast_query_variants": self.fast_query_variants,
                    "fallback_policy": self.fallback_policy,
                    "adaptive_source_ordering": self.adaptive_source_ordering,
                    "adaptive_queries": self.adaptive_queries,
                }
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        sources = [
            SourceConfig(
                name=s["name"],
                enabled=s.get("enabled", True),
                max_variants=s.get("max_variants"),
                min_downloadable_score=s.get("min_downloadable_score"),
                min_page_score=s.get("min_page_score"),
            )
            for s in data.get("sources", [])
        ]
        return cls(
            playlists_dir=Path(data.get("playlists_dir", str(default_playlists_dir()))),
            output_dir=Path(data.get("output_dir", str(default_output_dir()))),
            logs_dir=Path(data.get("logs_dir", str(default_data_dir() / "logs"))),
            delay=float(data.get("delay", 0.25)),
            max_results=int(data.get("max_results", 5)),
            timeout=int(data.get("timeout", 10)),
            retry_count=int(data.get("retry_count", 1)),
            backoff=float(data.get("backoff", 1.0)),
            per_song_timeout=int(data.get("per_song_timeout", 16)),
            phase_a_budget_ratio=float(data.get("phase_a_budget_ratio", 0.82)),
            min_downloadable_score=float(data.get("min_downloadable_score", 0.46)),
            min_page_score=float(data.get("min_page_score", 0.48)),
            min_best_seen_score=float(data.get("min_best_seen_score", 0.42)),
            early_exit_score=float(data.get("early_exit_score", DEFAULT_EARLY_EXIT_SCORE)),
            fast_mode=bool(data.get("fast_mode", False)),
            maximize_mode=bool(data.get("maximize_mode", False)),
            reduce_variants=bool(data.get("reduce_variants", False)),
            balanced_query_variants=int(data.get("balanced_query_variants", DEFAULT_QUERY_VARIANTS)),
            fast_query_variants=int(data.get("fast_query_variants", FAST_QUERY_VARIANTS)),
            maximize_query_variants=int(data.get("maximize_query_variants", MAXIMIZE_QUERY_VARIANTS)),
            fallback_policy=str(data.get("fallback_policy", DEFAULT_FALLBACK_POLICY)),
            adaptive_source_ordering=bool(data.get("adaptive_source_ordering", True)),
            adaptive_queries=bool(data.get("adaptive_queries", True)),
            cache_enabled=bool(data.get("cache_enabled", True)),
            persistent_cache_enabled=bool(data.get("persistent_cache_enabled", False)),
            cache_file=Path(data.get("cache_file", str(default_data_dir() / "cache" / "search_cache.json"))),
            degraded_after_timeouts=int(data.get("degraded_after_timeouts", DEFAULT_DEGRADED_AFTER_TIMEOUTS)),
            unhealthy_after_timeouts=int(data.get("unhealthy_after_timeouts", DEFAULT_UNHEALTHY_AFTER_TIMEOUTS)),
            blocked_after_failures=int(data.get("blocked_after_failures", DEFAULT_BLOCKED_AFTER_FAILURES)),
            source_priority=list(
                data.get(
                    "source_priority",
                    [
                        "Internet Archive",
                        "Free Music Archive",
                        "Bandcamp",
                        "Jamendo",
                        "Pixabay Music",
                    ],
                )
            ),
            sources=sources or cls.__dataclass_fields__["sources"].default_factory(),
            csv_report=bool(data.get("csv_report", True)),
            xlsx_report=bool(data.get("xlsx_report", True)),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(compact=True), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> AppConfig:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def apply_fast_mode(self) -> None:
        """Apply quick viability mode."""
        self.fast_mode = True
        self.maximize_mode = False
        self.delay = 0.1
        self.max_results = 2
        self.timeout = 5
        self.retry_count = 0
        self.per_song_timeout = 8
        self.reduce_variants = True
        self.min_page_score = max(self.min_page_score, 0.52)
        self.min_best_seen_score = max(self.min_best_seen_score, 0.50)

    def apply_maximize_mode(self) -> None:
        """Apply higher-effort recall mode."""
        self.fast_mode = False
        self.maximize_mode = True
        self.delay = max(self.delay, 0.2)
        self.max_results = max(self.max_results, 7)
        self.timeout = max(self.timeout, 12)
        self.retry_count = max(self.retry_count, 1)
        self.per_song_timeout = max(self.per_song_timeout, 24)
        self.phase_a_budget_ratio = min(max(self.phase_a_budget_ratio, 0.62), 0.70)
        self.reduce_variants = False
        self.maximize_query_variants = max(self.maximize_query_variants, MAXIMIZE_QUERY_VARIANTS)
        self.min_page_score = min(self.min_page_score, 0.44)
        self.min_best_seen_score = min(self.min_best_seen_score, 0.35)
        self.early_exit_score = max(self.early_exit_score, 0.98)
        # Enable additional sources for maximize mode
        for src in self.sources:
            if src.name in {"Jamendo", "Pixabay Music"}:
                src.enabled = True

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
        if self.per_song_timeout < 3:
            errors.append("per_song_timeout must be >= 3")
        if not (0.2 <= self.phase_a_budget_ratio <= 0.9):
            errors.append("phase_a_budget_ratio must be between 0.2 and 0.9")
        if not (0.0 <= self.min_downloadable_score <= 1.0):
            errors.append("min_downloadable_score must be between 0.0 and 1.0")
        if not (0.0 <= self.min_page_score <= 1.0):
            errors.append("min_page_score must be between 0.0 and 1.0")
        if not (0.0 <= self.min_best_seen_score <= 1.0):
            errors.append("min_best_seen_score must be between 0.0 and 1.0")
        if not (0.0 <= self.early_exit_score <= 1.0):
            errors.append("early_exit_score must be between 0.0 and 1.0")
        if min(
            self.balanced_query_variants,
            self.fast_query_variants,
            self.maximize_query_variants,
        ) < 1:
            errors.append("query variant limits must be >= 1")
        if self.degraded_after_timeouts < 1:
            errors.append("degraded_after_timeouts must be >= 1")
        if self.unhealthy_after_timeouts < self.degraded_after_timeouts:
            errors.append("unhealthy_after_timeouts must be >= degraded_after_timeouts")
        if self.blocked_after_failures < 1:
            errors.append("blocked_after_failures must be >= 1")
        if self.fallback_policy not in {"strict", "page_or_best_seen"}:
            errors.append("fallback_policy must be 'strict' or 'page_or_best_seen'")
        if self.cache_enabled and self.persistent_cache_enabled and not self.cache_file:
            errors.append("cache_file must be configured when persistent_cache_enabled is true")
        if not self.sources:
            errors.append("at least one source must be configured")
        return errors

    def source_config_for(self, name: str) -> SourceConfig | None:
        for source in self.sources:
            if source.name == name:
                return source
        return None

    def find_source(self, name: str) -> SourceConfig | None:
        """Find source config by exact or prefix match (case-insensitive)."""
        name_lower = name.lower().strip()
        for src in self.sources:
            if src.name.lower() == name_lower:
                return src
        for src in self.sources:
            if src.name.lower().startswith(name_lower):
                return src
        return None

    def apply_source_preset(self, preset_name: str) -> list[str]:
        """Enable/disable sources to match a named preset. Returns enabled names.

        Preset names: fast, balanced, maximize.
        """
        key = preset_name.lower().strip()
        preset_sources = SOURCE_PRESETS.get(key)
        if preset_sources is None:
            choices = ", ".join(SOURCE_PRESETS.keys())
            raise ValueError(f"Unknown preset {preset_name!r}. Choose from: {choices}")
        existing_names = {s.name for s in self.sources}
        for src_name in ALL_SOURCE_NAMES:
            if src_name not in existing_names:
                self.sources.append(SourceConfig(src_name, enabled=False))
        for src in self.sources:
            src.enabled = src.name in preset_sources
        return [s.name for s in self.sources if s.enabled]
