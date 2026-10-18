"""Quality control otomatis. Setiap pemeriksaan menghasilkan (status, nama, pesan, perbaikan)."""
from __future__ import annotations

import importlib
import re
import shutil
import subprocess
from pathlib import Path

from .subtitle_generator import validate_cues
from .timeline import validate_timeline
from .utils import Paths, ffprobe_json, load_json, log, media_duration, python_ok, save_json

OK, WARN, FAIL = "ok", "warn", "fail"
ICON = {OK: "✓", WARN: "!", FAIL: "✗"}


class Report:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, status: str, name: str, msg: str, fix: str = ""):
        self.items.append({"status": status, "check": name, "message": msg, "fix": fix})

    @property
    def failed(self) -> bool:
        return any(i["status"] == FAIL for i in self.items)

    def print(self, title: str = "Quality control"):
        log(f"\n── {title} " + "─" * max(0, 60 - len(title)))
        for i in self.items:
            log(f"  {ICON[i['status']]} {i['check']}: {i['message']}")
            if i["status"] != OK and i["fix"]:
                log(f"      → {i['fix']}")
        n_fail = sum(i["status"] == FAIL for i in self.items)
        n_warn = sum(i["status"] == WARN for i in self.items)
        log(f"  Hasil: {len(self.items) - n_fail - n_warn} lolos, {n_warn} peringatan, {n_fail} gagal")

    def save(self, path: Path):
        save_json(path, self.items)


# --------------------------------------------------------------------------- dependency

def check_dependencies(theme_fonts: dict | None = None) -> Report:
    r = Report()
    import sys
    r.add(OK if python_ok() else FAIL, "Python", sys.version.split()[0], "Gunakan Python 3.10 atau lebih baru.")
    for binary in ("ffmpeg", "ffprobe"):
        path = shutil.which(binary)
        r.add(OK if path else FAIL, binary, path or "tidak ditemukan",
              "Instal FFmpeg dan pastikan ada di PATH (lihat README).")
    if shutil.which("ffmpeg"):
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        flt = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        for name, hay in (("libx264", enc), ("aac", enc), ("loudnorm", flt), ("sidechaincompress", flt),
                          ("blackdetect", flt)):
            found = re.search(rf"\s{name}\s", hay) is not None
            r.add(OK if found else FAIL, f"FFmpeg {name}", "tersedia" if found else "tidak tersedia",
                  "Instal build FFmpeg lengkap (mis. paket ffmpeg dari distro atau gyan.dev untuk Windows).")
    for mod, pip_name in (("edge_tts", "edge-tts"), ("cairo", "pycairo"), ("numpy", "numpy"), ("PIL", "Pillow")):
        try:
            m = importlib.import_module(mod)
            r.add(OK, f"modul {mod}", getattr(m, "__version__", getattr(m, "version", "ok")))
        except ImportError:
            r.add(FAIL, f"modul {mod}", "tidak terpasang", f"pip install {pip_name}")
    if theme_fonts and shutil.which("fc-match"):
        for key, family in theme_fonts.items():
            got = subprocess.run(["fc-match", "-f", "%{family}", family], capture_output=True, text=True).stdout
            match = family.split()[0].lower() in got.lower()
            r.add(OK if match else WARN, f"font {key}", f"'{family}' → {got.split(',')[0]}",
                  f"Instal font '{family}' (Inter: https://rsms.me/inter/) atau ganti theme.fonts di project.json.")
    return r


def check_voice(r: Report, voice: str) -> None:
    from .tts_engine import list_voices
    try:
        names = {v["ShortName"] for v in list_voices(voice[:3])}
        r.add(OK if voice in names else FAIL, "Voice Edge-TTS", f"{voice} {'tersedia' if voice in names else 'TIDAK tersedia'}",
              f"Pilih voice lain dari: {', '.join(sorted(names))}")
    except Exception as e:  # noqa: BLE001
        r.add(WARN, "Voice Edge-TTS", f"tidak bisa memeriksa daftar voice ({e})", "Periksa koneksi internet.")


# --------------------------------------------------------------------------- audio / timeline / subtitle

def check_scene_audio(r: Report, paths: Paths, scene_ids: list[str]) -> None:
    for sid in scene_ids:
        meta_p = paths.scene_audio / f"{sid}.json"
        if not meta_p.exists():
            r.add(FAIL, f"audio {sid}", "belum dibuat", "python main.py --generate-voice")
            continue
        meta = load_json(meta_p)
        wav = paths.root / meta["file"]
        if not wav.exists():
            r.add(FAIL, f"audio {sid}", "file WAV hilang", "python main.py --generate-voice --no-cache")
            continue
        dur = media_duration(wav)
        diff = abs(dur - meta["duration"])
        approx = sum(t.get("approx", False) for t in meta["tokens"])
        status = OK if dur > 0.5 and diff < 0.02 else FAIL
        msg = f"{dur:.2f}s, {len(meta['tokens'])} kata"
        if approx:
            msg += f", {approx} kata dengan timing perkiraan"
        r.add(status if not approx else (WARN if status == OK else status), f"audio {sid}", msg,
              "Kata 'perkiraan' biasanya angka/singkatan; cek leksikon pengucapan." if approx else
              "Hapus output/audio/scenes lalu generate ulang.")


def check_timeline(r: Report, manifest: dict) -> None:
    probs = validate_timeline(manifest)
    r.add(FAIL if probs else OK, "Timeline", "; ".join(probs) if probs else
          f"{len(manifest['scenes'])} scene, {manifest['total_duration']:.2f}s, {manifest['total_frames']} frame",
          "Naikkan timeline.tail/lead_in atau perpendek transisi di naskah.")


def check_subtitles(r: Report, manifest: dict, cfg: dict) -> None:
    cues = manifest["subtitles"]
    probs = validate_cues(cues, manifest["total_duration"], cfg)
    for s in manifest["scenes"]:
        if not any(c["scene_id"] == s["scene_id"] for c in cues):
            probs.append(f"{s['scene_id']} tidak punya subtitle")
        for c in s["subtitles"]:
            if c["start"] < s["voice_start"] - 0.2 or c["end"] > s["end"]:
                probs.append(f"cue '{c['text'][:30]}…' di luar rentang narasi scene")
    approx = sum(c["approx"] for c in cues)
    status = FAIL if probs else (WARN if approx else OK)
    r.add(status, "Subtitle", "; ".join(probs[:5]) if probs else
          f"{len(cues)} cue, maks {max(len(c['text']) for c in cues)} karakter" +
          (f", {approx} cue memakai timing perkiraan" if approx else ""),
          "Periksa pengaturan subtitles di project.json.")


def check_master_audio(r: Report, report: dict | None, cfg: dict) -> None:
    if not report:
        return
    clip = report["clipping"]
    status = OK if clip["clipped_samples"] == 0 and clip["peak_dbfs"] <= cfg["clip_peak_dbfs"] else FAIL
    r.add(status, "Clipping audio", f"puncak {clip['peak_dbfs']} dBFS, {clip['clipped_samples']} sampel clipping",
          "Turunkan audio.sfx_gain_db / music_gain_db atau target master_lufs.")
    loud = report["loudness"]
    try:
        diff = abs(float(loud["output_i"]) - cfg["master_lufs"])
        r.add(OK if diff < 1.0 else WARN, "Loudness master", f"{loud['output_i']} LUFS (target {cfg['master_lufs']})",
              "Loudnorm tidak mencapai target; periksa dinamika stem.")
    except (TypeError, ValueError, KeyError):
        r.add(WARN, "Loudness master", "tidak terbaca")
    lin = loud.get("normalization_type") == "linear"
    r.add(OK if lin else WARN, "Normalisasi linear", f"mode {loud.get('normalization_type')}"
          + (f", limiter puncak {loud['limiter_db']} dBFS" if loud.get("limiter_db") is not None else ""),
          "Mode dynamic berarti ada kompresi; turunkan gain SFX atau longgarkan true_peak.")
    d = abs(report["duration"] - report["expected_duration"])
    r.add(OK if d < 0.03 else FAIL, "Durasi audio master", f"{report['duration']:.3f}s vs timeline "
          f"{report['expected_duration']:.3f}s", "Bangun ulang mix: python main.py --preview-audio")


# --------------------------------------------------------------------------- video

def check_video(r: Report, path: Path, manifest: dict, mode: dict, expect_fade_end: bool = True,
                blackdetect: bool = True) -> None:
    if not path.exists():
        r.add(FAIL, "File video", f"{path} tidak ada", "Jalankan render.")
        return
    try:
        info = ffprobe_json(path)
    except Exception as e:  # noqa: BLE001
        r.add(FAIL, "File video", f"tidak bisa dibaca ({e})", "File tidak lengkap/rusak; render ulang.")
        return
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        r.add(FAIL, "Stream video", "tidak ada", "Render ulang.")
        return
    res_ok = (v["width"], v["height"]) == (mode["width"], mode["height"])
    r.add(OK if res_ok else FAIL, "Resolusi", f"{v['width']}x{v['height']} (target {mode['width']}x{mode['height']})")
    num, den = map(int, v["r_frame_rate"].split("/"))
    fps = num / den
    r.add(OK if abs(fps - mode["fps"]) < 0.01 else FAIL, "Frame rate", f"{fps:.3f} fps (target {mode['fps']})")
    total = manifest["total_duration"]
    vdur = float(v.get("duration", info["format"]["duration"]))
    tol = 1.5 / mode["fps"]
    r.add(OK if abs(vdur - total) <= tol else FAIL, "Durasi video", f"{vdur:.3f}s vs timeline {total:.3f}s",
          "Render ulang; jangan memotong file secara manual.")
    if a:
        adur = float(a.get("duration", 0))
        drift = abs(adur - vdur)
        r.add(OK if drift <= max(tol, 0.05) else FAIL, "Sinkronisasi A/V",
              f"audio {adur:.3f}s, video {vdur:.3f}s, selisih {drift * 1000:.0f} ms",
              "Bangun ulang master audio dan mux ulang.")
    else:
        r.add(WARN, "Stream audio", "tidak ada (video tanpa suara)")
    if blackdetect:
        proc = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                               "blackdetect=d=0.2:pix_th=0.04:pic_th=0.98", "-an", "-f", "null", "-"],
                              capture_output=True, text=True)
        spans = [(float(a_), float(b_)) for a_, b_ in
                 re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", proc.stderr)]
        unintended = [s for s in spans if not (expect_fade_end and s[1] >= vdur - 0.1 and s[0] >= vdur - 2.0)]
        r.add(FAIL if unintended else OK, "Frame hitam",
              f"{len(unintended)} segmen tak disengaja: {unintended[:3]}" if unintended else
              "tidak ada frame hitam tak disengaja" + (" (fade akhir disengaja)" if spans else ""),
              "Periksa transisi scene atau elemen yang belum muncul.")


def contact_sheet(frames: list[Path], out: Path, cols: int = 4, width: int = 480) -> Path:
    """Gabungkan beberapa still PNG menjadi satu lembar (Pillow) untuk review cepat."""
    from PIL import Image, ImageDraw, ImageFont
    imgs = [Image.open(f).convert("RGB") for f in frames]
    h = int(width * imgs[0].height / imgs[0].width)
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width + (cols + 1) * 8, rows * (h + 30) + 8), (12, 14, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    for i, (img, f) in enumerate(zip(imgs, frames)):
        r_, c = divmod(i, cols)
        x, y = 8 + c * (width + 8), 8 + r_ * (h + 30)
        sheet.paste(img.resize((width, h), Image.LANCZOS), (x, y))
        draw.text((x, y + h + 6), f.stem, fill=(150, 160, 175), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
