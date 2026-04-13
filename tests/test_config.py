"""Tests for config loading and validation."""
import tempfile
from pathlib import Path

from legal_music.config import AppConfig, SourceConfig


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.delay > 0
        assert cfg.max_results > 0
        assert len(cfg.sources) > 0

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
        cfg = AppConfig()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            cfg.save(path)
            loaded = AppConfig.load(path)
            assert loaded.delay == cfg.delay
            assert loaded.max_results == cfg.max_results
            assert len(loaded.sources) == len(cfg.sources)
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
