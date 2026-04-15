# legal-music — Azərbaycan Dili Bələdçisi

**legal-music** — yalnız qanuni, açıq mənbəli saytlardan (Creative Commons, Internet Archive, Bandcamp) pulsuz musiqi yükləmək üçün Python CLI aləti və Telegram botu.

---

## Quraşdırma

### Tələblər

- Python 3.10+
- ffmpeg (yt-dlp üçün)
- pip

### Addımlar

```bash
# 1. Repositoriyanı klonlayın
git clone https://github.com/your-org/legal-music.git
cd legal-music

# 2. Virtual mühit yaradın (tövsiyə edilir)
python3 -m venv .venv
source .venv/bin/activate

# 3. Asılılıqları quraşdırın
pip install -r requirements.txt
pip install -e .

# 4. İlkin konfiqurasiyanı yaradın
legal-music init
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

### 3. .env faylı yaradın

```bash
cp .env.example .env
```

`.env` faylını redaktə edin:

```
BOT_TOKEN=123456:ABC-DEF1234...
CHANNEL_ID=@mykanaladi
```

### 4. Botu işə salın

```bash
# Birbaşa işə sal
python telegram_bot.py

# Arxa planda işə sal
nohup python telegram_bot.py > bot.log 2>&1 &
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
| `fast` | Yalnız Internet Archive |
| `balanced` | IA + Free Music Archive + Bandcamp |
| `maximize` | Hamısı (CCMixter, Incompetech, YouTube daxil) |

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
| CCMixter | Creative Commons | Remiks cəmiyyəti |
| Incompetech | Royalty-free | Kevin MacLeod musiqisi |
| YouTube Audio Library | CC | yt-dlp vasitəsilə |
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

### "mutagen tapılmadı"
```bash
pip install mutagen fuzzywuzzy python-Levenshtein
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
