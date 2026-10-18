"""Unit test: timeline, kalkulasi durasi, subtitle, konfigurasi voice, alignment, pemilihan scene.

Semua test berjalan offline (tanpa Edge-TTS dan tanpa render video).
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from src.alignment import align_tokens
from src.scene_manager import estimate_duration, select_scenes, selection_tag, validate_script
from src.subtitle_generator import build_cues, to_srt, validate_cues, wrap_lines
from src.timeline import SceneClock, build_timeline, validate_timeline
from src.tts_engine import (VoiceConfig, apply_pronunciation, assemble_units, resolve_voice, trim_point,
                            validate_voice)
from src.utils import PipelineError

ROOT = Path(__file__).resolve().parent.parent
PROJECT = json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8"))
PRESETS = json.loads((ROOT / "config" / "voice_presets.json").read_text(encoding="utf-8"))
SUB_CFG = PROJECT["subtitles"]


# --------------------------------------------------------------------------- helper

def fake_meta(sid: str, sentences: list[str], word_dur: float = 0.4, gap: float = 0.5) -> dict:
    """Metadata audio sintetis: setiap kata word_dur detik, jeda antarunit `gap`."""
    tokens, units, t = [], [], 0.1
    for ui, sent in enumerate(sentences):
        u_start = t
        for w in sent.split():
            tokens.append({"text": w, "start": round(t, 4), "end": round(t + word_dur * 0.9, 4), "unit": ui,
                           "approx": False})
            t += word_dur
        units.append({"index": ui, "start": u_start, "end": t, "text": sent})
        t += gap
    return {"scene_id": sid, "file": f"output/audio/scenes/{sid}.wav", "duration": round(t - gap + 0.3, 4),
            "tokens": tokens, "units": units, "hash": sid}


def scene(sid, narration, **kw):
    base = {"scene_id": sid, "title": sid, "narration": narration, "estimated_duration": 5,
            "visual_description": "-", "animation_style": "-", "transition": {"out": {"type": "fade", "dur": 0.6}},
            "sfx": [], "historical_sources": []}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- timeline

def test_timeline_uses_actual_audio_and_frame_quantization():
    s1 = scene("a", ["Satu dua tiga empat lima."])
    s2 = scene("b", ["Enam tujuh delapan."])
    audio = {"a": fake_meta("a", s1["narration"]), "b": fake_meta("b", s2["narration"])}
    m = build_timeline([s1, s2], audio, PROJECT, 30)
    a, b = m["scenes"]
    tl = PROJECT["timeline"]
    assert a["voice_start"] == pytest.approx(tl["first_scene_lead_in"])
    assert a["duration"] >= tl["first_scene_lead_in"] + audio["a"]["duration"] + tl["tail"] - 1e-6
    assert a["n_frames"] == math.ceil(a["duration"] * 30 - 1e-6)
    assert abs(a["duration"] * 30 - round(a["duration"] * 30)) < 1e-6      # batas frame
    assert b["start_frame"] == a["start_frame"] + a["n_frames"]             # kontinu, tanpa celah
    assert m["total_frames"] == a["n_frames"] + b["n_frames"]
    assert validate_timeline(m) == []


def test_timeline_recomputes_when_audio_changes():
    s1, s2 = scene("a", ["Satu dua tiga."]), scene("b", ["Empat lima."])
    short = {"a": fake_meta("a", s1["narration"]), "b": fake_meta("b", s2["narration"])}
    long = {"a": fake_meta("a", s1["narration"], word_dur=0.9), "b": short["b"]}
    m1, m2 = build_timeline([s1, s2], short, PROJECT, 30), build_timeline([s1, s2], long, PROJECT, 30)
    assert m2["scenes"][0]["duration"] > m1["scenes"][0]["duration"]
    shift = m2["scenes"][1]["start"] - m1["scenes"][1]["start"]
    assert shift == pytest.approx(m2["scenes"][0]["duration"] - m1["scenes"][0]["duration"], abs=1e-3)
    assert m2["scenes"][1]["voice_start"] - m1["scenes"][1]["voice_start"] == pytest.approx(shift, abs=1e-3)


def test_word_cue_resolution_and_errors():
    meta = fake_meta("a", ["Tahun 1946 ENIAC menyala.", "Lalu ENIAC dipakai."])
    clock = SceneClock("a", 10.0, 0.8, meta["duration"], meta["tokens"], meta["units"])
    first = clock.resolve({"word": "ENIAC"})
    second = clock.resolve({"word": "eniac", "n": 2})
    assert first == pytest.approx(0.8 + meta["tokens"][2]["start"])
    assert second > first
    assert clock.resolve({"word": "menyala", "offset": -0.5}) == pytest.approx(0.8 + meta["tokens"][3]["start"] - 0.5)
    assert clock.resolve({"unit": 2}) == pytest.approx(0.8 + meta["units"][1]["start"])
    assert clock.resolve({"scene": -1.0}) == pytest.approx(9.0)
    assert clock.resolve(1.5) == pytest.approx(2.3)
    with pytest.raises(PipelineError):
        clock.resolve({"word": "Babbage"})
    with pytest.raises(PipelineError):
        clock.resolve({"word": "ENIAC", "n": 3})


def test_validate_timeline_detects_cut_narration():
    s1 = scene("a", ["Satu dua tiga."])
    m = build_timeline([s1], {"a": fake_meta("a", s1["narration"])}, PROJECT, 30)
    m["scenes"][0]["voice_end"] = m["scenes"][0]["end"] + 0.5
    assert any("terpotong" in p for p in validate_timeline(m))


def test_transition_longer_than_tail_is_flagged():
    s1 = scene("a", ["Satu dua tiga."], transition={"out": {"type": "bars", "dur": 3.0}})
    m = build_timeline([s1], {"a": fake_meta("a", s1["narration"])}, PROJECT, 30)
    assert any("transisi keluar" in p for p in validate_timeline(m))


# --------------------------------------------------------------------------- durasi audio

def test_trim_point_never_cuts_words():
    sr = 1000
    words = [{"start": 0.1, "end": 1.2}, {"start": 1.3, "end": 2.0}]
    assert trim_point(5000, sr, words, 0.28) == int(round(2.28 * sr))
    assert trim_point(5000, sr, words, 0.0) == int(round(2.12 * sr))      # margin minimum 0.12s
    assert trim_point(2100, sr, words, 0.5) == 2100                       # tidak melebihi panjang file
    assert trim_point(3000, sr, [], 0.3) == 3000


def test_assemble_units_measured_pauses():
    sr = 1000
    clips = [np.ones(500, np.float32), np.ones(300, np.float32), np.ones(200, np.float32)]
    audio, spans = assemble_units(clips, [0.25, 0.5, 0.0], sr)
    assert len(audio) == 500 + 250 + 300 + 500 + 200
    assert spans == [(0.0, 0.5), (0.75, 1.05), (1.55, 1.75)]
    assert np.all(audio[500:750] == 0)


def test_assemble_units_crossfade_only_without_pause():
    sr = 1000
    clips = [np.ones(500, np.float32), np.ones(500, np.float32)]
    audio, spans = assemble_units(clips, [0.0, 0.0], sr, crossfade_ms=20)
    assert len(audio) == 980
    assert spans[1][0] == pytest.approx(0.48)


def test_estimate_duration():
    sc = scene("a", ["satu dua tiga empat", "lima enam"])
    assert estimate_duration(sc, wps=2.0, unit_pause=0.5) == pytest.approx(3.5)


# --------------------------------------------------------------------------- subtitle

def tokens_from(text: str, unit: int = 0, t0: float = 0.0, wd: float = 0.35):
    out = []
    for i, w in enumerate(text.split()):
        out.append({"text": w, "start": t0 + i * wd, "end": t0 + i * wd + wd * 0.9, "unit": unit})
    return out


def test_cues_have_no_orphans_overlaps_or_three_lines():
    text = ("Salah satu dari sedikit orang yang benar-benar memahami gagasan itu adalah Ada Lovelace. "
            "Tahun 1843, ia menerjemahkan sebuah artikel tentang Analytical Engine, lalu menambahkan catatan "
            "yang panjangnya hampir tiga kali lipat artikel aslinya.")
    toks = tokens_from(text)
    cues = build_cues(toks, SUB_CFG)
    assert " ".join(c["text"] for c in cues) == text                     # tidak ada kata hilang
    assert all(len(c["text"]) >= 20 for c in cues)                         # tidak ada cue yatim
    assert all(len(c["lines"]) <= SUB_CFG["max_lines"] for c in cues)
    assert all(b["start"] >= a["end"] for a, b in zip(cues, cues[1:]))
    assert all(c["end"] - c["start"] <= SUB_CFG["max_cue_duration"] + SUB_CFG["hold_s"] + 0.1 for c in cues)
    assert not any("Ada" == c["text"].split()[-1] for c in cues)            # nama diri tidak dipisah
    assert validate_cues(cues, toks[-1]["end"] + 1, SUB_CFG) == []


def test_cues_follow_actual_word_timing_not_equal_split():
    fast = tokens_from("Kalimat pertama yang cepat sekali.", unit=0, t0=0.5, wd=0.2)
    slow = tokens_from("Kalimat kedua yang lambat.", unit=1, t0=3.0, wd=0.8)
    cues = build_cues(fast + slow, SUB_CFG)
    assert len(cues) == 2                                                   # tidak melintasi unit
    assert cues[0]["start"] == pytest.approx(fast[0]["start"] - SUB_CFG["lead_s"], abs=1e-3)
    assert cues[1]["end"] == pytest.approx(slow[-1]["end"] + SUB_CFG["hold_s"], abs=1e-3)
    assert (cues[1]["end"] - cues[1]["start"]) > (cues[0]["end"] - cues[0]["start"])


def test_validate_cues_flags_problems():
    bad = [{"start": 0, "end": 2, "text": "", "lines": [""]},
           {"start": 1.5, "end": 9, "text": "x", "lines": ["x"]}]
    probs = validate_cues(bad, 5.0, SUB_CFG)
    assert any("kosong" in p for p in probs)
    assert any("luar durasi" in p for p in probs)
    assert any("tumpang tindih" in p for p in probs)


def test_wrap_lines_balanced():
    lines = wrap_lines("Matematikawan Inggris Charles Babbage membayangkan mesin yang menghitung", 42)
    assert len(lines) == 2 and all(len(x) <= 48 for x in lines)
    assert wrap_lines("pendek", 42) == ["pendek"]


def test_srt_format():
    srt = to_srt([{"start": 3661.5, "end": 3662.25, "lines": ["Halo", "dunia"]}])
    assert "01:01:01,500 --> 01:01:02,250" in srt
    assert srt.startswith("1\n")


# --------------------------------------------------------------------------- voice config

def test_presets_valid_and_baseline():
    for name in PRESETS["presets"]:
        cfg = resolve_voice(PRESETS, name)
        assert validate_voice(cfg, PRESETS["limits"]) == []
        assert cfg.voice == "id-ID-GadisNeural"
    base = resolve_voice(PRESETS, "warm_documentary")
    assert (base.rate, base.pitch, base.volume) == ("-5%", "+0Hz", "+0%")


def test_voice_overrides_and_limits():
    cfg = resolve_voice(PRESETS, "natural", rate="-3%")
    assert cfg.rate == "-3%" and cfg.preset == "natural"
    with pytest.raises(PipelineError):
        resolve_voice(PRESETS, "natural", rate="-60%")                       # ekstrem ditolak
    with pytest.raises(PipelineError):
        resolve_voice(PRESETS, "tidak_ada")
    assert validate_voice(VoiceConfig(pitch="+2"), PRESETS["limits"])       # format salah
    assert validate_voice(VoiceConfig(pitch="+30Hz"), PRESETS["limits"])    # di luar batas


def test_pronunciation_keeps_punctuation():
    lex = {"4004": "empat nol nol empat", "ENIAC": "Eniak"}
    assert apply_pronunciation("Intel 4004, lalu ENIAC.", lex) == "Intel empat nol nol empat, lalu Eniak."
    assert apply_pronunciation("tanpa leksikon", {}) == "tanpa leksikon"


# --------------------------------------------------------------------------- alignment

def test_alignment_maps_lexicon_words_back_to_display_tokens():
    words = [{"text": "Intel", "start": 0.1, "end": 0.4}, {"text": "empat", "start": 0.5, "end": 0.7},
             {"text": "nol", "start": 0.7, "end": 0.8}, {"text": "nol", "start": 0.8, "end": 0.9},
             {"text": "empat", "start": 0.9, "end": 1.1}, {"text": "rilis", "start": 1.2, "end": 1.5}]
    toks = align_tokens("Intel 4004 rilis.", words, {"4004": "empat nol nol empat"}, 2.0)
    assert [t["text"] for t in toks] == ["Intel", "4004", "rilis."]
    assert toks[1]["start"] == pytest.approx(0.5) and toks[1]["end"] == pytest.approx(1.1)
    assert not any(t["approx"] for t in toks)


def test_alignment_interpolates_unmatched_and_falls_back():
    words = [{"text": "Satu", "start": 0.0, "end": 0.3}, {"text": "tiga", "start": 1.0, "end": 1.3}]
    toks = align_tokens("Satu — tiga", words, {}, 2.0)
    assert toks[1]["approx"] and 0.3 <= toks[1]["start"] <= 1.0
    no_words = align_tokens("a bb ccc", [], {}, 3.0)
    assert all(t["approx"] for t in no_words)
    assert no_words[-1]["end"] <= 3.0 + 1e-6


# --------------------------------------------------------------------------- naskah

def test_real_script_is_valid():
    script = json.loads((ROOT / "scripts" / "documentary_id.json").read_text(encoding="utf-8"))
    assert validate_script(script) == []
    assert len(script["scenes"]) == 11


def test_scene_selection():
    scenes = [scene(f"s{i:02d}_x", ["a"]) for i in range(1, 6)]
    assert [s["scene_id"] for s in select_scenes(scenes, "s02-s04")] == ["s02_x", "s03_x", "s04_x"]
    assert [s["scene_id"] for s in select_scenes(scenes, "1,5")] == ["s01_x", "s05_x"]
    assert selection_tag(select_scenes(scenes, "s03"), scenes) == "s03"
    assert selection_tag(scenes, scenes) == "full"
    with pytest.raises(PipelineError):
        select_scenes(scenes, "s09")
