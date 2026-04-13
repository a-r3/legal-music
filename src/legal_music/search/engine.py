"""Search engine: orchestrates sources, queries, caching, and adaptive ranking."""
from __future__ import annotations

import json
import time
from collections import defaultdict

import requests

from ..config import AppConfig
from ..constants import HEADERS
from ..logging_utils import Printer
from ..models import ResultTier, SearchResult, SongStatus
from ..search.queries import QueryVariant, build_query_variants
from ..search.sources import (
    BandcampSource,
    FreeMusicArchiveSource,
    InternetArchiveSource,
    JamendoSource,
    PixabaySource,
)
from .base import SourceAdapter
from .health import RunContext, SourceHealth
from .profile import SongProfile, classify_song

_SOURCE_REGISTRY: dict[str, type[SourceAdapter]] = {
    "Internet Archive": InternetArchiveSource,
    "Bandcamp": BandcampSource,
    "Free Music Archive": FreeMusicArchiveSource,
    "Jamendo": JamendoSource,
    "Pixabay Music": PixabaySource,
}

_SOURCE_QUERY_ORDER: dict[str, list[str]] = {
    "Internet Archive": [
        "artist_title",
        "artist_title_quoted",
        "title_quoted",
        "title_core",
        "title_only",
        "artist_title_core",
        "normalized_full",
    ],
    "Bandcamp": [
        "artist_title",
        "artist_title_quoted",
        "title_quoted",
        "title_core",
        "title_only",
        "artist_title_core",
        "raw_quoted",
    ],
    "Free Music Archive": [
        "artist_title",
        "artist_title_quoted",
        "title_quoted",
        "title_core",
        "title_only",
        "artist_title_core",
        "normalized_full",
    ],
    "Jamendo": [
        "artist_title",
        "artist_title_quoted",
        "title_quoted",
        "title_core",
        "title_only",
        "normalized_full",
    ],
    "Pixabay Music": [
        "title_quoted",
        "title_only",
        "artist_title",
        "title_core",
    ],
}

_DOWNLOAD_FIRST_SOURCES = {"Internet Archive", "Free Music Archive", "Jamendo"}
_PAGE_HEAVY_SOURCES = {"Bandcamp"}


def build_session(cfg: AppConfig) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def build_sources(cfg: AppConfig, session: requests.Session) -> list[SourceAdapter]:
    """Build enabled sources in configured priority order."""
    sources: list[SourceAdapter] = []
    ordered = cfg.source_priority or [src.name for src in cfg.sources]
    enabled_map = {src.name: src for src in cfg.sources if src.enabled}

    for src_name in ordered:
        src_cfg = enabled_map.get(src_name)
        cls = _SOURCE_REGISTRY.get(src_name)
        if src_cfg is None or cls is None:
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
    configured = {source.name for source in sources}
    for src_cfg in cfg.sources:
        if not src_cfg.enabled or src_cfg.name in configured:
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
        self.run_context = RunContext(
            total_songs=0,
            degraded_after_timeouts=cfg.degraded_after_timeouts,
            unhealthy_after_timeouts=cfg.unhealthy_after_timeouts,
            blocked_after_failures=cfg.blocked_after_failures,
        )
        self.query_cache: dict[str, list[str]] = {}
        self.inspect_cache: dict[str, SearchResult] = {}
        self.persistent_cache: dict[str, dict[str, object]] = {"queries": {}, "inspects": {}}
        self.phase_metrics = self._empty_phase_metrics()
        self._load_persistent_cache()

    def set_run_context(self, total_songs: int) -> None:
        self.run_context = RunContext(
            total_songs=total_songs,
            degraded_after_timeouts=self.cfg.degraded_after_timeouts,
            unhealthy_after_timeouts=self.cfg.unhealthy_after_timeouts,
            blocked_after_failures=self.cfg.blocked_after_failures,
        )
        self.phase_metrics = self._empty_phase_metrics()

    def save_caches(self) -> None:
        if not (self.cfg.cache_enabled and self.cfg.persistent_cache_enabled):
            return
        self.cfg.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.cache_file.write_text(
            json.dumps(self.persistent_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def search_song(self, song: str) -> SearchResult:
        """Search a song using a fast high-value pass, then selective expansion."""
        song_start = time.time()
        profile = classify_song(song)
        variants = build_query_variants(song)
        variant_limit = self._variant_limit()
        phase_a_budget = self.cfg.per_song_timeout * self.cfg.phase_a_budget_ratio

        best_downloadable: SearchResult | None = None
        best_page: SearchResult | None = None
        best_seen: SearchResult | None = None
        seen_urls: set[str] = set()
        seen_queries_by_source: dict[str, set[str]] = defaultdict(set)

        phase_plan = [("phase_a", phase_a_budget), ("phase_b", self.cfg.per_song_timeout)]

        for phase_name, phase_budget in phase_plan:
            if self._budget_exceeded(song_start):
                break
            if phase_name == "phase_b":
                if best_downloadable:
                    break
                if best_page and best_page.result_tier == ResultTier.TIER_2_STRONG_PAGE and not self.cfg.maximize_mode:
                    break

            phase_started = time.time()
            phase_improved = self._run_phase(
                phase_name=phase_name,
                song=song,
                profile=profile,
                variants=variants,
                variant_limit=variant_limit,
                song_start=song_start,
                phase_budget=phase_budget,
                seen_urls=seen_urls,
                seen_queries_by_source=seen_queries_by_source,
                best_downloadable=best_downloadable,
                best_page=best_page,
                best_seen=best_seen,
            )
            best_downloadable = phase_improved["best_downloadable"]
            best_page = phase_improved["best_page"]
            best_seen = phase_improved["best_seen"]
            self._record_phase(phase_name, time.time() - phase_started, best_downloadable, best_page)

            if self.cfg.fast_mode and best_downloadable:
                break

        if best_downloadable:
            return best_downloadable
        if best_page:
            return best_page
        if best_seen and self.cfg.fallback_policy == "page_or_best_seen" and self._good_enough_best_seen(best_seen):
            best_seen.status = SongStatus.PAGE_FOUND
            best_seen.note = f"{best_seen.note} Rescued by fallback."
            best_seen.fallback_used = True
            return best_seen
        return SearchResult.not_found(song, best_seen=best_seen)

    def _variant_limit(self) -> int:
        if self.cfg.fast_mode:
            return self.cfg.fast_query_variants
        if self.cfg.maximize_mode:
            return self.cfg.maximize_query_variants
        return self.cfg.balanced_query_variants

    def _empty_phase_metrics(self) -> dict[str, dict[str, float | int]]:
        return {
            "phase_a": {"songs": 0, "downloads": 0, "pages": 0, "time": 0.0},
            "phase_b": {"songs": 0, "downloads": 0, "pages": 0, "time": 0.0},
        }

    def _record_phase(
        self,
        phase_name: str,
        elapsed: float,
        best_downloadable: SearchResult | None,
        best_page: SearchResult | None,
    ) -> None:
        metrics = self.phase_metrics[phase_name]
        metrics["songs"] += 1
        metrics["time"] += elapsed
        if best_downloadable:
            metrics["downloads"] += 1
        elif best_page:
            metrics["pages"] += 1

    def _run_phase(
        self,
        *,
        phase_name: str,
        song: str,
        profile: SongProfile,
        variants: list[QueryVariant],
        variant_limit: int,
        song_start: float,
        phase_budget: float,
        seen_urls: set[str],
        seen_queries_by_source: dict[str, set[str]],
        best_downloadable: SearchResult | None,
        best_page: SearchResult | None,
        best_seen: SearchResult | None,
    ) -> dict[str, SearchResult | None]:
        for source in self._ordered_sources(profile, phase_name):
            if self._budget_exceeded(song_start) or self._phase_budget_exceeded(song_start, phase_budget):
                break
            if self.run_context.should_skip_source(source.name):
                health = self.run_context.get_source_health(source.name)
                self.printer.vlog(f"skip {source.name} [{health.value}]")
                continue
            if self.cfg.fast_mode and self.run_context.get_source_health(source.name) != SourceHealth.HEALTHY:
                self.printer.vlog(f"skip {source.name} [fast/degraded]")
                continue

            source_variants = self._variants_for_source(source.name, variants, variant_limit, profile, phase_name)
            if not source_variants:
                continue
            self.printer.vlog(f"{phase_name}: search {source.name} with {len(source_variants)} variant(s)")

            for variant in source_variants:
                if self._budget_exceeded(song_start) or self._phase_budget_exceeded(song_start, phase_budget):
                    break
                if variant.query.casefold() in seen_queries_by_source[source.name]:
                    self.run_context.record_redundant_skip(source.name, variant.kind)
                    continue
                seen_queries_by_source[source.name].add(variant.query.casefold())

                urls = self._search_source(source, song, variant)
                if not urls:
                    continue

                for url in urls:
                    if self._budget_exceeded(song_start) or self._phase_budget_exceeded(song_start, phase_budget):
                        break
                    if url in seen_urls:
                        self.run_context.record_redundant_skip(source.name, variant.kind)
                        continue
                    seen_urls.add(url)

                    result = self._inspect_candidate(source, song, url, variant)
                    if result is None:
                        continue
                    result.result_tier = self._classify_result_tier(result)
                    best_seen = self._pick_better(best_seen, result)
                    self.printer.vlog(
                        f"  {phase_name}:{source.name} score={result.score:.2f} tier={result.result_tier.value}"
                    )

                    if result.status == SongStatus.DOWNLOADED and self._good_enough_download(result):
                        result.resolved_phase = phase_name
                        best_downloadable = self._pick_better(best_downloadable, result)
                        self.run_context.record_source_useful(source.name, variant.kind, downloaded=True)
                        # Fast-exit on confident downloads from primary sources
                        ia_exit = source.name == "Internet Archive" and result.score >= max(self.cfg.min_downloadable_score + 0.06, 0.57)
                        fma_exit = source.name == "Free Music Archive" and result.score >= max(self.cfg.min_downloadable_score + 0.12, 0.62)
                        if ia_exit or fma_exit or result.score >= self.cfg.early_exit_score:
                            return {
                                "best_downloadable": best_downloadable,
                                "best_page": best_page,
                                "best_seen": best_seen,
                            }
                    elif result.status == SongStatus.PAGE_FOUND and self._good_enough_page(result):
                        result.resolved_phase = phase_name
                        best_page = self._pick_better(best_page, result)
                        self.run_context.record_source_useful(
                            source.name,
                            variant.kind,
                            downloaded=False,
                            weak_page=result.result_tier == ResultTier.TIER_3_WEAK_PAGE,
                        )
                    elif phase_name == "phase_b" and result.status == SongStatus.PAGE_FOUND and self._good_enough_best_seen(result):
                        rescued = SearchResult(
                            **{**result.__dict__, "fallback_used": True},
                        )
                        rescued.resolved_phase = phase_name
                        rescued.result_tier = self._classify_result_tier(rescued)
                        best_page = self._pick_better(best_page, rescued)
                        self.run_context.record_source_useful(
                            source.name,
                            variant.kind,
                            downloaded=False,
                            weak_page=rescued.result_tier == ResultTier.TIER_3_WEAK_PAGE,
                        )

                if best_downloadable and phase_name == "phase_a":
                    break
            if best_downloadable and phase_name == "phase_a":
                break

        return {
            "best_downloadable": best_downloadable,
            "best_page": best_page,
            "best_seen": best_seen,
        }

    def _ordered_sources(self, profile: SongProfile, phase_name: str) -> list[SourceAdapter]:
        base_order = {name: index for index, name in enumerate(self.cfg.source_priority)}

        def key(source: SourceAdapter) -> tuple[float, float, float]:
            metrics = self.run_context.sources.get(source.name)
            base_rank = float(base_order.get(source.name, len(base_order)))
            usefulness_boost = -(metrics.usefulness_score * 1.2) if (self.cfg.adaptive_source_ordering and metrics) else 0.0
            latency_penalty = metrics.avg_search_latency * 0.22 if (self.cfg.adaptive_source_ordering and metrics) else 0.0
            weak_penalty = 0.0
            if metrics and metrics.search_attempts >= 3 and metrics.usefulness_score < 0.08:
                weak_penalty += 0.9
            if phase_name == "phase_a" and source.name in _PAGE_HEAVY_SOURCES:
                weak_penalty += 1.2
            if phase_name == "phase_b" and source.name in _PAGE_HEAVY_SOURCES:
                weak_penalty += metrics.low_value_page_ratio * 0.4 if metrics else 0.0
            return (
                base_rank + self._source_profile_bias(source.name, profile) + weak_penalty + latency_penalty + usefulness_boost,
                metrics.avg_search_latency if metrics else 0.0,
                -(metrics.usefulness_score if metrics else 0.0),
            )

        ordered = sorted(self.sources, key=key)
        if phase_name == "phase_a":
            return [source for source in ordered if source.name in _DOWNLOAD_FIRST_SOURCES or self._source_has_download_value(source.name)]
        return ordered

    def _source_profile_bias(self, source_name: str, profile: SongProfile) -> float:
        bias = 0.0
        if profile.is_classical or profile.is_instrumental:
            if source_name == "Internet Archive":
                bias -= 0.8
            if source_name == "Free Music Archive":
                bias -= 0.4
            if source_name == "Bandcamp":
                bias += 0.2
        if profile.is_soundtrack or profile.is_electronic:
            if source_name == "Bandcamp":
                bias -= 0.1
            if source_name == "Jamendo":
                bias -= 0.15
            if source_name == "Pixabay Music":
                bias -= 0.1
        if profile.has_accents or profile.has_non_ascii:
            if source_name in {"Bandcamp", "Free Music Archive", "Jamendo"}:
                bias -= 0.1
        if source_name == "Bandcamp":
            bias += 0.35
        return bias

    def _variants_for_source(
        self,
        source_name: str,
        variants: list[QueryVariant],
        limit: int,
        profile: SongProfile,
        phase_name: str,
    ) -> list[QueryVariant]:
        source_cfg = self.cfg.source_config_for(source_name)
        if source_cfg and source_cfg.max_variants is not None:
            limit = min(limit, source_cfg.max_variants)

        metrics = self.run_context.sources.get(source_name)
        if metrics and metrics.search_attempts >= 3 and metrics.usefulness_score < 0.08 and metrics.avg_search_latency > 1.0:
            limit = max(2, limit - 2)
        if self.cfg.maximize_mode and profile.is_classical:
            limit = min(len(variants), limit + 1)
        if source_name in _PAGE_HEAVY_SOURCES and not self.cfg.maximize_mode:
            limit = min(limit, 4)
        if phase_name == "phase_a":
            limit = min(limit, 2 if source_name in _DOWNLOAD_FIRST_SOURCES else 1)
        else:
            if not self.cfg.maximize_mode:
                limit = min(limit, 2)
            if source_name in _PAGE_HEAVY_SOURCES:
                limit = min(limit, 2)

        ordered_kinds = _SOURCE_QUERY_ORDER.get(source_name, [])
        ranking = {kind: index for index, kind in enumerate(ordered_kinds)}

        def sort_key(item: QueryVariant) -> tuple[float, float]:
            base = float(ranking.get(item.kind, len(ranking)))
            # Reduce fallback penalty: title searches in Phase A are high-recall, not truly fallback
            fallback_penalty = 0.10 if item.is_fallback and phase_name == "phase_a" and item.kind.startswith("title") else 0.18 if item.is_fallback else 0.0
            learned = 0.0
            if self.cfg.adaptive_queries and metrics is not None:
                learned -= metrics.query_usefulness(item.kind) * (1.2 if phase_name == "phase_a" else 0.8)
                query_metric = metrics.query_metrics.get(item.kind)
                if query_metric and query_metric.attempts >= 2 and query_metric.zero_results == query_metric.attempts:
                    learned += 0.45
            return (base + fallback_penalty + self._query_profile_bias(item.kind, profile) + learned, len(item.query))

        return sorted(variants, key=sort_key)[:limit]

    def _source_has_download_value(self, source_name: str) -> bool:
        metrics = self.run_context.sources.get(source_name)
        if metrics is None:
            return False
        return metrics.downloaded_count > 0 and metrics.downloaded_count >= metrics.page_found_count

    def _query_profile_bias(self, kind: str, profile: SongProfile) -> float:
        bias = 0.0
        if profile.is_classical or profile.is_instrumental:
            if kind in {"title_only", "title_core", "title_quoted"}:
                bias -= 0.5
            if kind == "raw_quoted":
                bias += 0.4
        if profile.has_accents or profile.has_non_ascii:
            if kind == "accent_folded_title":
                bias -= 0.45
        if profile.is_soundtrack:
            if kind in {"title_core", "title_only"}:
                bias -= 0.2
        if profile.is_electronic:
            if kind in {"artist_title_core", "title_core"}:
                bias -= 0.15
        return bias

    def _search_source(self, source: SourceAdapter, song: str, variant: QueryVariant) -> list[str]:
        cache_key = self._query_cache_key(source.name, variant.query)
        if self.cfg.cache_enabled:
            cached = self.query_cache.get(cache_key)
            if cached is None:
                persisted = self.persistent_cache["queries"].get(cache_key)
                if isinstance(persisted, list):
                    cached = [str(item) for item in persisted]
                    self.query_cache[cache_key] = cached
            if cached is not None:
                self.run_context.record_cache_hit(source.name, variant.kind)
                return cached

        started = time.time()
        try:
            urls = source.search(song, variant.query)
            latency = time.time() - started
            self.run_context.record_source_search(source.name, variant.kind, latency, len(urls))
            if urls:
                self.run_context.mark_source_success(source.name)
            if self.cfg.cache_enabled:
                self.query_cache[cache_key] = urls
                if self.cfg.persistent_cache_enabled:
                    self.persistent_cache["queries"][cache_key] = urls
            return urls
        except requests.Timeout:
            latency = time.time() - started
            self.run_context.record_source_search(source.name, variant.kind, latency, 0)
            self.run_context.mark_source_timeout(source.name)
            self.printer.vlog(f"timeout: {source.name}")
            return []
        except requests.ConnectionError:
            latency = time.time() - started
            self.run_context.record_source_search(source.name, variant.kind, latency, 0)
            self.run_context.mark_source_timeout(source.name)
            self.printer.vlog(f"connection error: {source.name}")
            return []
        except Exception as exc:
            latency = time.time() - started
            self.run_context.record_source_search(source.name, variant.kind, latency, 0)
            if "403" in str(exc) or "429" in str(exc):
                self.run_context.mark_source_blocked(source.name)
                self.printer.vlog(f"blocked: {source.name}")
            else:
                self.run_context.mark_source_error(source.name)
                self.printer.vlog(f"error: {source.name}: {exc}")
            return []

    def _inspect_candidate(
        self,
        source: SourceAdapter,
        song: str,
        url: str,
        variant: QueryVariant,
    ) -> SearchResult | None:
        cache_key = self._inspect_cache_key(source.name, song, url)
        if self.cfg.cache_enabled:
            cached = self.inspect_cache.get(cache_key)
            if cached is None:
                persisted = self.persistent_cache["inspects"].get(cache_key)
                if isinstance(persisted, dict):
                    cached = self._deserialize_result(persisted)
                    if cached is not None:
                        self.inspect_cache[cache_key] = cached
            if cached is not None:
                self.run_context.record_cache_hit(source.name, variant.kind)
                result = SearchResult(**{**cached.__dict__})
                result.matched_query = variant.query
                result.matched_query_kind = variant.kind
                result.fallback_used = variant.is_fallback
                return result

        started = time.time()
        try:
            result = source.inspect(song, url)
            self.run_context.record_source_inspect(source.name, time.time() - started)
        except requests.Timeout:
            self.run_context.record_source_inspect(source.name, time.time() - started)
            self.run_context.mark_source_timeout(source.name)
            return None
        except requests.ConnectionError:
            self.run_context.record_source_inspect(source.name, time.time() - started)
            self.run_context.mark_source_timeout(source.name)
            return None
        except Exception as exc:
            self.run_context.record_source_inspect(source.name, time.time() - started)
            if "403" in str(exc) or "429" in str(exc):
                self.run_context.mark_source_blocked(source.name)
            else:
                self.run_context.mark_source_error(source.name)
            return None

        result.matched_query = variant.query
        result.matched_query_kind = variant.kind
        result.fallback_used = variant.is_fallback
        if self.cfg.cache_enabled:
            self.inspect_cache[cache_key] = result
            if self.cfg.persistent_cache_enabled and result.status in {SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND}:
                self.persistent_cache["inspects"][cache_key] = self._serialize_result(result)
        return result

    def _pick_better(self, current: SearchResult | None, candidate: SearchResult) -> SearchResult:
        if current is None:
            return candidate
        if self._tier_rank(candidate.result_tier) < self._tier_rank(current.result_tier):
            return candidate
        if self._tier_rank(candidate.result_tier) > self._tier_rank(current.result_tier):
            return current
        if candidate.score > current.score:
            return candidate
        if candidate.score == current.score and candidate.status == SongStatus.DOWNLOADED:
            return candidate
        return current

    def _budget_exceeded(self, song_start: float) -> bool:
        elapsed = time.time() - song_start
        if elapsed > self.cfg.per_song_timeout:
            self.printer.vlog(
                f"per-song budget exceeded ({elapsed:.1f}s > {self.cfg.per_song_timeout}s)"
            )
            return True
        return False

    def _phase_budget_exceeded(self, song_start: float, phase_budget: float) -> bool:
        return (time.time() - song_start) > phase_budget

    def _good_enough_download(self, result: SearchResult) -> bool:
        threshold = self.cfg.min_downloadable_score
        source_cfg = self.cfg.source_config_for(result.source)
        if source_cfg and source_cfg.min_downloadable_score is not None:
            threshold = source_cfg.min_downloadable_score
        return result.score >= threshold

    def _good_enough_page(self, result: SearchResult) -> bool:
        threshold = self.cfg.min_page_score
        source_cfg = self.cfg.source_config_for(result.source)
        if source_cfg and source_cfg.min_page_score is not None:
            threshold = source_cfg.min_page_score
        if result.source == "Bandcamp":
            threshold = max(threshold, 0.66)
        if result.result_tier == ResultTier.TIER_3_WEAK_PAGE:
            threshold = max(threshold, 0.72)
        return result.score >= threshold

    def _good_enough_best_seen(self, result: SearchResult) -> bool:
        if result.result_tier == ResultTier.TIER_3_WEAK_PAGE:
            return False
        return result.score >= self.cfg.min_best_seen_score

    def _classify_result_tier(self, result: SearchResult) -> ResultTier:
        if result.status == SongStatus.DOWNLOADED and result.score >= max(0.42, self.cfg.min_downloadable_score - 0.05):
            return ResultTier.TIER_1_DOWNLOADABLE
        if result.status == SongStatus.PAGE_FOUND:
            if result.source in _PAGE_HEAVY_SOURCES:
                if result.score >= 0.78 and not result.fallback_used:
                    return ResultTier.TIER_2_STRONG_PAGE
                return ResultTier.TIER_3_WEAK_PAGE
            if result.score >= max(0.60, self.cfg.min_page_score):
                return ResultTier.TIER_2_STRONG_PAGE
            if result.score >= self.cfg.min_best_seen_score:
                return ResultTier.TIER_3_WEAK_PAGE
        return ResultTier.TIER_4_LOW_CONFIDENCE

    def _tier_rank(self, tier: ResultTier) -> int:
        order = {
            ResultTier.TIER_1_DOWNLOADABLE: 1,
            ResultTier.TIER_2_STRONG_PAGE: 2,
            ResultTier.TIER_3_WEAK_PAGE: 3,
            ResultTier.TIER_4_LOW_CONFIDENCE: 4,
        }
        return order[tier]

    def _query_cache_key(self, source_name: str, query: str) -> str:
        return f"{source_name}::{query.casefold()}"

    def _inspect_cache_key(self, source_name: str, song: str, url: str) -> str:
        return f"{source_name}::{song.casefold()}::{url}"

    def _serialize_result(self, result: SearchResult) -> dict[str, object]:
        data = dict(result.__dict__)
        data["status"] = result.status.value
        data["result_tier"] = result.result_tier.value
        return data

    def _deserialize_result(self, data: dict[str, object]) -> SearchResult | None:
        try:
            status_value = data.get("status", SongStatus.NOT_FOUND.value)
            status = SongStatus(status_value)
            tier_value = data.get("result_tier", ResultTier.TIER_4_LOW_CONFIDENCE.value)
            tier = ResultTier(tier_value)
            payload = dict(data)
            payload["status"] = status
            payload["result_tier"] = tier
            return SearchResult(**payload)
        except Exception:
            return None

    def _load_persistent_cache(self) -> None:
        if not (self.cfg.cache_enabled and self.cfg.persistent_cache_enabled):
            return
        if not self.cfg.cache_file.exists():
            return
        try:
            raw = json.loads(self.cfg.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(raw, dict):
            self.persistent_cache["queries"] = raw.get("queries", {})
            self.persistent_cache["inspects"] = raw.get("inspects", {})
