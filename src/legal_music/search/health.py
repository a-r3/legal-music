"""Source health tracking and adaptive runtime metrics."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class SourceHealth(Enum):
    """Health status of a search source."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class QueryMetrics:
    """Track how useful a query kind has been for a source during a run."""

    kind: str
    attempts: int = 0
    cache_hits: int = 0
    zero_results: int = 0
    useful_hits: int = 0
    total_latency: float = 0.0
    skipped_redundant: int = 0

    def record_attempt(self, latency: float, result_count: int) -> None:
        self.attempts += 1
        self.total_latency += latency
        if result_count == 0:
            self.zero_results += 1

    def record_useful(self) -> None:
        self.useful_hits += 1

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_redundant_skip(self) -> None:
        self.skipped_redundant += 1

    @property
    def avg_latency(self) -> float:
        return self.total_latency / max(1, self.attempts)

    @property
    def usefulness(self) -> float:
        return (self.useful_hits * 2.0 + self.cache_hits * 0.5) / max(0.5, self.total_latency + self.attempts * 0.2)


@dataclass
class SourceMetrics:
    """Track a source's performance during a run."""

    name: str
    timeout_count: int = 0
    blocked_count: int = 0
    error_count: int = 0
    success_count: int = 0
    last_attempt_time: float = 0.0
    health: SourceHealth = field(default=SourceHealth.HEALTHY)
    degraded_after_timeouts: int = 3
    unhealthy_after_timeouts: int = 5
    blocked_after_failures: int = 2
    search_attempts: int = 0
    inspect_attempts: int = 0
    cached_hits: int = 0
    skipped_redundant: int = 0
    candidate_count: int = 0
    useful_count: int = 0
    downloaded_count: int = 0
    page_found_count: int = 0
    weak_page_count: int = 0
    total_search_time: float = 0.0
    total_inspect_time: float = 0.0
    query_metrics: dict[str, QueryMetrics] = field(default_factory=dict)

    def _query(self, kind: str) -> QueryMetrics:
        if kind not in self.query_metrics:
            self.query_metrics[kind] = QueryMetrics(kind=kind)
        return self.query_metrics[kind]

    def mark_timeout(self) -> None:
        self.timeout_count += 1
        self._update_health()

    def mark_blocked(self) -> None:
        self.blocked_count += 1
        self._update_health()

    def mark_error(self) -> None:
        self.error_count += 1
        self._update_health()

    def mark_success(self) -> None:
        self.success_count += 1
        self.timeout_count = max(0, self.timeout_count - 1)
        self._update_health()

    def record_search(self, kind: str, latency: float, result_count: int) -> None:
        self.search_attempts += 1
        self.total_search_time += latency
        self.candidate_count += result_count
        self.last_attempt_time = time.time()
        self._query(kind).record_attempt(latency, result_count)

    def record_inspect(self, latency: float) -> None:
        self.inspect_attempts += 1
        self.total_inspect_time += latency
        self.last_attempt_time = time.time()

    def record_useful(self, kind: str, downloaded: bool, weak_page: bool = False) -> None:
        self.useful_count += 1
        self.downloaded_count += int(downloaded)
        self.page_found_count += int(not downloaded)
        self.weak_page_count += int(weak_page)
        self._query(kind).record_useful()

    def record_cache_hit(self, kind: str) -> None:
        self.cached_hits += 1
        self._query(kind).record_cache_hit()

    def record_redundant_skip(self, kind: str) -> None:
        self.skipped_redundant += 1
        self._query(kind).record_redundant_skip()

    def should_skip(self) -> bool:
        if self.health == SourceHealth.UNHEALTHY:
            return True
        if self.blocked_count >= self.blocked_after_failures:
            return True
        return False

    @property
    def total_time(self) -> float:
        return self.total_search_time + self.total_inspect_time

    @property
    def avg_search_latency(self) -> float:
        return self.total_search_time / max(1, self.search_attempts)

    @property
    def avg_inspect_latency(self) -> float:
        return self.total_inspect_time / max(1, self.inspect_attempts)

    @property
    def usefulness_score(self) -> float:
        value = (
            self.downloaded_count * 2.4
            + self.page_found_count * 0.9
            - self.weak_page_count * 0.5
            + self.cached_hits * 0.3
        )
        return value / max(0.75, self.total_time + self.search_attempts * 0.15)

    @property
    def low_value_page_ratio(self) -> float:
        return self.weak_page_count / max(1, self.page_found_count)

    def query_usefulness(self, kind: str) -> float:
        return self._query(kind).usefulness

    def _update_health(self) -> None:
        if self.timeout_count >= self.unhealthy_after_timeouts:
            self.health = SourceHealth.UNHEALTHY
        elif (
            self.timeout_count >= self.degraded_after_timeouts
            or self.blocked_count >= self.blocked_after_failures
        ):
            self.health = SourceHealth.DEGRADED
        elif self.health == SourceHealth.DEGRADED and self.success_count > 0:
            self.health = SourceHealth.HEALTHY


@dataclass
class RunContext:
    """Context for a single playlist run."""

    song_index: int = 0
    total_songs: int = 0
    sources: dict[str, SourceMetrics] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    degraded_after_timeouts: int = 3
    unhealthy_after_timeouts: int = 5
    blocked_after_failures: int = 2

    def _ensure_source(self, source_name: str) -> None:
        if source_name not in self.sources:
            self.sources[source_name] = SourceMetrics(
                name=source_name,
                degraded_after_timeouts=self.degraded_after_timeouts,
                unhealthy_after_timeouts=self.unhealthy_after_timeouts,
                blocked_after_failures=self.blocked_after_failures,
            )

    def get_elapsed(self) -> float:
        return time.time() - self.start_time

    def mark_source_timeout(self, source_name: str) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].mark_timeout()

    def mark_source_blocked(self, source_name: str) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].mark_blocked()

    def mark_source_error(self, source_name: str) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].mark_error()

    def mark_source_success(self, source_name: str) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].mark_success()

    def record_source_search(
        self,
        source_name: str,
        query_kind: str,
        latency: float,
        result_count: int,
    ) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].record_search(query_kind, latency, result_count)

    def record_source_inspect(self, source_name: str, latency: float) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].record_inspect(latency)

    def record_source_useful(
        self,
        source_name: str,
        query_kind: str,
        downloaded: bool,
        weak_page: bool = False,
    ) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].record_useful(query_kind, downloaded, weak_page=weak_page)

    def record_cache_hit(self, source_name: str, query_kind: str) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].record_cache_hit(query_kind)

    def record_redundant_skip(self, source_name: str, query_kind: str) -> None:
        self._ensure_source(source_name)
        self.sources[source_name].record_redundant_skip(query_kind)

    def should_skip_source(self, source_name: str) -> bool:
        if source_name not in self.sources:
            return False
        return self.sources[source_name].should_skip()

    def get_source_health(self, source_name: str) -> SourceHealth:
        if source_name not in self.sources:
            return SourceHealth.HEALTHY
        return self.sources[source_name].health
