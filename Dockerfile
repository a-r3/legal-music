# legal-music Dockerfile
# Suitable for Oracle Cloud, Railway, Render, and any container platform.
#
# Build:  docker build -t legal-music-bot .
# Run:    docker run --env-file .env legal-music-bot

FROM python:3.12-slim

# System deps: ffmpeg for yt-dlp audio conversion, git for version info
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash lmuser
WORKDIR /app

# Copy and install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Install the package in editable mode so `legal_music` is importable
RUN pip install --no-cache-dir -e .

# Create output and cache directories with correct ownership
RUN mkdir -p output /home/lmuser/.local/share/legal-music/cache \
    && chown -R lmuser:lmuser /app /home/lmuser

USER lmuser

# Healthcheck: verify python + legal-music import work
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import legal_music; print('ok')" || exit 1

# Default: run the Telegram bot
CMD ["python", "telegram_bot.py"]
