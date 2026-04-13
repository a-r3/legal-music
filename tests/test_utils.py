"""Tests for string normalization and parsing utilities."""

from legal_music.utils import (
    normalize_song,
    parse_artist_title,
    safe_filename,
    strip_accents,
    strip_mix_suffix,
    tokenize,
)


class TestNormalizeSong:
    def test_removes_official_audio(self):
        result = normalize_song("Artist - Song (Official Audio)")
        assert "official" not in result
        assert "audio" not in result
        assert "song" in result

    def test_removes_lyrics(self):
        result = normalize_song("Song Title [Lyrics]")
        assert "lyrics" not in result
        assert "song" in result
        assert "title" in result

    def test_strips_feat(self):
        result = normalize_song("Artist - Song feat. Other Artist")
        assert "other" not in result
        assert "song" in result

    def test_normalizes_dashes(self):
        result = normalize_song("Artist \u2013 Song")  # en dash
        assert "artist" in result
        assert "song" in result

    def test_empty_string(self):
        assert normalize_song("") == ""

    def test_only_noise_words(self):
        # All noise words should produce empty or near-empty
        result = normalize_song("official audio lyrics")
        assert result == ""

    def test_preserves_meaningful_content(self):
        result = normalize_song("Frank Sinatra - My Way")
        assert "frank" in result
        assert "sinatra" in result
        assert "way" in result

    def test_accent_folding(self):
        assert strip_accents("Beyoncé") == "Beyonce"

    def test_strip_mix_suffix_preserves_core_title(self):
        assert strip_mix_suffix("My Way (Live 1997 Remaster)") == "My Way"


class TestParseArtistTitle:
    def test_dash_separator(self):
        artist, title = parse_artist_title("Frank Sinatra - My Way")
        assert artist == "Frank Sinatra"
        assert title == "My Way"

    def test_em_dash(self):
        artist, title = parse_artist_title("Artist \u2014 Title")
        assert artist == "Artist"
        assert title == "Title"

    def test_no_separator(self):
        artist, title = parse_artist_title("Some Song Title")
        assert artist == ""
        assert title == "Some Song Title"

    def test_strips_feat(self):
        artist, title = parse_artist_title("Artist - Title feat. Someone")
        assert "Someone" not in title
        assert "feat" not in title.lower()


class TestTokenize:
    def test_returns_tokens(self):
        tokens = tokenize("Frank Sinatra - My Way")
        assert "frank" in tokens
        assert "sinatra" in tokens
        assert "way" in tokens

    def test_excludes_stop_words(self):
        tokens = tokenize("the song of the century")
        assert "the" not in tokens
        assert "of" not in tokens
        assert "song" in tokens

    def test_empty(self):
        assert tokenize("") == []


class TestSafeFilename:
    def test_removes_forbidden_chars(self):
        result = safe_filename('Artist: Song/Title?')
        assert ":" not in result
        assert "/" not in result
        assert "?" not in result

    def test_truncates_long_names(self):
        result = safe_filename("a" * 300, max_len=180)
        assert len(result) <= 180
