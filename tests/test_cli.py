"""CLI smoke tests."""

import json

import pytest

from legal_music.cli import build_parser, main


class TestCliParser:
    def test_version_flag(self, capsys):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--version"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "legal-music" in captured.out

    def test_dry_requires_playlist(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["dry"])

    def test_dl_requires_playlist(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["dl"])

    def test_maximize_flag(self):
        parser = build_parser()
        args = parser.parse_args(["dry", "--maximize", "playlist.txt"])
        assert args.maximize is True

    def test_cmd_version(self, capsys):
        rc = main(["version"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "legal-music" in captured.out


class TestCliInit:
    def test_init_creates_config(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        rc = main(["init", "--config", str(cfg_path)])
        assert rc == 0
        assert cfg_path.exists()

    def test_src_preset_balanced_repairs_legacy_config(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {"name": "Internet Archive", "enabled": True},
                        {"name": "Bandcamp", "enabled": True},
                        {"name": "Jamendo", "enabled": True},
                    ]
                }
            ),
            encoding="utf-8",
        )

        rc = main(["src", "preset", "balanced", "--config", str(cfg_path), "--no-color"])

        assert rc == 0
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["source_preset"] == "balanced"
        assert [source["name"] for source in data["sources"]] == [
            "Internet Archive",
            "Free Music Archive",
            "Bandcamp",
            "Jamendo",
            "Pixabay Music",
        ]
        enabled = [source["name"] for source in data["sources"] if source["enabled"]]
        assert enabled == ["Internet Archive", "Free Music Archive", "Bandcamp"]


class TestCliStats:
    def test_stats_missing_report(self, tmp_path, capsys):
        rc = main(["stats", str(tmp_path)])
        assert rc == 1

    def test_stats_with_report(self, tmp_path, capsys):
        # Create a minimal report.csv
        report = tmp_path / "report.csv"
        report.write_text(
            "song,source,status,score,matched_query,matched_query_kind,fallback_used,resolved_phase,result_tier,candidate_title,best_seen_source,best_seen_score,best_seen_tier,best_seen_url,page_url,direct_url,saved_file,note\n"
            "Test Song,Bandcamp,page_found,0.650,test,title_only,no,phase_b,tier_2_strong_page,Test Song,,,,,https://example.com,,, \n",
            encoding="utf-8",
        )
        rc = main(["stats", str(tmp_path)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "page_found" in captured.out
