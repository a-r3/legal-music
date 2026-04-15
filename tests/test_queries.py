"""Tests for query variant generation."""

from legal_music.search.queries import QueryVariant, build_query_variants


class TestBuildQueryVariants:
    def test_only_supported_variant_kinds_are_emitted(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        kinds = {variant.kind for variant in variants}

        assert kinds <= {
            "artist_title",
            "title_quoted",
            "translit_artist_title",
            "translit_raw",
            "artist_title_quoted",
            "title_only",
            "title_artist",
            "title_instrumental",
        }

    def test_returns_list(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert isinstance(variants, list)
        assert len(variants) >= 1
        assert isinstance(variants[0], QueryVariant)

    def test_includes_artist_title(self):
        variants = build_query_variants("Frank Sinatra - My Way")
        assert any(v.kind == "artist_title" and v.query == "Frank Sinatra My Way" for v in variants)

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
        assert any(v.kind == "title_only" and v.query == "My Song" for v in variants)

    def test_empty_after_normalize(self):
        # Should not crash on edge inputs
        variants = build_query_variants("")
        assert isinstance(variants, list)

    def test_includes_fallback_variants(self):
        variants = build_query_variants("Beyoncé - Halo (Live)")
        kinds = {variant.kind for variant in variants}
        assert "title_only" in kinds
        assert "title_quoted" in kinds

    def test_query_cleanup_removes_low_value_variants(self):
        variants = build_query_variants("Artist - Song (feat. Guest) [Live Mix]")
        kinds = {variant.kind for variant in variants}
        assert "raw_without_features" not in kinds
        assert "artist_title_core_quoted" not in kinds
        assert "title_core_quoted" not in kinds
        assert "normalized_title" not in kinds
        assert "title_artist_inverted" not in kinds
        assert "raw" not in kinds
        assert "raw_quoted" not in kinds
        assert "title_core" not in kinds
        assert "artist_title_core" not in kinds
        assert "normalized_full" not in kinds
        assert "accent_folded_title" not in kinds

    def test_includes_transliterated_artist_title_for_non_ascii(self):
        variants = build_query_variants("Молчат Дома - Судно")
        kinds = {variant.kind for variant in variants}
        assert "translit_artist_title" in kinds
