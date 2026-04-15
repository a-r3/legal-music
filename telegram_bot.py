"""Telegram bot for legal-music.

Usage:
    cp .env.example .env
    # Fill in BOT_TOKEN and CHANNEL_ID in .env
    python telegram_bot.py

Bot commands:
    /start  - Welcome message
    /help   - Usage instructions
    /status - Cache stats, download count, source health

Message handling:
    Any plain text  -> treated as a song name (e.g. "Dua Lipa - Levitating")
    Any URL         -> passed directly to yt-dlp for download

After a successful download the .mp3 is forwarded to CHANNEL_ID.
All errors are logged to output/error_log.txt.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Load .env before any other imports that might need env vars
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; fall back to os.environ

# ---------------------------------------------------------------------------
# Logging setup  — must be done before importing telegram
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("output")
LOG_DIR = OUTPUT_DIR
LOG_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG = LOG_DIR / "error_log.txt"

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
# Telegram imports
# ---------------------------------------------------------------------------

try:
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.error import NetworkError, TelegramError
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    logger.error(
        "python-telegram-bot not installed. Run: pip install python-telegram-bot"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# legal-music imports
# ---------------------------------------------------------------------------

try:
    from src.legal_music.async_engine import AsyncSearchRunner
    from src.legal_music.config import AppConfig
    from src.legal_music.db_cache import SQLiteCache
    from src.legal_music.downloader import download_file
    from src.legal_music.models import SongStatus
    from src.legal_music.utils import default_data_dir, default_output_dir
except ImportError:
    try:
        from legal_music.async_engine import AsyncSearchRunner
        from legal_music.config import AppConfig
        from legal_music.db_cache import SQLiteCache
        from legal_music.downloader import download_file
        from legal_music.models import SongStatus
        from legal_music.utils import default_data_dir, default_output_dir
    except ImportError:
        logger.error(
            "legal-music package not found. "
            "Run: pip install -e . from the repo root."
        )
        sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")
DOWNLOADS_DIR: Path = default_output_dir() / "bot_downloads"
DB_PATH: Path = default_data_dir() / "cache" / "bot_cache.db"

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set. Create a .env file with BOT_TOKEN=<token>")
    sys.exit(1)

if not CHANNEL_ID:
    logger.warning("CHANNEL_ID is not set — downloaded files will only be sent to the requester.")

_URL_RE = re.compile(
    r"https?://[^\s]+"
    r"|www\.[^\s]+"
    r"|youtu\.be/[^\s]+"
    r"|t\.me/[^\s]+",
    re.IGNORECASE,
)

# Separators users commonly write instead of " - "
_SEP_RE = re.compile(r"\s*[/|,–—]\s*|\s+by\s+|\s*:\s*", re.IGNORECASE)
_HAS_DASH_RE = re.compile(r"\s+-\s+")


def _smart_queries(text: str) -> list[str]:
    """Generate multiple search attempts from a free-form user input.

    Handles cases like:
      "dua lipa levitating"       → "dua lipa - levitating", "dua - lipa levitating" …
      "Levitating / Dua Lipa"     → "Levitating - Dua Lipa"
      "Dua Lipa - Levitating"     → passed through as-is (already correct)
      "eminem lose yourself"      → "eminem - lose yourself"
    Returns a deduplicated ordered list, best guesses first.
    """
    text = text.strip()
    attempts: list[str] = []

    def _add(q: str) -> None:
        q = re.sub(r"\s{2,}", " ", q).strip(" -")
        if q and q not in attempts:
            attempts.append(q)

    # 1. Always try the original input first
    _add(text)

    # 2. Normalise other separators (/ | , : — by) to " - "
    normalised = _SEP_RE.sub(" - ", text).strip()
    _add(normalised)

    # 3. Use the normalised version as the base for further attempts
    base = normalised if _HAS_DASH_RE.search(normalised) else text

    # 4. If there's STILL no " - ", try splitting at each word boundary
    #    so "dua lipa levitating" → "dua lipa - levitating" (best guess at position 2)
    if not _HAS_DASH_RE.search(base):
        words = base.split()
        if len(words) >= 2:
            for split in range(1, min(4, len(words))):
                artist_part = " ".join(words[:split])
                title_part  = " ".join(words[split:])
                if artist_part and title_part:
                    _add(f"{artist_part} - {title_part}")
        # Also try entire input as title-only
        _add(base)

    return attempts

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_cfg: AppConfig | None = None
_db: SQLiteCache | None = None
_downloads_total: int = 0


def _get_cfg() -> AppConfig:
    global _cfg
    if _cfg is None:
        from pathlib import Path
        cfg_path = Path.home() / ".config" / "legal-music" / "config.json"
        _cfg = AppConfig.load(cfg_path) if cfg_path.exists() else AppConfig()
    return _cfg


def _get_db() -> SQLiteCache:
    global _db
    if _db is None:
        _db = SQLiteCache(DB_PATH)
    return _db


# ---------------------------------------------------------------------------
# Helper: log error to file
# ---------------------------------------------------------------------------


def _log_error(context: str, exc: Exception) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] ERROR [{context}]: {exc}\n")
    except Exception:
        pass
    logger.error("[%s] %s", context, exc)


# ---------------------------------------------------------------------------
# Helper: safe reply that never crashes the bot
# ---------------------------------------------------------------------------


async def _safe_reply(update: Update, text: str) -> None:
    try:
        if update.message:
            await update.message.reply_text(text)
    except Exception as exc:
        logger.warning("Failed to send reply: %s", exc)


# ---------------------------------------------------------------------------
# Helper: send audio to channel + requester
# ---------------------------------------------------------------------------


async def _send_audio(
    context: ContextTypes.DEFAULT_TYPE,
    file_path: Path,
    caption: str,
    reply_update: Update | None = None,
) -> None:
    global _downloads_total
    _downloads_total += 1

    async def _send_one(chat_id: str | int) -> None:
        try:
            with file_path.open("rb") as audio_file:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    caption=caption[:1024],
                    read_timeout=60,
                    write_timeout=60,
                )
        except TelegramError as exc:
            logger.warning("send_audio failed to %s: %s", chat_id, exc)

    if CHANNEL_ID:
        await _send_one(CHANNEL_ID)

    if reply_update and reply_update.effective_chat:
        chat_id = reply_update.effective_chat.id
        if str(chat_id) != str(CHANNEL_ID):
            await _send_one(chat_id)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome handler."""
    await _safe_reply(
        update,
        "🎵 *Legal Music Bot*\n\n"
        "Mənə mahnı adı göndər, mən onu tapıb yükləyəcəyəm!\n\n"
        "Nümunə: `Dua Lipa - Levitating`\n\n"
        "Komandalar:\n"
        "  /help   - Kömək\n"
        "  /status - Bot statusu",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help command."""
    text = (
        "🎵 *Legal Music Bot — İstifadə Qaydası*\n\n"
        "*Mahnı axtar:*\n"
        "Sadəcə mahnının adını yaz:\n"
        "`İfaçı - Mahnı adı`\n"
        "Nümunə: `Bach - Prelude in C Major`\n\n"
        "*URL yüklə:*\n"
        "İstənilən YouTube/SoundCloud URL göndər, bot yt-dlp ilə yükləyəcək.\n\n"
        "*Komandalar:*\n"
        "  /status — Keş ölçüsü, yüklənmiş mahnılar, mənbə statusu\n"
        "  /help   — Bu mesaj\n\n"
        "*Qeyd:* Bot yalnız qanuni, Creative Commons licensiyalı mahnıları tapır."
    )
    await _safe_reply(update, text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status command — show cache and download stats."""
    try:
        db_stats = _get_db().stats()
        ytdlp_ok = shutil.which("yt-dlp") is not None

        cfg = _get_cfg()
        sources = cfg.enabled_source_names()

        lines = [
            "📊 *Bot Statusu*\n",
            f"💾 Keş (sorğu): {db_stats.get('query_cache_entries', 0)}",
            f"💾 Keş (mahnı): {db_stats.get('song_cache_entries', 0)}",
            f"✅ Yüklənmiş: {_downloads_total}",
            f"🎯 Fəal mənbələr: {', '.join(sources)}",
            f"🔧 yt-dlp: {'✅ quraşdırılıb' if ytdlp_ok else '❌ quraşdırılmayıb'}",
        ]
        await _safe_reply(update, "\n".join(lines))
    except Exception as exc:
        _log_error("cmd_status", exc)
        await _safe_reply(update, "⚠️ Status alınarkən xəta baş verdi.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages as song search requests."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # Route URLs to the URL handler
    if _URL_RE.search(text):
        await handle_url(update, context)
        return

    logger.info("Song search request: %r", text)

    # Generate smart query attempts from the raw input
    queries = _smart_queries(text)
    display_name = text  # shown to user in messages

    await _safe_reply(update, f"🔍 Axtarılır: *{display_name}*…")

    try:
        cfg = _get_cfg()
        result = None

        # Try each query variant until we get a hit
        for attempt in queries:
            logger.info("Trying query: %r", attempt)
            runner = AsyncSearchRunner(cfg, max_concurrent=1, db_path=DB_PATH)
            res = await runner.search_one(attempt)
            runner.close()

            if res.status in (SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND):
                result = res
                display_name = attempt  # show which variant succeeded
                break

        # If nothing found, use the last result (NOT_FOUND)
        if result is None:
            result = res  # type: ignore[possibly-undefined]

        if result.status == SongStatus.DOWNLOADED and result.direct_url:
            await _safe_reply(update, f"⬇️ Yüklənir: *{display_name}*…")
            try:
                DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
                saved = download_file(
                    result.direct_url,
                    display_name,
                    DOWNLOADS_DIR,
                )
                caption = f"🎵 {display_name}\n📂 {result.source} | ⭐ {result.score:.2f}"
                await _send_audio(context, saved, caption, reply_update=update)
            except FileNotFoundError:
                await _safe_reply(update, f"❌ Tapılmadı: {display_name}")
            except Exception as exc:
                _log_error(f"download:{display_name}", exc)
                await _safe_reply(update, f"⚠️ Yüklənmə xətası: {display_name}\n{exc}")

        elif result.status == SongStatus.PAGE_FOUND and result.page_url:
            await _safe_reply(
                update,
                f"🔗 Səhifə tapıldı (birbaşa yükləmə yoxdur):\n{result.page_url}",
            )
        else:
            await _safe_reply(
                update,
                f"❌ Tapılmadı: *{text}*\n\n"
                f"💡 İpucu: `İfaçı - Mahnı adı` formatında yaz\n"
                f"Nümunə: `Dua Lipa - Levitating`",
            )

    except Exception as exc:
        _log_error(f"handle_text:{text}", exc)
        await _safe_reply(update, f"⚠️ Xəta baş verdi: {exc}")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URL messages — download via yt-dlp."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    match = _URL_RE.search(text)
    if not match:
        return

    url = match.group(0)
    logger.info("URL download request: %r", url)

    if not shutil.which("yt-dlp"):
        await _safe_reply(update, "❌ yt-dlp quraşdırılmayıb. `pip install yt-dlp` edin.")
        return

    await _safe_reply(update, f"⬇️ URL yüklənir…\n`{url}`")

    try:
        from .search.sources.ytdlp_source import download_via_ytdlp
    except ImportError:
        try:
            from legal_music.search.sources.ytdlp_source import download_via_ytdlp
        except ImportError:
            from src.legal_music.search.sources.ytdlp_source import download_via_ytdlp  # type: ignore[no-redef]

    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        dest = DOWNLOADS_DIR / "url_download"
        saved = await asyncio.get_event_loop().run_in_executor(
            None, lambda: download_via_ytdlp(url, dest)
        )
        caption = f"🎵 URL yükləməsi\n{url[:80]}"
        await _send_audio(context, saved, caption, reply_update=update)
    except Exception as exc:
        _log_error(f"handle_url:{url}", exc)
        await _safe_reply(update, f"❌ URL yüklənmədi: {exc}")


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and attempt to recover from network issues."""
    exc = context.error
    if isinstance(exc, NetworkError):
        logger.warning("Network error (will auto-reconnect): %s", exc)
    else:
        logger.error("Unhandled exception: %s", exc, exc_info=exc)
        if exc:
            _log_error("unhandled", exc)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("Starting Legal Music Bot…")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))

    # Message handlers — URLs take priority over plain text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
