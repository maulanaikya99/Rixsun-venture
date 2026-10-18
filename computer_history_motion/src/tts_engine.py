"""Voice-over Indonesia dengan Microsoft Edge-TTS.

Yang benar-benar dikontrol Edge-TTS hanya: voice, rate, pitch, volume. Tidak ada tag emosi.
Dinamika narasi dibangun dari pemenggalan unit (paragraf/kalimat), tanda baca, jeda antarunit
yang terukur, dan override rate/pitch per unit yang tetap konservatif (lihat `limits`).
"""
from __future__ import annotations

import asyncio
import os
import re
import ssl
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .alignment import align_tokens
from .utils import (PipelineError, Paths, decode_audio, load_json, log, media_duration, save_json,
                    stable_hash, write_wav)

ENGINE_VERSION = 3  # naikkan bila logika sintesis/trim berubah agar cache lama tidak dipakai

_RATE_RE = re.compile(r"^[+-]\d{1,3}%$")
_PITCH_RE = re.compile(r"^[+-]\d{1,3}Hz$")


# --------------------------------------------------------------------------- konfigurasi voice

@dataclass
class VoiceConfig:
    voice: str = "id-ID-GadisNeural"
    rate: str = "-5%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    language: str = "id-ID"
    unit_pause: float = 0.5
    preset: str = "custom"

    def tts_params(self) -> dict:
        return {"voice": self.voice, "rate": self.rate, "pitch": self.pitch, "volume": self.volume}

    def with_overrides(self, **kw) -> "VoiceConfig":
        data = asdict(self)
        data.update({k: v for k, v in kw.items() if v is not None and k in data})
        return VoiceConfig(**data)


def _num(value: str) -> int:
    return int(re.sub(r"[^\d+-]", "", value))


def validate_voice(cfg: VoiceConfig, limits: dict | None = None) -> list[str]:
    """Kembalikan daftar masalah (kosong = valid). Menolak nilai ekstrem sesuai `limits`."""
    limits = limits or {}
    problems = []
    if not re.match(r"^[a-z]{2,3}-[A-Z]{2}-\w+Neural$", cfg.voice):
        problems.append(f"voice '{cfg.voice}' tidak berformat seperti 'id-ID-GadisNeural'")
    for name, regex, key, unit in (("rate", _RATE_RE, "rate_pct", "%"), ("volume", _RATE_RE, "volume_pct", "%"),
                                   ("pitch", _PITCH_RE, "pitch_hz", "Hz")):
        value = getattr(cfg, name)
        if not regex.match(value):
            problems.append(f"{name} '{value}' harus berformat seperti '{'+0Hz' if unit == 'Hz' else '-5%'}'")
            continue
        lo, hi = limits.get(key, (-100, 100))
        if not lo <= _num(value) <= hi:
            problems.append(f"{name} {value} di luar batas aman [{lo}{unit}, {hi}{unit}]")
    lo, hi = limits.get("unit_pause_s", (0.0, 3.0))
    if not lo <= cfg.unit_pause <= hi:
        problems.append(f"unit_pause {cfg.unit_pause}s di luar batas [{lo}, {hi}]")
    return problems


def load_voice_presets(paths: Paths) -> dict:
    return load_json(paths.config / "voice_presets.json")


def resolve_voice(presets: dict, name: str | None = None, **overrides) -> VoiceConfig:
    name = name or presets.get("default", "warm_documentary")
    if name not in presets["presets"]:
        raise PipelineError(f"Preset voice '{name}' tidak ada.",
                            f"Pilih salah satu: {', '.join(presets['presets'])}")
    data = {k: v for k, v in presets["presets"][name].items() if k != "description"}
    cfg = VoiceConfig(preset=name, **data).with_overrides(**overrides)
    problems = validate_voice(cfg, presets.get("limits"))
    if problems:
        raise PipelineError("Konfigurasi voice tidak valid: " + "; ".join(problems),
                            "Ubah nilai di config/voice_presets.json atau opsi CLI. Gunakan nilai konservatif.")
    return cfg


# --------------------------------------------------------------------------- pengucapan

_EDGE_PUNCT = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.UNICODE)


def apply_pronunciation(text: str, lexicon: dict) -> str:
    """Ganti kata per token (tanda baca dipertahankan). Hanya untuk teks yang dikirim ke TTS."""
    if not lexicon:
        return text
    out = []
    for tok in text.split():
        lead, core, trail = _EDGE_PUNCT.match(tok).groups()
        out.append(f"{lead}{lexicon.get(core, core)}{trail}")
    return " ".join(out)


# --------------------------------------------------------------------------- jaringan

def patch_edge_tts_ssl() -> None:
    """edge-tts memakai bundle certifi secara hardcode. Di jaringan dengan proxy TLS (kantor,
    sandbox), CA tambahan dari SSL_CERT_FILE/REQUESTS_CA_BUNDLE perlu ikut dipercaya.
    Verifikasi TLS TETAP aktif; kita hanya menambah CA tepercaya."""
    extra = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if not extra or not Path(extra).exists():
        return
    import certifi
    import edge_tts.communicate as ec
    import edge_tts.voices as ev
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(cafile=extra)
    ec._SSL_CTX = ctx
    ev._SSL_CTX = ctx


def explain_tts_error(exc: BaseException) -> PipelineError:
    name = type(exc).__name__
    text = str(exc)
    if "Certificate" in name or "CERTIFICATE_VERIFY_FAILED" in text:
        fix = ("Jaringan memakai proxy dengan sertifikat sendiri. Set SSL_CERT_FILE ke bundle CA proxy "
               "(modul ini otomatis memakainya).")
    elif "NoAudioReceived" in name:
        fix = "Server tidak mengembalikan audio. Periksa nama voice (python main.py --list-voices) dan teks narasi."
    elif "403" in text or "WSServerHandshakeError" in name:
        fix = "Server Microsoft menolak permintaan. Perbarui library: pip install -U edge-tts."
    elif isinstance(exc, asyncio.TimeoutError) or "Timeout" in name:
        fix = "Koneksi lambat/terputus. Coba lagi, atau naikkan tts.timeout_s di config/project.json."
    else:
        fix = "Periksa koneksi internet. Edge-TTS membutuhkan akses ke speech.platform.bing.com."
    return PipelineError(f"Edge-TTS gagal: {name}: {text[:300]}", fix)


async def list_voices_async(locale_prefix: str | None = "id-") -> list[dict]:
    import edge_tts
    patch_edge_tts_ssl()
    voices = await edge_tts.list_voices()
    if locale_prefix:
        voices = [v for v in voices if v["ShortName"].startswith(locale_prefix)]
    return sorted(voices, key=lambda v: v["ShortName"])


def list_voices(locale_prefix: str | None = "id-") -> list[dict]:
    try:
        return asyncio.run(list_voices_async(locale_prefix))
    except Exception as e:  # noqa: BLE001
        raise explain_tts_error(e) from e


# --------------------------------------------------------------------------- sintesis satu unit

@dataclass
class UnitResult:
    text: str
    tts_text: str
    mp3: Path
    words: list[dict]          # [{text, start, end}] detik, relatif terhadap awal mp3
    duration: float
    cache_key: str
    cached: bool = False


@dataclass
class TTSSettings:
    retries: int = 4
    timeout_s: float = 60.0
    backoff_s: float = 2.0
    concurrency: int = 3
    use_cache: bool = True


class EdgeTTSEngine:
    def __init__(self, paths: Paths, settings: TTSSettings, lexicon: dict | None = None):
        self.paths = paths
        self.settings = settings
        self.lexicon = {k: v for k, v in (lexicon or {}).items() if not k.startswith("_")}
        paths.tts_cache.mkdir(parents=True, exist_ok=True)
        patch_edge_tts_ssl()

    def cache_key(self, tts_text: str, voice: VoiceConfig) -> str:
        return stable_hash({"text": tts_text, **voice.tts_params(), "engine": ENGINE_VERSION,
                            "boundary": "WordBoundary"}, 24)

    async def _synth_once(self, tts_text: str, voice: VoiceConfig, mp3: Path) -> list[dict]:
        import edge_tts
        com = edge_tts.Communicate(tts_text, boundary="WordBoundary", connect_timeout=15,
                                   receive_timeout=int(self.settings.timeout_s), **voice.tts_params())
        words, audio = [], bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"text": chunk["text"], "start": round(start, 4),
                              "end": round(start + chunk["duration"] / 1e7, 4)})
        if not audio:
            raise PipelineError("Edge-TTS tidak mengirim audio.", "Periksa teks dan nama voice.")
        tmp = mp3.with_suffix(".part")
        tmp.write_bytes(bytes(audio))
        tmp.replace(mp3)
        return words

    async def synth(self, text: str, voice: VoiceConfig, sem: asyncio.Semaphore) -> UnitResult:
        tts_text = apply_pronunciation(text, self.lexicon)
        key = self.cache_key(tts_text, voice)
        mp3 = self.paths.tts_cache / f"{key}.mp3"
        meta = self.paths.tts_cache / f"{key}.json"
        if self.settings.use_cache and mp3.exists() and meta.exists():
            data = load_json(meta)
            return UnitResult(text, tts_text, mp3, data["words"], data["duration"], key, cached=True)
        last_exc: BaseException | None = None
        for attempt in range(1, self.settings.retries + 1):
            try:
                async with sem:
                    words = await asyncio.wait_for(self._synth_once(tts_text, voice, mp3),
                                                   timeout=self.settings.timeout_s)
                duration = media_duration(mp3)
                if duration < 0.2:
                    raise PipelineError(f"Audio terlalu pendek ({duration:.2f}s)", "Coba ulang.")
                save_json(meta, {"text": text, "tts_text": tts_text, "voice": voice.tts_params(),
                                 "duration": duration, "words": words})
                return UnitResult(text, tts_text, mp3, words, duration, key)
            except Exception as e:  # noqa: BLE001 — semua error jaringan diulang
                last_exc = e
                wait = self.settings.backoff_s * (2 ** (attempt - 1))
                log(f"    ! TTS percobaan {attempt}/{self.settings.retries} gagal ({type(e).__name__}); "
                    f"ulang dalam {wait:.0f}s")
                await asyncio.sleep(wait)
        raise explain_tts_error(last_exc)


# --------------------------------------------------------------------------- perakitan narasi scene

@dataclass
class AssemblySettings:
    sample_rate: int = 48000
    trim_tail_s: float = 0.28
    edge_fade_ms: float = 8.0
    crossfade_ms: float = 0.0


def trim_point(n_samples: int, sr: int, words: list[dict], trim_tail_s: float) -> int:
    """Titik potong ekor hening: akhir kata terakhir + margin. Tidak pernah memotong kata."""
    if not words:
        return n_samples
    end = max(w["end"] for w in words) + max(trim_tail_s, 0.12)
    return int(min(n_samples, round(end * sr)))


def _fade_edges(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
    n = int(sr * ms / 1000)
    if n <= 1 or len(x) < 4 * n:
        return x
    x = x.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def assemble_units(clips: list[np.ndarray], pauses: list[float], sr: int, crossfade_ms: float = 0.0
                   ) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Gabungkan klip dengan jeda hening terukur. Crossfade hanya dipakai bila jeda = 0 dan
    crossfade_ms > 0 (menghindari klik pada sambungan rapat). Mengembalikan (audio, [(start,end)])."""
    out: list[np.ndarray] = []
    spans = []
    pos = 0
    xf = int(sr * crossfade_ms / 1000)
    for i, clip in enumerate(clips):
        if out and xf > 0 and pauses[i - 1] <= 0 and len(out[-1]) > xf and len(clip) > xf:
            ramp = np.linspace(0, 1, xf, dtype=np.float32)
            prev = out[-1]
            prev[-xf:] = prev[-xf:] * ramp[::-1] + clip[:xf] * ramp
            clip = clip[xf:]
            start = pos - xf  # unit ini mulai di dalam ekor unit sebelumnya
        else:
            start = pos
        out.append(clip.astype(np.float32))
        pos += len(clip)
        spans.append((start / sr, pos / sr))
        if i < len(clips) - 1 and pauses[i] > 0:
            gap = np.zeros(int(round(pauses[i] * sr)), dtype=np.float32)
            out.append(gap)
            pos += len(gap)
    return (np.concatenate(out) if out else np.zeros(0, np.float32)), spans


def normalize_units(scene: dict) -> list[dict]:
    """Narasi boleh berupa string atau {text, pause_after, rate, pitch}."""
    units = []
    for u in scene["narration"]:
        units.append({"text": u} if isinstance(u, str) else dict(u))
    return units


async def _generate_scenes(engine: EdgeTTSEngine, scenes: list[dict], base_voice: VoiceConfig,
                           limits: dict) -> dict[str, list[UnitResult]]:
    sem = asyncio.Semaphore(engine.settings.concurrency)
    jobs, index = [], []
    for scene in scenes:
        for ui, unit in enumerate(normalize_units(scene)):
            voice = base_voice.with_overrides(rate=unit.get("rate"), pitch=unit.get("pitch"))
            problems = validate_voice(voice, limits)
            if problems:
                raise PipelineError(f"Override voice di {scene['scene_id']} unit {ui + 1} tidak valid: "
                                    + "; ".join(problems), "Perbaiki nilai rate/pitch unit di naskah.")
            jobs.append(engine.synth(unit["text"], voice, sem))
            index.append(scene["scene_id"])
    results = await asyncio.gather(*jobs)
    grouped: dict[str, list[UnitResult]] = {}
    for sid, res in zip(index, results):
        grouped.setdefault(sid, []).append(res)
    return grouped


def generate_voice(paths: Paths, scenes: list[dict], voice: VoiceConfig, presets: dict, project: dict,
                   use_cache: bool = True) -> list[dict]:
    """Generate audio semua unit, rakit per scene, normalisasi loudness, simpan WAV + metadata."""
    from .audio_mixer import loudnorm_file

    tcfg, acfg = project["tts"], project["audio"]
    settings = TTSSettings(retries=tcfg["retries"], timeout_s=tcfg["timeout_s"], backoff_s=tcfg["backoff_s"],
                           concurrency=tcfg["concurrency"], use_cache=use_cache)
    asm = AssemblySettings(tcfg["sample_rate"], tcfg["trim_tail_s"], tcfg["edge_fade_ms"], tcfg["crossfade_ms"])
    engine = EdgeTTSEngine(paths, settings, presets.get("pronunciation"))
    log(f"• Voice: {voice.voice}  rate={voice.rate} pitch={voice.pitch} volume={voice.volume} "
        f"(preset {voice.preset})")
    try:
        grouped = asyncio.run(_generate_scenes(engine, scenes, voice, presets.get("limits", {})))
    except PipelineError:
        raise
    except Exception as e:  # noqa: BLE001
        raise explain_tts_error(e) from e

    paths.scene_audio.mkdir(parents=True, exist_ok=True)
    metas = []
    for scene in scenes:
        sid = scene["scene_id"]
        units = normalize_units(scene)
        results = grouped[sid]
        clips, pauses, unit_meta = [], [], []
        for ui, (unit, res) in enumerate(zip(units, results)):
            audio = decode_audio(res.mp3, asm.sample_rate)
            cut = trim_point(len(audio), asm.sample_rate, res.words, asm.trim_tail_s)
            clips.append(_fade_edges(audio[:cut], asm.sample_rate, asm.edge_fade_ms))
            pauses.append(float(unit.get("pause_after", voice.unit_pause)))
            unit_meta.append({"index": ui, "text": res.text, "tts_text": res.tts_text, "cache_key": res.cache_key,
                              "cached": res.cached, "raw_duration": round(res.duration, 3),
                              "pause_after": pauses[-1] if ui < len(units) - 1 else 0.0, "words": res.words})
        data, spans = assemble_units(clips, pauses, asm.sample_rate, asm.crossfade_ms)
        raw_wav = paths.scene_audio / f"{sid}_raw.wav"
        wav = paths.scene_audio / f"{sid}.wav"
        write_wav(raw_wav, data, asm.sample_rate)
        loud = loudnorm_file(raw_wav, wav, acfg["voice_lufs"], acfg["true_peak"], acfg["lra"], asm.sample_rate)
        raw_wav.unlink(missing_ok=True)
        duration = media_duration(wav)

        tokens = []
        for um, (start, end) in zip(unit_meta, spans):
            um["start"], um["end"] = round(start, 4), round(end, 4)
            for tok in align_tokens(um["text"], um["words"], engine.lexicon, end - start):
                tokens.append({"text": tok["text"], "start": round(start + tok["start"], 4),
                               "end": round(start + tok["end"], 4), "unit": um["index"],
                               "approx": tok["approx"]})
        meta = {"scene_id": sid, "file": str(wav.relative_to(paths.root)), "duration": round(duration, 4),
                "sample_rate": asm.sample_rate, "voice": asdict(voice), "units": unit_meta, "tokens": tokens,
                "loudness": loud,
                "hash": stable_hash([u["cache_key"] for u in unit_meta] + [pauses, asdict(asm), loud.get("output_i")])}
        save_json(paths.scene_audio / f"{sid}.json", meta)
        cached = sum(u["cached"] for u in unit_meta)
        approx = sum(t["approx"] for t in tokens)
        log(f"  ✓ {sid}: {duration:6.2f}s  {len(units)} unit ({cached} dari cache)  "
            f"{len(tokens)} kata{f', {approx} kata timing perkiraan' if approx else ''}  "
            f"loudness {loud.get('output_i', '?')} LUFS")
        metas.append(meta)
    return metas


def load_scene_audio_meta(paths: Paths, scene_id: str) -> dict | None:
    p = paths.scene_audio / f"{scene_id}.json"
    return load_json(p) if p.exists() else None


def synth_test_phrase(paths: Paths, text: str, voice: VoiceConfig, presets: dict, out: Path) -> Path:
    """Render satu kalimat uji (untuk menyetel pengucapan/preset)."""
    engine = EdgeTTSEngine(paths, TTSSettings(use_cache=False), presets.get("pronunciation"))

    async def go():
        return await engine.synth(text, voice, asyncio.Semaphore(1))
    try:
        res = asyncio.run(go())
    except Exception as e:  # noqa: BLE001
        raise explain_tts_error(e) from e
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(res.mp3.read_bytes())
    return out
