# legal-music

**legal-music** is a practical Python CLI that finds and downloads music **only from legal, permitted, openly downloadable sources**, optimized for **the most useful legal result**, with bounded search time, source-aware fallback, and adaptive source health handling.

> **Legal boundary**: This tool does NOT support piracy, DRM bypass, Spotify/Apple Music/YouTube ripping, stream decryption, or any unauthorized content access. Only openly permitted sources are supported.

## Why legal-music?

- **Practical, never frozen**: Per-song time budgets, adaptive caching, and source health tracking
- **Higher recall**: Multi-variant query generation, accent folding, mix/remaster cleanup, and source-specific search strategies
- **Smarter runtime behavior**: Sources and query variants are reordered during a run based on usefulness and latency
- **Staged search**: Fast high-value pass first, then selective recall expansion only when needed
- **Legal-only**: Internet Archive (public domain), Bandcamp (free/PWYW), Free Music Archive, optional Jamendo and Pixabay
- **Simple defaults**: Good out-of-the-box behavior without tuning
- **Simple search profiles**: balanced default and `--maximize` for stronger staged recall, with `--fast` kept only for quick viability checks

## Design philosophy

This tool is optimized for **maximum practical results under legal-only constraints**:

- Try native source search paths first where available
- Generate controlled query variants instead of a single brittle search string
- Reuse run-level and optional persistent cache entries instead of repeating known-bad or known-good work
- Set per-song time budgets to prevent stalling
- Track source health during runs and degrade only when a source is clearly unhealthy
- Prefer `downloaded`, then `page_found`, then strong fallback matches instead of immediate `not_found`
- Rank results in tiers so mediocre page hits do not beat plausible downloadable matches
- Split each song into a short phase A and a selective phase B instead of sending every track through maximum effort

### Result tiers

- **Tier 1**: strong downloadable result
- **Tier 2**: strong legal page match
- **Tier 3**: weak fallback page
- **Tier 4**: low-confidence / not found

The engine prefers higher-value tiers first, so a medium Bandcamp page no longer beats a plausible downloadable candidate from a stronger source.

---

## Install

### Quick install (pipx)

```bash
pipx install .
legal-music init
```

### Development

```bash
pip install -e ".[dev]"
```

### Upgrade

```bash
pipx install --force .
```

---

## Quick start

```bash
# 1. Initialize
legal-music init

# 2. Create playlist
cat > ~/.local/share/legal-music/playlists/my_songs.txt << 'EOF'
Beethoven - Moonlight Sonata
Bach - Prelude in C Major
Chopin - Nocturne Op. 9 No. 2
EOF

# 3. Check what's available (dry-run)
legal-music dry ~/.local/share/legal-music/playlists/my_songs.txt

# 4. Download when ready
legal-music dl ~/.local/share/legal-music/playlists/my_songs.txt
```

---

## Commands

| Command | Purpose |
|---|---|
| `legal-music init` | Initialize config and directories |
| `legal-music doctor` | Check connectivity and dependencies |
| `legal-music version` | Show version |
| `legal-music cfg` | Display current config |
| `legal-music src` | List configured sources |
| `legal-music dry <playlist.txt>` | Dry-run (search only) |
| `legal-music dl <playlist.txt>` | Search and download |
| `legal-music batch-dry <dir>` | Dry-run all playlists in directory |
| `legal-music batch-dl <dir>` | Download all playlists in directory |
| `legal-music stats [path]` | Show stats from previous run |

### Practical flags

| Flag | Meaning |
|---|---|
| `--fast` | Fast mode: fewer variants, lower timeouts, quick viability checks |
| `--maximize` | Maximize recall mode: more variants, broader fallback, more effort per song |
| `--delay N` | Override delay between requests (seconds) |
| `--max-results N` | Override max results per source |
| `-v, --verbose` | Show search logic and scoring |
| `--no-color` | Disable colored output |

---

## Playlist format

Plain text, one song per line:

```
# Comments start with #
Beethoven - Moonlight Sonata
Bach - Prelude in C Major
Artist - Song Title
```

Lines starting with `#` are ignored. Duplicates are detected automatically.

---

## Output

Each playlist run creates:

```
output/<name>/
  report.csv          # Status, source, score for each song
  report.xlsx         # Color-coded Excel report (if openpyxl installed)
  summary.json        # Source latency/usefulness and query-usefulness summary
  duplicates.csv      # Skipped duplicates
  errors.log          # Errors encountered
  downloads/          # Audio files (not in dry-run mode)
```

Default runs use one compact result line per song, while `--verbose` shows query, tier, and runtime detail. The end-of-run summary also prints total elapsed time and average time per song so speed is easy to judge in real use.

---

## Configuration

Generated at `~/.config/legal-music/config.json`:

```json
{
  "delay": 0.25,
  "max_results": 5,
  "timeout": 10,
  "retry_count": 1,
  "per_song_timeout": 16,
  "phase_a_budget_ratio": 0.82,
  "min_downloadable_score": 0.46,
  "min_page_score": 0.48,
  "min_best_seen_score": 0.42,
  "balanced_query_variants": 5,
  "maximize_query_variants": 8,
  "cache_enabled": true,
  "persistent_cache_enabled": false,
  "source_priority": ["Internet Archive", "Free Music Archive", "Bandcamp", "Jamendo", "Pixabay Music"],
  "sources": [
    {"name": "Internet Archive", "enabled": true, "max_variants": 5},
    {"name": "Free Music Archive", "enabled": true, "max_variants": 4},
    {"name": "Bandcamp", "enabled": true, "max_variants": 3},
    {"name": "Jamendo", "enabled": false, "max_variants": 4},
    {"name": "Pixabay Music", "enabled": false, "max_variants": 3}
  ],
  "csv_report": true,
  "xlsx_report": true
}
```

### Settings explained

- **delay**: Seconds between requests (increase if getting rate-limited)
- **max_results**: Max results per source per query
- **timeout**: HTTP request timeout (fail fast if too low, too slow if too high)
- **retry_count**: Retries on connection errors (0 = fail fast)
- **per_song_timeout**: Max seconds to spend searching one song (prevents stalling)
- **phase_a_budget_ratio**: Fraction of the song budget reserved for the fast high-value pass before fallback expansion
- **min_downloadable_score**: Score threshold for direct download status
- **min_page_score**: Score threshold for "page found" status
- **min_best_seen_score**: Threshold for rescuing a strong candidate via fallback
- **balanced_query_variants / maximize_query_variants**: Query breadth for the two main search profiles
- **cache_enabled / persistent_cache_enabled**: Reuse previous query and inspect work instead of repeating it
- **source_priority**: Default source order before adaptive runtime reordering
- **sources[].max_variants**: Per-source cap on query variants before adaptive demotion kicks in

### Practical tuning

If playlists are too slow:
```json
{
  "delay": 0.15,
  "max_results": 2,
  "timeout": 5,
  "per_song_timeout": 8
}
```

If you want more recall:
```json
{
  "max_results": 7,
  "per_song_timeout": 24,
  "maximize_query_variants": 8
}
```

If getting rate-limited:
```json
{
  "delay": 2.0,
  "timeout": 20,
  "retry_count": 1
}
```

---

## Legal sources

| Source | Content | Search method |
|---|---|---|
| **Internet Archive** | Public domain + CC-licensed | Native Archive API first |
| **Bandcamp** | Free/pay-what-you-want downloads | Native Bandcamp search first, DuckDuckGo fallback |
| **Free Music Archive** | Free and artist-permitted downloads | Native FMA search first, DuckDuckGo fallback |
| **Jamendo** | CC-licensed music | Native Jamendo site search first, DuckDuckGo fallback |
| **Pixabay** | Royalty-free music | Native Pixabay music search first, DuckDuckGo fallback |

**Why this order?** Internet Archive is most reliable, doesn't depend on DuckDuckGo. Other sources use fallback search.

---

## What makes this practical

### 1. Source health tracking

Sources are tracked during a run:
- **Healthy**: Working normally
- **Degraded**: Some timeouts or blocks, but still useful
- **Unhealthy**: Repeated failures (timeouts ≥3 or blocks ≥2)

Unhealthy sources are skipped for the rest of the run, but the thresholds are tuned to avoid giving up too early on still-usable sources.

### 2. Per-song time budget

Each song has a bounded search budget (16s balanced by default, 8s in fast mode, 24s in maximize mode). The engine spends most songs in a short high-value phase first, then only expands when needed. This prevents:
- One failing song freezing the entire playlist
- Network outages from stalling for minutes
- User wondering if the tool is hung

Once the budget is exceeded, the tool moves to the next song.

### 3. Adaptive source degradation

If DuckDuckGo is unavailable, direct source search paths still run. If a source itself times out repeatedly, it is degraded and eventually skipped for the rest of the run.

### 4. Adaptive source economics

Sources start from the configured priority order, but are reordered during a run using:
- usefulness score
- average latency
- useful-result rate
- song-type hints such as classical, soundtrack, electronic, or accented names

This improves recall-per-second instead of just trying everything in a fixed order.

### 5. Caching and runtime memory

The engine keeps run-level memory for:
- search queries that already failed
- search queries that already produced candidates
- inspected URLs that already yielded useful matches
- redundant attempts that can be skipped safely

If `persistent_cache_enabled` is turned on, strong cached results can also be reused across runs.

### 6. Priority defaults

Sources start in this order:
1. Internet Archive (most reliable, native API)
2. Free Music Archive (artist-permitted catalog + fallback)
3. Bandcamp (strict page-based fallback)
4. Jamendo (optional, off by default)
5. Pixabay (native music search + fallback)

---

## Examples

### Basic workflow

```bash
# Check one playlist
legal-music dry my_songs.txt

# If results look good, download
legal-music dl my_songs.txt

# Check the output
ls -la output/my_songs/
cat output/my_songs/report.csv
```

### Fast checks

```bash
# Quick viability check
legal-music dry --fast my_songs.txt

# Good for checking if sources are accessible
legal-music batch-dry --fast ~/playlists/
```

### Maximize recall

```bash
# Smart maximize: better variants, adaptive ordering, broader fallback
legal-music dry --maximize my_songs.txt

# Maximize recall across a directory of playlists
legal-music batch-dry --maximize ~/playlists/
```

### Tuning for slow conditions

```bash
# If getting rate-limited
legal-music dl --delay 2.0 my_songs.txt

# If one source is very slow
legal-music dry --delay 1.0 --max-results 3 my_songs.txt
```

### Batch processing

```bash
# Put multiple playlists in a directory
ls ~/playlists/
# rock.txt  jazz.txt  classical.txt

# Dry-run all
legal-music batch-dry ~/playlists/

# Download all
legal-music batch-dl ~/playlists/

# Fast check all
legal-music batch-dry --fast ~/playlists/
```

---

## Troubleshooting

### "Tool feels slow / hangs on a song"

The tool respects per-song time budgets. If it appears stuck:
- Use `--fast` mode
- Check `legal-music doctor` to see if any sources are unhealthy
- Use `-v` to see what sources are being tried

### "Getting 403/429 rate-limit errors"

Solution: Increase `delay` in config or on command line:

```bash
legal-music dl --delay 2.0 my_songs.txt
```

Or edit `~/.config/legal-music/config.json`:

```json
{
  "delay": 2.0
}
```

### "Internet Archive is down"

The tool will gracefully degrade and try other sources. Check:

```bash
legal-music doctor
```

If Internet Archive API fails but other sources work, they'll be prioritized in the current run.

### "No results found for any song"

Possible reasons:
1. All sources are unavailable → check `legal-music doctor`
2. Songs don't exist on legal sources → check titles are correct
3. Network is blocking requests → try from a different network
4. DuckDuckGo is unavailable → native source search still runs, but recall may still drop on sources that need fallback

### "openpyxl not found"

XLSX reports won't be generated. Install:

```bash
pip install openpyxl
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Build
python3 -m build --no-isolation
```

---

## Known limitations

- **Bandcamp**: Some pages don't offer direct downloads (status: page_found requires manual check)
- **Free Music Archive**: Search result markup can change and some artist pages are stronger than track pages
- **Jamendo**: Search result markup can change, and some downloads may require account interaction
- **Pixabay**: Similar to Jamendo; direct page structure may change and some downloads may require account interaction
- **Coverage**: Legal/open sources simply do not have full commercial-catalog coverage
- **Adaptive learning**: Runtime learning improves a run and optional cache reuse helps later runs, but neither can create coverage that legal catalogs do not have
- **Scoring**: Matching is much stronger now but still heuristic-based, especially on sparse page titles

---

## License

MIT — see LICENSE

---

## Philosophy

This tool is designed for **real-world use**:

- **Recall-oriented, still bounded**: More valid hits without letting one song freeze a playlist
- **Adaptive, not static**: Search order and query order change when the run proves a strategy is weak or strong
- **Resilient, not fragile**: One bad source doesn't break the whole run
- **Practical, not theoretical**: Actually useful defaults
- **Legal-only**: Never tries unauthorized sources
