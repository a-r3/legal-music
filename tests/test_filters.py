"""Tests for duplicate detection."""

from legal_music.search.filters import dedupe_songs


class TestDedupeSongs:
    def test_removes_exact_duplicates(self):
        songs = ["Artist - Song", "Artist - Song"]
        unique, removed = dedupe_songs(songs)
        assert len(unique) == 1
        assert len(removed) == 1

    def test_keeps_unique(self):
        songs = ["Frank Sinatra - My Way", "John Mayer - Gravity"]
        unique, removed = dedupe_songs(songs)
        assert len(unique) == 2
        assert len(removed) == 0

    def test_detects_near_duplicates(self):
        songs = [
            "Artist - Song (Official Audio)",
            "Artist - Song",
        ]
        unique, removed = dedupe_songs(songs)
        assert len(unique) == 1
        assert len(removed) == 1

    def test_removed_tuple_structure(self):
        songs = ["A - B", "A - B"]
        _, removed = dedupe_songs(songs)
        assert len(removed) == 1
        raw, matched, reason = removed[0]
        assert raw == "A - B"
        assert matched == "A - B"
        assert reason == "exact"

    def test_empty_input(self):
        unique, removed = dedupe_songs([])
        assert unique == []
        assert removed == []

    def test_skips_blank_entries(self):
        songs = ["", "Artist - Song", "  "]
        unique, removed = dedupe_songs(songs)
        assert len(unique) == 1
