# =============================================================================
#  legal-music — Windows Installer (PowerShell)
#  Tələb: Windows 10/11, Python 3.10+, PowerShell 5+
#  İcra: Right-click → "Run with PowerShell"
#        və ya: powershell -ExecutionPolicy Bypass -File install.ps1
# =============================================================================

$ErrorActionPreference = "Stop"
$REPO_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

function ok($msg)   { Write-Host "OK  $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function err($msg)  { Write-Host "ERR $msg" -ForegroundColor Red; Read-Host "Enter duymesine basin"; exit 1 }
function step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "       legal-music  Installer         " -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Python ─────────────────────────────────────────────────────────────
step "Python yoxlanilir..."
$PYTHON = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
                $PYTHON = $cmd
                ok "Python $major.$minor ($cmd)"
                break
            } else {
                err "Python 3.10+ lazimdir (sizde: $major.$minor). https://python.org dan yukleyin."
            }
        }
    } catch {}
}
if (-not $PYTHON) {
    err "Python tapilmadi. https://python.org/downloads/ adresinden Python 3.10+ yukleyin."
}

# ── 2. pip ────────────────────────────────────────────────────────────────
step "pip yoxlanilir..."
try {
    & $PYTHON -m pip --version | Out-Null
    ok "pip mövcuddur"
} catch {
    err "pip tapilmadi. Python-u yeniden qurarkən 'Add pip' seceneyi secin."
}

# ── 3. yt-dlp ─────────────────────────────────────────────────────────────
step "yt-dlp yoxlanilir..."
$ytdlp = Get-Command "yt-dlp" -ErrorAction SilentlyContinue
if (-not $ytdlp) {
    warn "yt-dlp yoxdur, pip ile qurulur..."
    & $PYTHON -m pip install -q yt-dlp
}
$ytver = & yt-dlp --version 2>&1
ok "yt-dlp $ytver"

# ── 4. ffmpeg ─────────────────────────────────────────────────────────────
step "ffmpeg yoxlanilir..."
$ff = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
if (-not $ff) {
    warn "ffmpeg tapilmadi."
    # winget ile cehd et
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($winget) {
        warn "winget ile ffmpeg qurulur..."
        try {
            winget install Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
            ok "ffmpeg quruldu (winget)"
        } catch {
            warn "winget ile qurmaq olmadi."
            warn "Manual qurmaq ucun: https://www.gyan.dev/ffmpeg/builds/"
            warn "ffmpeg/bin/ qovlugunu PATH-e elave edin, sonra bu skripti yeniden icra edin."
            Read-Host "ffmpeg-i qurduqdan sonra Enter duymesine basin"
        }
    } else {
        warn "winget tapilmadi. ffmpeg-i manual qurun:"
        warn "  1. https://www.gyan.dev/ffmpeg/builds/ -> ffmpeg-release-essentials.zip yukle"
        warn "  2. C:\ffmpeg\ qovluguna cixar"
        warn "  3. Sistem PATH-ine C:\ffmpeg\bin elave et"
        Read-Host "ffmpeg-i qurduqdan sonra Enter duymesine basin"
    }
} else {
    ok "ffmpeg mövcuddur"
}

# ── 5. Python paketleri ───────────────────────────────────────────────────
step "Python paketleri qurulur..."
& $PYTHON -m pip install -q --upgrade pip
& $PYTHON -m pip install -q -r "$REPO_DIR\requirements.txt"
& $PYTHON -m pip install -q -e "$REPO_DIR"
ok "Butun paketler quruldu"

# ── 6. Qovluqlar ──────────────────────────────────────────────────────────
step "Qovluqlar yaradilir..."
New-Item -ItemType Directory -Force -Path "$REPO_DIR\output"    | Out-Null
New-Item -ItemType Directory -Force -Path "$REPO_DIR\downloads" | Out-Null
ok "output\ ve downloads\ hazirdir"

# ── 7. .env konfiqurasiyasi ───────────────────────────────────────────────
step "Bot konfiqurasiyasi..."
$ENV_FILE = "$REPO_DIR\.env"

if (Test-Path $ENV_FILE) {
    warn ".env artiq movcuddur."
    $overwrite = Read-Host "Yeniden konfiqurasiya etmek isteyirsiniz? [y/N]"
    if ($overwrite -notmatch "^[Yy]$") {
        ok ".env saxlanildi"
    } else {
        Remove-Item $ENV_FILE -Force
    }
}

if (-not (Test-Path $ENV_FILE)) {
    Write-Host ""
    Write-Host "Telegram Bot Token (BotFather-den alin):" -ForegroundColor White
    $BOT_TOKEN = Read-Host
    if (-not $BOT_TOKEN) { err "Bot token bos ola bilmez" }

    Write-Host ""
    Write-Host "Telegram Channel ID (mes: -1001234567890):" -ForegroundColor White
    Write-Host "  Bilmirsinizse: bota /start yazin, sonra acin:" -ForegroundColor Yellow
    Write-Host "  https://api.telegram.org/bot$BOT_TOKEN/getUpdates" -ForegroundColor Yellow
    $CHANNEL_ID = Read-Host
    if (-not $CHANNEL_ID) { err "Channel ID bos ola bilmez" }

    "BOT_TOKEN=$BOT_TOKEN`nCHANNEL_ID=$CHANNEL_ID`nSAVE_LOCAL=true" | Set-Content $ENV_FILE -Encoding UTF8
    ok ".env yaradildi"
}

# ── 8. music-start.bat / music-stop.bat ──────────────────────────────────
step "Baslat/dayandır skriptleri yaradilir..."

$startScript = @"
@echo off
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq telegram_bot*" 2>nul | find /I "python.exe" >nul
if not errorlevel 1 (
    echo Bot artiq isleyir
    pause
    exit /b 0
)
cd /d "$REPO_DIR"
start "legal-music-bot" /min $PYTHON telegram_bot.py
echo Bot basladi
"@

$stopScript = @"
@echo off
taskkill /FI "WINDOWTITLE eq legal-music-bot" /F >nul 2>&1
taskkill /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *telegram_bot*" /F >nul 2>&1
echo Bot dayandırildi
pause
"@

$startScript | Set-Content "$REPO_DIR\music-start.bat" -Encoding UTF8
$stopScript  | Set-Content "$REPO_DIR\music-stop.bat"  -Encoding UTF8
ok "music-start.bat ve music-stop.bat yaradildi"

# ── 9. Desktop shortcut (optional) ───────────────────────────────────────
$desktop = [System.Environment]::GetFolderPath("Desktop")
$wsh = New-Object -ComObject WScript.Shell

$sc = $wsh.CreateShortcut("$desktop\Music Bot Start.lnk")
$sc.TargetPath  = "$REPO_DIR\music-start.bat"
$sc.WorkingDirectory = $REPO_DIR
$sc.Description = "legal-music botu basladır"
$sc.Save()
ok "Desktop-da 'Music Bot Start' shortcut yaradildi"

# ── 10. Test ──────────────────────────────────────────────────────────────
step "Qurasdirma yoxlanilir..."
$test = & $PYTHON -c "import telegram, mutagen, yt_dlp; print('OK')" 2>&1
if ($test -match "OK") {
    ok "Butun modullar isleyir"
} else {
    warn "Bezi modullar yuklenmeye biler: $test"
}

# ── Tamamlandi ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "    Qurasdirma tamamlandi!            " -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Botu baslatmaq: music-start.bat     " -ForegroundColor White
Write-Host "  Botu dayandirmaq: music-stop.bat    " -ForegroundColor White
Write-Host "  Desktop-da shortcut yaradildi       " -ForegroundColor White
Write-Host ""

$startNow = Read-Host "Botu indi baslatmaq isteyirsiniz? [Y/n]"
if ($startNow -notmatch "^[Nn]$") {
    Set-Location $REPO_DIR
    Start-Process "$REPO_DIR\music-start.bat"
}
