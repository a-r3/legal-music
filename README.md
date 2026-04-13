# legal-music

**legal-music** is a professional Python CLI for finding and downloading music **only from permitted sources**.
It is designed for workflows like:
- taking a text playlist (`songs.txt`)
- checking tracks with `--dry-run`
- downloading matches from allowed sources
- exporting results into CSV/XLSX reports
- moving the downloaded files into another library or device workflow

## Core principles

- Searches only configured, permitted sources
- Does **not** bypass DRM
- Does **not** target unauthorized download sources
- Keeps local config, reports, and runtime logs separate from repo files

## Install

### Editable install

```bash
pip install -e .
```

### Standard install

```bash
pip install .
```

After install, the CLI command is:

```bash
legal-music --help
```

## Quick start

```bash
legal-music init
legal-music run --dry-run
legal-music run
legal-music stats
```

## Main commands

```bash
legal-music init
legal-music run --dry-run
legal-music run
legal-music run -v
legal-music stats
legal-music backup-config
legal-music reset-config
legal-music doctor
legal-music config-paths
legal-music sources
legal-music version
legal-music shell-completion bash
legal-music shell-completion zsh
legal-music self-update
```

## Repo structure

```text
legal-music/
├─ .github/
│  └─ workflows/
├─ src/
│  └─ legal_music/
├─ tests/
├─ pyproject.toml
├─ README.md
├─ LICENSE
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ SECURITY.md
├─ config.example.json
└─ songs.example.txt
```

## Development

Install development tools:

```bash
pip install -e . pytest ruff build
```

Run checks:

```bash
pytest
ruff check .
python -m build
```

## Notes

- Example files are included as `config.example.json` and `songs.example.txt`
- Real user config should stay outside the repo
- Generated reports and downloaded media should not be committed

## License

MIT
