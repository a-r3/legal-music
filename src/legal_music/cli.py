"""Command-line interface for legal-music."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import ALL_SOURCE_NAMES, SOURCE_PRESETS, AppConfig
from .constants import VERSION
from .downloader import download_file
from .logging_utils import Printer
from .models import DuplicateEntry, RunStats, SearchResult, SongStatus
from .playlist import read_playlist, read_playlists_dir, write_example_playlist
from .reports import (
    HAS_XLSX,
    format_elapsed,
    print_summary,
    save_csv,
    save_duplicates_csv,
    save_errors_log,
    save_summary_json,
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
    run_started = time.time()
    p = Printer(color=not no_color, verbose=verbose)
    engine = SearchEngine(cfg, printer=p)
    engine.set_run_context(len(songs))

    downloads_dir = output_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Deduplication
    unique_songs, removed = dedupe_songs(songs)
    duplicates = [DuplicateEntry(r, m, reason) for r, m, reason in removed]

    stats = RunStats(total=len(unique_songs), duplicates=len(duplicates))

    search_mode = "maximize" if cfg.maximize_mode else "fast" if cfg.fast_mode else "balanced"
    mode_label = "dry-run" if dry_run else "download"
    p.bold(f"\nLEGAL MUSIC v{VERSION}  |  {playlist_name}  [{mode_label} / {search_mode}]")
    p.info(f"songs                  : {len(unique_songs)} unique  ({len(songs)} input)")
    p.info(f"sources                : {', '.join(cfg.enabled_source_names())}")

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
        song_started = time.time()
        if verbose:
            p.vlog(f"searching: {song}")
        result = engine.search_song(song)
        song_elapsed = time.time() - song_started
        phase_tag = " [B]" if result.resolved_phase == "phase_b" else ""
        t = f"{song_elapsed:.1f}s"

        if result.status == SongStatus.DOWNLOADED and result.direct_url:
            if dry_run:
                stats.downloaded += 1
                p.ok(_format_song_line(idx, total, song, f"✓ {result.source}  score={result.score:.2f}{phase_tag}  {t}"))
                if verbose and result.matched_query:
                    p.dim(f"    {result.result_tier.value}  query={result.matched_query_kind or 'raw'}")
                    p.dim(f"    {result.direct_url}")
            else:
                try:
                    saved = download_file(
                        result.direct_url, song, downloads_dir, engine.session
                    )
                    result.saved_file = str(saved)
                    stats.downloaded += 1
                    p.ok(_format_song_line(idx, total, song, f"✓ {saved.name}  score={result.score:.2f}{phase_tag}  {t}"))
                    if verbose and result.matched_query:
                        p.dim(f"    {result.result_tier.value}  query={result.matched_query_kind or 'raw'}")
                except Exception as e:
                    result.status = SongStatus.DOWNLOAD_ERROR
                    result.note = f"Download error: {e}"
                    stats.download_error += 1
                    err_msg = f"[DOWNLOAD ERROR] {song} | {result.direct_url} | {e}"
                    errors.append(err_msg)
                    p.err(_format_song_line(idx, total, song, f"! download error  {t}"))

        elif result.status == SongStatus.PAGE_FOUND:
            stats.page_found += 1
            fallback_tag = " [fallback]" if result.fallback_used else ""
            p.warn(_format_song_line(idx, total, song, f"~ {result.source}  score={result.score:.2f}{phase_tag}{fallback_tag}  {t}"))
            if verbose and result.matched_query:
                p.dim(f"    {result.result_tier.value}  query={result.matched_query_kind or 'raw'}")
            if verbose and result.page_url:
                p.dim(f"    {result.page_url}")

        elif result.status == SongStatus.BLOCKED:
            stats.blocked += 1
            p.warn(_format_song_line(idx, total, song, f"blocked {result.source}  {t}"))

        elif result.status == SongStatus.NOT_FOUND:
            stats.not_found += 1
            best_tag = f"  best={result.best_seen_score:.2f}@{result.best_seen_source}" if result.best_seen_score else ""
            p.dim(_format_song_line(idx, total, song, f"- not found{best_tag}  {t}"))

        elif result.status in (SongStatus.ERROR, SongStatus.DOWNLOAD_ERROR):
            stats.errors += 1
            errors.append(f"[ERROR] {song} | {result.note}")
            p.err(_format_song_line(idx, total, song, f"! error  {t}"))

        if result.status in {SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND}:
            if result.resolved_phase == "phase_a":
                stats.phase_a_wins += 1
            elif result.resolved_phase == "phase_b":
                stats.phase_b_wins += 1

        results.append(result)
        time.sleep(cfg.delay)

    stats.elapsed_seconds = time.time() - run_started
    stats.avg_seconds_per_song = stats.elapsed_seconds / max(1, stats.total)
    useful_results = stats.downloaded + stats.page_found
    stats.avg_seconds_per_success = stats.elapsed_seconds / useful_results if useful_results else 0.0

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

    engine.save_caches()

    paths: dict[str, Path | None] = {
        "csv report": output_dir / "report.csv" if cfg.csv_report else None,
        "xlsx report": xlsx_path,
        "run summary": output_dir / "summary.json",
        "duplicates": dup_path,
        "errors log": err_path,
        "downloads": downloads_dir if not dry_run else None,
    }
    print_summary(stats, paths, use_color=not no_color)

    rescued_by_fallback = sum(1 for r in results if r.fallback_used and r.status in {SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND})
    source_successes: dict[str, int] = {}
    query_successes: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    bandcamp_fallback_wins = 0
    for result in results:
        if result.status in {SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND}:
            if result.source:
                source_successes[result.source] = source_successes.get(result.source, 0) + 1
            if result.matched_query_kind:
                query_successes[result.matched_query_kind] = query_successes.get(result.matched_query_kind, 0) + 1
            tier_counts[result.result_tier.value] = tier_counts.get(result.result_tier.value, 0) + 1
            if result.source == "Bandcamp" and result.status == SongStatus.PAGE_FOUND:
                bandcamp_fallback_wins += 1

    if verbose and (source_successes or query_successes or rescued_by_fallback):
        p.info("")
        p.dim("Recall summary:")
        if rescued_by_fallback:
            p.dim(f"  rescued by fallback   : {rescued_by_fallback}")
        if bandcamp_fallback_wins:
            p.dim(f"  bandcamp page wins    : {bandcamp_fallback_wins}")
        for source, count in sorted(source_successes.items(), key=lambda item: (-item[1], item[0])):
            p.dim(f"  source success        : {source} = {count}")
        for kind, count in sorted(query_successes.items(), key=lambda item: (-item[1], item[0]))[:6]:
            p.dim(f"  query success         : {kind} = {count}")
        for tier, count in sorted(tier_counts.items(), key=lambda item: item[0]):
            p.dim(f"  result tier           : {tier} = {count}")

    if verbose and engine.run_context.sources:
        p.info("")
        p.dim("Runtime summary:")
        for src, metric in sorted(
            engine.run_context.sources.items(),
            key=lambda item: (-item[1].usefulness_score, item[0]),
        ):
            useful_rate = metric.useful_count / max(1, metric.search_attempts)
            p.dim(
                "  "
                f"{src}: usefulness={metric.usefulness_score:.2f} "
                f"avg_search={metric.avg_search_latency:.2f}s "
                f"time={metric.total_time:.1f}s "
                f"useful_rate={useful_rate:.2f} "
                f"downloads={metric.downloaded_count} "
                f"pages={metric.page_found_count} "
                f"weak_page_ratio={metric.low_value_page_ratio:.2f} "
                f"cache_hits={metric.cached_hits} "
                f"redundant_skips={metric.skipped_redundant}"
            )

    if verbose and engine.phase_metrics:
        p.info("")
        p.dim("Phase summary:")
        for phase_name, phase in engine.phase_metrics.items():
            p.dim(
                "  "
                f"{phase_name}: songs={phase['songs']} "
                f"downloads={phase['downloads']} "
                f"pages={phase['pages']} "
                f"time={phase['time']:.1f}s"
            )

    # Show source health status if any issues
    health_status = {
        src: engine.run_context.get_source_health(src)
        for src in engine.run_context.sources.keys()
    }
    if verbose and any(h.value != "healthy" for h in health_status.values()):
        p.info("")
        p.dim("Source health summary:")
        for src, health in health_status.items():
            metric = engine.run_context.sources[src]
            status_sym = "✓" if health.value == "healthy" else "⚠" if health.value == "degraded" else "✗"
            p.dim(f"  {status_sym} {src}: {health.value} (ok={metric.success_count}, timeout={metric.timeout_count}, blocked={metric.blocked_count})")

    source_summary = {
        src: {
            "health": metric.health.value,
            "search_attempts": metric.search_attempts,
            "inspect_attempts": metric.inspect_attempts,
            "useful_count": metric.useful_count,
            "downloaded_count": metric.downloaded_count,
            "page_found_count": metric.page_found_count,
            "weak_page_count": metric.weak_page_count,
            "low_value_page_ratio": round(metric.low_value_page_ratio, 3),
            "cache_hits": metric.cached_hits,
            "redundant_skips": metric.skipped_redundant,
            "avg_search_latency": round(metric.avg_search_latency, 3),
            "avg_inspect_latency": round(metric.avg_inspect_latency, 3),
            "time_spent": round(metric.total_time, 3),
            "usefulness_score": round(metric.usefulness_score, 3),
            "query_metrics": {
                kind: {
                    "attempts": q.attempts,
                    "cache_hits": q.cache_hits,
                    "zero_results": q.zero_results,
                    "useful_hits": q.useful_hits,
                    "avg_latency": round(q.avg_latency, 3),
                    "usefulness": round(q.usefulness, 3),
                    "redundant_skips": q.skipped_redundant,
                }
                for kind, q in metric.query_metrics.items()
            },
        }
        for src, metric in engine.run_context.sources.items()
    }
    summary = {
        "playlist": playlist_name,
        "mode": "dry-run" if dry_run else "download",
        "profile": search_mode,
        "stats": stats.__dict__,
        "elapsed_seconds": round(stats.elapsed_seconds, 3),
        "elapsed_human": format_elapsed(stats.elapsed_seconds),
        "avg_seconds_per_song": round(stats.avg_seconds_per_song, 3),
        "avg_seconds_per_success": round(stats.avg_seconds_per_success, 3),
        "phase_a_wins": stats.phase_a_wins,
        "phase_b_wins": stats.phase_b_wins,
        "rescued_by_fallback": rescued_by_fallback,
        "bandcamp_page_wins": bandcamp_fallback_wins,
        "source_successes": source_successes,
        "query_successes": query_successes,
        "tier_counts": tier_counts,
        "source_runtime": source_summary,
        "phase_runtime": engine.phase_metrics,
    }
    save_summary_json(summary, output_dir / "summary.json")

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

    # DuckDuckGo connectivity check (optional, not critical)
    try:
        import requests as req

        r = req.get("https://html.duckduckgo.com/html/?q=test", timeout=5)
        r.raise_for_status()
        p.ok("  ok  DuckDuckGo connectivity")
    except Exception as e:
        p.warn(f"  DuckDuckGo unreachable (optional): {e}")

    # Internet Archive API check (critical)
    try:
        import requests as req

        r = req.get("https://archive.org/advancedsearch.php?q=test&rows=1&output=json", timeout=5)
        r.raise_for_status()
        p.ok("  ok  Internet Archive API")
    except Exception as e:
        p.err(f"  Internet Archive API unreachable: {e}")
        all_ok = False

    p.separator()
    if all_ok:
        p.ok("All critical checks passed.")
    else:
        p.warn("Some critical checks failed. See above.")
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
    p = Printer(color=not getattr(args, "no_color", False))

    action = getattr(args, "src_action", None)
    name = getattr(args, "src_name", None)

    if action is None:
        # List sources with preset reference
        p.bold("Sources:")
        for s in cfg.sources:
            marker = "+" if s.enabled else "-"
            p.info(f"  [{marker}] {s.name}")
        p.info("")
        p.dim("Presets  : fast (IA only) | balanced (IA+FMA+Bandcamp) | maximize (all)")
        p.dim("Commands : legal-music src enable NAME")
        p.dim("           legal-music src disable NAME")
        p.dim("           legal-music src preset PRESET")
        return 0

    if not name:
        p.err(f"Error: 'src {action}' requires a name argument.")
        return 1

    if action == "enable":
        src = cfg.find_source(name)
        if src is None:
            p.err(f"Unknown source: {name!r}")
            p.info(f"Known sources: {', '.join(ALL_SOURCE_NAMES)}")
            return 1
        was_enabled = src.enabled
        src.enabled = True
        cfg.save(cfg_path)
        if was_enabled:
            p.info(f"  {src.name} was already enabled")
        else:
            p.ok(f"  enabled: {src.name}")
        p.dim(f"  saved: {cfg_path}")
        return 0

    if action == "disable":
        src = cfg.find_source(name)
        if src is None:
            p.err(f"Unknown source: {name!r}")
            p.info(f"Known sources: {', '.join(ALL_SOURCE_NAMES)}")
            return 1
        was_enabled = src.enabled
        src.enabled = False
        cfg.save(cfg_path)
        if not was_enabled:
            p.info(f"  {src.name} was already disabled")
        else:
            p.warn(f"  disabled: {src.name}")
        p.dim(f"  saved: {cfg_path}")
        return 0

    if action == "preset":
        try:
            enabled_names = cfg.apply_source_preset(name)
        except ValueError as exc:
            p.err(f"Error: {exc}")
            choices = ", ".join(SOURCE_PRESETS.keys())
            p.info(f"Available presets: {choices}")
            return 1
        cfg.save(cfg_path)
        p.bold(f"Preset applied: {name}")
        for src in cfg.sources:
            marker = "+" if src.enabled else "-"
            p.info(f"  [{marker}] {src.name}")
        p.dim(f"  saved: {cfg_path}")
        _ = enabled_names  # used implicitly via cfg.sources
        return 0

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
    batch_started = time.time()
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
        total_stats.blocked += stats.blocked
        total_stats.download_error += stats.download_error
        total_stats.errors += stats.errors
        total_stats.duplicates += stats.duplicates
        total_stats.total += stats.total

    p.separator()
    p.bold("BATCH COMPLETE")
    p.info(f"playlists processed    : {len(playlists)}")
    p.info(f"total songs processed  : {total_stats.total}")
    p.ok(f"total downloaded       : {total_stats.downloaded}") if total_stats.downloaded else None
    p.warn(f"total page found       : {total_stats.page_found}") if total_stats.page_found else None
    p.info(f"total not found        : {total_stats.not_found}")
    if total_stats.errors:
        p.err(f"total errors           : {total_stats.errors}")
    batch_elapsed = time.time() - batch_started
    p.info(f"elapsed time           : {format_elapsed(batch_elapsed)}")
    p.info(f"avg per playlist       : {batch_elapsed / max(1, len(playlists)):.1f}s")
    p.info(f"avg per song           : {batch_elapsed / max(1, total_stats.total):.1f}s")

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
    sources: dict[str, int] = {}
    query_kinds: dict[str, int] = {}
    rescued = 0
    borderline = 0
    for row in rows:
        s = row.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
        if row.get("source"):
            sources[row["source"]] = sources.get(row["source"], 0) + 1
        if row.get("matched_query_kind"):
            query_kinds[row["matched_query_kind"]] = query_kinds.get(row["matched_query_kind"], 0) + 1
        if row.get("fallback_used") == "yes":
            rescued += 1
        if s == "not_found" and row.get("best_seen_source"):
            borderline += 1

    p.bold(f"Stats from: {report_path}")
    p.info(f"total entries          : {len(rows)}")
    for status, count in sorted(counts.items(), key=lambda x: -x[1]):
        p.info(f"  {status:<22} : {count}")
    if rescued:
        p.info(f"  rescued_by_fallback     : {rescued}")
    if borderline:
        p.info(f"  borderline_not_found    : {borderline}")
    for source, count in sorted(sources.items(), key=lambda x: (-x[1], x[0]))[:6]:
        p.info(f"  source:{source:<15} : {count}")
    for kind, count in sorted(query_kinds.items(), key=lambda x: (-x[1], x[0]))[:6]:
        p.info(f"  query:{kind:<16} : {count}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_output_dir(args: argparse.Namespace, cfg: AppConfig, playlist_path: Path) -> Path:
    if hasattr(args, "output") and args.output:
        return Path(args.output)
    return cfg.output_dir / playlist_path.stem


def _compact_song(song: str, width: int = 46) -> str:
    clean = " ".join(song.split())
    if len(clean) <= width:
        return clean
    return f"{clean[: width - 1]}…"


def _format_song_line(index: int, total: int, song: str, outcome: str) -> str:
    return f"[{index}/{total}] {_compact_song(song)} | {outcome}"


def _apply_cfg_overrides(cfg: AppConfig, args: argparse.Namespace) -> None:
    if hasattr(args, "fast") and args.fast:
        cfg.apply_fast_mode()
    if hasattr(args, "maximize") and args.maximize:
        cfg.apply_maximize_mode()
    if hasattr(args, "delay") and args.delay is not None:
        cfg.delay = args.delay
    if hasattr(args, "max_results") and args.max_results is not None:
        cfg.max_results = args.max_results


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_EPILOG = """\
Legal sources only: Bandcamp, Internet Archive, Free Music Archive, Jamendo, Pixabay Music.
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
    (("--fast",), dict(action="store_true", help="fast mode: fewer variants, lower timeouts")),
    (("--maximize",), dict(action="store_true", help="maximize recall mode: broader queries and fallback")),
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
    p_src = sub.add_parser(
        "src",
        help="list or manage sources (enable, disable, preset)",
        description=(
            "Manage search sources.\n\n"
            "  legal-music src                     list configured sources\n"
            "  legal-music src enable NAME         enable a source\n"
            "  legal-music src disable NAME        disable a source\n"
            "  legal-music src preset PRESET       apply a source preset\n\n"
            "Presets: fast (Internet Archive only), balanced (IA+FMA+Bandcamp), maximize (all)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_src.add_argument(
        "src_action",
        nargs="?",
        choices=["enable", "disable", "preset"],
        metavar="ACTION",
        help="enable | disable | preset",
    )
    p_src.add_argument(
        "src_name",
        nargs="?",
        metavar="NAME",
        help="source name or preset name",
    )
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
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        return args.func(args)
    except KeyboardInterrupt:
        print("\n\nRun cancelled by user.")
        return 130  # Standard exit code for Ctrl+C
