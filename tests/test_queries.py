"""Tests for query variant generation."""

from legal_music.search.queries import QueryVariant, build_query_variants


class TestBuildQueryVariants:
    def test_returns_list(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert isinstance(variants, list)
        assert len(variants) >= 1
        assert isinstance(variants[0], QueryVariant)

    def test_includes_raw(self):
        song = "Frank Sinatra - My Way"
        variants = build_query_variants(song)
        assert any(v.query == song for v in variants)

    def test_includes_title(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert any("My Way" in v.query for v in variants)

    def test_includes_artist_title_quoted(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert any('"Frank Sinatra"' in v.query for v in variants)

    def test_no_duplicates(self):
        variants = build_query_variants("Artist - Title")
        queries = [variant.query for variant in variants]
        assert len(queries) == len(set(queries))

    def test_no_separator(self):
        variants = build_query_variants("My Song")
        assert any(v.query == "My Song" for v in variants)

    def test_empty_after_normalize(self):
        # Should not crash on edge inputs
        variants = build_query_variants("")
        assert isinstance(variants, list)

    def test_includes_fallback_variants(self):
        variants = build_query_variants("Beyoncé - Halo (Live)")
        kinds = {variant.kind for variant in variants}
        assert "title_only" in kinds or "title_core" in kinds
        assert "normalized_full" in kinds or "accent_folded_title" in kinds
