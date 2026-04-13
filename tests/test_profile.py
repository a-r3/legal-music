"""Tests for lightweight song profiling."""

from legal_music.search.profile import classify_song


def test_classify_classical_song():
    profile = classify_song("Beethoven - Moonlight Sonata")
    assert profile.is_classical is True
    assert profile.is_instrumental is True


def test_classify_accented_song():
    profile = classify_song("Beyoncé - Halo")
    assert profile.has_accents is True
