"""CLI smoke tests."""

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


class TestCliStats:
    def test_stats_missing_report(self, tmp_path, capsys):
        rc = main(["stats", str(tmp_path)])
        assert rc == 1

    def test_stats_with_report(self, tmp_path, capsys):
        # Create a minimal report.csv
        report = tmp_path / "report.csv"
        report.write_text(
            "song,source,status,score,matched_query,candidate_title,page_url,direct_url,saved_file,note\n"
            "Test Song,Bandcamp,page_found,0.650,test,Test Song,https://example.com,,, \n",
            encoding="utf-8",
        )
        rc = main(["stats", str(tmp_path)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "page_found" in captured.out
