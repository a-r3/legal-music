from pathlib import Path

from legal_music import __version__
from legal_music.cli import clean_song_name, generate_search_variants


def test_version_present():
    assert isinstance(__version__, str)
    assert __version__


def test_clean_song_name_removes_noise():
    value = clean_song_name("Artist - Song (Official Audio) [Lyrics]")
    assert "official" not in value
    assert "lyrics" not in value
    assert "song" in value


def test_generate_search_variants_returns_values():
    variants = generate_search_variants("Artist - Song")
    assert variants
    assert any("Song" in item or "song" in item for item in variants)
