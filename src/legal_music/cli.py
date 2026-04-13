"""Command-line interface for legal-music."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import AppConfig
from .constants import VERSION
from .downloader import download_file
from .logging_utils import Printer
from .models import DuplicateEntry, RunStats, SearchResult, SongStatus
from .playlist import read_playlist, read_playlists_dir, write_example_playlist
from .reports import (
    HAS_XLSX,
    print_summary,
    save_csv,
    save_duplicates_csv,
    save_errors_log,
    save_xlsx,
)
from .search import SearchEngine, dedupe_songs
from .utils import default_config_dir, default_output_dir, default_playlists_dir

APP = "legal-music"
DEFAULT_CONFIG = default_config_dir() / "config.json"


# ---------------------------------------------------------------------------
# Core run logic
# ---------------------------------------------------------------------------


def _run_playlist(
    songs: list[str],
    playlist_name: str,
    cfg: AppConfig,
    output_dir: Path,
    dry_run: bool,
    verbose: bool,
    no_color: bool,
) -> RunStats:
    p = Printer(color=not no_color, verbose=verbose)
    engine = SearchEngine(cfg, printer=p)

    downloads_dir = output_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Deduplication
    unique_songs, removed = dedupe_songs(songs)
    duplicates = [DuplicateEntry(r, m, reason) for r, m, reason in removed]

    stats = RunStats(total=len(unique_songs), duplicates=len(duplicates))

    p.bold(f"\nLEGAL MUSIC v{VERSION}  |  {playlist_name}")
    p.info(f"input rows             : {len(songs)}")
    p.info(f"unique after cleanup   : {len(unique_songs)}")
    p.info(f"active sources         : {', '.join(cfg.enabled_source_names())}")
    p.info(f"mode                   : {'dry-run' if dry_run else 'download'}")

    if duplicates:
        p.warn(f"duplicates skipped     : {len(duplicates)}")
        for d in duplicates[:8]:
            p.dim(f"  ~ {d.raw_song!r} -> {d.matched_song!r} [{d.reason}]")
        if len(duplicates) > 8:
            p.dim(f"  ... and {len(duplicates) - 8} more")

    p.separator()

    results: list[SearchResult] = []
    errors: list[str] = []
    total = len(unique_songs)

    for idx, song in enumerate(unique_songs, 1):
        p.progress(idx, total, song)
        result = engine.search_song(song)

        if result.status == SongStatus.DOWNLOADED and result.direct_url:
            if dry_run:
                stats.downloaded += 1
                p.ok(f"  + downloadable found  | score={result.score:.2f} | {result.source}")
                p.vlog(f"direct url: {result.direct_url}")
            else:
                try:
                    saved = download_file(
                        result.direct_url, song, downloads_dir, engine.session
                    )
                    result.saved_file = str(saved)
                    stats.downloaded += 1
                    p.ok(f"  + downloaded          | score={result.score:.2f} | {saved.name}")
                except Exception as e:
                    result.status = SongStatus.DOWNLOAD_ERROR
                    result.note = f"Download error: {e}"
                    stats.download_error += 1
                    err_msg = f"[DOWNLOAD ERROR] {song} | {result.direct_url} | {e}"
                    errors.append(err_msg)
                    p.err(f"  x download error      | {e}")

        elif result.status == SongStatus.PAGE_FOUND:
            stats.page_found += 1
            p.warn(f"  o page found          | score={result.score:.2f} | {result.source}")
            if verbose and result.page_url:
                p.dim(f"    {result.page_url}")

        elif result.status == SongStatus.BLOCKED:
            stats.blocked += 1
            p.warn(f"  ! blocked             | {result.source}")

        elif result.status == SongStatus.NOT_FOUND:
            stats.not_found += 1
            p.dim("  - not found")

        elif result.status in (SongStatus.ERROR, SongStatus.DOWNLOAD_ERROR):
            stats.errors += 1
            errors.append(f"[ERROR] {song} | {result.note}")
            p.err(f"  x error               | {result.note}")

        results.append(result)
        time.sleep(cfg.delay)

    # Save reports
    if cfg.csv_report:
        csv_path = output_dir / "report.csv"
        save_csv(results, csv_path)

    xlsx_path: Path | None = None
    if cfg.xlsx_report and HAS_XLSX:
        xlsx_path = output_dir / "report.xlsx"
        save_xlsx(results, xlsx_path)

    dup_path: Path | None = None
    if duplicates:
        dup_path = output_dir / "duplicates.csv"
        save_duplicates_csv(duplicates, dup_path)

    err_path: Path | None = None
    if errors:
        err_path = output_dir / "errors.log"
        save_errors_log(errors, err_path)

    paths: dict[str, Path | None] = {
        "csv report": output_dir / "report.csv" if cfg.csv_report else None,
        "xlsx report": xlsx_path,
        "duplicates": dup_path,
        "errors log": err_path,
        "downloads": downloads_dir if not dry_run else None,
    }
    print_summary(stats, paths, use_color=not no_color)

    return stats


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config)
    playlists_dir = default_playlists_dir()
    output_dir = default_output_dir()

    p = Printer()
    p.bold(f"Initializing {APP}...")

    cfg = AppConfig()
    if not cfg_path.exists():
        cfg.save(cfg_path)
        p.ok(f"  created config      : {cfg_path}")
    else:
        p.info(f"  config exists       : {cfg_path}")

    playlists_dir.mkdir(parents=True, exist_ok=True)
    example = playlists_dir / "example.txt"
    write_example_playlist(example)
    p.ok(f"  playlists dir       : {playlists_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    p.ok(f"  output dir          : {output_dir}")

    p.info("")
    p.info("Next steps:")
    p.info(f"  1. Add playlists to  : {playlists_dir}")
    p.info("  2. Dry run           : legal-music dry <playlist.txt>")
    p.info("  3. Download          : legal-music dl <playlist.txt>")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import importlib

    p = Printer()
    p.bold(f"legal-music v{VERSION} doctor")
    p.separator()

    checks = [
        ("requests", "HTTP client"),
        ("bs4", "HTML parser (beautifulsoup4)"),
        ("openpyxl", "Excel report support"),
    ]
    all_ok = True
    for mod, desc in checks:
        try:
            importlib.import_module(mod)
            p.ok(f"  ok  {desc}")
        except ImportError:
            p.warn(f"  --  {desc} (not installed, optional)")

    # Config check
    cfg_path = Path(args.config)
    if cfg_path.exists():
        try:
            cfg = AppConfig.load(cfg_path)
            errs = cfg.validate()
            if errs:
                for e in errs:
                    p.err(f"  config error: {e}")
                all_ok = False
            else:
                p.ok(f"  ok  config at {cfg_path}")
        except Exception as e:
            p.err(f"  config parse error: {e}")
            all_ok = False
    else:
        p.warn(f"  no config at {cfg_path} (using defaults)")

    # DuckDuckGo connectivity
    try:
        import requests as req

        r = req.get("https://html.duckduckgo.com/html/?q=test", timeout=8)
        r.raise_for_status()
        p.ok("  ok  DuckDuckGo connectivity")
    except Exception as e:
        p.err(f"  DuckDuckGo unreachable: {e}")
        all_ok = False

    p.separator()
    if all_ok:
        p.ok("All checks passed.")
    else:
        p.warn("Some checks failed. See above.")
    return 0 if all_ok else 1


def cmd_version(args: argparse.Namespace) -> int:
    print(f"legal-music {VERSION}")
    return 0


def cmd_cfg(args: argparse.Namespace) -> int:
    import json

    cfg_path = Path(args.config)
    p = Printer()
    if not cfg_path.exists():
        p.warn(f"No config found at {cfg_path}. Using defaults.")
        cfg = AppConfig()
    else:
        cfg = AppConfig.load(cfg_path)

    p.bold(f"Config: {cfg_path}")
    print(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_src(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config)
    cfg = AppConfig.load(cfg_path) if cfg_path.exists() else AppConfig()
    p = Printer()
    p.bold("Configured sources:")
    for s in cfg.sources:
        status = "enabled" if s.enabled else "disabled"
        marker = "+" if s.enabled else "-"
        p.info(f"  [{marker}] {s.name}  ({status})")
    return 0


def cmd_dry(args: argparse.Namespace) -> int:
    playlist_path = Path(args.playlist)
    cfg_path = Path(args.config)
    cfg = AppConfig.load(cfg_path) if cfg_path.exists() else AppConfig()

    _apply_cfg_overrides(cfg, args)

    try:
        songs = read_playlist(playlist_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    output_dir = _resolve_output_dir(args, cfg, playlist_path)
    _run_playlist(
        songs,
        playlist_path.stem,
        cfg,
        output_dir,
        dry_run=True,
        verbose=getattr(args, "verbose", False),
        no_color=getattr(args, "no_color", False),
    )
    return 0


def cmd_dl(args: argparse.Namespace) -> int:
    playlist_path = Path(args.playlist)
    cfg_path = Path(args.config)
    cfg = AppConfig.load(cfg_path) if cfg_path.exists() else AppConfig()

    _apply_cfg_overrides(cfg, args)

    try:
        songs = read_playlist(playlist_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    output_dir = _resolve_output_dir(args, cfg, playlist_path)
    _run_playlist(
        songs,
        playlist_path.stem,
        cfg,
        output_dir,
        dry_run=False,
        verbose=getattr(args, "verbose", False),
        no_color=getattr(args, "no_color", False),
    )
    return 0


def cmd_batch_dry(args: argparse.Namespace) -> int:
    return _batch_run(args, dry_run=True)


def cmd_batch_dl(args: argparse.Namespace) -> int:
    return _batch_run(args, dry_run=False)


def _batch_run(args: argparse.Namespace, dry_run: bool) -> int:
    playlist_dir = Path(args.playlist_dir)
    cfg_path = Path(args.config)
    cfg = AppConfig.load(cfg_path) if cfg_path.exists() else AppConfig()

    _apply_cfg_overrides(cfg, args)

    try:
        playlists = read_playlists_dir(playlist_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    p = Printer(color=not getattr(args, "no_color", False))
    p.bold(f"Batch {'dry-run' if dry_run else 'download'}: {len(playlists)} playlist(s)")

    base_output = Path(args.output) if hasattr(args, "output") and args.output else cfg.output_dir
    total_stats = RunStats()

    for name, songs in playlists.items():
        p.cyan(f"\n=== Playlist: {name} ===")
        output_dir = base_output / name
        stats = _run_playlist(
            songs,
            name,
            cfg,
            output_dir,
            dry_run=dry_run,
            verbose=getattr(args, "verbose", False),
            no_color=getattr(args, "no_color", False),
        )
        total_stats.downloaded += stats.downloaded
        total_stats.page_found += stats.page_found
        total_stats.not_found += stats.not_found
        total_stats.errors += stats.errors
        total_stats.duplicates += stats.duplicates

    p.separator()
    p.bold("BATCH COMPLETE")
    p.info(f"playlists processed    : {len(playlists)}")
    p.ok(f"total downloaded       : {total_stats.downloaded}") if total_stats.downloaded else None
    p.warn(f"total page found       : {total_stats.page_found}") if total_stats.page_found else None
    p.info(f"total not found        : {total_stats.not_found}")
    if total_stats.errors:
        p.err(f"total errors           : {total_stats.errors}")

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    import csv as _csv

    target = Path(args.target) if hasattr(args, "target") and args.target else None
    p = Printer()

    if target and target.is_file():
        report_path = target
    elif target and target.is_dir():
        report_path = target / "report.csv"
    else:
        report_path = default_output_dir() / "report.csv"

    if not report_path.exists():
        p.warn(f"No report found at: {report_path}")
        p.info("Run a playlist first to generate a report.")
        return 1

    with report_path.open(encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))

    if not rows:
        p.warn("Report is empty.")
        return 1

    counts: dict[str, int] = {}
    for row in rows:
        s = row.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1

    p.bold(f"Stats from: {report_path}")
    p.info(f"total entries          : {len(rows)}")
    for status, count in sorted(counts.items(), key=lambda x: -x[1]):
        p.info(f"  {status:<22} : {count}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_output_dir(args: argparse.Namespace, cfg: AppConfig, playlist_path: Path) -> Path:
    if hasattr(args, "output") and args.output:
        return Path(args.output)
    return cfg.output_dir / playlist_path.stem


def _apply_cfg_overrides(cfg: AppConfig, args: argparse.Namespace) -> None:
    if hasattr(args, "delay") and args.delay is not None:
        cfg.delay = args.delay
    if hasattr(args, "max_results") and args.max_results is not None:
        cfg.max_results = args.max_results


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_EPILOG = """\
Legal sources only: Bandcamp, Internet Archive, Jamendo, Pixabay Music.
No piracy, no DRM bypass, no stream ripping.
"""

_COMMON_FLAGS = [
    (("-c", "--config"), dict(default=str(DEFAULT_CONFIG), help="path to config.json")),
    (("-v", "--verbose"), dict(action="store_true", help="verbose output")),
    (("--no-color",), dict(action="store_true", help="disable colored output")),
]

_RUN_FLAGS = [
    (("-o", "--output"), dict(default=None, help="output directory override")),
    (("--delay",), dict(type=float, default=None, help="delay between requests (seconds)")),
    (("--max-results",), dict(type=int, default=None, help="max search results per source")),
]


def _add_common(sub: argparse.ArgumentParser) -> None:
    for flags, kwargs in _COMMON_FLAGS:
        sub.add_argument(*flags, **kwargs)


def _add_run_flags(sub: argparse.ArgumentParser) -> None:
    for flags, kwargs in _RUN_FLAGS:
        sub.add_argument(*flags, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP,
        description="Find and download music from legal, permitted sources.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # init
    p_init = sub.add_parser("init", help="create default config and playlist dir")
    _add_common(p_init)
    p_init.set_defaults(func=cmd_init)

    # doctor
    p_doc = sub.add_parser("doctor", help="check dependencies and connectivity")
    _add_common(p_doc)
    p_doc.set_defaults(func=cmd_doctor)

    # version
    p_ver = sub.add_parser("version", help="show version")
    p_ver.set_defaults(func=cmd_version)

    # cfg
    p_cfg = sub.add_parser("cfg", help="show current configuration")
    _add_common(p_cfg)
    p_cfg.set_defaults(func=cmd_cfg)

    # src
    p_src = sub.add_parser("src", help="list configured sources")
    _add_common(p_src)
    p_src.set_defaults(func=cmd_src)

    # dry
    p_dry = sub.add_parser("dry", help="dry run for a single playlist (no download)")
    p_dry.add_argument("playlist", help="path to playlist .txt file")
    _add_common(p_dry)
    _add_run_flags(p_dry)
    p_dry.set_defaults(func=cmd_dry)

    # dl
    p_dl = sub.add_parser("dl", help="search and download from a single playlist")
    p_dl.add_argument("playlist", help="path to playlist .txt file")
    _add_common(p_dl)
    _add_run_flags(p_dl)
    p_dl.set_defaults(func=cmd_dl)

    # batch-dry
    p_bdry = sub.add_parser("batch-dry", help="dry run for all playlists in a directory")
    p_bdry.add_argument("playlist_dir", help="path to playlist directory")
    _add_common(p_bdry)
    _add_run_flags(p_bdry)
    p_bdry.set_defaults(func=cmd_batch_dry)

    # batch-dl
    p_bdl = sub.add_parser("batch-dl", help="download all playlists in a directory")
    p_bdl.add_argument("playlist_dir", help="path to playlist directory")
    _add_common(p_bdl)
    _add_run_flags(p_bdl)
    p_bdl.set_defaults(func=cmd_batch_dl)

    # stats
    p_stats = sub.add_parser("stats", help="show stats from a previous run report")
    p_stats.add_argument("target", nargs="?", help="path to report.csv or output dir")
    _add_common(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
