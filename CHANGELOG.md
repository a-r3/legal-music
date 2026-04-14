# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] — Phase 3 completion

### ✨ Features
- **Query variant management**: Better query generation and variant selection
- **Balanced vs Maximize modes**: `--maximize` for better recall, balanced as default
- **Smart source presets**: `balanced` (IA+FMA+Bandcamp), `maximize` (all sources), `fast` (IA only)
- **Report generation**: CSV and optional XLSX (color-coded) reports with source and score
- **Source management**: `legal-music src` command to list, enable, disable, or switch presets

### 🔧 Improvements
- Config/preset mismatch handling: Properly manage enable/disable state across preset changes
- Per-song timeout budgets: Prevent stalling on difficult songs
- Source health tracking: Adaptive degradation of unhealthy sources during runs
- Better scoring and ranking: Tier-based result ranking (download > page > fallback)
- Clearer CLI help text: All subcommands have detailed, consistent help

### 📦 Packaging & docs
- Professional README with complete usage guide
- Development setup documentation
- CI/CD workflows for testing and release
- Clear legal boundary statements
- Example playlists and configuration

### ⚙️ Technical
- All 51+ tests passing
- Linting 100% clean (ruff)
- Successful build and packaging
- Python 3.10, 3.11, 3.12 support

---

## [2.1.0] — Practical Real-World Optimization

### Architecture
- **Source health tracking**: Tracks timeouts, blocks, and errors per source during runs
- **Adaptive degradation**: Sources that are unhealthy (3+ timeouts or 2+ blocks) are automatically skipped for the rest of the run
- **Per-song time budgets**: Each song has a time limit (default 20s, 10s in fast mode) to prevent stalling
- **Priority-ordered sources**: Internet Archive first (native API), other sources with fallback handling
- **Practical query reduction**: Default reduces query variants to 2 (most specific + fallback)

### Configuration — Optimized for real-world
- **delay**: 0.6s (down from 0.8s) — practical for most networks
- **max_results**: 4 (down from 5) — fewer but faster results
- **timeout**: 12s (down from 15s) — fail fast on slow endpoints
- **retry_count**: 0 (no retries) — better to move on than retry forever
- **per_song_timeout**: NEW — 20s per song budget (10s in fast mode)
- **reduce_variants**: NEW — use only most specific query variants

### CLI/UX
- **Source health reporting**: Shows health status after each run
- **Fast-mode tuning**: Reduces per-song budget to 10s, timeout to 8s, delay to 0.3s
- **Better error tracking**: Distinguishes timeouts, blocks, and errors per source
- **Clearer progress**: Per-song budget prevents "frozen" appearance

### Quality
- All 51 tests pass
- Linting 100% clean
- Build successful
- Practical defaults verified

### Why this design

This version prioritizes **practical usefulness**:
1. **Never feel frozen**: Per-song budgets + source health skip prevent stalling
2. **Return useful results fast**: Lower timeouts, fewer retries, priority ordering
3. **Degrade gracefully**: Unhealthy sources are automatically skipped
4. **Real-world ready**: Tested with actual network conditions

---

## 2.0.0 — Search backend abstraction

### Architecture Improvements
- Search backend abstraction: modular search strategies
- Internet Archive native API (no DuckDuckGo dependency)
- Bandcamp, Jamendo, Pixabay dedicated search backends
- DuckDuckGo as fallback strategy, not primary

### CLI Enhancements
- Fast mode: `--fast` flag for quick searches
- Improved doctor command: Internet Archive API as critical check

### Configuration Defaults
- delay: 1.2s → 0.8s
- max_results: 8 → 5
- timeout: 30s → 15s
- retry_count: 2 → 1
- backoff: 2.0 → 1.5

---

## 1.2.0 — Package infrastructure

- Converted to installable Python package
- Added CLI subcommands for stats, config, doctor
- Added report generation and dry-run support

---

## 1.1.0 — Logging and output

- Added runtime logging
- Improved terminal output

---

## 1.0.0 — Initial release

- Basic CLI for searching legal music sources
