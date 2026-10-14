@echo off
REM Jalankan Badai Shinobi lewat server lokal (Windows), lalu buka http://localhost:8000
cd /d "%~dp0"
echo Badai Shinobi berjalan di http://localhost:8000 (tutup jendela ini untuk berhenti)
start "" http://localhost:8000
python -m http.server 8000
