#!/bin/bash
cd /home/oem/Documents/01_Projects/legal-music
pkill -f telegram_bot.py 2>/dev/null
nohup python3 telegram_bot.py >> output/bot.log 2>&1 &
echo "✅ Bot başladı (PID: $!)"
echo "📄 Log: tail -f output/bot.log"
