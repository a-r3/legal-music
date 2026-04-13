"""Smoke tests: package version and imports."""
from legal_music import __version__
from legal_music.constants import VERSION


def test_version_is_string():
    assert isinstance(__version__, str)
    assert __version__


def test_version_matches_constant():
    assert __version__ == VERSION
