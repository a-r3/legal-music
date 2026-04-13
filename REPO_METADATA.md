# GitHub Metadata

## Repository name
legal-music

## Repository description
Professional Python CLI for finding and downloading music only from permitted sources.

## Suggested topics
python
cli
music
downloader
legal
playlist
automation
reports
packaging
setuptools

## Recommended About blurb
A professional Python CLI for checking playlist text files against permitted music sources, with dry-run mode, reports, config management, and packaging support.

## First release title
v1.2.0 — Initial public package release

## First release notes
### Highlights
- Installable Python package with `legal-music` console command
- Dry-run and download workflow
- CSV/XLSX reporting
- Duplicate detection
- Stats, doctor, config-paths, backup-config, and reset-config commands
- GitHub Actions CI and release build workflow

### Install
```bash
pip install .
```

### Quick start
```bash
legal-music init
legal-music run --dry-run
legal-music run
```
