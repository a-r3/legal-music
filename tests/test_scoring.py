"""Tests for candidate scoring."""
from legal_music.search.scoring import score_candidate


class TestScoreCandidate:
    def test_returns_float_in_range(self):
        score = score_candidate("Frank Sinatra - My Way", "Frank Sinatra - My Way", "https://example.com")
        assert 0.0 <= score <= 1.0

    def test_exact_match_high_score(self):
        score = score_candidate(
            "Frank Sinatra - My Way",
            "Frank Sinatra My Way",
            "https://archive.org/details/frank-sinatra-my-way",
        )
        assert score >= 0.5

    def test_unrelated_low_score(self):
        score = score_candidate(
            "Frank Sinatra - My Way",
            "Heavy Metal Band - Destruction",
            "https://archive.org/details/heavy-metal-destruction",
        )
        assert score < 0.4

    def test_empty_candidate(self):
        score = score_candidate("Frank Sinatra - My Way", "", "https://example.com")
        assert 0.0 <= score <= 1.0

    def test_url_contributes_to_score(self):
        score_relevant = score_candidate(
            "Frank Sinatra - My Way",
            "",
            "https://archive.org/details/frank-sinatra-my-way",
        )
        score_irrelevant = score_candidate(
            "Frank Sinatra - My Way",
            "",
            "https://archive.org/details/xyz-123-abc",
        )
        assert score_relevant > score_irrelevant
