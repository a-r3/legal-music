"""CLI smoke tests."""

import json
from argparse import Namespace

import pytest

from legal_music.cli import _batch_run, build_parser, main
from legal_music.models import RunStats
from legal_music.reports import print_summary


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
        source_names = [source["name"] for source in data["sources"]]
        # All known sources must be present (original 5 + 3 new ones)
        for name in ["Internet Archive", "Free Music Archive", "Bandcamp", "Jamendo", "Pixabay Music"]:
            assert name in source_names
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
            "song,source,source_used,status,score,cache_hit,cache_hits,matched_query,matched_query_kind,fallback_used,resolved_phase,result_tier,candidate_title,best_seen_source,best_seen_score,best_seen_tier,best_seen_url,page_url,direct_url,saved_file,note\n"
            "Test Song,Bandcamp,Bandcamp,page_found,0.650,no,0,test,title_only,no,phase_b,tier_2_strong_page,Test Song,,,,,https://example.com,,, \n",
            encoding="utf-8",
        )
        rc = main(["stats", str(tmp_path)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "page_found" in captured.out


class TestSummaryOutput:
    def test_print_summary_includes_required_totals(self, capsys):
        stats = RunStats(
            total=5,
            downloaded=2,
            page_found=1,
            not_found=2,
            elapsed_seconds=12.0,
            avg_seconds_per_song=2.4,
            avg_seconds_per_success=4.0,
            phase_a_wins=2,
            phase_b_wins=1,
        )

        print_summary(stats, {}, use_color=False)

        captured = capsys.readouterr()
        assert "total processed" in captured.out
        assert "downloaded" in captured.out
        assert "page_found" in captured.out
        assert "not_found" in captured.out
        assert "avg per song" in captured.out
        assert "avg per useful result" in captured.out
        assert "phase wins             : A=2, B=1" in captured.out


class TestBatchOutput:
    def test_batch_run_prints_compact_playlist_rollup(self, tmp_path, monkeypatch, capsys):
        playlists_dir = tmp_path / "playlists"
        playlists_dir.mkdir()
        (playlists_dir / "alpha.txt").write_text("Song A\nSong B\n", encoding="utf-8")

        def fake_run_playlist(songs, playlist_name, cfg, output_dir, dry_run, verbose, no_color):
            output_dir.mkdir(parents=True, exist_ok=True)
            return RunStats(total=2, downloaded=1, page_found=1, not_found=0)

        monkeypatch.setattr("legal_music.cli._run_playlist", fake_run_playlist)

        rc = _batch_run(
            Namespace(
                playlist_dir=str(playlists_dir),
                config=str(tmp_path / "missing.json"),
                output=str(tmp_path / "output"),
                fast=False,
                maximize=False,
                delay=None,
                max_results=None,
                verbose=False,
                no_color=True,
            ),
            dry_run=True,
        )

        assert rc == 0
        captured = capsys.readouterr()
        assert "alpha - processed=2 downloaded=1 page_found=1 not_found=0" in captured.out
