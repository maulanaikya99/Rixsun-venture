"""Musik, ambience, dan SFX generatif (NumPy) sebagai placeholder bebas lisensi.

Semua suara di sini disintesis dari nol (gelombang sinus, noise, envelope), sehingga aman dipakai.
Untuk mengganti dengan aset sendiri, taruh file WAV di:
  assets/sfx/<nama>.wav           → menggantikan SFX bernama sama (mis. whoosh.wav)
  assets/music/<file>             → lalu set audio.music_file di config/project.json
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .utils import Paths, decode_audio, stable_hash, write_wav

SR = 48000
SYNTH_VERSION = 2


def _midi(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _wavetable(harmonics: int = 6, rolloff: float = 1.6, size: int = 4096) -> np.ndarray:
    ph = np.arange(size) / size * 2 * np.pi
    tab = sum(np.sin(h * ph) / h ** rolloff for h in range(1, harmonics + 1))
    return (tab / np.abs(tab).max()).astype(np.float32)


_PAD_TABLE = _wavetable(6, 1.7)


def _osc(freq: float, n: int, sr: int, table=_PAD_TABLE, phase0: float = 0.0) -> np.ndarray:
    idx = ((phase0 + freq * np.arange(n) / sr) * len(table)) % len(table)
    return table[idx.astype(np.int32)]


def _fft_filter(x: np.ndarray, sr: int, lo: float | None = None, hi: float | None = None,
                slope: float = 0.0) -> np.ndarray:
    """Filter band sederhana di domain frekuensi (tanpa SciPy)."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    gain = np.ones_like(f)
    if lo:
        gain *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi:
        gain *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if slope:
        gain *= (np.maximum(f, 20) / 1000.0) ** slope
    return np.fft.irfft(spec * gain, n=len(x)).astype(np.float32)


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.abs(x).max()
    return (x / m * peak).astype(np.float32) if m > 0 else x.astype(np.float32)


def _env(n: int, attack: float, decay: float, sr: int = SR) -> np.ndarray:
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return (a * np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4))).astype(np.float32)


def _onepole_sweep(noise: np.ndarray, cutoff: np.ndarray, sr: int) -> np.ndarray:
    """Lowpass satu kutub dengan cutoff berubah waktu (loop pendek, hanya untuk SFX)."""
    out = np.empty_like(noise)
    y = 0.0
    coef = 1 - np.exp(-2 * np.pi * cutoff / sr)
    for i in range(len(noise)):
        y += coef[i] * (noise[i] - y)
        out[i] = y
    return out


# --------------------------------------------------------------------------- SFX

def sfx_whoosh(sr=SR, dur=1.1, seed=1):
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    t = np.linspace(0, 1, n)
    cutoff = 300 + 5200 * np.sin(np.pi * t) ** 2
    x = _onepole_sweep(rng.standard_normal(n).astype(np.float32), cutoff, sr)
    x = x - _onepole_sweep(x, np.full(n, 180.0), sr)  # buang dengung rendah
    env = np.sin(np.pi * t) ** 1.5
    left = x * env * (0.6 + 0.4 * t)
    right = x * env * (1.0 - 0.4 * t)
    return _norm(np.stack([left, right], 1), 0.8)


def sfx_tick(sr=SR, seed=2):
    rng = np.random.default_rng(seed)
    n = int(0.12 * sr)
    t = np.arange(n) / sr
    burst = rng.standard_normal(n) * np.exp(-t / 0.004)
    ping = np.sin(2 * np.pi * 2350 * t) * np.exp(-t / 0.018) * 0.5
    return _norm(_fft_filter(burst + ping, sr, lo=900, hi=7000), 0.7)


def sfx_clunk(sr=SR, seed=3):
    rng = np.random.default_rng(seed)
    n = int(0.6 * sr)
    t = np.arange(n) / sr
    body = np.sin(2 * np.pi * 92 * t) * np.exp(-t / 0.09)
    metal = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d) * a
                for f, d, a in ((523, 0.12, 0.25), (1371, 0.07, 0.18), (2213, 0.05, 0.12), (3307, 0.03, 0.08)))
    noise = _fft_filter(rng.standard_normal(n), sr, lo=400, hi=4000) * np.exp(-t / 0.015) * 0.6
    return _norm(body + metal + noise, 0.85)


def sfx_relay(sr=SR):
    a = sfx_tick(sr, seed=7)
    out = np.zeros(int(0.2 * sr), np.float32)
    out[:len(a)] += a
    off = int(0.034 * sr)
    out[off:off + len(a)] += a * 0.7
    return _norm(out, 0.7)


def sfx_blip(sr=SR):
    n = int(0.16 * sr)
    t = np.arange(n) / sr
    f = 1100 + 900 * (t / t[-1])
    x = np.sin(2 * np.pi * np.cumsum(f) / sr) * _env(n, 0.006, 0.05, sr)
    return _norm(x, 0.6)


def sfx_data(sr=SR, seed=4):
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.9 * sr), np.float32)
    for k in range(9):
        f = rng.choice([1320, 1560, 1760, 2090, 2350])
        n = int(0.045 * sr)
        t = np.arange(n) / sr
        b = np.sin(2 * np.pi * f * t) * _env(n, 0.003, 0.012, sr)
        s = int(k * 0.085 * sr)
        out[s:s + n] += b * (0.5 + 0.5 * rng.random())
    return _norm(out, 0.55)


def sfx_impact(sr=SR, seed=5):
    rng = np.random.default_rng(seed)
    n = int(2.4 * sr)
    t = np.arange(n) / sr
    f = 70 * np.exp(-t / 0.6) + 38
    sub = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.7)
    air = _fft_filter(rng.standard_normal(n), sr, lo=200, hi=2500) * np.exp(-t / 0.25) * 0.25
    x = (sub + air) * np.clip(t / 0.01, 0, 1)
    return _norm(np.stack([x, x * 0.96], 1), 0.85)


def sfx_riser(sr=SR, dur=2.2, seed=6):
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    t = np.linspace(0, 1, n)
    cutoff = 200 + 6000 * t ** 2
    noise = _onepole_sweep(rng.standard_normal(n).astype(np.float32), cutoff, sr)
    tone = np.sin(2 * np.pi * np.cumsum(220 + 440 * t ** 2) / sr) * 0.15
    x = (noise + tone) * t ** 2 * np.clip((1 - t) / 0.05, 0, 1)
    return _norm(np.stack([x, x], 1), 0.6)


def sfx_chime(sr=SR):
    n = int(3.2 * sr)
    t = np.arange(n) / sr
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d) * a
            for f, d, a in ((880, 1.4, 0.5), (1320.5, 1.0, 0.25), (2217, 0.6, 0.15), (2960, 0.4, 0.08)))
    x *= np.clip(t / 0.004, 0, 1)
    return _norm(np.stack([x, np.roll(x, int(0.012 * sr))], 1), 0.55)


def sfx_keys(sr=SR, seed=8):
    rng = np.random.default_rng(seed)
    out = np.zeros(int(1.1 * sr), np.float32)
    tick = sfx_tick(sr, seed=9)
    pos = 0.0
    while pos < 0.95:
        s = int(pos * sr)
        seg = tick[: len(out) - s] * (0.4 + 0.5 * rng.random())
        out[s:s + len(seg)] += seg
        pos += 0.07 + 0.09 * rng.random()
    return _norm(_fft_filter(out, sr, lo=600, hi=5000), 0.55)


SFX_LIBRARY = {
    "whoosh": sfx_whoosh, "tick": sfx_tick, "clunk": sfx_clunk, "relay": sfx_relay, "blip": sfx_blip,
    "data": sfx_data, "impact": sfx_impact, "riser": sfx_riser, "chime": sfx_chime, "keys": sfx_keys,
}


def get_sfx(paths: Paths, name: str, sr: int = SR) -> np.ndarray:
    """SFX stereo float32. Prioritas: assets/sfx/<name>.wav milik pengguna → hasil generatif (di-cache)."""
    user = paths.assets / "sfx" / f"{name}.wav"
    if user.exists():
        return decode_audio(user, sr, 2)
    if name not in SFX_LIBRARY:
        from .utils import PipelineError
        raise PipelineError(f"SFX '{name}' tidak dikenal.",
                            f"Gunakan salah satu: {', '.join(SFX_LIBRARY)} atau taruh assets/sfx/{name}.wav")
    gen = paths.assets / "sfx" / "generated" / f"{name}_v{SYNTH_VERSION}.wav"
    if not gen.exists():
        x = SFX_LIBRARY[name](sr)
        if x.ndim == 1:
            x = np.stack([x, x], 1)
        write_wav(gen, x, sr)
    return decode_audio(gen, sr, 2)


# --------------------------------------------------------------------------- ambience

def ambience(kind: str, dur: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    n = int(dur * sr)
    rng = np.random.default_rng(seed)
    if kind == "none" or n == 0:
        return np.zeros((n, 2), np.float32)
    room = _fft_filter(rng.standard_normal(n).astype(np.float32), sr, lo=40, hi=900) * 0.25
    x = room.copy()
    if kind == "mechanical":
        tick = sfx_tick(sr, seed=11) * 0.35
        pos = 0.3
        while pos < dur - 0.2:
            s = int(pos * sr)
            seg = tick[: n - s]
            x[s:s + len(seg)] += seg * (0.6 + 0.4 * rng.random())
            pos += 0.62 + rng.normal(0, 0.02)
    elif kind == "electric":
        t = np.arange(n) / sr
        hum = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((60, 0.10), (120, 0.06), (180, 0.03)))
        x += hum * (0.85 + 0.15 * np.sin(2 * np.pi * 0.13 * t))
        x += _fft_filter(rng.standard_normal(n).astype(np.float32), sr, lo=3000, hi=9000) * 0.04
        relay = sfx_relay(sr) * 0.25
        pos = 1.0
        while pos < dur - 0.3:
            s = int(pos * sr)
            seg = relay[: n - s]
            x[s:s + len(seg)] += seg
            pos += 1.5 + 3.5 * rng.random()
    elif kind == "digital":
        x = _fft_filter(rng.standard_normal(n).astype(np.float32), sr, lo=300, hi=6000, slope=-0.5) * 0.18
        blip = sfx_blip(sr) * 0.12
        pos = 1.5
        while pos < dur - 0.3:
            s = int(pos * sr)
            seg = blip[: n - s]
            x[s:s + len(seg)] += seg
            pos += 2.5 + 4.0 * rng.random()
    x = _norm(x, 0.5)
    right = np.roll(x, int(0.011 * sr))
    return np.stack([x, right], 1)


# --------------------------------------------------------------------------- musik

# Progresi D minor yang tenang: Dm9 – Bbmaj7 – Fmaj7 – Csus2 (catatan MIDI).
CHORDS = [
    [38, 50, 57, 62, 65, 64],
    [34, 46, 53, 62, 65, 69],
    [41, 53, 60, 64, 69],
    [36, 48, 55, 62, 67],
]
PENTATONIC = [74, 77, 79, 81, 84, 86]  # D F G A C D (oktaf 5–6)


def music_score(dur: float, sr: int = SR, seed: int = 7, chord_s: float = 9.0, xfade_s: float = 3.0,
                pulse_regions: list[tuple[float, float]] | None = None) -> np.ndarray:
    """Pad sinematik + lonceng pentatonik jarang + (opsional) denyut lembut di wilayah tertentu."""
    n = int(dur * sr)
    out = np.zeros((n, 2), np.float32)
    rng = np.random.default_rng(seed)
    n_chords = math.ceil(dur / chord_s) + 1
    for ci in range(n_chords):
        start = ci * chord_s - xfade_s / 2
        s0, s1 = max(0, int(start * sr)), min(n, int((start + chord_s + xfade_s) * sr))
        if s1 <= s0:
            continue
        m = s1 - s0
        tt = (np.arange(s0, s1) / sr) - start
        fade_in = np.clip(tt / xfade_s, 0, 1)
        fade_out = np.clip((chord_s + xfade_s - tt) / xfade_s, 0, 1)
        env = (np.sin(fade_in * np.pi / 2) * np.sin(fade_out * np.pi / 2)).astype(np.float32)
        chord = CHORDS[ci % len(CHORDS)]
        for k, note in enumerate(chord):
            f = _midi(note)
            amp = 0.55 if k == 0 else 0.22
            if k == 0:  # bas: sinus murni
                tone = np.sin(2 * np.pi * f * (np.arange(s0, s1) / sr)).astype(np.float32)
                out[s0:s1, 0] += tone * env * amp
                out[s0:s1, 1] += tone * env * amp
                continue
            for side, det in ((0, 0.9988), (1, 1.0012)):
                tone = _osc(f * det, m, sr, phase0=rng.random())
                lfo = 0.85 + 0.15 * np.sin(2 * np.pi * (0.07 + 0.02 * k) * tt + k)
                out[s0:s1, side] += tone * env * amp * lfo.astype(np.float32)
    out = np.stack([_fft_filter(out[:, 0], sr, lo=35, hi=2400), _fft_filter(out[:, 1], sr, lo=35, hi=2400)], 1)

    # lonceng pentatonik jarang + gema sederhana
    bells = np.zeros(n, np.float32)
    pos = 3.0
    while pos < dur - 3:
        note = _midi(rng.choice(PENTATONIC))
        bn = int(3.0 * sr)
        t = np.arange(bn) / sr
        b = (np.sin(2 * np.pi * note * t) + 0.3 * np.sin(2 * np.pi * note * 2.01 * t)) * _env(bn, 0.01, 0.9, sr)
        s = int(pos * sr)
        seg = b[: n - s] * (0.10 + 0.06 * rng.random())
        bells[s:s + len(seg)] += seg
        pos += 3.5 + 4.5 * rng.random()
    echo = bells.copy()
    for d, g in ((0.37, 0.45), (0.74, 0.25), (1.11, 0.12)):
        k = int(d * sr)
        echo[k:] += bells[:-k] * g
    out[:, 0] += echo
    out[:, 1] += np.roll(echo, int(0.019 * sr))

    # denyut lembut (akar & kuint akor aktif), mengisi momen klimaks
    for (a, b) in (pulse_regions or []):
        t0 = a
        step = 60 / 96 / 2
        while t0 < b - 0.2:
            ci = int((t0 + xfade_s / 2) // chord_s) % len(CHORDS)
            note = CHORDS[ci][1] + (7 if int(t0 / step) % 4 == 2 else 12)
            pn = int(0.4 * sr)
            t = np.arange(pn) / sr
            p = _osc(_midi(note), pn, sr) * _env(pn, 0.004, 0.12, sr)
            rel = (t0 - a) / max(b - a, 1e-3)
            gain = 0.10 * min(1.0, rel * 4, (1 - rel) * 4)
            s = int(t0 * sr)
            seg = p[: n - s] * gain
            out[s:s + len(seg), 0] += seg
            out[s:s + len(seg), 1] += seg * 0.9
            t0 += step
    return _norm(out, 0.8)


def get_music(paths: Paths, dur: float, music_file: str | None, pulse_regions, sr: int = SR) -> np.ndarray:
    if music_file:
        src = paths.assets / "music" / music_file
        if not src.exists():
            from .utils import PipelineError
            raise PipelineError(f"File musik '{src}' tidak ada.",
                                "Taruh file di assets/music/ atau set audio.music_file = null untuk musik generatif.")
        x = decode_audio(src, sr, 2)
        reps = math.ceil(dur * sr / max(len(x), 1))
        return np.tile(x, (reps, 1))[: int(dur * sr)]
    key = stable_hash([round(dur, 2), pulse_regions, SYNTH_VERSION, sr], 12)
    cached = paths.assets / "music" / "generated" / f"score_{key}.wav"
    if not cached.exists():
        write_wav(cached, music_score(dur, sr, pulse_regions=pulse_regions), sr)
    x = decode_audio(cached, sr, 2)
    return x[: int(dur * sr)]
