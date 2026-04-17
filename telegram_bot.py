"""Telegram bot for legal-music.

Xüsusiyyətlər:
  - Mahnı adı ilə axtarış  → qanuni mənbələr, tapılmazsa yt-dlp fallback
  - URL göndər             → birbaşa yt-dlp ilə yüklə
  - .txt fayl göndər       → toplu yükləmə (hər sətir bir mahnı)
  - /status, /help, /start
  - Canlı progress mesajları (edit_text ilə yenilənir)

BOT_TOKEN və CHANNEL_ID → .env faylından oxunur
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
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
    from telegram import Message, Update
    from telegram.error import NetworkError, TelegramError
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    logger.error("python-telegram-bot not installed: pip install python-telegram-bot")
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
        logger.error("legal-music package not found: pip install -e .")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN: str  = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")
DOWNLOADS_DIR   = Path(os.getenv("DOWNLOADS_DIR", str(default_output_dir() / "bot_downloads")))
DB_PATH         = default_data_dir() / "cache" / "bot_cache.db"

# SAVE_LOCAL=true  → yüklənmiş fayllar cihazda saxlanılır (default)
# SAVE_LOCAL=false → Telegram-a göndərildikdən sonra fayllar silinir
SAVE_LOCAL: bool = os.getenv("SAVE_LOCAL", "true").strip().lower() != "false"

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found. Check your .env file.")
    sys.exit(1)

logger.info("Downloads dir: %s | Save local: %s",
            DOWNLOADS_DIR, "enabled" if SAVE_LOCAL else "disabled")

_URL_RE      = re.compile(r"https?://[^\s]+|www\.[^\s]+|youtu\.be/[^\s]+", re.IGNORECASE)
_SEP_RE      = re.compile(r"\s*[/|,–—]\s*|\s+by\s+|\s*:\s*", re.IGNORECASE)
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
# Progress message helper
# ---------------------------------------------------------------------------

async def _safe_edit(msg: Optional[Message], text: str) -> None:
    """Mesajı yenilə; xəta olarsa susqun keç."""
    if not msg:
        return
    try:
        await msg.edit_text(text)
    except Exception:
        pass


async def _safe_reply(update: Update, text: str) -> Optional[Message]:
    """Cavab göndər; mesaj obyektini qaytar (sonradan edit üçün)."""
    try:
        if update.message:
            return await update.message.reply_text(text, parse_mode=None)
    except Exception as exc:
        logger.warning("reply failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Audio göndər
# ---------------------------------------------------------------------------

def _parse_title_performer(song: str) -> tuple[str, str | None]:
    """'Dua Lipa - Levitating' → ('Levitating', 'Dua Lipa')"""
    parts = song.split(" - ", 1)
    if len(parts) == 2:
        return parts[1].strip(), parts[0].strip()
    return song.strip(), None


async def _send_audio(
    context: ContextTypes.DEFAULT_TYPE,
    file_path: Path,
    caption: str,
    reply_update: Update | None = None,
    title: str | None = None,
    performer: str | None = None,
) -> None:
    global _downloads_total
    _downloads_total += 1

    # title verilməyibsə faylın adından çıxar (yt-dlp %(title)s formatı)
    display_title     = title     or file_path.stem
    display_performer = performer or None

    async def _one(chat_id: str | int) -> None:
        try:
            with file_path.open("rb") as f:
                await context.bot.send_audio(
                    chat_id=chat_id, audio=f,
                    caption=caption[:1024],
                    title=display_title[:64],
                    performer=display_performer,
                    read_timeout=60, write_timeout=60,
                )
        except TelegramError as e:
            logger.warning("send_audio error (%s): %s", chat_id, e)

    if CHANNEL_ID:
        await _one(CHANNEL_ID)
    if reply_update and reply_update.effective_chat:
        cid = reply_update.effective_chat.id
        if str(cid) != str(CHANNEL_ID):
            await _one(cid)

    if not SAVE_LOCAL:
        try:
            file_path.unlink(missing_ok=True)
            logger.debug("File deleted (SAVE_LOCAL=false): %s", file_path.name)
        except Exception as exc:
            logger.warning("File deletion failed: %s", exc)


# ---------------------------------------------------------------------------
# yt-dlp fallback
# ---------------------------------------------------------------------------

async def _ytdlp_download(target: str, dest_dir: Path) -> Path:
    """URL və ya axtarış sorğusu ilə MP3 yüklə.

    Unikal temp qovluğa yükləyir → yalnız o qovluqdakı mp3-ü tapır →
    dest_dir-ə köçürür. Fayl adı yt-dlp-in %(title)s-indən gəlir.
    """
    import subprocess
    import shutil as _shutil

    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp quraşdırılmayıb")

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Hər yükləmə üçün ayrı temp qovluq — başqa fayllarla qarışıq olmur
    tmp_dir = dest_dir / f"_tmp_{os.getpid()}_{id(target) & 0xFFFF:04x}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    source = target if target.startswith("http") else f"ytsearch1:{target}"

    ffmpeg_loc = os.getenv("FFMPEG_LOCATION", "").strip()
    if not ffmpeg_loc:
        for candidate in [r"C:\ffmpeg\bin", r"C:\ffmpeg"]:
            if Path(candidate).exists():
                ffmpeg_loc = candidate
                break

    cmd = [
        "yt-dlp", source,
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", str(tmp_dir / "%(title)s.%(ext)s"),
        "--no-warnings", "--quiet",
        "--no-playlist",
        "--extractor-args", "youtube:player_client=android,web",
    ]
    if ffmpeg_loc:
        cmd += ["--ffmpeg-location", ffmpeg_loc]
    browser = os.getenv("YTDLP_BROWSER", "").strip()
    if browser:
        cmd += ["--cookies-from-browser", browser]

    def _run() -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:300] or "yt-dlp xətası")

    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)

        mp3_files = list(tmp_dir.glob("*.mp3"))
        if not mp3_files:
            raise RuntimeError("yt-dlp: fayl yaradılmadı")

        src = mp3_files[0]
        dst = dest_dir / src.name
        # Eyni adlı fayl varsa, üzərinə yaz (yenilənmiş versiya)
        _shutil.move(str(src), str(dst))
        return dst
    finally:
        # Temp qovluğu təmizlə
        try:
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# köhnə adı saxla — geriyə uyğunluq üçün
_ytdlp_search_download = _ytdlp_download


# ---------------------------------------------------------------------------
# Core: bir mahnını axtar + yüklə
# ---------------------------------------------------------------------------

async def _search_and_download(
    song: str,
    context: ContextTypes.DEFAULT_TYPE,
    reply_update: Update | None = None,
    status_msg: Optional[Message] = None,
) -> bool:
    """Mahnını axtar, yüklə, göndər. Uğursa True qaytarır.

    status_msg varsa, hər mərhələdə həmin mesajı edit edir
    (ayrı mesaj göndərmir).
    """
    queries       = _smart_queries(song)
    cfg           = _get_cfg()
    result        = None
    matched_query = song

    # ── Mərhələ 1: qanuni mənbələr ─────────────────────────────────────────
    await _safe_edit(status_msg, f"⏳ Qanuni mənbələrdə axtarılır…\n🎵 {song}")

    for attempt in queries:
        runner = AsyncSearchRunner(cfg, max_concurrent=1, db_path=DB_PATH)
        res    = await runner.search_one(attempt)
        runner.close()
        if res.status in (SongStatus.DOWNLOADED, SongStatus.PAGE_FOUND):
            result        = res
            matched_query = attempt
            break

    # ── Mərhələ 2: tapıldısa yüklə ─────────────────────────────────────────
    if result and result.status == SongStatus.DOWNLOADED and result.direct_url:
        try:
            await _safe_edit(status_msg, f"⬇️ Yüklənir…\n🎵 {matched_query}")
            DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            saved = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: download_file(result.direct_url, matched_query, DOWNLOADS_DIR),
            )
            await _safe_edit(status_msg, f"📤 Göndərilir…\n🎵 {matched_query}")
            t, p = _parse_title_performer(matched_query)
            await _send_audio(context, saved, f"🎵 {matched_query}\n📂 {result.source}",
                               reply_update, title=t, performer=p)
            return True
        except Exception as exc:
            logger.warning("Legal source download error (%s): %s", song, exc)

    # ── Mərhələ 3: yt-dlp YouTube fallback ────────────────────────────────
    await _safe_edit(status_msg, f"🔄 YouTube-da axtarılır…\n🎵 {song}")
    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        saved = await _ytdlp_search_download(song, DOWNLOADS_DIR)
        await _safe_edit(status_msg, f"📤 Göndərilir…\n🎵 {song}")
        t, p = _parse_title_performer(song)
        # yt-dlp faylı %(title)s ilə adlandırır — həm stem-i, həm song-u göstər
        await _send_audio(context, saved, f"🎵 {song}\n📂 YouTube (yt-dlp)",
                          reply_update, title=saved.stem[:64], performer=p)
        return True
    except Exception as exc:
        logger.warning("yt-dlp search error (%s): %s", song, exc)
        return False


# ---------------------------------------------------------------------------
# Batch progress helper
# ---------------------------------------------------------------------------

class _BatchProgress:
    """Batch yükləmə üçün canlı progress mesajı idarə edir."""

    _ICON = {"pending": "⬜", "active": "⏳", "ok": "✅", "fail": "❌"}
    _MAX_VISIBLE = 12   # mesajda göstərilən maksimum sətir sayı

    def __init__(self, songs: list[str], msg: Message) -> None:
        self.songs    = songs
        self.total    = len(songs)
        self.states   = ["pending"] * len(songs)
        self.msg      = msg
        self.ok_count = 0
        self.fail_count = 0

    def set_active(self, i: int) -> None:
        self.states[i] = "active"

    def set_done(self, i: int, ok: bool) -> None:
        self.states[i] = "ok" if ok else "fail"
        if ok:
            self.ok_count += 1
        else:
            self.fail_count += 1

    def _progress_bar(self) -> str:
        done  = self.ok_count + self.fail_count
        filled = round(10 * done / self.total) if self.total else 0
        return "█" * filled + "░" * (10 - filled)

    async def render(self) -> None:
        done  = self.ok_count + self.fail_count
        bar   = self._progress_bar()
        lines = [f"📋 {bar}  {done}/{self.total}  (✅{self.ok_count} ❌{self.fail_count})\n"]

        # Cari aktiv indeksi tap
        active_i = next(
            (i for i, s in enumerate(self.states) if s == "active"), done
        )

        # Görünən pəncərə: aktiv sətrin ətrafı
        start = max(0, active_i - self._MAX_VISIBLE + 3)
        end   = min(self.total, start + self._MAX_VISIBLE)

        if start > 0:
            lines.append(f"  ↑ {start} mahnı")

        for i in range(start, end):
            icon  = self._ICON[self.states[i]]
            label = self.songs[i][:45]
            lines.append(f"{icon} {label}")

        if end < self.total:
            lines.append(f"  ↓ {self.total - end} mahnı")

        await _safe_edit(self.msg, "\n".join(lines))

    async def finish(self, fail_list: list[str]) -> None:
        text = (
            f"📊 Tamamlandı!\n\n"
            f"✅ Yükləndi: {self.ok_count}/{self.total}\n"
            f"❌ Tapılmadı: {self.fail_count}/{self.total}"
        )
        if fail_list:
            text += "\n\nTapılmayanlar:\n" + "\n".join(f"• {s}" for s in fail_list[:20])
            if len(fail_list) > 20:
                text += f"\n… və {len(fail_list) - 20} daha"
        await _safe_edit(self.msg, text)


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
        "/help  /status"
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
        "  songs.txt göndər — hər sətirdə bir mahnı\n\n"
        "/status — statistika\n"
        "/help   — bu mesaj"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        stats  = _get_db().stats()
        ytdlp  = "✅" if shutil.which("yt-dlp") else "❌"
        sources = ", ".join(_get_cfg().enabled_source_names())
        await _safe_reply(update,
            f"📊 Bot Statusu\n\n"
            f"💾 Keş (sorğu): {stats.get('query_cache_entries', 0)}\n"
            f"💾 Keş (mahnı): {stats.get('song_cache_entries', 0)}\n"
            f"✅ Bu sessiyada yüklənmiş: {_downloads_total}\n"
            f"🎯 Aktiv mənbələr: {sources}\n"
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

    # Canlı status mesajı göndər, sonra mərhələ-mərhələ edit edirik
    status_msg = await _safe_reply(update, f"🔍 Axtarılır: {text}…")
    found = await _search_and_download(
        text, context,
        reply_update=update,
        status_msg=status_msg,
    )

    if found:
        # Status mesajını sil — audio artıq göndərilib
        try:
            if status_msg:
                await status_msg.delete()
        except Exception:
            pass
    else:
        await _safe_edit(
            status_msg,
            f"❌ Tapılmadı: {text}\n\n"
            f"💡 Format: İfaçı - Mahnı adı\n"
            f"Nümunə: Dua Lipa - Levitating",
        )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """URL mesajı → yt-dlp ilə yüklə."""
    if not update.message or not update.message.text:
        return
    text  = update.message.text.strip()
    match = _URL_RE.search(text)
    if not match:
        return
    url = match.group(0)

    if not shutil.which("yt-dlp"):
        await _safe_reply(update, "❌ yt-dlp quraşdırılmayıb: pip install yt-dlp")
        return

    status_msg = await _safe_reply(update, "⬇️ URL yüklənir…")

    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        # _ytdlp_download URL-i birbaşa yükləyir, fayl adı %(title)s olur
        saved = await _ytdlp_download(url, DOWNLOADS_DIR)
        await _safe_edit(status_msg, "📤 Göndərilir…")
        await _send_audio(context, saved, f"🎵 {saved.stem}",
                          reply_update=update, title=saved.stem[:64])
        try:
            if status_msg:
                await status_msg.delete()
        except Exception:
            pass
    except Exception as exc:
        _log_error(f"handle_url:{url}", exc)
        await _safe_edit(status_msg, f"❌ URL yüklənmədi: {exc}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """TXT fayl → toplu yükləmə (canlı progress ilə)."""
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await _safe_reply(update, "⚠️ Yalnız .txt faylı göndərin (hər sətirdə bir mahnı)")
        return

    status_msg = await _safe_reply(update, "📄 Fayl alındı, oxunur…")

    # ── Faylı yüklə ───────────────────────────────────────────────────────
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await tg_file.download_to_drive(tmp_path)
    except Exception as exc:
        _log_error("handle_document:download", exc)
        await _safe_edit(status_msg, f"❌ Fayl yüklənmədi: {exc}")
        return

    # ── Mahnı adlarını oxu ────────────────────────────────────────────────
    try:
        songs = read_playlist(tmp_path)
        tmp_path.unlink(missing_ok=True)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        await _safe_edit(status_msg, f"❌ Fayl oxunmadı: {exc}")
        return

    if not songs:
        await _safe_edit(status_msg, "⚠️ Faylda mahnı tapılmadı.")
        return

    # ── Batch progress başlat ─────────────────────────────────────────────
    progress = _BatchProgress(songs, status_msg)  # type: ignore[arg-type]
    await progress.render()

    fail_list: list[str] = []

    for i, song in enumerate(songs):
        progress.set_active(i)
        await progress.render()

        try:
            found = await _search_and_download(
                song, context,
                reply_update=None,   # batch-də ayrı cavab göndərmirik
                status_msg=None,     # progress mesajını batch özü idarə edir
            )
        except Exception as exc:
            _log_error(f"batch:{song}", exc)
            found = False

        progress.set_done(i, found)
        if not found:
            fail_list.append(song)
        await progress.render()

    # ── Yekun ─────────────────────────────────────────────────────────────
    await progress.finish(fail_list)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    exc = context.error
    if isinstance(exc, NetworkError):
        logger.warning("Network error (auto-reconnecting): %s", exc)
    else:
        logger.error("Error: %s", exc, exc_info=exc)
        if exc:
            _log_error("unhandled", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Legal Music Bot starting...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))

    app.add_handler(MessageHandler(filters.Document.ALL,         handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(error_handler)

    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
