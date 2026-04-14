"""Engine behavior regressions around presets and balanced mode."""

import time
from collections import defaultdict

from legal_music.config import AppConfig
from legal_music.models import ResultTier, SearchResult, SongStatus
from legal_music.search.engine import SearchEngine
from legal_music.search.profile import classify_song
from legal_music.search.queries import build_query_variants


def test_balanced_phase_a_prefers_primary_and_secondary_sources():
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    ordered = [source.name for source in engine._ordered_sources(classify_song("Artist - Song"), "phase_a")]

    assert ordered == ["Internet Archive", "Free Music Archive"]


def test_maximize_phase_a_adds_jamendo_but_not_page_heavy_bandcamp():
    cfg = AppConfig()
    cfg.apply_maximize_mode()
    engine = SearchEngine(cfg)

    ordered = [source.name for source in engine._ordered_sources(classify_song("Artist - Song"), "phase_a")]

    assert ordered == ["Internet Archive", "Free Music Archive", "Jamendo"]


def test_balanced_bandcamp_phase_b_is_tightly_limited():
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    variants = build_query_variants("Artist - Song")
    selected = engine._variants_for_source(
        "Bandcamp",
        variants,
        cfg.balanced_query_variants,
        classify_song("Artist - Song"),
        "phase_b",
    )

    assert len(selected) == 1


def test_balanced_internet_archive_phase_a_reaches_title_quoted():
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    variants = build_query_variants("Artist - Song")
    selected = engine._variants_for_source(
        "Internet Archive",
        variants,
        cfg.balanced_query_variants,
        classify_song("Artist - Song"),
        "phase_a",
    )

    assert [variant.kind for variant in selected] == ["artist_title", "title_quoted", "artist_title_quoted"]


def test_balanced_internet_archive_phase_b_uses_broader_recovery_variants():
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    variants = build_query_variants("Artist - Song")
    selected = engine._variants_for_source(
        "Internet Archive",
        variants,
        cfg.balanced_query_variants,
        classify_song("Artist - Song"),
        "phase_b",
    )

    assert [variant.kind for variant in selected] == [
        "artist_title",
        "title_quoted",
        "artist_title_quoted",
        "raw_quoted",
    ]


def test_balanced_can_rescue_strong_bandcamp_best_seen():
    cfg = AppConfig()
    engine = SearchEngine(cfg)
    result = SearchResult(
        song="Artist - Song",
        source="Bandcamp",
        status=SongStatus.PAGE_FOUND,
        score=0.71,
        matched_query_kind="artist_title",
        result_tier=ResultTier.TIER_3_WEAK_PAGE,
    )

    assert engine._good_enough_best_seen(result) is True


def test_phase_a_internet_archive_prioritizes_translit_for_non_ascii_song():
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    variants = build_query_variants("Молчат Дома - Судно")
    selected = engine._variants_for_source(
        "Internet Archive",
        variants,
        cfg.balanced_query_variants,
        classify_song("Молчат Дома - Судно"),
        "phase_a",
    )

    assert [variant.kind for variant in selected] == [
        "artist_title",
        "translit_artist_title",
        "title_quoted",
    ]


def test_phase_a_fma_prioritizes_translit_for_non_ascii_song():
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    variants = build_query_variants("Молчат Дома - Судно")
    selected = engine._variants_for_source(
        "Free Music Archive",
        variants,
        cfg.balanced_query_variants,
        classify_song("Молчат Дома - Судно"),
        "phase_a",
    )

    assert [variant.kind for variant in selected] == [
        "artist_title",
        "translit_artist_title",
    ]


def test_phase_a_exits_after_two_leading_zero_result_attempts_on_ia(monkeypatch):
    cfg = AppConfig()
    engine = SearchEngine(cfg)

    search_calls: list[str] = []

    def fake_search_source(source, song, variant):
        search_calls.append(variant.kind)
        return []

    monkeypatch.setattr(engine, "_search_source", fake_search_source)
    monkeypatch.setattr(engine, "_ordered_sources", lambda profile, phase_name: [type("S", (), {"name": "Internet Archive"})()])

    variants = build_query_variants("Artist - Song")
    result = engine._run_phase(
        phase_name="phase_a",
        song="Artist - Song",
        profile=classify_song("Artist - Song"),
        variants=variants,
        variant_limit=cfg.balanced_query_variants,
        song_start=time.time(),
        phase_budget=9999.0,
        seen_urls=set(),
        seen_queries_by_source=defaultdict(set),
        best_downloadable=None,
        best_page=None,
        best_seen=None,
    )

    assert result["best_downloadable"] is None
    assert result["best_page"] is None
    assert result["best_seen"] is None
    assert search_calls == ["artist_title", "title_quoted"]
