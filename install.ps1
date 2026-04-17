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
$PIP_SSL = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org")
$ytdlp = Get-Command "yt-dlp" -ErrorAction SilentlyContinue
if (-not $ytdlp) {
    warn "yt-dlp yoxdur, pip ile qurulur..."
    & $PYTHON -m pip install -q @PIP_SSL yt-dlp
}
$ytver = & $PYTHON -m yt_dlp --version 2>&1
ok "yt-dlp $ytver"

# ── 4. ffmpeg ─────────────────────────────────────────────────────────────
step "ffmpeg yoxlanilir..."
$ff = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
if (-not $ff) {
    warn "ffmpeg tapilmadi, avtomatik qurulur..."
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    $ffmpegOk = $false
    if ($winget) {
        try {
            winget install Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements | Out-Null
            $ffmpegOk = $true
            ok "ffmpeg quruldu (winget)"
        } catch {}
    }
    if (-not $ffmpegOk) {
        warn "winget yoxdur/islemedi, manual yukleme baslanir..."
        $ffUrl  = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        $ffZip  = "$env:TEMP\ffmpeg.zip"
        $ffDest = "C:\ffmpeg"
        try {
            Write-Host "    ffmpeg yuklenir (~ 100 MB)..." -ForegroundColor Yellow
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $ffUrl -OutFile $ffZip -UseBasicParsing
            Expand-Archive -Path $ffZip -DestinationPath "$env:TEMP\ffmpeg_extract" -Force
            $inner = Get-ChildItem "$env:TEMP\ffmpeg_extract" -Directory | Select-Object -First 1
            if (Test-Path $ffDest) { Remove-Item $ffDest -Recurse -Force }
            Move-Item $inner.FullName $ffDest
            Remove-Item $ffZip -Force
            $binPath = "$ffDest\bin"
            $cur = [Environment]::GetEnvironmentVariable("Path", "Machine")
            if ($cur -notlike "*$binPath*") {
                [Environment]::SetEnvironmentVariable("Path", "$cur;$binPath", "Machine")
            }
            $env:Path += ";$binPath"
            ok "ffmpeg quruldu (manual: $ffDest)"
            $ffmpegOk = $true
        } catch {
            err "ffmpeg qurulmadi: $_"
        }
    }
} else {
    ok "ffmpeg mövcuddur"
}

# ── 5. Python paketleri ───────────────────────────────────────────────────
step "Python paketleri qurulur..."
& $PYTHON -m pip install -q @PIP_SSL --upgrade pip
& $PYTHON -m pip install -q @PIP_SSL -r "$REPO_DIR\requirements.txt"
& $PYTHON -m pip install -q @PIP_SSL -e "$REPO_DIR"
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
