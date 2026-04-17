# =============================================================================
#  legal-music — Windows Installer (PowerShell)
#  Requirements: Windows 10/11, Python 3.10+, PowerShell 5+
#  Run: Right-click → "Run with PowerShell"
#       or: powershell -ExecutionPolicy Bypass -File install.ps1
# =============================================================================

$ErrorActionPreference = "Stop"
$REPO_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

function ok($msg)   { Write-Host "OK  $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function err($msg)  { Write-Host "ERR $msg" -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
function step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "       legal-music  Installer         " -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Python ─────────────────────────────────────────────────────────────
step "Checking Python..."
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
                err "Python 3.10+ required (found: $major.$minor). Download from https://python.org"
            }
        }
    } catch {}
}
if (-not $PYTHON) {
    err "Python not found. Download Python 3.10+ from https://python.org/downloads/"
}

# ── 2. pip ────────────────────────────────────────────────────────────────
step "Checking pip..."
try {
    & $PYTHON -m pip --version | Out-Null
    ok "pip available"
} catch {
    err "pip not found. Reinstall Python and make sure to select 'Add pip'."
}

# SSL-intercepting networks (corporate/antivirus proxies)
$PIP_SSL = @("--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org")

# ── 3. yt-dlp ─────────────────────────────────────────────────────────────
step "Checking yt-dlp..."
$ytdlp = Get-Command "yt-dlp" -ErrorAction SilentlyContinue
if (-not $ytdlp) {
    warn "yt-dlp not found, installing..."
    & $PYTHON -m pip install -q @PIP_SSL yt-dlp
}
$ytver = & $PYTHON -m yt_dlp --version 2>&1
ok "yt-dlp $ytver"

# ── 4. ffmpeg ─────────────────────────────────────────────────────────────
step "Checking ffmpeg..."
$FFMPEG_BIN = $null
$ff = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
if ($ff) {
    $FFMPEG_BIN = Split-Path $ff.Source
    ok "ffmpeg available ($FFMPEG_BIN)"
} else {
    warn "ffmpeg not found, installing automatically..."
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    $ffmpegOk = $false
    if ($winget) {
        try {
            winget install Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements | Out-Null
            $ffmpegOk = $true
            $FFMPEG_BIN = "$env:ProgramFiles\ffmpeg\bin"
            ok "ffmpeg installed (winget)"
        } catch {}
    }
    if (-not $ffmpegOk) {
        warn "winget unavailable, downloading manually..."
        $ffUrl  = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        $ffZip  = "$env:TEMP\ffmpeg.zip"
        $ffDest = "C:\ffmpeg"
        try {
            Write-Host "    Downloading ffmpeg (~100 MB)..." -ForegroundColor Yellow
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $ffUrl -OutFile $ffZip -UseBasicParsing
            Expand-Archive -Path $ffZip -DestinationPath "$env:TEMP\ffmpeg_extract" -Force
            $inner = Get-ChildItem "$env:TEMP\ffmpeg_extract" -Directory | Select-Object -First 1
            if (Test-Path $ffDest) { Remove-Item $ffDest -Recurse -Force }
            Move-Item $inner.FullName $ffDest
            Remove-Item $ffZip -Force
            $FFMPEG_BIN = "$ffDest\bin"
            $cur = [Environment]::GetEnvironmentVariable("Path", "Machine")
            if ($cur -notlike "*$FFMPEG_BIN*") {
                [Environment]::SetEnvironmentVariable("Path", "$cur;$FFMPEG_BIN", "Machine")
            }
            $env:Path += ";$FFMPEG_BIN"
            ok "ffmpeg installed ($FFMPEG_BIN)"
            $ffmpegOk = $true
        } catch {
            err "ffmpeg installation failed: $_"
        }
    }
}

# ── 5. Python packages ────────────────────────────────────────────────────
step "Installing Python packages..."
& $PYTHON -m pip install -q @PIP_SSL --upgrade pip
& $PYTHON -m pip install -q @PIP_SSL python-dotenv
& $PYTHON -m pip install -q @PIP_SSL -r "$REPO_DIR\requirements.txt"
& $PYTHON -m pip install -q @PIP_SSL -e "$REPO_DIR"
ok "All packages installed"

# ── 6. Directories ────────────────────────────────────────────────────────
step "Creating directories..."
New-Item -ItemType Directory -Force -Path "$REPO_DIR\output"    | Out-Null
New-Item -ItemType Directory -Force -Path "$REPO_DIR\downloads" | Out-Null
ok "output\ and downloads\ ready"

# ── 7. .env configuration ─────────────────────────────────────────────────
step "Bot configuration..."
$ENV_FILE = "$REPO_DIR\.env"

if (Test-Path $ENV_FILE) {
    warn ".env already exists."
    $overwrite = Read-Host "Reconfigure? [y/N]"
    if ($overwrite -notmatch "^[Yy]$") {
        ok ".env kept"
    } else {
        Remove-Item $ENV_FILE -Force
    }
}

if (-not (Test-Path $ENV_FILE)) {
    Write-Host ""
    Write-Host "Telegram Bot Token (get from BotFather):" -ForegroundColor White
    $BOT_TOKEN = Read-Host
    if (-not $BOT_TOKEN) { err "Bot token cannot be empty" }

    Write-Host ""
    Write-Host "Telegram Channel ID (e.g. -1001234567890):" -ForegroundColor White
    Write-Host "  If unknown: send /start to your bot, then open:" -ForegroundColor Yellow
    Write-Host "  https://api.telegram.org/bot$BOT_TOKEN/getUpdates" -ForegroundColor Yellow
    $CHANNEL_ID = Read-Host
    if (-not $CHANNEL_ID) { err "Channel ID cannot be empty" }

    $ffmpegLine = if ($FFMPEG_BIN) { "`nFFMPEG_LOCATION=$FFMPEG_BIN" } else { "" }
    $envContent = "BOT_TOKEN=$BOT_TOKEN`nCHANNEL_ID=$CHANNEL_ID`nSAVE_LOCAL=true$ffmpegLine`n"
    [System.IO.File]::WriteAllText($ENV_FILE, $envContent)
    ok ".env created"
} elseif ($FFMPEG_BIN) {
    # Update FFMPEG_LOCATION in existing .env if missing
    $existing = [System.IO.File]::ReadAllText($ENV_FILE)
    if ($existing -notmatch "FFMPEG_LOCATION") {
        [System.IO.File]::WriteAllText($ENV_FILE, $existing.TrimEnd() + "`nFFMPEG_LOCATION=$FFMPEG_BIN`n")
        ok ".env updated with FFMPEG_LOCATION"
    }
}

# ── 8. music-start.bat / music-stop.bat ──────────────────────────────────
step "Creating start/stop scripts..."

$startScript = @"
@echo off
tasklist /FI "WINDOWTITLE eq legal-music-bot" 2>nul | find /I "cmd.exe" >nul
if not errorlevel 1 (
    echo Bot is already running
    timeout /t 2 >nul
    exit /b 0
)
cd /d "$REPO_DIR"
start "legal-music-bot" /min $PYTHON telegram_bot.py
echo Bot started
timeout /t 2 >nul
"@

$stopScript = @"
@echo off
taskkill /FI "WINDOWTITLE eq legal-music-bot" /F >nul 2>&1
echo Bot stopped
timeout /t 2 >nul
"@

[System.IO.File]::WriteAllText("$REPO_DIR\music-start.bat", $startScript)
[System.IO.File]::WriteAllText("$REPO_DIR\music-stop.bat",  $stopScript)
ok "music-start.bat and music-stop.bat created"

# ── 9. Desktop shortcut ───────────────────────────────────────────────────
$desktop = [System.Environment]::GetFolderPath("Desktop")
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut("$desktop\Music Bot Start.lnk")
$sc.TargetPath       = "$REPO_DIR\music-start.bat"
$sc.WorkingDirectory = $REPO_DIR
$sc.Description      = "Start legal-music bot"
$sc.Save()
ok "Desktop shortcut 'Music Bot Start' created"

# ── 10. Verify ────────────────────────────────────────────────────────────
step "Verifying installation..."
$test = & $PYTHON -c "import telegram, mutagen, yt_dlp, dotenv; print('OK')" 2>&1
if ($test -match "OK") {
    ok "All modules working"
} else {
    warn "Some modules may be missing: $test"
}

# ── Done ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "    Installation complete!            " -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Start bot: music-start.bat          " -ForegroundColor White
Write-Host "  Stop bot:  music-stop.bat           " -ForegroundColor White
Write-Host "  Desktop shortcut created            " -ForegroundColor White
Write-Host ""

$startNow = Read-Host "Start the bot now? [Y/n]"
if ($startNow -notmatch "^[Nn]$") {
    Set-Location $REPO_DIR
    Start-Process "$REPO_DIR\music-start.bat"
}
