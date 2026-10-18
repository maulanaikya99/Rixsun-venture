# Sejarah Komputer: Dari Mesin Mekanis hingga Era Kecerdasan Buatan

Pipeline video dokumenter *motion graphics* berbahasa Indonesia, dibangun dengan Python.

- **Narasi:** Microsoft Edge-TTS (`id-ID-GadisNeural`, wanita).
- **Grafik:** vektor dari Cairo, dirender langsung ke FFmpeg.
- **Musik dan SFX:** generatif dengan NumPy, bebas lisensi.
- **Subtitle:** disinkronkan dari timing kata aktual TTS.

Output utama: **1920×1080, 30 fps, H.264 + AAC, 9:59 menit, 11 scene, 136 subtitle.**

```
python main.py --all          # naskah → voice → subtitle → mix audio → render final → QC
```

---

## 1. Kebutuhan

| Komponen | Versi yang diuji | Catatan |
|---|---|---|
| Python | 3.13 (≥ 3.10) | |
| FFmpeg + FFprobe | 6.1 | perlu `libx264`, `aac`, `loudnorm`, `sidechaincompress`, `blackdetect` |
| edge-tts | 7.3.1 | butuh internet ke `speech.platform.bing.com` |
| pycairo | 1.29 (Cairo 1.18) | grafik vektor anti-aliasing dan tipografi |
| NumPy, Pillow | 2.5, 12.3 | sintesis audio, contact sheet QC |
| Font | Inter, Inter Display, DejaVu Sans Mono | bisa diganti di `config/project.json` |

Instalasi:

```bash
pip install -r requirements.txt
# Ubuntu/Debian : sudo apt install ffmpeg libcairo2-dev fonts-inter
# macOS         : brew install ffmpeg cairo pkg-config && brew install --cask font-inter
# Windows       : pakai FFmpeg build dari gyan.dev (tambahkan ke PATH); pycairo tersedia sebagai wheel
python main.py --check        # verifikasi semua dependency dan font
```

## 2. Perintah CLI

| Perintah | Fungsi |
|---|---|
| `--check` | Periksa Python, FFmpeg (beserta encoder/filter), modul, dan font |
| `--list-voices [--locale id-]` | Daftar voice Edge-TTS |
| `--say "teks"` | Render satu kalimat uji ke `output/previews/say.mp3`, untuk menyetel preset atau pengucapan |
| `--generate-script` | Validasi naskah, lalu ekspor `output/script/storyboard.md` dan `narasi.txt` |
| `--generate-voice` | Generate voice-over per scene (hanya scene yang berubah, kecuali `--force-voice`) |
| `--preview-audio` | Mix lengkap ke MP3, ditambah MP3 voice saja dan tabel durasi/kata per menit |
| `--generate-subtitles` | SRT + ASS dari timing aktual |
| `--stills` | Still per scene + contact sheet untuk review visual cepat |
| `--render-preview` | Video cepat (default 960×540, 15 fps, x264 ultrafast) |
| `--render-final` | Video final 1920×1080, 30 fps, CRF 18 |
| `--qc` | Quality control atas semua output yang ada |
| `--all` | Seluruh pipeline + QC |

Opsi tambahan:

| Opsi | Fungsi |
|---|---|
| `--scenes s01` / `1,3` / `s02-s05` | Pilih scene |
| `--preset natural\|warm_documentary\|dramatic_subtle` | Preset voice |
| `--rate -5% --pitch +0Hz --volume +0% --voice …` | Override voice |
| `--preview-scale 0.5 --preview-fps 15` | Resolusi dan fps preview |
| `--output-dir DIR` | Folder output lain |
| `--no-cache` | Abaikan cache TTS, render, dan mix |
| `--workers N` | Jumlah proses render |
| `--no-burn-subtitles` | Subtitle sebagai track terpisah (mov_text), bukan burn-in |
| `--offline` / `--fast-qc` | QC tanpa cek voice online / tanpa deteksi frame hitam |

Contoh alur kerja per scene:

```bash
python main.py --say "Tahun 1946, ENIAC menyala." --preset dramatic_subtle
python main.py --generate-voice --scenes s05
python main.py --preview-audio --scenes s05
python main.py --render-preview --scenes s05
python main.py --render-final
```

## 3. Struktur proyek

```
computer_history_motion/
├── main.py                    CLI dan orkestrasi (cache + deteksi perubahan)
├── config/
│   ├── project.json           video, timeline, audio, subtitle, tema (warna, font)
│   └── voice_presets.json     preset voice, batas aman, leksikon pengucapan
├── scripts/documentary_id.json  naskah + spesifikasi visual per scene
├── src/
│   ├── tts_engine.py          Edge-TTS: retry, timeout, cache, trim, jeda, loudness
│   ├── alignment.py           pemetaan timing kata TTS ke teks asli
│   ├── audio_mixer.py         stem, ducking, loudnorm 2-pass linear, cek clipping
│   ├── sound_synth.py         musik/ambience/SFX generatif (placeholder bebas lisensi)
│   ├── scene_manager.py       validasi/pemilihan scene, storyboard
│   ├── timeline.py            timeline dari durasi audio aktual + resolusi cue kata
│   ├── subtitle_generator.py  pemenggalan cue (dynamic programming), SRT, ASS
│   ├── animation_engine.py    easing, kamera/parallax, tipografi, latar, transisi
│   ├── illustrations.py       28 ilustrasi line-art prosedural
│   ├── scene_elements.py      elemen yang bisa disusun dari JSON
│   ├── renderer.py            Cairo → FFmpeg paralel, concat, mux
│   └── qc.py                  pemeriksaan otomatis + contact sheet
├── assets/{fonts,images,music,sfx}/   aset milik Anda (opsional, menggantikan yang generatif)
├── cache/                     cache TTS dan render (aman dihapus)
├── output/
│   ├── audio/scenes/          WAV + metadata JSON per scene (durasi, unit, kata)
│   ├── audio/stems/           voice.wav, music.wav, fx.wav
│   ├── subtitles/             *.srt, *.ass
│   ├── previews/              video preview, MP3 audio, still, contact sheet
│   ├── final/                 video final
│   ├── script/                storyboard.md, narasi.txt
│   └── timing_manifest.json   sumber kebenaran timing
└── tests/test_pipeline.py     21 unit test (offline)
```

## 4. Alur sinkronisasi

1. **Naskah final.** Setiap scene terdiri dari beberapa *unit* narasi (paragraf atau kalimat). Setiap unit dirender sebagai satu klip TTS.
2. **Generate audio Edge-TTS.** Event `WordBoundary` disimpan, sehingga waktu setiap kata diketahui.
3. **Ukur dan rakit.**
   - Durasi diukur dengan FFprobe.
   - Ekor hening dipotong di *akhir kata terakhir + 0,28 s*, sehingga kata tidak pernah terpotong.
   - Antarunit diberi jeda hening terukur (`unit_pause` atau `pause_after` per unit), tanpa mengubah kecepatan bicara.
   - Loudness voice dinormalisasi ke -18 LUFS.
4. **Bangun timeline.**
   - `durasi scene = lead_in + durasi narasi + tail`, dibulatkan ke atas ke batas frame.
   - Scene berikutnya mulai tepat di frame berikutnya.
5. **Resolve cue.** Elemen visual, SFX, dan gerak kamera memakai penanda waktu yang di-resolve dari kata yang diucapkan, misalnya `{"word": "ENIAC"}`. Kata yang tidak ada akan ditolak dengan saran kata terdekat.
6. **Render preview.** Lalu QC: durasi video = timeline, selisih A/V, resolusi/fps, frame hitam.
7. **Render final.**

Bila naskah atau voice satu scene berubah, hanya scene itu yang di-generate ulang. Timeline lalu dihitung ulang, dan scene yang posisinya bergeser dirender ulang otomatis (cache render memakai hash isi scene, posisi, tema, dan kode).

Isi `timing_manifest.json` per scene:

- durasi audio aktual, `start`/`end`, frame awal dan jumlah frame;
- `voice_start`/`voice_end`, unit narasi beserta waktunya;
- waktu kemunculan dan keluarnya setiap elemen (`text_appearances`);
- transisi masuk/keluar beserta durasinya, gerak kamera, event SFX;
- cue subtitle beserta posisinya;
- referensi file audio dan hash render.

### Format waktu di naskah

```jsonc
"at": 2.5                                   // detik sejak narasi scene mulai
"at": "start" | "end" | "voice_start" | "voice_end"
"at": {"scene": -1.5}                       // dari akhir scene
"at": {"word": "ENIAC", "n": 2, "offset": -0.2, "edge": "start"}
"at": {"unit": 3}                           // awal unit narasi ke-3
```

Hati-hati dengan kata umum seperti "ia", "itu", atau "untuk", yang bisa muncul lebih awal di narasi yang sama. Untuk kata seperti ini, gunakan `n` atau `{"unit": …}`.

## 5. Voice-over (Edge-TTS)

Edge-TTS hanya mendukung **voice, rate, pitch, volume**. Tidak ada tag emosi, dan proyek ini tidak mengklaim adanya kontrol emosi. Dinamika dibangun dari:

- pemenggalan unit dan tanda baca;
- jeda antarunit yang terukur;
- override `rate`/`pitch` per unit yang konservatif. Contohnya kalimat penutup bab memakai `rate: -7%`, dan nilai ekstrem ditolak oleh `limits`.

| Preset | rate | pitch | jeda unit | Kegunaan |
|---|---|---|---|---|
| `natural` | +0% | +0Hz | 0,40 s | penjelasan ringan |
| `warm_documentary` (default) | -5% | +0Hz | 0,50 s | baseline dokumenter |
| `dramatic_subtle` | -9% | -2Hz | 0,65 s | pembuka/penutup |

**Leksikon pengucapan** (`voice_presets.json → pronunciation`) hanya mengubah teks yang dikirim ke TTS, misalnya `"4004": "empat nol nol empat"` atau `"ENIAC": "Eniak"`. Subtitle tetap memakai ejaan asli, dan timing kata dipetakan balik oleh `alignment.py`.

Keandalan:

- retry 4× dengan *exponential backoff*, timeout per permintaan;
- error dijelaskan beserta langkah perbaikan (sertifikat, 403, voice salah, koneksi);
- cache per unit berbasis hash dari teks, voice, rate, pitch, volume, dan versi engine.

> **Jaringan dengan proxy TLS (kantor/sandbox):** edge-tts memakai bundle CA `certifi` secara hardcode. `tts_engine.patch_edge_tts_ssl()` menambahkan CA dari `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` bila variabel itu di-set. Verifikasi TLS tetap aktif.

## 6. Audio

- **Voice.** Elemen utama, -18 LUFS per scene (loudnorm dua tahap, linear).
- **Musik.** Pad sinematik D minor generatif dengan lonceng pentatonik jarang, plus denyut lembut di bab klimaks (`music_pulse`). Di-*duck* oleh voice lewat `sidechaincompress`.
- **Ambience per era.** `mechanical` (detak), `electric` (dengung 60 Hz + relay), `digital` (udara + blip).
- **SFX selektif.** `whoosh`, `tick`, `clunk`, `relay`, `blip`, `data`, `impact`, `riser`, `chime`, `keys`, dengan cue kata per scene.
- **Master.** -16 LUFS, true peak ≤ -1,5 dBTP, loudnorm dua tahap **linear** (tanpa kompresi dinamis). Bila ada puncak transien yang menghalangi mode linear, puncak itu saja yang dipangkas oleh limiter sebelum normalisasi. QC memberi peringatan bila FFmpeg tetap jatuh ke mode `dynamic`.

**Mengganti placeholder.** Semua musik dan SFX saat ini dibuat secara generatif (`src/sound_synth.py`), jadi tidak ada aset berhak cipta.

- SFX: taruh `assets/sfx/<nama>.wav`, misalnya `whoosh.wav`, dan file itu otomatis dipakai.
- Musik: taruh file di `assets/music/`, lalu set `"music_file": "nama.wav"` di `project.json`. Musik di-loop atau dipotong sesuai durasi.

## 7. Subtitle

- Sumber timing: event `WordBoundary` Edge-TTS, bukan pembagian rata per kalimat.
- Pemenggalan cue memakai *dynamic programming* per unit narasi:
  - target sekitar 58 karakter, maksimal 2 × 42 karakter dan 5,5 s;
  - memotong di tanda baca;
  - menghindari akhiran kata lemah ("dan", "yang");
  - tidak memisahkan nama diri, tidak menyisakan cue yatim, tidak melintasi jeda antarunit.
- Burn-in digambar renderer: kotak semi-transparan, Inter Medium 38 px, di bawah *safe area* konten (y ≤ 860).
- File SRT dan ASS tersedia di `output/subtitles/`.

**Batasan.** Timing kata berasal dari TTS, bukan *forced alignment* akustik. Token yang tidak bisa dicocokkan (misalnya angka yang dieja lain) mendapat timing interpolasi dan ditandai `approx`, lalu dilaporkan oleh QC. Pada render terakhir, jumlah token `approx` adalah 0.

## 8. Visual

- **Gaya.** Latar gelap (charcoal → navy) dengan grid dan partikel yang digerakkan waktu global, sehingga kontinu antarscene. Aksen per era: amber untuk mekanis, cyan untuk elektronik/digital.
- **Tipografi.** Inter Display dan Inter, dengan label mono DejaVu.
- **Kamera.** *Push-in* lambat dengan parallax per lapisan, plus dorongan kamera berbasis cue (misalnya zoom ke chip di bab 6).
- **Transisi berbasis bentuk.** `iris`, `bars` (panel cover/reveal), `line_wipe`, `zoom`, `fade`, `slide`, `fade_black`. Transisi masuk sebuah scene otomatis meniru transisi keluar scene sebelumnya.
- **Elemen JSON.**
  - Teks: `headline`, `text`, `kicker`, `title`, `counter` (tahun atau angka berformat Indonesia).
  - Ilustrasi: `icon`, `morph`, `strip`, `icon_grid`, `number_field`.
  - Struktur informasi: `timeline`, `chips`, `card`, `diagram`, `network`, `moore_chart`, `line`.
  - Semua elemen mendukung `pos`, `path` (gerak berbasis cue), `depth` (parallax), `at`, dan `until`.
- **Ilustrasi.** 28 ilustrasi line-art dibuat dari kode, mulai dari abakus dan Pascaline sampai ENIAC, transistor, die 4004, GUI, globe, jaringan saraf, dan qubit. Semuanya mendukung *draw-on*, *retract*, dan gerak idle.
- **Kustomisasi tanpa menulis ulang kode.**
  - Warna, font, grid, dan partikel: `project.json → theme`.
  - Durasi jeda: `timeline`, atau `timing` per scene.
  - Layout dan animasi: `elements` di naskah.

## 9. Quality control

`python main.py --qc` memeriksa:

- dependency, encoder, filter, dan font;
- ketersediaan voice;
- keberadaan dan durasi audio per scene, termasuk token timing perkiraan;
- validitas timeline: kontinu, narasi tidak terpotong, transisi tidak menimpa narasi, elemen dan SFX berada di dalam scene;
- subtitle: kosong, di luar durasi, tumpang tindih, lebih dari 2 baris;
- clipping, loudness, mode linear, dan durasi master;
- resolusi, fps, durasi video vs timeline, selisih A/V;
- frame hitam yang tidak disengaja (fade akhir dikecualikan);
- file yang tidak lengkap atau rusak.

`pytest` menjalankan 21 unit test untuk timeline, kalkulasi durasi, subtitle, konfigurasi voice, alignment, dan pemilihan scene.

## 10. Hasil yang sudah dijalankan

Pada Ubuntu 24.04, 4 CPU:

| Item | Hasil |
|---|---|
| Video final | `output/final/sejarah_komputer_full.mp4`, 1920×1080, 30 fps, 599,0 s |
| Selisih A/V | 0 ms (preview dan final) |
| Loudness master | -15,97 LUFS, linear, puncak ≈ -2,6 dBFS, 0 sampel clipping |
| Narasi | 11 scene, 859 kata, sekitar 4,5 suku kata/detik saat berbicara, ±17% jeda, 0 kata dengan timing perkiraan |
| Subtitle | 136 cue, 0 cue yatim, 0 cue > 2 baris |
| Waktu render | preview 10 menit ≈ 31 s render; final ≈ 12 menit (sekitar 25 fps total, termasuk encode x264 medium) |
| Unit test | 21 lolos |

Video, audio, dan cache tidak di-commit karena ukurannya besar. Buat ulang dengan `python main.py --all`. Cache TTS membuat proses ulang tidak perlu memanggil server lagi.

## 11. Akurasi sejarah

Naskah ditulis tanpa kutipan langsung tokoh; gagasan Ada Lovelace diparafrasekan. Angka perkiraan diberi kata "sekitar", misalnya ENIAC dengan sekitar 18 ribu tabung (17.468), ±27 ton, dan ±5.000 penjumlahan per detik. Setiap scene mencantumkan `historical_sources`.

**Belum diverifikasi.** URL sumber belum bisa dibuka dari lingkungan tempat proyek ini dibangun karena jaringannya dibatasi. Periksa kembali setiap tautan dan fakta sebelum publikasi. Dua tautan yang tidak pasti sudah dihapus dan hanya judul rujukannya yang dipertahankan.

## 12. Batasan dan saran penyetelan

- **Kealamian suara** hanya bisa dinilai dengan telinga. Dengarkan `output/previews/*_voice_only.mp3`, lalu sesuaikan preset, `pause_after` per unit, atau leksikon.
  - Pengucapan nama asing (Babbage, Leibniz, Lovelace, Analytical Engine) mengikuti aturan bawaan voice Indonesia.
  - Bila kurang pas, tambahkan ejaan fonetis di leksikon, lalu uji dengan `--say`.
- **Musik dan SFX** adalah placeholder sintetis yang sederhana. Untuk rilis, ganti dengan aset berlisensi (lihat bagian 6).
- **Edge-TTS** adalah layanan online tanpa SLA. Cache memastikan audio yang sudah jadi tidak perlu diminta ulang.
