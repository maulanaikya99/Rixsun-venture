#!/bin/sh
# Jalankan Badai Shinobi lewat server lokal (Mac/Linux), lalu buka http://localhost:8000
cd "$(dirname "$0")" || exit 1
echo "Badai Shinobi berjalan di http://localhost:8000 (Ctrl+C untuk berhenti)"
( sleep 1; open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null ) &
python3 -m http.server 8000
