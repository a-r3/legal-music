"""Tests for config loading and validation."""
import json
import tempfile
from pathlib import Path

from legal_music.config import AppConfig, SourceConfig
from legal_music.search.engine import build_session, build_sources


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.delay > 0
        assert cfg.max_results > 0
        assert len(cfg.sources) > 0
        assert cfg.balanced_query_variants >= cfg.fast_query_variants
        assert cfg.source_preset == "balanced"
        assert cfg.configured_source_names() == ["Internet Archive", "Free Music Archive", "Bandcamp"]
        assert cfg.phase_a_budget_ratio == 0.70
        assert cfg.min_page_score == 0.50
        assert cfg.min_best_seen_score == 0.50

    def test_validate_ok(self):
        cfg = AppConfig()
        assert cfg.validate() == []

    def test_validate_bad_delay(self):
        cfg = AppConfig(delay=-1.0)
        errors = cfg.validate()
        assert any("delay" in e for e in errors)

    def test_validate_bad_max_results(self):
        cfg = AppConfig(max_results=0)
        errors = cfg.validate()
        assert any("max_results" in e for e in errors)

    def test_validate_no_sources(self):
        cfg = AppConfig(sources=[])
        errors = cfg.validate()
        assert any("source" in e for e in errors)

    def test_round_trip_json(self):
        cfg = AppConfig(
            phase_a_budget_ratio=0.6,
            persistent_cache_enabled=True,
            source_preset="custom",
            sources=[
                SourceConfig("Internet Archive", enabled=False),
                SourceConfig("Free Music Archive", enabled=False),
                SourceConfig("Bandcamp", enabled=True, max_variants=3, min_page_score=0.4),
                SourceConfig("Jamendo", enabled=False),
                SourceConfig("Pixabay Music", enabled=False),
            ],
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            cfg.save(path)
            loaded = AppConfig.load(path)
            assert loaded.delay == cfg.delay
            assert loaded.max_results == cfg.max_results
            assert len(loaded.sources) == len(cfg.sources)
            assert loaded.source_priority == cfg.source_priority
            assert loaded.persistent_cache_enabled is True
            assert loaded.phase_a_budget_ratio == 0.6
            assert loaded.source_preset == "custom"
            assert loaded.source_config_for("Bandcamp").max_variants == 3
        finally:
            path.unlink(missing_ok=True)

    def test_load_missing_returns_defaults(self):
        cfg = AppConfig.load(Path("/tmp/does_not_exist_legal_music.json"))
        assert cfg.delay > 0

    def test_enabled_source_names(self):
        cfg = AppConfig(
            sources=[
                SourceConfig("Bandcamp", enabled=True),
                SourceConfig("Jamendo", enabled=False),
            ]
        )
        names = cfg.enabled_source_names()
        assert "Bandcamp" in names
        assert "Jamendo" not in names

    def test_apply_maximize_mode(self):
        cfg = AppConfig()
        cfg.apply_maximize_mode()
        assert cfg.maximize_mode is True
        assert cfg.per_song_timeout >= 24
        assert cfg.maximize_query_variants >= cfg.balanced_query_variants
        assert 0.5 <= cfg.phase_a_budget_ratio <= 0.7
        assert cfg.configured_source_names() == ["Internet Archive", "Free Music Archive", "Bandcamp"]
        assert cfg.enabled_source_names() == [
            "Internet Archive",
            "Free Music Archive",
            "Bandcamp",
            "Jamendo",
            "Pixabay Music",
        ]

    def test_validate_bad_phase_ratio(self):
        cfg = AppConfig(phase_a_budget_ratio=1.2)
        errors = cfg.validate()
        assert any("phase_a_budget_ratio" in e for e in errors)

    def test_source_config_lookup(self):
        cfg = AppConfig(sources=[SourceConfig("Bandcamp", max_variants=4)])
        assert cfg.source_config_for("Bandcamp") is not None
        assert cfg.source_config_for("Bandcamp").max_variants == 4

    def test_legacy_incomplete_sources_migrate_to_balanced(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "delay": 0.6,
                    "sources": [
                        {"name": "Internet Archive", "enabled": True},
                        {"name": "Bandcamp", "enabled": True},
                        {"name": "Jamendo", "enabled": True},
                        {"name": "Pixabay Music", "enabled": True},
                    ],
                    "phase_a_budget_ratio": 0.78,
                    "min_page_score": 0.52,
                    "min_best_seen_score": 0.55,
                    "max_results": 4,
                }
            ),
            encoding="utf-8",
        )

        cfg = AppConfig.load(cfg_path)

        assert cfg.source_preset == "balanced"
        assert cfg.configured_source_names() == ["Internet Archive", "Free Music Archive", "Bandcamp"]
        assert [source.name for source in cfg.sources] == [
            "Internet Archive",
            "Free Music Archive",
            "Bandcamp",
            "Jamendo",
            "Pixabay Music",
        ]
        assert cfg.find_source("Jamendo").enabled is False
        assert cfg.find_source("Pixabay").enabled is False
        assert cfg.phase_a_budget_ratio == 0.70
        assert cfg.min_page_score == 0.50
        assert cfg.min_best_seen_score == 0.50
        assert cfg.max_results == 5

    def test_complete_legacy_custom_sources_remain_custom(self):
        cfg = AppConfig.from_dict(
            {
                "sources": [
                    {"name": "Internet Archive", "enabled": True},
                    {"name": "Free Music Archive", "enabled": True},
                    {"name": "Bandcamp", "enabled": False},
                    {"name": "Jamendo", "enabled": False},
                    {"name": "Pixabay Music", "enabled": False},
                ]
            }
        )

        assert cfg.source_preset == "custom"
        assert cfg.configured_source_names() == ["Internet Archive", "Free Music Archive"]

    def test_build_sources_uses_effective_runtime_sources(self):
        cfg = AppConfig()
        balanced_sources = build_sources(cfg, build_session(cfg))
        assert [source.name for source in balanced_sources] == [
            "Internet Archive",
            "Free Music Archive",
            "Bandcamp",
        ]

        cfg.apply_maximize_mode()
        maximize_sources = build_sources(cfg, build_session(cfg))
        assert [source.name for source in maximize_sources] == [
            "Internet Archive",
            "Free Music Archive",
            "Bandcamp",
            "Jamendo",
            "Pixabay Music",
        ]
