"""Utilitas bersama: path proyek, konfigurasi, FFmpeg/FFprobe, dan error yang mudah dipahami."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


class PipelineError(RuntimeError):
    """Error dengan penjelasan penyebab dan langkah perbaikan."""

    def __init__(self, message: str, fix: str | None = None):
        super().__init__(message)
        self.fix = fix

    def __str__(self) -> str:
        text = super().__str__()
        return f"{text}\n  → Perbaikan: {self.fix}" if self.fix else text


def log(msg: str) -> None:
    print(msg, flush=True)


def load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise PipelineError(f"File tidak ditemukan: {path}", "Periksa path atau jalankan dari folder proyek.")
    except json.JSONDecodeError as e:
        raise PipelineError(f"JSON tidak valid di {path} baris {e.lineno} kolom {e.colno}: {e.msg}",
                            "Perbaiki sintaks JSON (koma, kutip, kurung).")


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def stable_hash(obj, length: int = 16) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


@dataclass
class Paths:
    root: Path = ROOT
    output: Path = field(default_factory=lambda: ROOT / "output")

    @property
    def config(self) -> Path: return self.root / "config"
    @property
    def scripts(self) -> Path: return self.root / "scripts"
    @property
    def assets(self) -> Path: return self.root / "assets"
    @property
    def cache(self) -> Path: return self.root / "cache"
    @property
    def tts_cache(self) -> Path: return self.cache / "tts"
    @property
    def render_cache(self) -> Path: return self.cache / "render"
    @property
    def audio(self) -> Path: return self.output / "audio"
    @property
    def scene_audio(self) -> Path: return self.audio / "scenes"
    @property
    def stems(self) -> Path: return self.audio / "stems"
    @property
    def subtitles(self) -> Path: return self.output / "subtitles"
    @property
    def previews(self) -> Path: return self.output / "previews"
    @property
    def final(self) -> Path: return self.output / "final"
    @property
    def manifest(self) -> Path: return self.output / "timing_manifest.json"

    def ensure(self) -> None:
        for p in (self.tts_cache, self.render_cache, self.scene_audio, self.stems, self.subtitles,
                  self.previews, self.final, self.assets / "music", self.assets / "sfx"):
            p.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- FFmpeg

def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise PipelineError(f"'{name}' tidak ditemukan di PATH.",
                            "Instal FFmpeg (Ubuntu: sudo apt install ffmpeg, macOS: brew install ffmpeg, "
                            "Windows: unduh dari ffmpeg.org lalu tambahkan folder bin ke PATH).")
    return path


def run(cmd: list[str], what: str, capture: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=capture, text=True)
    except FileNotFoundError:
        require_binary(cmd[0])
        raise
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-12:]
        raise PipelineError(f"{what} gagal (exit {proc.returncode}).\n    " + "\n    ".join(tail),
                            "Baca pesan FFmpeg di atas; biasanya file input hilang/rusak atau filter tidak didukung.")
    return proc


def ffprobe_json(path: Path) -> dict:
    if not Path(path).exists():
        raise PipelineError(f"File media tidak ada: {path}", "Jalankan langkah sebelumnya untuk membuat file ini.")
    proc = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
               f"ffprobe {Path(path).name}")
    return json.loads(proc.stdout)


def media_duration(path: Path) -> float:
    info = ffprobe_json(path)
    dur = info.get("format", {}).get("duration")
    if dur is None:
        raise PipelineError(f"Durasi tidak terbaca dari {path}", "File mungkin rusak; hapus dan buat ulang.")
    return float(dur)


def decode_audio(path: Path, sr: int = 48000, channels: int = 1) -> np.ndarray:
    """Dekode file audio apa pun menjadi float32 [-1, 1] dengan bentuk (n,) atau (n, ch)."""
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", str(channels),
                           "-ar", str(sr), "-"], capture_output=True)
    if proc.returncode != 0:
        raise PipelineError(f"Gagal mendekode audio {path}: {proc.stderr.decode(errors='ignore')[-400:]}",
                            "Pastikan file audio valid; hapus cache lalu generate ulang.")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    return data.reshape(-1, channels) if channels > 1 else data


def write_wav(path: Path, data: np.ndarray, sr: int) -> None:
    """Tulis float32 [-1,1] ke WAV PCM 16-bit (dengan pembatas agar tidak wrap-around)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(data, dtype=np.float32)
    channels = 1 if arr.ndim == 1 else arr.shape[1]
    pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).round().astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
    return (data.reshape(-1, ch) if ch > 1 else data), sr


def db_to_gain(db: float) -> float:
    return float(10 ** (db / 20.0))


def python_ok() -> bool:
    return sys.version_info >= (3, 10)
