# Badai Shinobi

Arena ninja 3D berbasis Three.js (r160) yang berjalan langsung di browser (Safari & Chrome).
Sumber awalnya artifact Claude "Badai Shinobi".

## Menjalankan

Game memuat modul dan aset lewat `fetch`, jadi harus dibuka lewat server lokal, bukan dengan klik dua kali `index.html`.

- Mac/Linux: `./jalankan-game.sh`
- Windows: klik dua kali `jalankan-game.bat`

Lalu buka http://localhost:8000. Butuh Python 3.

## Struktur

| Path | Isi |
| --- | --- |
| `index.html` | Seluruh logika game: input, pertarungan, AI CPU, HUD, menu |
| `js/arena.js` | Pemuat arena, collider, adegan sinematik |
| `js/petarung.js` | Pemuat model petarung, material, garis tinta |
| `js/penonton.js` | Penonton NPC di sekeliling arena |
| `assets/arena/` | 4 arena (glTF dalam JSON) |
| `assets/petarung/` | 4 petarung (Bayu, Gempar, Guntur, Tirta) + warna alternatif P2 |
| `assets/npc/` | Paket karakter penonton |
| `lib/three/` | Three.js dan addon-nya (lisensi MIT) |
