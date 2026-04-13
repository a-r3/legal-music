# Changelog

## 2.1.0 — Practical Real-World Optimization

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
