"""File downloading utilities."""
from __future__ import annotations

from pathlib import Path

import requests

from .constants import AUDIO_EXTENSIONS, DOWNLOAD_TIMEOUT, HEADERS
from .utils import safe_filename


def guess_extension(response: requests.Response, url: str) -> str:
    ct = (response.headers.get("Content-Type") or "").lower()
    ul = url.lower()
    for ext in AUDIO_EXTENSIONS:
        if ext.lstrip(".") in ul or ext.lstrip(".") in ct:
            return ext
    if "mp4" in ct or "m4a" in ct:
        return ".m4a"
    return ".mp3"


def download_file(
    url: str,
    song_name: str,
    dest_dir: Path,
    session: requests.Session | None = None,
) -> Path:
    """Download audio file to dest_dir. Returns path to saved file."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    headers = dict(HEADERS)

    if session:
        r = session.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
    else:
        r = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()

    ext = guess_extension(r, url)
    filename = f"{safe_filename(song_name)}{ext}"
    dest = dest_dir / filename

    # Avoid overwriting: append counter if needed
    counter = 1
    while dest.exists():
        filename = f"{safe_filename(song_name)}_{counter}{ext}"
        dest = dest_dir / filename
        counter += 1

    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=131072):
            if chunk:
                f.write(chunk)

    return dest
