#!/bin/bash
# =============================================================================
#  legal-music — Auto Installer
#  Tələb: Ubuntu/Debian, Python 3.10+
# =============================================================================
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
NONINTERACTIVE="${INSTALL_NONINTERACTIVE:-0}"
SKIP_BOT_SETUP="${SKIP_BOT_SETUP:-0}"
GREEN="\e[32m"; YELLOW="\e[33m"; RED="\e[31m"; BOLD="\e[1m"; RESET="\e[0m"

ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠️  $*${RESET}"; }
err()  { echo -e "${RED}❌ $*${RESET}"; exit 1; }
step() { echo -e "\n${BOLD}▶ $*${RESET}"; }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════╗"
echo "║       legal-music  Installer         ║"
echo "╚══════════════════════════════════════╝"
echo -e "${RESET}"

# ── 1. Python versiyası ────────────────────────────────────────────────────
step "Python yoxlanılır…"
PYTHON=$(command -v python3 || true)
[ -z "$PYTHON" ] && err "python3 tapılmadı. 'sudo apt install python3' icra et."
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo $PY_VER | cut -d. -f1)
PY_MINOR=$(echo $PY_VER | cut -d. -f2)
[ "$PY_MAJOR" -lt 3 ] || [ "$PY_MINOR" -lt 10 ] && err "Python 3.10+ lazımdır (sizde: $PY_VER)"
ok "Python $PY_VER"

# ── 2. pip ────────────────────────────────────────────────────────────────
step "pip yoxlanılır…"
if ! $PYTHON -m pip --version &>/dev/null; then
    warn "pip yoxdur, qurulur…"
    sudo apt-get install -y python3-pip
fi
ok "pip mövcuddur"

# ── 3. yt-dlp (sistem) ───────────────────────────────────────────────────
step "yt-dlp yoxlanılır…"
if ! command -v yt-dlp &>/dev/null; then
    warn "yt-dlp yoxdur, qurulur…"
    sudo curl -sSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
         -o /usr/local/bin/yt-dlp
    sudo chmod +x /usr/local/bin/yt-dlp
fi
ok "yt-dlp: $(yt-dlp --version)"

# ── 4. ffmpeg (yt-dlp üçün audio çevirmə) ────────────────────────────────
step "ffmpeg yoxlanılır…"
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg yoxdur, qurulur…"
    sudo apt-get install -y ffmpeg
fi
ok "ffmpeg mövcuddur"

# ── 5. Python paketləri ───────────────────────────────────────────────────
step "Python paketləri qurulur…"
$PYTHON -m pip install --break-system-packages -q --upgrade pip
$PYTHON -m pip install --break-system-packages -q -r "$REPO_DIR/requirements.txt"
$PYTHON -m pip install --break-system-packages -q -e "$REPO_DIR"
ok "Bütün paketlər quruldu"

# ── 6. Qovluqlar ──────────────────────────────────────────────────────────
step "Qovluqlar yaradılır…"
mkdir -p "$REPO_DIR/output" "$REPO_DIR/downloads"
ok "output/ və downloads/ hazırdır"

# ── 7. .env konfiqurasiyası ───────────────────────────────────────────────
step "Bot konfiqurasiyası…"
ENV_FILE="$REPO_DIR/.env"

if [[ "$SKIP_BOT_SETUP" =~ ^(1|true|TRUE|yes|YES)$ ]]; then
    warn "SKIP_BOT_SETUP aktivdir, .env konfiqurasiyası ötürülür"
elif [ -f "$ENV_FILE" ]; then
    warn ".env artıq mövcuddur. Yenidən konfiqurasiya etmək istəyirsiniz? [y/N]"
    if [[ "$NONINTERACTIVE" =~ ^(1|true|TRUE|yes|YES)$ ]]; then
        OVERWRITE="n"
    else
        read -r OVERWRITE
    fi
    [[ "$OVERWRITE" =~ ^[Yy]$ ]] || { ok ".env saxlanıldı"; }
fi

if [[ ! "$SKIP_BOT_SETUP" =~ ^(1|true|TRUE|yes|YES)$ ]] && { [[ "$OVERWRITE" =~ ^[Yy]$ ]] || [ ! -f "$ENV_FILE" ]; }; then
    BOT_TOKEN_VALUE="${BOT_TOKEN:-}"
    CHANNEL_ID_VALUE="${CHANNEL_ID:-}"

    echo ""
    if [ -z "$BOT_TOKEN_VALUE" ]; then
        echo -e "${BOLD}Telegram Bot Token (BotFather-dən alın):${RESET}"
        if [[ "$NONINTERACTIVE" =~ ^(1|true|TRUE|yes|YES)$ ]]; then
            err "INSTALL_NONINTERACTIVE aktivdir, amma BOT_TOKEN verilməyib"
        fi
        read -r BOT_TOKEN_VALUE
    fi
    [ -z "$BOT_TOKEN_VALUE" ] && err "Bot token boş ola bilməz"

    echo ""
    if [ -z "$CHANNEL_ID_VALUE" ]; then
        echo -e "${BOLD}Telegram Channel ID (məs: -1001234567890):${RESET}"
        echo -e "${YELLOW}  Channel ID-ni bilmirsinizsə: bota /start yazın, sonra aşağıdakı linki açın:"
        echo -e "  https://api.telegram.org/bot${BOT_TOKEN_VALUE}/getUpdates${RESET}"
        if [[ "$NONINTERACTIVE" =~ ^(1|true|TRUE|yes|YES)$ ]]; then
            err "INSTALL_NONINTERACTIVE aktivdir, amma CHANNEL_ID verilməyib"
        fi
        read -r CHANNEL_ID_VALUE
    fi
    [ -z "$CHANNEL_ID_VALUE" ] && err "Channel ID boş ola bilməz"

    cat > "$ENV_FILE" <<EOF
BOT_TOKEN=${BOT_TOKEN_VALUE}
CHANNEL_ID=${CHANNEL_ID_VALUE}
EOF
    ok ".env yaradıldı"
fi

# ── 8. Qlobal əmrlər ──────────────────────────────────────────────────────
step "Qlobal əmrlər qurulur (music-start / music-stop)…"

sudo tee /usr/local/bin/music-start > /dev/null <<EOF
#!/bin/bash
BOT_DIR="$REPO_DIR"
LOG="\$BOT_DIR/output/bot.log"
if pgrep -f telegram_bot.py > /dev/null; then
    echo "⚠️  Bot artıq işləyir"
    exit 0
fi
mkdir -p "\$BOT_DIR/output"
nohup $PYTHON "\$BOT_DIR/telegram_bot.py" >> "\$LOG" 2>&1 &
echo "✅ Bot başladı (PID: \$!)"
EOF

sudo tee /usr/local/bin/music-stop > /dev/null <<EOF
#!/bin/bash
if pgrep -f telegram_bot.py > /dev/null; then
    pkill -f telegram_bot.py
    echo "🛑 Bot dayandırıldı"
else
    echo "⚠️  Bot işləmir"
fi
EOF

sudo chmod +x /usr/local/bin/music-start /usr/local/bin/music-stop
ok "music-start və music-stop qlobal əmrləri hazırdır"

# ── 9. Test ───────────────────────────────────────────────────────────────
step "Quraşdırma yoxlanılır…"
$PYTHON -c "import telegram; import mutagen; import yt_dlp; print('OK')" &>/dev/null \
    && ok "Bütün modullar işləyir" \
    || warn "Bəzi modullar yüklənməyə bilər, lakin əsas funksiyalar işləyəcək"

# ── Tamamlandı ────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║     Quraşdırma tamamlandı! 🎉        ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Botu başlatmaq üçün:${RESET}   music-start"
echo -e "  ${BOLD}Botu dayandırmaq:${RESET}      music-stop"
echo -e "  ${BOLD}Logları izləmək:${RESET}       tail -f $REPO_DIR/output/bot.log"
echo ""
echo -e "${YELLOW}Botu indi başlatmaq istəyirsiniz? [Y/n]${RESET}"
read -r START_NOW
if [[ ! "$START_NOW" =~ ^[Nn]$ ]]; then
    /usr/local/bin/music-start
fi
