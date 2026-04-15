"""Telegram bot for legal-music.

Xüsusiyyətlər:
  - Mahnı adı ilə axtarış  → qanuni mənbələr, tapılmazsa yt-dlp fallback
  - URL göndər             → birbaşa yt-dlp ilə yüklə
  - .txt fayl göndər       → toplu yükləmə (hər sətir bir mahnı)
  - /status, /help, /start

BOT_TOKEN və CHANNEL_ID → .env faylından oxunur
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG = OUTPUT_DIR / "error_log.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(ERROR_LOG), encoding="utf-8"),
    ],
)
logger = logging.getLogger("legal-music.bot")

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

try:
    from telegram import Update
    from telegram.error import NetworkError, TelegramError
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    logger.error("python-telegram-bot quraşdırılmayıb: pip install python-telegram-bot")
    sys.exit(1)

# ---------------------------------------------------------------------------
# legal-music
# ---------------------------------------------------------------------------

try:
    from legal_music.async_engine import AsyncSearchRunner
    from legal_music.config import AppConfig
    from legal_music.db_cache import SQLiteCache
    from legal_music.downloader import download_file
    from legal_music.models import SongStatus
    from legal_music.playlist import read_playlist
    from legal_music.utils import default_data_dir, default_output_dir
except ImportError:
    try:
        from src.legal_music.async_engine import AsyncSearchRunner
        from src.legal_music.config import AppConfig
        from src.legal_music.db_cache import SQLiteCache
        from src.legal_music.downloader import download_file
        from src.legal_music.models import SongStatus
        from src.legal_music.playlist import read_playlist
        from src.legal_music.utils import default_data_dir, default_output_dir
    except ImportError:
        logger.error("legal-music paketi tapılmadı: pip install -e .")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN: str  = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")
DOWNLOADS_DIR   = default_output_dir() / "bot_downloads"
DB_PATH         = default_data_dir() / "cache" / "bot_cache.db"

if not BOT_TOKEN:
    logger.error("BOT_TOKEN tapılmadı. .env faylını yoxlayın.")
    sys.exit(1)

_URL_RE = re.compile(r"https?://[^\s]+|www\.[^\s]+|youtu\.be/[^\s]+", re.IGNORECASE)
_SEP_RE = re.compile(r"\s*[/|,–—]\s*|\s+by\s+|\s*:\s*", re.IGNORECASE)
_HAS_DASH_RE = re.compile(r"\s+-\s+")

_cfg: AppConfig | None = None
_db:  SQLiteCache | None = None
_downloads_total: int = 0


def _get_cfg() -> AppConfig:
    global _cfg
    if _cfg is None:
        p = Path.home() / ".config" / "legal-music" / "config.json"
        _cfg = AppConfig.load(p) if p.exists() else AppConfig()
    return _cfg


def _get_db() -> SQLiteCache:
    global _db
    if _db is None:
        _db = SQLiteCache(DB_PATH)
    return _db


# ---------------------------------------------------------------------------
# Smart query generator
# ---------------------------------------------------------------------------

def _smart_queries(text: str) -> list[str]:
    """'dua lipa levitating' → ['dua lipa levitating', 'dua lipa - levitating', ...]"""
    text = text.strip()
    attempts: list[str] = []

    def _add(q: str) -> None:
        q = re.sub(r"\s{2,}", " ", q).strip(" -")
        if q and q not in attempts:
            attempts.append(q)

    _add(text)

    normalised = _SEP_RE.sub(" - ", text).strip()
    _add(normalised)

    base = normalised if _HAS_DASH_RE.search(normalised) else text
    if not _HAS_DASH_RE.search(base):
        words = base.split()
        for split in range(1, min(4, len(words))):
            artist = " ".join(words[:split])
            title  = " ".join(words[split:])
            if artist and title:
                _add(f"{artist} - {title}")
        _add(base)

    return attempts


# ---------------------------------------------------------------------------
# yt-dlp fallback: search by name and download
# ---------------------------------------------------------------------------

async def _ytdlp_search_download(query: str, dest_dir: Path) -> Path:
    """YouTube-da 'query' axtarıb birinci nəticəni MP3 kimi yüklə."""
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp quraşdırılmayıb")

    dest_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(dest_dir / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        f"ytsearch1:{query}",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", output_template,
        "--no-warnings", "--quiet",
        "--no-playlist",
    ]

    loop = asyncio.get_event_loop()
    import subprocess

    def _run():
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:300] or "yt-dlp xətası")

    await loop.run_in_executor(None, _run)

    # Ən son MP3 faylı tap
    mp3_files = sorted(dest_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    if not mp3_files:
        raise RuntimeError("yt-dlp: fayl tapılmadı")
    return mp3_files[-1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_error(ctx: str, exc: Exception) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] ERROR [{ctx}]: {exc}\n")
    except Exception:
        pass
    logger.error("[%s] %s", ctx, exc)


async def _safe_reply(update: Update, text: str) -> None:
    try:
        if update.message:
            await update.message.reply_text(text, parse_mode=None)
    except Exception as exc:
        logger.warning("reply göndərilmədi: %s", exc)


async def _send_audio(
    context: ContextTypes.DEFAULT_TYPE,
    file_path: Path,
    caption: str,
    reply_update: Update | None = None,
) -> None:
    global _downloads_total
    _downloads_total += 1

    async def _one(chat_id):
        try:
            with file_path.open("rb") as f:
                await context.bot.send_audio(
                    chat_id=chat_id, audio=f,
                    caption=caption[:1024],
                    read_timeout=60, write_timeout=60,
                )
        except TelegramError as e:
            logger.warning("send_audio xətası (%s): %s", chat_id, e)

    if CHANNEL_ID:
        await _one(CHANNEL_ID)
    if reply_update and reply_update.effective_chat:
        cid = reply_update.effective_chat.id
        if str(cid) != str(CHANNEL_ID):
            await _one(cid)


# ---------------------------------------------------------------------------
# Bir mahnını axtar + yüklə  (core logic, hər yerdə istifadə edilir)
# ---------------------------------------------------------------------------

async def _search_and_download(
    song: str,
    context: ContextTypes.DEFAULT_TYPE,
    reply_update: Update | None = None,
) -> bool:
    """Mahnını axtar, yüklə, kanala göndər. Uğursa True qaytarır."""
    queries = _smart_queries(song)
    cfg     = _get_cfg()
    result  = None
    matched_query = song

    # 1. Qanuni mənbələr
    for attempt in queries:
        runner = AsyncSearchRunner(cfg, max_concurrent=1, db_path=DB_PATH)
        res = await runner.search_one(attempt)
        runner.close()
        if res.status in (SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND):
            result = res
            matched_query = attempt
            break

    # 2. Tapıldısa yüklə
    if result and result.status == SongStatus.DOWNLOADED and result.direct_url:
        try:
            DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            saved = await asyncio.get_event_loop().run_in_executor(
                None, lambda: download_file(result.direct_url, matched_query, DOWNLOADS_DIR)
            )
            caption = f"🎵 {matched_query}\n📂 {result.source}"
            await _send_audio(context, saved, caption, reply_update)
            return True
        except Exception as exc:
            logger.warning("Qanuni mənbə yükləmə xətası (%s): %s", song, exc)

    # 3. yt-dlp fallback — YouTube-da axtar
    logger.info("yt-dlp fallback: %r", song)
    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        saved = await _ytdlp_search_download(song, DOWNLOADS_DIR)
        caption = f"🎵 {song}\n📂 YouTube (yt-dlp)"
        await _send_audio(context, saved, caption, reply_update)
        return True
    except Exception as exc:
        logger.warning("yt-dlp axtarış xətası (%s): %s", song, exc)
        return False


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(update,
        "🎵 Legal Music Bot\n\n"
        "Mahnı adı yaz → yükləyirəm\n"
        "YouTube/URL göndər → yükləyirəm\n"
        ".txt fayl göndər → toplu yükləmə\n\n"
        "Nümunə: Dua Lipa - Levitating\n\n"
        "/help /status"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(update,
        "🎵 Legal Music Bot — İstifadə\n\n"
        "Mahnı adı:\n"
        "  Dua Lipa - Levitating\n"
        "  dua lipa levitating  (tire olmadan da olur)\n\n"
        "URL yüklə:\n"
        "  https://youtube.com/watch?v=...\n\n"
        "Toplu yükləmə:\n"
        "  songs.txt faylı göndər (hər sətirdə bir mahnı)\n\n"
        "/status — statistika\n"
        "/help   — bu mesaj"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        stats = _get_db().stats()
        ytdlp = "✅" if shutil.which("yt-dlp") else "❌"
        sources = ", ".join(_get_cfg().enabled_source_names())
        await _safe_reply(update,
            f"📊 Bot Statusu\n\n"
            f"💾 Keş (sorğu): {stats.get('query_cache_entries', 0)}\n"
            f"💾 Keş (mahnı): {stats.get('song_cache_entries', 0)}\n"
            f"✅ Yüklənmiş: {_downloads_total}\n"
            f"🎯 Mənbələr: {sources}\n"
            f"🔧 yt-dlp: {ytdlp}"
        )
    except Exception as exc:
        _log_error("cmd_status", exc)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mətn mesajı → mahnı axtarışı."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    if _URL_RE.search(text):
        await handle_url(update, context)
        return

    await _safe_reply(update, f"🔍 Axtarılır: {text}…")
    found = await _search_and_download(text, context, reply_update=update)
    if not found:
        await _safe_reply(update,
            f"❌ Tapılmadı: {text}\n\n"
            f"💡 Format: İfaçı - Mahnı adı\n"
            f"Nümunə: Dua Lipa - Levitating"
        )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """URL mesajı → yt-dlp ilə yüklə."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    match = _URL_RE.search(text)
    if not match:
        return
    url = match.group(0)

    if not shutil.which("yt-dlp"):
        await _safe_reply(update, "❌ yt-dlp quraşdırılmayıb: pip install yt-dlp")
        return

    await _safe_reply(update, f"⬇️ URL yüklənir…")

    try:
        from legal_music.search.sources.ytdlp_source import download_via_ytdlp
    except ImportError:
        from src.legal_music.search.sources.ytdlp_source import download_via_ytdlp  # type: ignore

    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        dest = DOWNLOADS_DIR / "url_download"
        saved = await asyncio.get_event_loop().run_in_executor(
            None, lambda: download_via_ytdlp(url, dest)
        )
        await _send_audio(context, saved, f"🎵 {url[:80]}", reply_update=update)
    except Exception as exc:
        _log_error(f"handle_url:{url}", exc)
        await _safe_reply(update, f"❌ URL yüklənmədi: {exc}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """TXT fayl → toplu yükləmə."""
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await _safe_reply(update, "⚠️ Yalnız .txt faylı göndərin (hər sətirdə bir mahnı)")
        return

    await _safe_reply(update, "📄 Fayl alındı, mahnılar axtarılır…")

    # Faylı yüklə
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await tg_file.download_to_drive(tmp_path)
    except Exception as exc:
        _log_error("handle_document:download", exc)
        await _safe_reply(update, f"❌ Fayl yüklənmədi: {exc}")
        return

    # Sətirləri oxu
    try:
        songs = read_playlist(tmp_path)
        tmp_path.unlink(missing_ok=True)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        await _safe_reply(update, f"❌ Fayl oxunmadı: {exc}")
        return

    if not songs:
        await _safe_reply(update, "⚠️ Faylda mahnı tapılmadı.")
        return

    await _safe_reply(update, f"🎵 {len(songs)} mahnı tapıldı. Yüklənir…")

    ok_count = 0
    fail_count = 0
    fail_list: list[str] = []

    for i, song in enumerate(songs, 1):
        try:
            await _safe_reply(update, f"[{i}/{len(songs)}] 🔍 {song}")
            found = await _search_and_download(song, context, reply_update=None)
            if found:
                ok_count += 1
            else:
                fail_count += 1
                fail_list.append(song)
        except Exception as exc:
            _log_error(f"batch:{song}", exc)
            fail_count += 1
            fail_list.append(song)

    # Yekun hesabat
    summary = (
        f"✅ Toplu yükləmə tamamlandı!\n\n"
        f"✅ Uğurlu: {ok_count}/{len(songs)}\n"
        f"❌ Tapılmadı: {fail_count}/{len(songs)}"
    )
    if fail_list:
        summary += "\n\nTapılmayanlar:\n" + "\n".join(f"• {s}" for s in fail_list[:20])
        if len(fail_list) > 20:
            summary += f"\n… və {len(fail_list) - 20} daha"
    await _safe_reply(update, summary)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    exc = context.error
    if isinstance(exc, NetworkError):
        logger.warning("Şəbəkə xətası (avtomatik yenidən qoşulur): %s", exc)
    else:
        logger.error("Xəta: %s", exc, exc_info=exc)
        if exc:
            _log_error("unhandled", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Legal Music Bot başladılır…")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))

    # Sənəd (txt fayl) → toplu yükləmə
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Mətn → mahnı axtarışı
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(error_handler)

    logger.info("Bot işləyir. Ctrl+C ilə dayandırın.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
