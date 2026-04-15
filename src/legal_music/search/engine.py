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
    CCMixterSource,
    FreeMusicArchiveSource,
    IncompetechSource,
    InternetArchiveSource,
    JamendoSource,
    PixabaySource,
    YouTubeAudioLibrarySource,
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
    "CCMixter": CCMixterSource,
    "Incompetech": IncompetechSource,
    "YouTube Audio Library": YouTubeAudioLibrarySource,
}

_SOURCE_QUERY_ORDER: dict[str, list[str]] = {
    "Internet Archive": [
        "artist_title",
        "title_quoted",
        "translit_artist_title",
        "artist_title_quoted",
        "translit_raw",
        "raw_quoted",
        "title_only",
    ],
    "Bandcamp": [
        "artist_title",
        "artist_title_quoted",
        "title_quoted",
        "translit_artist_title",
        "title_only",
        "raw_quoted",
    ],
    "Free Music Archive": [
        "artist_title",
        "title_quoted",
        "translit_artist_title",
        "artist_title_quoted",
        "translit_raw",
        "title_only",
    ],
    "Jamendo": [
        "artist_title",
        "artist_title_quoted",
        "title_quoted",
        "translit_artist_title",
        "title_only",
        "raw_quoted",
    ],
    "Pixabay Music": [
        "title_quoted",
        "title_only",
        "artist_title",
        "raw_quoted",
    ],
    "CCMixter": [
        "title_artist",
        "title_only",
        "artist_title",
        "title_quoted",
        "title_instrumental",
    ],
    "Incompetech": [
        "title_only",
        "title_quoted",
        "artist_title",
        "title_instrumental",
    ],
    "YouTube Audio Library": [
        "artist_title",
        "title_artist",
        "title_only",
        "title_instrumental",
    ],
}

_PRIMARY_SOURCES = {"Internet Archive"}
_SECONDARY_SOURCES = {"Free Music Archive"}
_SELECTIVE_FALLBACK_SOURCES = {"Bandcamp"}
_OPT_IN_SOURCES = {"Jamendo", "Pixabay Music", "CCMixter", "Incompetech", "YouTube Audio Library"}
_DOWNLOAD_FIRST_SOURCES = _PRIMARY_SOURCES | _SECONDARY_SOURCES | {"Jamendo"}
_PAGE_HEAVY_SOURCES = _SELECTIVE_FALLBACK_SOURCES
_PHASE_B_BALANCED_SOURCES = {"Bandcamp"}
_PHASE_B_MAXIMIZE_SOURCES = {"Bandcamp", "Jamendo", "Pixabay Music", "CCMixter", "Incompetech", "YouTube Audio Library"}
_PHASE_A_ZERO_RESULT_EXIT: dict[str, int] = {
    "Internet Archive": 2,
    "Free Music Archive": 2,
}


def build_session(cfg: AppConfig) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def build_sources(cfg: AppConfig, session: requests.Session) -> list[SourceAdapter]:
    """Build enabled sources in configured priority order."""
    sources: list[SourceAdapter] = []
    ordered = cfg.effective_source_priority()
    enabled_map = {src.name: src for src in cfg.effective_source_configs()}

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
    for src_cfg in cfg.effective_source_configs():
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
        self._song_cache_hits = 0
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
        self._song_cache_hits = 0
        profile = classify_song(song)
        variants = build_query_variants(song)
        variant_limit = self._variant_limit()
        phase_a_budget = self.cfg.per_song_timeout * self.cfg.phase_a_budget_ratio

        best_downloadable: SearchResult | None = None
        best_page: SearchResult | None = None
        best_seen: SearchResult | None = None
        seen_urls: set[str] = set()
        seen_queries_by_source: dict[str, set[str]] = defaultdict(set)

        phase_b_budget = self.cfg.per_song_timeout * (0.38 if self.cfg.maximize_mode else 0.28)
        phase_plan = [("phase_a", phase_a_budget), ("phase_b", phase_b_budget)]

        for phase_name, phase_budget in phase_plan:
            if self._budget_exceeded(song_start):
                break
            if phase_name == "phase_b":
                # Phase B is rescue-only. If Phase A already produced an
                # accepted downloadable or page result, skip rescue entirely.
                if best_downloadable or best_page:
                    break

                time_spent = time.time() - song_start
                time_remaining = self.cfg.per_song_timeout - time_spent
                if time_remaining < (3.0 if self.cfg.maximize_mode else 2.5):
                    break

            phase_started = time.time()
            phase_improved = self._run_phase(
                phase_name=phase_name,
                song=song,
                profile=profile,
                variants=variants,
                variant_limit=variant_limit,
                song_start=song_start,
                phase_start=phase_started,
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
            return self._finalize_result(best_downloadable)
        if best_page:
            return self._finalize_result(best_page)
        if best_seen and self.cfg.fallback_policy == "page_or_best_seen" and self._good_enough_best_seen(best_seen):
            best_seen.status = SongStatus.PAGE_FOUND
            best_seen.note = f"{best_seen.note} Rescued by fallback."
            best_seen.fallback_used = True
            return self._finalize_result(best_seen)
        return self._finalize_result(SearchResult.not_found(song, best_seen=best_seen))

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
        phase_start: float,
        phase_budget: float,
        seen_urls: set[str],
        seen_queries_by_source: dict[str, set[str]],
        best_downloadable: SearchResult | None,
        best_page: SearchResult | None,
        best_seen: SearchResult | None,
    ) -> dict[str, SearchResult | None]:
        for source in self._ordered_sources(profile, phase_name):
            if self._budget_exceeded(song_start) or self._phase_budget_exceeded(phase_start, phase_budget):
                break
            if not self._should_try_source(
                source.name,
                phase_name=phase_name,
                profile=profile,
                song_start=song_start,
                best_downloadable=best_downloadable,
                best_page=best_page,
                best_seen=best_seen,
            ):
                continue
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

            leading_zero_result_attempts = 0
            for variant in source_variants:
                if self._budget_exceeded(song_start) or self._phase_budget_exceeded(phase_start, phase_budget):
                    break
                if variant.query.casefold() in seen_queries_by_source[source.name]:
                    self.run_context.record_redundant_skip(source.name, variant.kind)
                    continue
                seen_queries_by_source[source.name].add(variant.query.casefold())

                urls = self._search_source(source, song, variant)
                if source.name in _PAGE_HEAVY_SOURCES and not self.cfg.maximize_mode:
                    urls = urls[:1]
                if not urls:
                    leading_zero_result_attempts += 1
                    if self._should_early_exit_phase_a_zero_results(source.name, leading_zero_result_attempts):
                        self.printer.vlog(
                            f"  {phase_name}: early exit {source.name} ({leading_zero_result_attempts} leading zero-result variants)"
                        )
                        break
                    continue

                # Only leading zero-result attempts trigger the conservative Phase A cutoff.
                leading_zero_result_attempts = 0

                for url in urls:
                    if self._budget_exceeded(song_start) or self._phase_budget_exceeded(phase_start, phase_budget):
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
        base_order = {name: index for index, name in enumerate(self.cfg.effective_source_priority())}

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

    def _should_try_source(
        self,
        source_name: str,
        *,
        phase_name: str,
        profile: SongProfile,
        song_start: float,
        best_downloadable: SearchResult | None,
        best_page: SearchResult | None,
        best_seen: SearchResult | None,
    ) -> bool:
        if self.cfg.fast_mode:
            return source_name in _PRIMARY_SOURCES

        if not self.cfg.maximize_mode:
            if source_name in _OPT_IN_SOURCES:
                return False
            if phase_name == "phase_a":
                return source_name in (_PRIMARY_SOURCES | _SECONDARY_SOURCES)
            if source_name in _PHASE_B_BALANCED_SOURCES:
                return self._should_try_bandcamp(
                    profile=profile,
                    song_start=song_start,
                    best_downloadable=best_downloadable,
                    best_page=best_page,
                    best_seen=best_seen,
                )
            return False

        if phase_name == "phase_a":
            return source_name not in _PAGE_HEAVY_SOURCES
        return source_name in _PHASE_B_MAXIMIZE_SOURCES

    def _should_try_bandcamp(
        self,
        *,
        profile: SongProfile,
        song_start: float,
        best_downloadable: SearchResult | None,
        best_page: SearchResult | None,
        best_seen: SearchResult | None,
    ) -> bool:
        if self.cfg.maximize_mode:
            return True
        if best_downloadable is not None:
            return False
        if best_page is not None:
            return False

        time_remaining = self.cfg.per_song_timeout - (time.time() - song_start)
        if time_remaining < max(4.0, self.cfg.per_song_timeout * 0.22):
            return False

        metric = self.run_context.sources.get("Bandcamp")
        if metric and metric.page_found_count >= 2 and metric.downloaded_count == 0 and metric.low_value_page_ratio >= 0.75:
            return False

        if best_seen and best_seen.source in (_PRIMARY_SOURCES | _SECONDARY_SOURCES):
            if best_seen.score >= max(self.cfg.min_best_seen_score + 0.04, 0.56):
                return False

        if profile.is_classical or profile.is_instrumental or profile.is_soundtrack or profile.is_electronic:
            return True
        if profile.has_accents or profile.has_non_ascii:
            return True
        if best_seen is None:
            return False
        return (
            best_seen.source == "Bandcamp"
            or best_seen.score >= max(self.cfg.min_best_seen_score + 0.10, 0.64)
        )

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
            limit = min(limit, 1)
        if phase_name == "phase_a":
            if self.cfg.maximize_mode:
                limit = min(limit, 3 if source_name in _DOWNLOAD_FIRST_SOURCES else 1)
            elif source_name == "Internet Archive":
                # Balanced Phase A is intentionally compact but must still reach
                # the high-value transliteration path for non-ASCII songs.
                limit = min(limit, 3)
            elif source_name == "Free Music Archive":
                limit = min(limit, 2)
            else:
                limit = min(limit, 1)
        else:
            if not self.cfg.maximize_mode:
                if source_name == "Internet Archive":
                    limit = min(limit, 3)
                elif source_name == "Free Music Archive":
                    limit = min(limit, 2)
                else:
                    limit = min(limit, 1)
            if source_name in _PAGE_HEAVY_SOURCES:
                limit = min(limit, 1 if not self.cfg.maximize_mode else 2)

        ordered_kinds = _SOURCE_QUERY_ORDER.get(source_name, [])
        ranking = {kind: index for index, kind in enumerate(ordered_kinds)}

        def sort_key(item: QueryVariant) -> tuple[float, float]:
            base = float(ranking.get(item.kind, len(ranking)))
            # Title and transliterated artist/title variants are intentionally kept
            # competitive in Phase A because they carry the best recall gains for IA/FMA.
            if item.kind == "translit_artist_title":
                fallback_penalty = 0.0
            elif item.is_fallback and phase_name == "phase_a" and item.kind in {"title_only", "title_quoted"}:
                fallback_penalty = 0.04
            elif item.is_fallback:
                fallback_penalty = 0.16
            else:
                fallback_penalty = 0.0
            learned = 0.0
            if self.cfg.adaptive_queries and metrics is not None:
                learned -= metrics.query_usefulness(item.kind) * (1.0 if phase_name == "phase_a" else 0.8)
                query_metric = metrics.query_metrics.get(item.kind)
                if query_metric and query_metric.attempts >= 2 and query_metric.zero_results == query_metric.attempts:
                    learned += 0.18 if phase_name == "phase_a" else 0.35
            return (base + fallback_penalty + self._query_profile_bias(item.kind, profile) + learned, len(item.query))

        selected = sorted(variants, key=sort_key)[:limit]

        # Non-ASCII songs need transliteration to remain reachable inside the
        # tight balanced Phase A caps. IA can carry all top 3 high-value
        # variants; FMA keeps artist_title + translit_artist_title when capped at 2.
        if (
            phase_name == "phase_a"
            and not self.cfg.maximize_mode
            and profile.has_non_ascii
            and source_name in {"Internet Archive", "Free Music Archive"}
        ):
            selected = self._ensure_phase_a_translit_reachable(source_name, variants, selected, limit)

        return selected

    def _ensure_phase_a_translit_reachable(
        self,
        source_name: str,
        variants: list[QueryVariant],
        selected: list[QueryVariant],
        limit: int,
    ) -> list[QueryVariant]:
        by_kind = {variant.kind: variant for variant in variants}
        translit = by_kind.get("translit_artist_title")
        if translit is None or any(variant.kind == "translit_artist_title" for variant in selected):
            return selected

        if source_name == "Internet Archive":
            preferred_kinds = ["artist_title", "title_quoted", "translit_artist_title"]
        else:
            preferred_kinds = ["artist_title", "translit_artist_title", "title_quoted"]

        promoted: list[QueryVariant] = []
        for kind in preferred_kinds:
            variant = by_kind.get(kind)
            if variant is not None and variant not in promoted:
                promoted.append(variant)

        for variant in selected:
            if variant not in promoted:
                promoted.append(variant)

        return promoted[:limit]

    def _should_early_exit_phase_a_zero_results(self, source_name: str, zero_result_attempts: int) -> bool:
        cutoff = _PHASE_A_ZERO_RESULT_EXIT.get(source_name)
        return cutoff is not None and zero_result_attempts >= cutoff

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
                if isinstance(persisted, list) and persisted:
                    cached = [str(item) for item in persisted]
                    self.query_cache[cache_key] = cached
            if cached is not None:
                self.run_context.record_cache_hit(source.name, variant.kind)
                self._song_cache_hits += 1
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
                if self.cfg.persistent_cache_enabled and urls:
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
                self._song_cache_hits += 1
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

    def _phase_budget_exceeded(self, phase_start: float, phase_budget: float) -> bool:
        return (time.time() - phase_start) > phase_budget

    def _finalize_result(self, result: SearchResult) -> SearchResult:
        result.cache_hits = self._song_cache_hits
        result.cache_hit = self._song_cache_hits > 0
        return result

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
            threshold = max(threshold, 0.76 if not self.cfg.maximize_mode else 0.78)
        if result.result_tier == ResultTier.TIER_3_WEAK_PAGE:
            threshold = max(threshold, 0.72)
        return result.score >= threshold

    def _good_enough_best_seen(self, result: SearchResult) -> bool:
        if result.result_tier == ResultTier.TIER_3_WEAK_PAGE:
            if (
                not self.cfg.maximize_mode
                and result.source == "Bandcamp"
                and result.score >= 0.76
                and result.matched_query_kind in {"artist_title", "artist_title_quoted", "title_quoted"}
            ):
                return True
            if (
                self.cfg.maximize_mode
                and result.source in _PHASE_B_MAXIMIZE_SOURCES
                and result.score >= 0.78
            ):
                return True
            return False
        return result.score >= self.cfg.min_best_seen_score

    def _classify_result_tier(self, result: SearchResult) -> ResultTier:
        if result.status == SongStatus.DOWNLOADED and result.score >= max(0.42, self.cfg.min_downloadable_score - 0.05):
            return ResultTier.TIER_1_DOWNLOADABLE
        if result.status == SongStatus.PAGE_FOUND:
            if result.source in _PAGE_HEAVY_SOURCES:
                if result.score >= (0.80 if self.cfg.maximize_mode else 0.78):
                    return ResultTier.TIER_2_STRONG_PAGE
                return ResultTier.TIER_3_WEAK_PAGE
            if result.score >= max(0.60, self.cfg.min_page_score):
                return ResultTier.TIER_2_STRONG_PAGE
            if result.score >= max(self.cfg.min_best_seen_score, 0.68):
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
