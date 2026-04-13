from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.parse import quote, urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

try:
    from openpyxl import Workbook
    HAS_XLSX = True
except Exception:
    HAS_XLSX = False

VERSION = "1.2.0"
APP_NAME = "legal-music"
APP_DIR_NAME = "legal-music"
DEFAULT_INPUT_FILE = "songs.txt"
DEFAULT_CONFIG_FILE = "config.json"

DEFAULT_SEARCH_TARGETS = [
    {"name": "Bandcamp", "query": "site:bandcamp.com {query}", "enabled": True},
    {"name": "Internet Archive", "query": "site:archive.org {query}", "enabled": True},
    {"name": "Jamendo", "query": "site:jamendo.com {query}", "enabled": True},
    {"name": "Pixabay Music", "query": "site:pixabay.com/music {query}", "enabled": True},
]

ALLOWED_AUDIO_EXTENSIONS = (".mp3", ".flac", ".ogg", ".wav", ".m4a")
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

NOISE_WORDS = {
    "official", "audio", "video", "lyrics", "lyric", "live", "remix", "edit", "version",
    "remastered", "remaster", "hq", "hd", "full", "album", "topic", "track", "music",
    "feat", "featuring", "ft", "karaoke", "instrumental", "cover", "extended", "radio",
    "prod", "produced", "performance", "clip", "visualizer", "teaser", "clean", "explicit"
}

STOP_WORDS = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "by"}

LONG_HELP = """\
legal-music — professional CLI for checking music only on allowed sources

Main workflow:
  1) legal-music init
  2) edit songs file
  3) legal-music run --dry-run
  4) legal-music run

Core commands:
  legal-music run
  legal-music run --dry-run
  legal-music run -v
  legal-music sources
  legal-music doctor
  legal-music stats
  legal-music config-paths
  legal-music version

Config commands:
  legal-music backup-config
  legal-music reset-config
  legal-music shell-completion bash
  legal-music shell-completion zsh
  legal-music self-update
"""

BASH_COMPLETION = r"""
_legal_music_completions() {
    local cur prev words cword
    _init_completion || return
    local commands="run init sources config-paths doctor version shell-completion self-update stats reset-config backup-config"
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands --help" -- "$cur") )
        return
    fi
    case "${words[1]}" in
        run)
            COMPREPLY=( $(compgen -W "--help -i --input -o --output -c --config --delay --max-results -v --verbose --no-color --dry-run" -- "$cur") )
            ;;
        init|reset-config|backup-config)
            COMPREPLY=( $(compgen -W "--help -i --input -c --config" -- "$cur") )
            ;;
        shell-completion)
            COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") )
            ;;
        *)
            COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
            ;;
    esac
}
complete -F _legal_music_completions legal-music
"""

ZSH_COMPLETION = r"""
#compdef legal-music
_arguments \
  '1: :((run\:run init\:init sources\:sources config-paths\:paths doctor\:doctor version\:version shell-completion\:completion self-update\:update stats\:stats reset-config\:reset backup-config\:backup))' \
  '*::arg:->args'
case $state in
  args)
    case $words[2] in
      run)
        _arguments '--input[Input file]:file:_files' '--output[Output dir]:dir:_files -/' '--config[Config file]:file:_files' '--delay[Delay]' '--max-results[Max results]' '--verbose[Verbose]' '--no-color[No color]' '--dry-run[Dry run]'
        ;;
      init|reset-config|backup-config)
        _arguments '--input[Input file]:file:_files' '--config[Config file]:file:_files'
        ;;
      shell-completion)
        _values 'shell' bash zsh
        ;;
    esac
    ;;
esac
"""

class T:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"

def supports_color() -> bool:
    return sys.stdout.isatty()

def c(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{T.RESET}" if enabled else text

def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"

def default_data_dir() -> Path:
    if os_name() == "windows":
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME

def default_config_dir() -> Path:
    if os_name() == "windows":
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME

def default_output_dir() -> Path:
    return default_data_dir() / "output"

def default_runtime_log() -> Path:
    return default_data_dir() / "runtime.log"

def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@dataclass
class SearchResult:
    song: str
    source_name: str
    page_url: str
    direct_download_url: Optional[str]
    status: str
    note: str
    score: float = 0.0
    matched_query: str = ""
    candidate_title: str = ""

class LegalMusicFinder:
    def __init__(self, output_dir: Path, search_targets: List[dict], delay: float = 1.2, max_results: int = 8, verbose: bool = False, no_color: bool = False, dry_run: bool = False, min_downloadable_score: float = 0.40, min_page_score: float = 0.52, min_best_seen_score: float = 0.55):
        self.output_dir = output_dir
        self.download_dir = output_dir / "downloads"
        self.report_file = output_dir / "report.csv"
        self.report_xlsx = output_dir / "report.xlsx"
        self.error_log = output_dir / "errors.log"
        self.duplicates_file = output_dir / "duplicates.csv"
        self.runtime_log = default_runtime_log()
        self.delay = delay
        self.max_results = max_results
        self.verbose = verbose
        self.use_color = supports_color() and not no_color
        self.dry_run = dry_run
        self.min_downloadable_score = min_downloadable_score
        self.min_page_score = min_page_score
        self.min_best_seen_score = min_best_seen_score
        self.search_targets = [x for x in search_targets if x.get("enabled", True)]
        self.stats = {"downloaded": 0, "page_found": 0, "not_found": 0, "errors": 0, "download_error": 0, "other": 0}

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_log.parent.mkdir(parents=True, exist_ok=True)

    def append_runtime(self, message: str) -> None:
        with self.runtime_log.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")

    def start_runtime_session(self) -> None:
        self.append_runtime("=" * 72)
        self.append_runtime(f"session_start: {now_stamp()}")
        self.append_runtime(f"version      : {VERSION}")
        self.append_runtime(f"mode         : {'dry-run' if self.dry_run else 'download'}")
        self.append_runtime(f"output_dir   : {self.output_dir}")

    def log_error(self, message: str) -> None:
        with self.error_log.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
        self.append_runtime(f"error: {message}")

    def vlog(self, message: str) -> None:
        if self.verbose:
            print(c(f"   > {message}", T.DIM, self.use_color))
        self.append_runtime(f"verbose: {message}")

    def ok(self, message: str) -> None:
        print(c(message, T.GREEN, self.use_color))
        self.append_runtime(message)

    def warn(self, message: str) -> None:
        print(c(message, T.YELLOW, self.use_color))
        self.append_runtime(message)

    def err(self, message: str) -> None:
        print(c(message, T.RED, self.use_color))
        self.append_runtime(message)

    @staticmethod
    def safe_filename(name: str) -> str:
        name = re.sub(r'[\\/*?:"<>|]', "_", name)
        return re.sub(r"\s+", " ", name).strip()[:180]

    @classmethod
    def strip_bracketed_noise(cls, value: str) -> str:
        patterns = [
            r"\((?:[^)]*?(?:official|lyrics?|live|remix|remaster(?:ed)?|audio|video|hq|hd|karaoke|instrumental|feat\.?|featuring|ft\.?|prod\.?).*?)\)",
            r"\[(?:[^\]]*?(?:official|lyrics?|live|remix|remaster(?:ed)?|audio|video|hq|hd|karaoke|instrumental|feat\.?|featuring|ft\.?|prod\.?).*?)\]",
        ]
        for pat in patterns:
            value = re.sub(pat, " ", value, flags=re.IGNORECASE)
        return value

    @classmethod
    def normalize_song_name(cls, name: str) -> str:
        value = name.casefold().strip()
        value = cls.strip_bracketed_noise(value)
        value = re.sub(r"[\u2013\u2014]", "-", value)
        value = re.sub(r"\b(feat\.?|featuring|ft\.?)\b", " feat ", value)
        value = re.sub(r"\b(prod\.?|produced by)\b", " prod ", value)
        value = re.sub(r"\bfeat\b.*$", " ", value)
        value = re.sub(r"\bprod\b.*$", " ", value)
        value = re.sub(r"[()\[\]{}_]+", " ", value)
        value = re.sub(r"[^-\w\s]+", " ", value, flags=re.UNICODE)
        tokens = []
        for token in re.split(r"\s+", value):
            token = token.strip("-_ ")
            if token and token not in NOISE_WORDS:
                tokens.append(token)
        return re.sub(r"\s+", " ", " ".join(tokens)).strip()

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        return [p for p in re.split(r"[\s\-]+", cls.normalize_song_name(text)) if p and p not in STOP_WORDS]

    @classmethod
    def parse_artist_title(cls, song: str) -> Tuple[str, str]:
        raw = re.sub(r"\s+", " ", song).strip()
        raw = re.sub(r"\s+(feat\.?|featuring|ft\.?)\s+.*$", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s+(prod\.?|produced by)\s+.*$", "", raw, flags=re.IGNORECASE)
        for sep in [" - ", " — ", " – ", "-"]:
            if sep in raw:
                left, right = raw.split(sep, 1)
                return left.strip(), right.strip()
        return "", raw

    @classmethod
    def dedupe_songs(cls, songs: List[str]) -> Tuple[List[str], List[Tuple[str, str, str]]]:
        unique, seen, removed = [], [], []
        for song in songs:
            norm = cls.normalize_song_name(song)
            tokens = set(cls.tokenize(song))
            if not norm:
                continue
            duplicate_of = None
            for existing_song, existing_norm, existing_tokens in seen:
                if norm == existing_norm:
                    duplicate_of = (existing_song, "exact")
                    break
                ratio = difflib.SequenceMatcher(None, norm, existing_norm).ratio()
                token_overlap = (len(tokens & existing_tokens) / max(1, len(tokens | existing_tokens))) if (tokens or existing_tokens) else 0.0
                if ratio >= 0.94:
                    duplicate_of = (existing_song, f"near:{ratio:.2f}")
                    break
                if token_overlap >= 0.88 and min(len(tokens), len(existing_tokens)) >= 2:
                    duplicate_of = (existing_song, f"token:{token_overlap:.2f}")
                    break
            if duplicate_of:
                removed.append((song, duplicate_of[0], duplicate_of[1]))
            else:
                unique.append(song)
                seen.append((song, norm, tokens))
        return unique, removed

    @classmethod
    def build_query_variants(cls, song: str) -> List[str]:
        raw = re.sub(r"\s+", " ", song).strip()
        artist, title = cls.parse_artist_title(raw)
        norm = cls.normalize_song_name(raw)
        title_norm = cls.normalize_song_name(title)
        artist_norm = cls.normalize_song_name(artist)
        variants = [raw]
        if norm and norm != raw:
            variants.append(norm)
        if artist and title:
            variants.extend([f'"{artist}" "{title}"', f"{artist} {title}", title])
            if artist_norm and title_norm:
                variants.extend([f'"{artist_norm}" "{title_norm}"', f"{artist_norm} {title_norm}", title_norm])
        else:
            variants.append(title)
        out, seen = [], set()
        for item in variants:
            item = re.sub(r"\s+", " ", item).strip()
            if item and item not in seen:
                out.append(item); seen.add(item)
        return out

    @classmethod
    def score_candidate(cls, song: str, candidate_title: str, page_url: str) -> float:
        artist, title = cls.parse_artist_title(song)
        song_norm = cls.normalize_song_name(song)
        cand_norm = cls.normalize_song_name(candidate_title or "")
        url_text = unquote(urlparse(page_url).path).replace("/", " ")
        url_norm = cls.normalize_song_name(url_text)
        song_tokens = set(cls.tokenize(song))
        title_tokens = set(cls.tokenize(title))
        artist_tokens = set(cls.tokenize(artist))
        cand_tokens = set(cls.tokenize(candidate_title + " " + url_text))
        seq1 = difflib.SequenceMatcher(None, song_norm, cand_norm).ratio() if cand_norm else 0.0
        seq2 = difflib.SequenceMatcher(None, song_norm, url_norm).ratio() if url_norm else 0.0
        token_all = len(song_tokens & cand_tokens) / max(1, len(song_tokens))
        token_title = len(title_tokens & cand_tokens) / max(1, len(title_tokens)) if title_tokens else 0.0
        token_artist = len(artist_tokens & cand_tokens) / max(1, len(artist_tokens)) if artist_tokens else 0.0
        score = max(seq1, seq2) * 0.4 + token_all * 0.25 + token_title * 0.25 + token_artist * 0.10
        if token_title >= 0.7 and (not artist_tokens or token_artist >= 0.5):
            score += 0.15
        return min(score, 1.0)

    @staticmethod
    def extract_page_title(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.text:
            return soup.title.text.strip()
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            return og["content"].strip()
        h1 = soup.find("h1")
        return h1.get_text(" ", strip=True) if h1 else ""

    @staticmethod
    def read_song_list(file_path: Path) -> List[str]:
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        songs = []
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                songs.append(line)
        if not songs:
            raise ValueError("Input file is empty.")
        return songs

    @staticmethod
    def load_config(config_path: Path) -> dict:
        if not config_path.exists():
            return {"search_targets": DEFAULT_SEARCH_TARGETS, "min_downloadable_score": 0.40, "min_page_score": 0.52, "min_best_seen_score": 0.55}
        return json.loads(config_path.read_text(encoding="utf-8"))

    @staticmethod
    def create_default_config(config_path: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"search_targets": DEFAULT_SEARCH_TARGETS, "min_downloadable_score": 0.40, "min_page_score": 0.52, "min_best_seen_score": 0.55}, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def create_default_songs(input_path: Path) -> None:
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text("# One song per line\nMuslim Magomayev - Лучший город земли\nJohn Mayer - Gravity\nFrank Sinatra - My Way\nJohn Mayer - Gravity (Official Audio)\n", encoding="utf-8")

    def fetch(self, url: str) -> requests.Response:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r

    def duckduckgo_search(self, query: str) -> List[str]:
        soup = BeautifulSoup(self.fetch(f"https://html.duckduckgo.com/html/?q={quote(query)}").text, "html.parser")
        links = []
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href and href not in links:
                links.append(href)
            if len(links) >= self.max_results:
                break
        return links

    def extract_direct_audio_links_from_html(self, page_url: str, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser"); results = []
        for tag in soup.find_all(["audio", "source", "a"]):
            candidate = tag.get("src") or tag.get("href")
            if not candidate:
                continue
            full_url = urljoin(page_url, candidate)
            if any(ext in full_url.lower() for ext in ALLOWED_AUDIO_EXTENSIONS) and full_url not in results:
                results.append(full_url)
        return results

    def build_result(self, song: str, source_name: str, page_url: str, html: str, direct_url: Optional[str], status: str, note: str) -> SearchResult:
        page_title = self.extract_page_title(html)
        return SearchResult(song, source_name, page_url, direct_url, status, note, score=self.score_candidate(song, page_title, page_url), candidate_title=page_title)

    def find_bandcamp(self, song: str, page_url: str) -> SearchResult:
        try:
            html = self.fetch(page_url).text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links_from_html(page_url, html)
            if direct_links:
                return self.build_result(song, "Bandcamp", page_url, html, direct_links[0], "downloadable", "Direct audio link found.")
            if any(key in text for key in ["buy digital", "download", "name your price"]):
                return self.build_result(song, "Bandcamp", page_url, html, None, "page_found", "Legal page found.")
            return self.build_result(song, "Bandcamp", page_url, html, None, "not_sure", "Page found but download not confirmed.")
        except Exception as e:
            return SearchResult(song, "Bandcamp", page_url, None, "error", f"Bandcamp error: {e}")

    def find_archive(self, song: str, page_url: str) -> SearchResult:
        try:
            html = self.fetch(page_url).text
            direct_links = self.extract_direct_audio_links_from_html(page_url, html)
            if direct_links:
                return self.build_result(song, "Internet Archive", page_url, html, direct_links[0], "downloadable", "Direct audio link found.")
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(page_url, a["href"])
                if any(href.lower().endswith(ext) for ext in ALLOWED_AUDIO_EXTENSIONS):
                    return self.build_result(song, "Internet Archive", page_url, html, href, "downloadable", "Direct audio link found.")
            return self.build_result(song, "Internet Archive", page_url, html, None, "page_found", "Archive page found.")
        except Exception as e:
            return SearchResult(song, "Internet Archive", page_url, None, "error", f"Archive error: {e}")

    def find_jamendo(self, song: str, page_url: str) -> SearchResult:
        try:
            html = self.fetch(page_url).text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links_from_html(page_url, html)
            if direct_links:
                return self.build_result(song, "Jamendo", page_url, html, direct_links[0], "downloadable", "Direct audio link found.")
            if "free download" in text or "download" in text or "royalty free" in text:
                return self.build_result(song, "Jamendo", page_url, html, None, "page_found", "Legal page found.")
            return self.build_result(song, "Jamendo", page_url, html, None, "not_sure", "Page found but download not confirmed.")
        except Exception as e:
            return SearchResult(song, "Jamendo", page_url, None, "error", f"Jamendo error: {e}")

    def find_pixabay(self, song: str, page_url: str) -> SearchResult:
        try:
            html = self.fetch(page_url).text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
            direct_links = self.extract_direct_audio_links_from_html(page_url, html)
            if direct_links:
                return self.build_result(song, "Pixabay Music", page_url, html, direct_links[0], "downloadable", "Direct audio link found.")
            if "free download" in text or "music" in text:
                return self.build_result(song, "Pixabay Music", page_url, html, None, "page_found", "Legal page found.")
            return self.build_result(song, "Pixabay Music", page_url, html, None, "not_sure", "Page found but download not confirmed.")
        except Exception as e:
            return SearchResult(song, "Pixabay Music", page_url, None, "error", f"Pixabay error: {e}")

    def inspect_candidate(self, song: str, source_name: str, page_url: str) -> SearchResult:
        lowered = source_name.lower()
        if "bandcamp" in lowered: return self.find_bandcamp(song, page_url)
        if "internet archive" in lowered: return self.find_archive(song, page_url)
        if "jamendo" in lowered: return self.find_jamendo(song, page_url)
        if "pixabay" in lowered: return self.find_pixabay(song, page_url)
        return SearchResult(song, source_name, page_url, None, "unsupported", "Unsupported source.")

    @staticmethod
    def guess_extension_from_response(response: requests.Response, url: str) -> str:
        ct = (response.headers.get("Content-Type") or "").lower(); ul = url.lower()
        if ".flac" in ul or "flac" in ct: return ".flac"
        if ".ogg" in ul or "ogg" in ct: return ".ogg"
        if ".wav" in ul or "wav" in ct: return ".wav"
        if ".m4a" in ul or "m4a" in ct or "mp4" in ct: return ".m4a"
        return ".mp3"

    def download_file(self, url: str, song_name: str) -> Path:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=60); r.raise_for_status()
        path = self.download_dir / f"{self.safe_filename(song_name)}{self.guess_extension_from_response(r, url)}"
        with path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 128):
                if chunk: f.write(chunk)
        return path

    def is_relevant_enough(self, result: SearchResult) -> bool:
        if result.status == "downloadable": return result.score >= self.min_downloadable_score
        if result.status == "page_found": return result.score >= self.min_page_score
        if result.status == "not_sure": return result.score >= max(self.min_page_score, 0.62)
        return False

    def progress_prefix(self, index: int, total: int) -> str:
        width = 24; done = int((index / max(total, 1)) * width)
        return f"[{index}/{total}] [{'#' * done}{'-' * (width - done)}]"

    def search_song(self, song: str) -> SearchResult:
        fallback = None; best_seen = None; seen_urls = set()
        variants = self.build_query_variants(song); self.vlog(f"variants: {', '.join(variants[:6])}")
        for variant in variants:
            for target in self.search_targets:
                query = target["query"].format(query=variant); self.vlog(f"search: {target['name']} | query={query}")
                try:
                    urls = self.duckduckgo_search(query); self.vlog(f"results: {len(urls)}")
                except Exception as e:
                    self.log_error(f"[SEARCH ERROR] {song} | {target['name']} | {e}"); continue
                for url in urls:
                    if url in seen_urls: continue
                    seen_urls.add(url)
                    try:
                        result = self.inspect_candidate(song, target["name"], url); result.matched_query = variant
                        self.vlog(f"candidate: source={result.source_name} score={result.score:.3f} status={result.status} title={result.candidate_title[:80]}")
                        if best_seen is None or result.score > best_seen.score: best_seen = result
                        if result.status == "downloadable" and self.is_relevant_enough(result): return result
                        if result.status == "page_found" and self.is_relevant_enough(result):
                            if fallback is None or result.score > fallback.score: fallback = result
                    except Exception as e:
                        self.log_error(f"[INSPECT ERROR] {song} | {url} | {e}")
                    time.sleep(self.delay)
        if fallback: return fallback
        if best_seen and best_seen.score >= self.min_best_seen_score:
            best_seen.note += " Best relevance match."; return best_seen
        return SearchResult(song, "", "", None, "not_found", "Allowed source not found.", score=0.0)

    def save_report(self, rows: List[dict]) -> None:
        fields = ["song", "source", "status", "score", "matched_query", "candidate_title", "page_url", "direct_download_url", "saved_file", "note"]
        with self.report_file.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        if HAS_XLSX:
            wb = Workbook(); ws = wb.active; ws.title = "report"; ws.append(fields)
            for row in rows: ws.append([row.get(col, "") for col in fields])
            wb.save(self.report_xlsx)

    def save_duplicates(self, removed_duplicates: List[Tuple[str, str, str]]) -> None:
        with self.duplicates_file.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f); writer.writerow(["raw_song", "matched_song", "reason"]); writer.writerows(removed_duplicates)

    def print_summary(self, total_unique: int, duplicate_count: int) -> None:
        print("-" * 72); print(c("SUMMARY", T.BOLD, self.use_color))
        print(f"unique songs processed : {total_unique}")
        print(f"duplicates skipped     : {duplicate_count}")
        print(f"downloaded             : {self.stats['downloaded']}")
        print(f"page found             : {self.stats['page_found']}")
        print(f"not found              : {self.stats['not_found']}")
        print(f"download errors        : {self.stats['download_error']}")
        print(f"errors                 : {self.stats['errors']}")
        if self.stats['other']: print(f"other                  : {self.stats['other']}")
        print("-" * 72)
        print(f"report csv   : {self.report_file}")
        if HAS_XLSX: print(f"report xlsx  : {self.report_xlsx}")
        if duplicate_count: print(f"duplicates   : {self.duplicates_file}")
        print(f"downloads    : {self.download_dir}")
        print(f"runtime log  : {self.runtime_log}")
        if self.error_log.exists(): print(f"errors log   : {self.error_log}")

    def run(self, songs: List[str]) -> int:
        self.ensure_dirs(); self.start_runtime_session()
        report_rows = []; original_count = len(songs); songs, removed_duplicates = self.dedupe_songs(songs)
        print(c(f"LEGAL MUSIC CLI v{VERSION}", T.BOLD, self.use_color))
        print(f"input rows             : {original_count}")
        print(f"unique after cleanup   : {len(songs)}")
        print(f"active sources         : {', '.join(x['name'] for x in self.search_targets)}")
        print(f"mode                   : {'dry-run' if self.dry_run else 'download'}")
        if removed_duplicates:
            self.warn(f"duplicates skipped     : {len(removed_duplicates)}")
            for raw_song, matched_song, reason in removed_duplicates[:10]: print(f"  ~ {raw_song} -> {matched_song} [{reason}]")
            if len(removed_duplicates) > 10: print(f"  ... and {len(removed_duplicates) - 10} more")
            self.save_duplicates(removed_duplicates)
        print("-" * 72)
        total = len(songs)
        for index, song in enumerate(songs, start=1):
            print(c(f"{self.progress_prefix(index, total)} {song}", T.BLUE, self.use_color)); result = self.search_song(song); saved_file = ""
            if result.status == "downloadable" and result.direct_download_url:
                if self.dry_run:
                    self.stats["downloaded"] += 1; self.ok(f"  ✔ downloadable found | score={result.score:.2f}")
                    if self.verbose: self.vlog(f"direct url: {result.direct_download_url}")
                else:
                    try:
                        downloaded = self.download_file(result.direct_download_url, song); saved_file = str(downloaded); self.stats["downloaded"] += 1
                        self.ok(f"  ✔ downloaded | score={result.score:.2f} | {downloaded.name}")
                    except Exception as e:
                        result.status = "download_error"; result.note = f"Download error: {e}"; self.stats["download_error"] += 1
                        self.log_error(f"[DOWNLOAD ERROR] {song} | {result.direct_download_url} | {e}"); self.err(f"  ✖ download error | {e}")
            elif result.status == "page_found":
                self.stats["page_found"] += 1; self.warn(f"  • legal page found | score={result.score:.2f}")
            elif result.status == "not_found":
                self.stats["not_found"] += 1; self.warn("  - no allowed source found")
            elif result.status in {"error", "download_error"}:
                self.stats["errors"] += 1; self.err(f"  ✖ error | {result.note}")
            else:
                self.stats["other"] += 1; self.warn(f"  - status={result.status} | score={result.score:.2f}")
            report_rows.append({"song": song, "source": result.source_name, "status": result.status, "score": f"{result.score:.3f}", "matched_query": result.matched_query, "candidate_title": result.candidate_title, "page_url": result.page_url, "direct_download_url": result.direct_download_url or "", "saved_file": saved_file, "note": result.note})
            time.sleep(self.delay)
        self.save_report(report_rows); self.print_summary(len(songs), len(removed_duplicates)); return 0



def clean_song_name(name: str) -> str:
    """Public helper used by tests and callers."""
    return LegalMusicFinder.normalize_song_name(name)


def generate_search_variants(song: str) -> List[str]:
    """Public helper used by tests and callers."""
    return LegalMusicFinder.build_query_variants(song)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Find and optionally download music only from allowed sources.", epilog=LONG_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="search and optionally download", epilog=LONG_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    run_cmd.add_argument("-i", "--input", default=str(default_config_dir() / DEFAULT_INPUT_FILE), help="path to songs list")
    run_cmd.add_argument("-o", "--output", default=str(default_output_dir()), help="output directory")
    run_cmd.add_argument("-c", "--config", default=str(default_config_dir() / DEFAULT_CONFIG_FILE), help="path to config.json")
    run_cmd.add_argument("--delay", type=float, default=1.2, help="delay between requests")
    run_cmd.add_argument("--max-results", type=int, default=8, help="max search results per source")
    run_cmd.add_argument("-v", "--verbose", action="store_true", help="verbose logs")
    run_cmd.add_argument("--no-color", action="store_true", help="disable colored output")
    run_cmd.add_argument("--dry-run", action="store_true", help="do not download files, only check matches")

    init_cmd = sub.add_parser("init", help="create default songs.txt and config.json")
    init_cmd.add_argument("-i", "--input", default=str(default_config_dir() / DEFAULT_INPUT_FILE), help="where to create songs.txt")
    init_cmd.add_argument("-c", "--config", default=str(default_config_dir() / DEFAULT_CONFIG_FILE), help="where to create config.json")

    stats_cmd = sub.add_parser("stats", help="show local result statistics")
    stats_cmd.add_argument("-o", "--output", default=str(default_output_dir()), help="output directory")

    backup_cmd = sub.add_parser("backup-config", help="create timestamped backup of config and songs")
    backup_cmd.add_argument("-i", "--input", default=str(default_config_dir() / DEFAULT_INPUT_FILE), help="songs file path")
    backup_cmd.add_argument("-c", "--config", default=str(default_config_dir() / DEFAULT_CONFIG_FILE), help="config file path")

    reset_cmd = sub.add_parser("reset-config", help="reset songs.txt and config.json to defaults")
    reset_cmd.add_argument("-i", "--input", default=str(default_config_dir() / DEFAULT_INPUT_FILE), help="songs file path")
    reset_cmd.add_argument("-c", "--config", default=str(default_config_dir() / DEFAULT_CONFIG_FILE), help="config file path")

    sub.add_parser("sources", help="show supported sources")
    sub.add_parser("config-paths", help="show default config/data/output paths")
    sub.add_parser("doctor", help="check installation and folders")
    sub.add_parser("version", help="show version")

    comp_cmd = sub.add_parser("shell-completion", help="print shell completion script")
    comp_cmd.add_argument("shell", choices=["bash", "zsh"], help="shell type")

    upd_cmd = sub.add_parser("self-update", help="show self-update guidance")
    upd_cmd.add_argument("--check-only", action="store_true", help="show current install metadata only")
    return parser

def cmd_init(input_path: Path, config_path: Path) -> int:
    LegalMusicFinder.create_default_songs(input_path); LegalMusicFinder.create_default_config(config_path)
    print(f"Created songs file : {input_path}"); print(f"Created config file: {config_path}"); return 0

def cmd_sources() -> int:
    print("Supported sources:")
    for item in DEFAULT_SEARCH_TARGETS: print(f"- {item['name']} [{'ON' if item.get('enabled', True) else 'OFF'}]")
    return 0

def cmd_config_paths() -> int:
    print(f"os            : {os_name()}")
    print(f"config dir    : {default_config_dir()}")
    print(f"data dir      : {default_data_dir()}")
    print(f"default input : {default_config_dir() / DEFAULT_INPUT_FILE}")
    print(f"default config: {default_config_dir() / DEFAULT_CONFIG_FILE}")
    print(f"default output: {default_output_dir()}")
    print(f"runtime log   : {default_runtime_log()}")
    return 0

def cmd_doctor() -> int:
    print(f"LEGAL MUSIC DOCTOR v{VERSION}")
    print(f"python        : {sys.executable}")
    print(f"os            : {os_name()}")
    print(f"config dir    : {default_config_dir()}")
    print(f"data dir      : {default_data_dir()}")
    print(f"output dir    : {default_output_dir()}")
    print(f"runtime log   : {default_runtime_log()}")
    print(f"xlsx support  : {'yes' if HAS_XLSX else 'no'}")
    print(f"config exists : {'yes' if (default_config_dir() / DEFAULT_CONFIG_FILE).exists() else 'no'}")
    print(f"songs exists  : {'yes' if (default_config_dir() / DEFAULT_INPUT_FILE).exists() else 'no'}")
    return 0

def cmd_version() -> int:
    print(VERSION); return 0

def cmd_shell_completion(shell: str) -> int:
    print(BASH_COMPLETION if shell == "bash" else ZSH_COMPLETION); return 0

def cmd_self_update(check_only: bool) -> int:
    print(f"legal-music version: {VERSION}")
    install_meta = default_data_dir() / "install-meta.json"
    if install_meta.exists():
        print(f"install meta  : {install_meta}")
    print("Self-update is packaged as a reinstall workflow.")
    if check_only:
        print("Check-only mode: no changes made."); return 0
    print("To update:")
    print("  1) Download the latest package.")
    print("  2) Run installer again or pip install --upgrade .")
    print("  3) Verify with: legal-music version")
    return 0

def cmd_stats(output_dir: Path) -> int:
    report = output_dir / "report.csv"
    duplicates = output_dir / "duplicates.csv"
    downloads = output_dir / "downloads"
    print("LEGAL MUSIC STATS")
    print(f"output dir    : {output_dir}")
    print(f"report exists : {'yes' if report.exists() else 'no'}")
    print(f"dupes exists  : {'yes' if duplicates.exists() else 'no'}")
    print(f"downloads dir : {'yes' if downloads.exists() else 'no'}")
    if report.exists():
        with report.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        total = len(rows)
        counts = {}
        for row in rows:
            counts[row.get("status", "unknown")] = counts.get(row.get("status", "unknown"), 0) + 1
        print(f"report rows   : {total}")
        for k in sorted(counts):
            print(f"{k:14}: {counts[k]}")
    if downloads.exists():
        files = [p for p in downloads.iterdir() if p.is_file()]
        print(f"download files: {len(files)}")
    return 0

def cmd_backup_config(input_path: Path, config_path: Path) -> int:
    backup_dir = default_config_dir() / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    if config_path.exists():
        shutil.copy2(config_path, backup_dir / config_path.name); copied += 1
    if input_path.exists():
        shutil.copy2(input_path, backup_dir / input_path.name); copied += 1
    print(f"backup dir    : {backup_dir}")
    print(f"files copied  : {copied}")
    return 0

def cmd_reset_config(input_path: Path, config_path: Path) -> int:
    LegalMusicFinder.create_default_songs(input_path)
    LegalMusicFinder.create_default_config(config_path)
    print(f"reset songs   : {input_path}")
    print(f"reset config  : {config_path}")
    return 0

def main() -> int:
    parser = build_parser(); args = parser.parse_args()
    if args.command == "init": return cmd_init(Path(args.input).expanduser(), Path(args.config).expanduser())
    if args.command == "sources": return cmd_sources()
    if args.command == "config-paths": return cmd_config_paths()
    if args.command == "doctor": return cmd_doctor()
    if args.command == "version": return cmd_version()
    if args.command == "shell-completion": return cmd_shell_completion(args.shell)
    if args.command == "self-update": return cmd_self_update(args.check_only)
    if args.command == "stats": return cmd_stats(Path(args.output).expanduser())
    if args.command == "backup-config": return cmd_backup_config(Path(args.input).expanduser(), Path(args.config).expanduser())
    if args.command == "reset-config": return cmd_reset_config(Path(args.input).expanduser(), Path(args.config).expanduser())
    if args.command == "run":
        try:
            cfg = LegalMusicFinder.load_config(Path(args.config).expanduser())
        except Exception as e:
            print(f"Config read error: {e}"); return 1
        finder = LegalMusicFinder(
            output_dir=Path(args.output).expanduser(),
            search_targets=cfg.get("search_targets", DEFAULT_SEARCH_TARGETS),
            delay=args.delay, max_results=args.max_results, verbose=args.verbose, no_color=args.no_color, dry_run=args.dry_run,
            min_downloadable_score=float(cfg.get("min_downloadable_score", 0.40)),
            min_page_score=float(cfg.get("min_page_score", 0.52)),
            min_best_seen_score=float(cfg.get("min_best_seen_score", 0.55)),
        )
        try:
            songs = finder.read_song_list(Path(args.input).expanduser())
        except Exception as e:
            print(f"Input error: {e}"); print("Run 'legal-music init' to create default files."); return 1
        return finder.run(songs)
    parser.print_help(); return 1
