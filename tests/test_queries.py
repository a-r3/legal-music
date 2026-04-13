"""Tests for query variant generation."""

from legal_music.search.queries import build_query_variants


class TestBuildQueryVariants:
    def test_returns_list(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert isinstance(variants, list)
        assert len(variants) >= 1

    def test_includes_raw(self):
        song = "Frank Sinatra - My Way"
        variants = build_query_variants(song)
        assert song in variants

    def test_includes_title(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert any("My Way" in v for v in variants)

    def test_includes_artist_title_quoted(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert any('"Frank Sinatra"' in v for v in variants)

    def test_no_duplicates(self):
        variants = build_query_variants("Artist - Title")
        assert len(variants) == len(set(variants))

    def test_no_separator(self):
        variants = build_query_variants("My Song")
        assert "My Song" in variants

    def test_empty_after_normalize(self):
        # Should not crash on edge inputs
        variants = build_query_variants("")
        assert isinstance(variants, list)
