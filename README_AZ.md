# legal-music — Azərbaycan Dili Bələdçisi

**legal-music** — yalnız qanuni, açıq mənbəli saytlardan (Creative Commons, Internet Archive, Bandcamp) pulsuz musiqi yükləmək üçün Python CLI aləti və Telegram botu.

---

## Quraşdırma

### Tövsiyə olunan tam quraşdırma (CLI + Telegram bot)

```bash
git clone https://github.com/a-r3/legal-music.git
cd legal-music
bash install.sh
```

Bu skript avtomatik olaraq:
- Python 3.10+, `yt-dlp` və `ffmpeg` yoxlayır
- Python asılılıqlarını qurur
- `.env` faylını Bot Token və Channel ID ilə yaradır
- `music-start` və `music-stop` qlobal əmrlərini qeyd edir
- İstəsəniz botu dərhal başladır

Quraşdırmadan sonra:

```bash
music-start
music-stop
```

### CLI-only quraşdırma

```bash
git clone https://github.com/a-r3/legal-music.git
cd legal-music
pip install --break-system-packages -e .
```

### Development quraşdırması

```bash
git clone https://github.com/a-r3/legal-music.git
cd legal-music
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## CLI İstifadəsi

### Əsas əmrlər

```bash
# Pleylist sınaq (yükləmə yoxdur)
legal-music dry my_songs.txt

# Pleylist yüklə
legal-music dl my_songs.txt

# Bütün pleylistləri yüklə (qovluq)
legal-music batch-dl ~/playlists/

# Mövcud hesabatdan statistikaya bax
legal-music stats output/my_songs/
```

### Pleylist formatı

Hər sətirdə bir mahnı, format: `İfaçı - Mahnı adı`:

```
# Şərhlər # ilə başlayır
Bach - Prelude in C Major
Beethoven - Moonlight Sonata
Dua Lipa - Levitating
```

### Nəticə qovluğu

```
output/my_songs/
  report.csv          # Mahnı statusları (downloaded/page_found/not_found)
  report.xlsx         # Rəngli Excel hesabatı
  summary.json        # Statistika
  downloads/          # Yüklənmiş fayllar
  mismatch_log.txt    # Metadata uyğunsuzluq qeydləri
  error_log.txt       # Xəta qeydləri
```

---

## Telegram Botu Quraşdırılması

### 1. Bot tokeni əldə edin

1. Telegram-da [@BotFather](https://t.me/BotFather) ilə əlaqə saxlayın
2. `/newbot` əmrini işlədin
3. Bot adı və istifadəçi adı verin
4. **Token**-i kopyalayın (məs. `123456:ABC-DEF1234...`)

### 2. Kanal ID-si tapın

- Public kanal: `@mykanaladi` (məs. `@musiqikanal`)
- Private kanal/qrup: bota qoşulun, sonra `https://api.telegram.org/bot<TOKEN>/getUpdates` ilə ID alın

### 3. `.env` faylı

`bash install.sh` bunu sizin üçün avtomatik yaradır. Əl ilə yaratmaq istəyirsinizsə:

```bash
cp .env.example .env
```

Sonra aşağıdakı dəyərləri doldurun:

```dotenv
BOT_TOKEN=123456:ABC-DEF1234...
CHANNEL_ID=@mykanaladi
SAVE_LOCAL=true
```

### 4. Botu işə salın

```bash
music-start
tail -f output/bot.log
```

Alternativ olaraq repo daxilindən:

```bash
python3 telegram_bot.py
```

### Bot əmrləri

| Əmr | Funksiya |
|-----|----------|
| `Dua Lipa - Levitating` | Mahnı axtar və yüklə |
| `https://youtube.com/...` | URL-dən yt-dlp ilə yüklə |
| `/status` | Keş ölçüsü, yüklənmiş say, mənbə statusu |
| `/help` | İstifadə qaydası |

---

## Docker ilə Yerləşdirmə (Oracle Cloud / Railway / Render)

### Docker Build

```bash
docker build -t legal-music-bot .
```

### Docker Run

```bash
docker run -d \
  --name legal-music-bot \
  --env-file .env \
  --restart unless-stopped \
  -v $(pwd)/output:/app/output \
  legal-music-bot
```

### Railway.app üçün

1. GitHub reponu Railway-ə bağlayın
2. **Variables** bölməsindən `BOT_TOKEN` və `CHANNEL_ID` əlavə edin
3. Deploy edin — `Dockerfile` avtomatik aşkarlanacaq

### Render.com üçün

1. New Web Service → GitHub repo seçin
2. Environment Variables əlavə edin
3. Dockerfile-ı avtomatik aşkarlamağa icazə verin

---

## Konfiqurasiya

Konfiqurasiya faylı: `~/.config/legal-music/config.json`

```json
{
  "source_preset": "balanced",
  "delay": 0.25,
  "timeout": 10,
  "per_song_timeout": 18
}
```

### Mənbə presetlər

| Preset | Mənbələr |
|--------|----------|
| `balanced` | Internet Archive + Free Music Archive + Bandcamp |
| `maximize` | Bandcamp + Jamendo + Pixabay Music daxil olmaqla daha geniş fallback |

```bash
# Maksimum axtarış
legal-music dl --maximize my_songs.txt

# Sürətli yoxlama
legal-music dry --fast my_songs.txt
```

---

## Qanuni Mənbələr

| Mənbə | Lisenziya | Qeyd |
|-------|-----------|------|
| Internet Archive | Public Domain + CC | Ən etibarlı |
| Free Music Archive | CC lisenziyalı | İfaçı icazəsi var |
| Bandcamp | Pulsuz yükləmə | Bəzi ifaçılar pulsuz verir |
| Jamendo | CC lisenziyalı | Əlavə seçim |
| Pixabay Music | Royalty-free | Əlavə seçim |

> **Qeyd:** Bu alət yalnız qanuni mənbələri dəstəkləyir. Piratçılıq, DRM bypass, Spotify/Apple Music/YouTube ripping dəstəklənmir.

---

## Problemlər

### "yt-dlp tapılmadı"
```bash
pip install yt-dlp
# və ya
sudo apt install yt-dlp
```

### Bot işə düşmür
```bash
# Token düzgündür?
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('BOT_TOKEN'))"
```

### Mahnı tapılmır
- Qanuni mənbələrdə bütün mahnılar mövcud deyil (xüsusən son kommersiya mahnıları)
- `--maximize` bayrağı ilə cəhd edin: `legal-music dl --maximize songs.txt`
- İfaçı adı düzgün yazılmış olmalıdır

---

## Lisenziya

MIT — ətraflı məlumat üçün [LICENSE](LICENSE) faylına baxın.
