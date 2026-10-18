"""Mixing: voice-over (utama), musik dengan ducking, ambience per era, dan SFX selektif.

Loudness memakai loudnorm EBU R128 dua tahap (linear bila memungkinkan, jadi tidak ada kompresi
dinamis tambahan). Ducking memakai sidechaincompress FFmpeg dengan voice sebagai pemicu.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np

from .sound_synth import ambience, get_music, get_sfx
from .utils import (PipelineError, Paths, db_to_gain, decode_audio, log, media_duration, read_wav, run,
                    write_wav)


def _parse_loudnorm_json(stderr: str) -> dict:
    blocks = re.findall(r"\{[^{}]*\}", stderr, re.S)
    if not blocks:
        raise PipelineError("Output loudnorm tidak terbaca.", "Pastikan FFmpeg mendukung filter loudnorm.")
    return json.loads(blocks[-1])


def measure_loudness(path: Path) -> dict:
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                "loudnorm=print_format=json", "-f", "null", "-"], f"Ukur loudness {Path(path).name}")
    d = _parse_loudnorm_json(proc.stderr)
    return {"input_i": d["input_i"], "input_tp": d["input_tp"], "input_lra": d["input_lra"],
            "input_thresh": d["input_thresh"]}


def loudnorm_file(src: Path, dst: Path, target_i: float, target_tp: float, lra: float, sr: int,
                  codec: str = "pcm_s16le") -> dict:
    """Normalisasi loudness dua tahap. Mengembalikan statistik (input & output)."""
    m = measure_loudness(src)
    if m["input_i"] in ("-inf", "inf") or float(m["input_i"]) < -70:
        shutil.copy(src, dst)
        return {"skipped": "audio hampir hening", **m}
    # Mode linear loudnorm hanya mungkin bila puncak + gain ≤ target TP. Jika tidak, FFmpeg diam-diam
    # beralih ke kompresi dinamis. Kita pangkas hanya puncak transien yang melanggar dengan limiter
    # (attack cepat, tanpa makeup), lalu ukur ulang — dinamika narasi tetap utuh.
    gain = target_i - float(m["input_i"])
    excess = float(m["input_tp"]) + gain - target_tp
    limited = None
    if excess > 0:
        limit_db = target_tp - gain - 0.5
        limited = dst.with_name(dst.stem + "_lim.wav")
        run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-af",
             f"alimiter=limit={10 ** (limit_db / 20):.5f}:attack=1:release=60:level=false:asc=1",
             "-c:a", "pcm_f32le", str(limited)], "Limiter puncak sebelum loudnorm")
        src = limited
        m = {**measure_loudness(src), "limiter_db": round(limit_db, 2), "peak_excess_db": round(excess, 2)}
    # FFmpeg ≥ 6 menolak mode linear bila LRA terukur > target LRA. Pada mode linear LRA tidak dipakai
    # (hanya gain tetap), jadi target LRA dinaikkan setinggi LRA terukur agar tidak beralih ke kompresi.
    lra = min(50.0, max(lra, float(m["input_lra"]) + 0.5))
    filt = (f"loudnorm=I={target_i}:TP={target_tp}:LRA={lra}:measured_I={m['input_i']}:"
            f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
            f"linear=true:print_format=json")
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-af", filt, "-ar", str(sr),
                "-c:a", codec, str(dst)], f"Normalisasi loudness {Path(src).name}")
    d = _parse_loudnorm_json(proc.stderr)
    if limited:
        limited.unlink(missing_ok=True)
    return {"input_i": m["input_i"], "input_tp": m["input_tp"], "output_i": d.get("output_i"),
            "output_tp": d.get("output_tp"), "output_lra": d.get("output_lra"),
            "normalization_type": d.get("normalization_type"), "limiter_db": m.get("limiter_db")}


def clipping_report(data: np.ndarray, threshold: float = 0.999) -> dict:
    peak = float(np.abs(data).max()) if data.size else 0.0
    return {"peak": round(peak, 4), "peak_dbfs": round(20 * np.log10(max(peak, 1e-9)), 2),
            "clipped_samples": int((np.abs(data) >= threshold).sum())}


def _place(buf: np.ndarray, clip: np.ndarray, at: float, sr: int, gain: float = 1.0) -> None:
    s = int(round(at * sr))
    if s >= len(buf) or s + len(clip) <= 0:
        return
    a = max(0, -s)
    seg = clip[a: len(buf) - s]
    buf[s + a: s + a + len(seg)] += seg * gain


def build_stems(paths: Paths, manifest: dict, project: dict) -> dict[str, Path]:
    acfg = project["audio"]
    sr = acfg["sample_rate"]
    total = manifest["total_duration"]
    n = int(round(total * sr))
    voice = np.zeros((n, 2), np.float32)
    fx = np.zeros((n, 2), np.float32)

    for sc in manifest["scenes"]:
        wav = paths.root / sc["audio_file"]
        data, wsr = read_wav(wav)
        if wsr != sr:
            data = decode_audio(wav, sr)
        if data.ndim == 1:
            data = np.stack([data, data], 1)
        _place(voice, data, sc["voice_start"], sr)

        # ambience era dengan fade 1 detik di batas scene
        kind = sc.get("ambience", "none")
        if kind != "none":
            amb = ambience(kind, sc["duration"], sr, seed=sc["index"])
            f = min(int(sr * 1.0), len(amb) // 3)
            if f > 0:
                ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
                amb[:f] *= ramp
                amb[-f:] *= ramp[::-1]
            _place(fx, amb, sc["start"], sr, db_to_gain(acfg["ambience_gain_db"]))

        for ev in sc.get("sfx_events", []):
            clip = get_sfx(paths, ev["name"], sr)
            _place(fx, clip, ev["time"], sr, db_to_gain(acfg["sfx_gain_db"] + ev.get("gain_db", 0.0)))

    pulse = [(r[0], r[1]) for r in manifest.get("music_pulse_regions", [])]
    music = get_music(paths, total, acfg.get("music_file"), pulse, sr)
    if len(music) < n:
        music = np.pad(music, ((0, n - len(music)), (0, 0)))
    music = music[:n] * db_to_gain(acfg["music_gain_db"])
    fi, fo = int(acfg["music_fade_in_s"] * sr), int(acfg["music_fade_out_s"] * sr)
    if 0 < fi < n:
        music[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)[:, None]
    if 0 < fo < n:
        music[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]

    paths.stems.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, arr in (("voice", voice), ("music", music), ("fx", fx)):
        p = paths.stems / f"{name}.wav"
        write_wav(p, arr, sr)
        out[name] = p
    return out


def mix_master(paths: Paths, manifest: dict, project: dict, out_wav: Path) -> dict:
    """Bangun stem → ducking → amix → loudnorm master. Mengembalikan laporan QC audio."""
    acfg = project["audio"]
    sr = acfg["sample_rate"]
    stems = build_stems(paths, manifest, project)
    d = acfg["duck"]
    pre = paths.stems / "premaster.wav"
    graph = (f"[0:a]asplit=2[vmain][vkey];"
             f"[1:a][vkey]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:"
             f"attack={d['attack_ms']}:release={d['release_ms']}:makeup={d['makeup']}[mduck];"
             f"[vmain][mduck][2:a]amix=inputs=3:normalize=0:duration=first[mix]")
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(stems["voice"]), "-i", str(stems["music"]),
         "-i", str(stems["fx"]), "-filter_complex", graph, "-map", "[mix]", "-ar", str(sr),
         "-c:a", "pcm_f32le", str(pre)], "Mixing stem (ducking + amix)")
    loud = loudnorm_file(pre, out_wav, acfg["master_lufs"], acfg["true_peak"], acfg["lra"], sr)
    data, _ = read_wav(out_wav)
    clip = clipping_report(data)
    duration = media_duration(out_wav)
    pre.unlink(missing_ok=True)
    report = {"file": str(out_wav.relative_to(paths.root)), "duration": round(duration, 4),
              "expected_duration": manifest["total_duration"], "loudness": loud, "clipping": clip}
    log(f"  ✓ Master audio {duration:.2f}s  {loud.get('output_i')} LUFS  TP {loud.get('output_tp')} dBTP  "
        f"puncak {clip['peak_dbfs']} dBFS  ({loud.get('normalization_type')})")
    return report


def voice_only_preview(paths: Paths, out_mp3: Path) -> Path:
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(paths.stems / "voice.wav"), "-ac", "1", "-b:a", "128k",
         str(out_mp3)], "Ekspor preview voice")
    return out_mp3


def encode_mp3(src: Path, dst: Path, bitrate: str = "192k") -> Path:
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-b:a", bitrate, str(dst)], f"Ekspor {dst.name}")
    return dst
