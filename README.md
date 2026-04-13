# legal-music

**legal-music** is a professional Python CLI that finds and downloads music **only from legal, permitted, openly downloadable sources**.

> **Legal boundary**: This tool does NOT support piracy, DRM bypass, Spotify/Apple Music/YouTube ripping, stream decryption, or any unauthorized content access. Only openly permitted sources are supported.

## Features

- Search and download from Bandcamp, Internet Archive, Jamendo, and Pixabay Music
- Clean `.txt` playlist workflow
- Dry-run mode to check matches before downloading
- Batch processing of multiple playlists
- CSV and XLSX reports with color-coded status
- Duplicate detection in playlist files
- Retry logic, timeout handling, and 403/rate-limit detection
- Configurable sources, delays, scoring thresholds
- Designed for `pipx` global install on Linux

## Install

### Recommended: pipx (global CLI, no venv required)

```bash
pipx install .
# or
./scripts/install_pipx.sh
```

After install, `legal-music` is available globally — no `source .venv/bin/activate` needed.

### pip install

```bash
pip install .
```

### Editable (development)

```bash
pip install -e ".[dev]"
# or
./scripts/install_dev.sh
```

### Upgrade

```bash
pipx install --force .   # for pipx
pip install --force-reinstall .  # for pip
```

### Uninstall

```bash
./scripts/uninstall.sh
```

---

## Quick start

```bash
# 1. Initialize default dirs and config
legal-music init

# 2. Create a playlist file
cat > ~/playlists/my_songs.txt << 'EOF'
Frank Sinatra - My Way
John Mayer - Gravity
Nina Simone - Feeling Good
EOF

# 3. Dry run (search, no download)
legal-music dry ~/playlists/my_songs.txt

# 4. Download
legal-music dl ~/playlists/my_songs.txt
```

---

## Commands

| Command | Description |
|---|---|
| `legal-music init` | Create default config and playlist dirs |
| `legal-music doctor` | Check dependencies and connectivity |
| `legal-music version` | Show version |
| `legal-music cfg` | Show current config |
| `legal-music src` | List configured sources |
| `legal-music dry <playlist.txt>` | Dry run for one playlist |
| `legal-music dl <playlist.txt>` | Search and download one playlist |
| `legal-music batch-dry <dir>` | Dry run all playlists in a directory |
| `legal-music batch-dl <dir>` | Download all playlists in a directory |
| `legal-music stats [path]` | Show stats from a previous run |

### Common flags

| Flag | Description |
|---|---|
| `-c, --config` | Path to config.json (default: `~/.config/legal-music/config.json`) |
| `-v, --verbose` | Verbose output |
| `--no-color` | Disable colored output |
| `-o, --output` | Override output directory |
| `--delay` | Seconds between requests (default: 1.2) |
| `--max-results` | Max search results per source (default: 8) |

---

## Playlist format

Playlists are plain `.txt` files, one song per line:

```
# Comments start with #
Frank Sinatra - My Way
John Mayer - Gravity
Artist - Song Title
```

- Lines starting with `#` are ignored
- Use `Artist - Title` format for best results
- Duplicates are detected and skipped automatically

---

## Output structure

Each playlist run creates:

```
output/<playlist_name>/
  report.csv          — full search results
  report.xlsx         — color-coded Excel report (if openpyxl installed)
  duplicates.csv      — songs skipped as duplicates
  errors.log          — errors encountered
  downloads/          — downloaded audio files
```

Batch runs create one subdirectory per playlist.

---

## Configuration

Config lives at `~/.config/legal-music/config.json`. Generate it with `legal-music init`.

Key settings:

```json
{
  "delay": 1.2,
  "max_results": 8,
  "timeout": 30,
  "retry_count": 2,
  "backoff": 2.0,
  "min_downloadable_score": 0.40,
  "min_page_score": 0.52,
  "sources": [
    {"name": "Internet Archive", "enabled": true},
    {"name": "Bandcamp", "enabled": true},
    {"name": "Jamendo", "enabled": true},
    {"name": "Pixabay Music", "enabled": true}
  ],
  "csv_report": true,
  "xlsx_report": true
}
```

Disable a source: set `"enabled": false`.

---

## Legal sources

| Source | What it provides |
|---|---|
| **Internet Archive** | Public domain and Creative Commons music; fully open API |
| **Bandcamp** | Artist pages where download is explicitly offered (Free/Pay-what-you-want) |
| **Jamendo** | Royalty-free Creative Commons music |
| **Pixabay Music** | Free-to-use music for any purpose |

---

## Batch workflow (multiple playlists)

```bash
# Put all playlists in a directory
ls playlists/
# rock.txt  jazz.txt  classical.txt

# Dry run all
legal-music batch-dry playlists/

# Download all
legal-music batch-dl playlists/
```

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/install_pipx.sh` | Install via pipx |
| `scripts/install_dev.sh` | Set up dev environment |
| `scripts/uninstall.sh` | Uninstall |
| `scripts/run_playlist.sh` | Run a single playlist |
| `scripts/run_all_playlists.sh` | Run all playlists in a directory |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .

# Build
python3 -m build
```

---

## Troubleshooting

**`legal-music: command not found` after pipx install**

Run `pipx ensurepath`, then restart your shell.

**403 / blocked errors**

Some sources rate-limit or block scrapers. Increase `delay` in config. Blocked results appear in `report.csv` as `blocked` status.

**No matches found**

- Check `legal-music doctor` for connectivity issues
- Try increasing `max_results`
- The song may simply not be available on permitted sources

**openpyxl not found**

XLSX report won't be generated. Install with: `pip install openpyxl`

---

## Known limitations

- Bandcamp, Jamendo, and Pixabay search relies on DuckDuckGo `site:` queries, which can be rate-limited
- Internet Archive has the most reliable open API
- Not all Bandcamp pages offer free downloads — `page_found` status indicates a page exists but direct download was not confirmed
- Pixabay and Jamendo may require a browser/account login for full download, even when pages are found
