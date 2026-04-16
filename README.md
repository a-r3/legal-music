<p align="center">
  <img src="assets/logo.svg" alt="Legal Music logo" width="640">
</p>

# legal-music

**legal-music** is a professional Python CLI for finding and downloading music **from legal, permitted, and openly downloadable sources only**.

It's optimized for practical real-world use:
- Bounded search time per song
- Source-aware fallback strategies  
- Adaptive source health tracking
- Smart query optimization
- Practical defaults that work out of the box

> **🔒 Legal boundary**: This tool supports **only** legal and permitted sources. It does **NOT** support piracy, DRM bypass, Spotify/Apple Music/YouTube ripping, stream decryption, or any unauthorized content access.

## Why legal-music?

- **Recall-oriented**: Multi-variant query generation, accent folding, and source-specific search strategies for better hits
- **Practical defaults**: Good results out of the box without tuning
- **Smart fallback**: If one source fails, others are automatically tried
- **Bounded execution**: Per-song time budgets prevent stalling on difficult searches
- **Source health tracking**: Unhealthy sources are automatically skipped and retried later
- **Two search profiles**: Balanced mode (fast, practical) and maximize mode (more thorough)
- **Phase-based search**: Phase A prioritizes Internet Archive + Free Music Archive; Phase B is bounded rescue
- **Legal-only**: Internet Archive, Bandcamp, Free Music Archive, Jamendo, Pixabay Music — no piracy
- **Simple workflow**: dry-run mode to check, then download when ready

## Design philosophy

This tool is optimized for **maximum practical results under legal-only constraints**:

- **Try native source search paths first**: Internet Archive API, direct source searches where available
- **Controlled query variants**: Generate 5–8 query variants instead of one brittle search string
- **Adaptive caching**: Reuse run-level memory of failed/successful queries to avoid repeated work
- **Per-song time budgets**: Prevent one difficult song from freezing the entire playlist
- **Source health tracking**: Track timeouts, blocks, and errors; degrade unhealthy sources automatically
- **Smart result ranking**: Prefer downloadable matches over page-only matches, strong matches over weak ones
- **Staged search**: Fast high-value pass first (phase A), then selective recall expansion (phase B) only when needed

### Result tiers

**legal-music** ranks matches in tiers to avoid false positives:

- **Tier 1**: Direct download available
- **Tier 2**: Legal page found (e.g., Bandcamp page without direct link)
- **Tier 3**: Weak fallback match
- **Tier 4**: No match found

The engine prefers higher tiers first, so a downloaded track always beats a page-only match.

---

## Install

### One-command setup (Telegram Bot + CLI)

```bash
git clone https://github.com/a-r3/legal-music.git
cd legal-music
bash install.sh
```

The installer will:
1. Check Python 3.10+, install `yt-dlp` and `ffmpeg` if missing
2. Install all Python dependencies automatically
3. Ask for your **Bot Token** (from [@BotFather](https://t.me/BotFather)) and **Channel ID**
4. Register global commands `music-start` / `music-stop`
5. Optionally start the bot immediately

After install, from any terminal:
```bash
music-start   # start the bot
music-stop    # stop the bot
```

### CLI only (without Telegram bot)

```bash
git clone https://github.com/a-r3/legal-music.git
cd legal-music
pip install --break-system-packages -e .
```

### Upgrade

```bash
cd legal-music && git pull && bash install.sh
```

---

## Quick start

```bash
# 1. Initialize (creates config and playlist directory)
legal-music init

# 2. Create a playlist
cat > ~/.local/share/legal-music/playlists/my_songs.txt << 'EOF'
# Comments start with #
Beethoven - Moonlight Sonata
Bach - Prelude in C Major
Chopin - Nocturne Op. 9 No. 2
EOF

# 3. Check what's available (dry-run, no download)
legal-music dry ~/.local/share/legal-music/playlists/my_songs.txt

# 4. Download when results look good
legal-music dl ~/.local/share/legal-music/playlists/my_songs.txt

# 5. Check the results
cat output/my_songs/report.csv
ls -la output/my_songs/downloads/
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
# Comments start with # and are ignored
# Format: Artist Name - Song Title
Artist - Song Title
Another Artist - Another Song

# Blank lines are ignored
Composer - Piece Name
```

**Notes**:
- Lines starting with `#` are ignored as comments
- Blank lines are ignored
- Duplicates are detected and skipped automatically

---

## Output and reports

Each playlist run creates an `output/<playlist_name>/` directory:

```
output/my_songs/
  report.csv           # Song status, source, score (easy to audit)
  report.xlsx          # Color-coded Excel version (if openpyxl installed)
  summary.json         # Source stats and timing
  duplicates.csv       # Skipped duplicate entries
  errors.log           # Errors encountered during run
  downloads/           # Audio files (download mode only)
```

**Report columns** (CSV/XLSX):
- `Song`: The searched query
- `Status`: `downloaded`, `page_found`, `not_found`, or `error`
- `Source`: Which source found it
- `Score`: Confidence score (0.0–1.0)
- `URL`: Link to the result (or empty for `not_found`)

**Summary stats**:
- Source latency and success rate
- Query effectiveness
- Total runtime and average time per song

---

## Configuration

Generated at `~/.config/legal-music/config.json`:

```json
{
  "source_preset": "balanced",
  "delay": 0.25,
  "max_results": 5,
  "timeout": 10,
  "retry_count": 1,
  "per_song_timeout": 18,
  "phase_a_budget_ratio": 0.76,
  "min_downloadable_score": 0.46,
  "min_page_score": 0.50,
  "min_best_seen_score": 0.50,
  "balanced_query_variants": 5,
  "maximize_query_variants": 6,
  "cache_enabled": true,
  "persistent_cache_enabled": true,
  "source_priority": ["Internet Archive", "Free Music Archive", "Bandcamp", "Jamendo", "Pixabay Music"],
  "sources": [
    {"name": "Internet Archive", "enabled": true, "max_variants": 5},
    {"name": "Free Music Archive", "enabled": true, "max_variants": 4},
    {"name": "Bandcamp", "enabled": true, "max_variants": 1, "min_page_score": 0.76},
    {"name": "Jamendo", "enabled": false, "max_variants": 2},
    {"name": "Pixabay Music", "enabled": false, "max_variants": 2}
  ],
  "csv_report": true,
  "xlsx_report": true
}
```

### Settings explained

| Setting | Default | Purpose |
|---------|---------|---------|
| `delay` | 0.25s | Pause between requests (increase if rate-limited) |
| `max_results` | 5 | Results per source per query |
| `timeout` | 10s | HTTP request timeout |
| `per_song_timeout` | 18s | Max time to search one song (balanced mode) |
| `phase_a_budget_ratio` | 0.76 | Fraction of budget reserved for the high-value IA/FMA pass |
| `min_downloadable_score` | 0.46 | Threshold for "download available" status |
| `min_page_score` | 0.50 | Threshold for "page found" status |
| `cache_enabled` | true | Reuse query results within a run |
| `persistent_cache_enabled` | true | Reuse strong query/inspect results across runs |
| `source_preset` | balanced | Source profile: `balanced`, `maximize`, or `custom` |

**source_preset values**:
- `balanced`: Internet Archive + Free Music Archive first, then bounded Bandcamp rescue
- `maximize`: Internet Archive + Free Music Archive first, then Bandcamp + Jamendo + Pixabay rescue
- `custom`: Use current source enable/disable settings

**Tuning for conditions**:

*Slow networks*:
```json
{"delay": 2.0, "timeout": 20, "retry_count": 1}
```

*More recall needed*:
```json
{"max_results": 7, "per_song_timeout": 26, "maximize_query_variants": 6}
```

*Rate-limited*:
```json
{"delay": 2.0, "timeout": 20}
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

Each song has a bounded search budget (18s balanced by default, 8s in fast mode, 26s in maximize mode). The engine spends most songs in a high-value Phase A first, then only expands into bounded rescue when needed. In balanced mode, Phase A favors Internet Archive and Free Music Archive recall-per-second, and Phase B is Bandcamp-only rescue. This prevents:
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

Persistent cache is enabled by default, so strong cached results can also be reused across runs.

### 6. Priority defaults

Sources start in this order:
1. Internet Archive (most reliable, native API)
2. Free Music Archive (artist-permitted catalog + strong Phase A recall)
3. Bandcamp (strict page-based rescue in balanced mode)
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
# Smart maximize: broader fallback while keeping Phase A focused on IA/FMA
legal-music dry --maximize my_songs.txt

# Maximize recall across a directory of playlists
legal-music batch-dry --maximize ~/playlists/

# Or use the repo wrapper for all playlists under ./playlists
./scripts/run_playlists.sh --maximize
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

# Repo-local wrapper: process every playlists/*.txt to output/<playlist>/
./scripts/run_playlists.sh
./scripts/run_playlists.sh --download
```

---

## Troubleshooting

### "Tool appears to hang or is slow on a song"

The tool respects per-song time budgets to prevent stalling. If a song takes a long time:

- Use `--fast` mode for quicker searches
- Check source health with `legal-music doctor`
- Use `-v` to see what sources are being tried
- Increase `delay` if getting rate-limited

### "Getting 403/429 rate-limit errors"

Increase the delay between requests:

```bash
legal-music dl --delay 2.0 my_songs.txt
```

Or edit `~/.config/legal-music/config.json`:

```json
{"delay": 2.0}
```

### "Internet Archive is temporarily down"

The tool gracefully degrades to other sources. Check:

```bash
legal-music doctor
```

If Internet Archive API fails, other sources will be prioritized automatically for the current run.

### "No results found for any song"

Possible causes:

1. **All sources are down** → Run `legal-music doctor` to check connectivity
2. **Song titles are incorrect** → Verify artist and title spelling
3. **Legal sources don't have the song** → Legal catalogs have limited commercial coverage
4. **Network is blocking requests** → Try from a different network
5. **DuckDuckGo is unavailable** → Some fallback queries may fail, but native source searches still run

### "openpyxl not found / No XLSX report generated"

XLSX reports require the optional `openpyxl` library. Install it:

```bash
pip install openpyxl
```

CSV reports will still be generated.

---

## Development

### Setup

```bash
# Clone and enter the repository
git clone https://github.com/a-r3/legal-music.git
cd legal-music

# Install in editable mode with dev tools
pip install -e ".[dev]"
```

### Run tests and linting

```bash
# Run all tests
pytest

# Run linter
ruff check .

# Format code (safe, non-breaking)
ruff format .

# Full check (lint + test)
make check

# Build package
python3 -m build --no-isolation
```

### Make commands

```bash
make help       # Show all available commands
make dev        # Install dev dependencies
make test       # Run pytest
make lint       # Run ruff check
make format     # Format code with ruff
make check      # Lint + test
make build      # Build sdist + wheel
```

### Project structure

```
legal-music/
  src/legal_music/
    __init__.py         # Package init
    cli.py              # CLI entry point
    config.py           # Configuration handling
    downloader.py       # Download logic
    models.py           # Data models
    playlist.py         # Playlist parsing
    reports.py          # Report generation
    search/
      __init__.py
      engine.py         # Main search engine
      query.py          # Query generation
      scoring.py        # Result scoring
      sources/          # Individual source implementations
        archive.py
        bandcamp.py
        fma.py
        jamendo.py
        pixabay.py
  tests/
    test_*.py           # Test modules
  README.md             # This file
  pyproject.toml        # Package metadata
  pytest.ini            # Test configuration
  ruff.toml             # Linter configuration
```

---

## Known limitations

- **Source coverage**: Legal and open sources have limited commercial music coverage (especially recent, major-label releases)
- **Bandcamp pages**: Some artists don't offer direct downloads; you'll get a `page_found` status that requires manual checking
- **Free Music Archive**: Search result markup can change; some artist pages yield better results than individual track pages
- **Jamendo & Pixabay**: Markup can change; some downloads may require account interaction
- **Fallback search**: If DuckDuckGo is unavailable, fallback queries won't run, but native source search still works
- **Heuristic matching**: Result matching is strong but still heuristic-based; some false positives/negatives are possible on sparse or unusual titles

**Bottom line**: legal-music is best suited for:
- Classical and pre-1950s music (strong public domain coverage)
- Independent and CC-licensed music
- Bandcamp artists with free downloads
- Music that exists on legal, open sources

It's not suitable for:
- Recent major-label commercial releases (not on legal, open sources)
- Piracy or bypassing DRM
- Unauthorized streaming download

---

## License

MIT — See [LICENSE](LICENSE) for details.

---

## Philosophy

**legal-music** is built on these principles:

- **Legal-first**: Never tries unauthorized sources; legal sources only
- **Practical**: Real-world defaults that work without tuning
- **Adaptive**: Runtime behavior adjusts to source health and effectiveness
- **Resilient**: One failing source doesn't break the entire playlist
- **Transparent**: Reports show exactly what was found and where
- **Bounded**: Per-song time limits prevent stalling
- **Honest**: Limited coverage on legal sources, but no false promises
