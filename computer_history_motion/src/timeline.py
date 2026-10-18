"""Timeline berbasis durasi audio aktual.

Durasi scene = lead_in + durasi narasi (diukur FFprobe) + tail, dibulatkan ke atas ke batas frame.
Semua waktu (elemen, SFX, subtitle) diturunkan dari sini, sehingga mengganti audio satu scene
otomatis menggeser scene berikutnya ketika timeline dibangun ulang.

Format waktu (`at` / `until`) dalam naskah:
  2.5                         detik sejak narasi scene mulai (boleh negatif)
  "start" | "end"             awal / akhir scene
  "voice_start" | "voice_end" awal / akhir narasi
  {"scene": 1.2}              detik sejak awal scene (negatif = dari akhir scene)
  {"word": "ENIAC", "n": 2, "offset": -0.2, "edge": "start"}   kata ke-n di narasi scene
  {"unit": 3, "offset": 0}    awal unit narasi ke-3 (1-based)
"""
from __future__ import annotations

import copy
import difflib
import math

from .alignment import norm
from .subtitle_generator import build_cues
from .utils import PipelineError, stable_hash


class SceneClock:
    def __init__(self, scene_id: str, duration: float, lead: float, voice_dur: float, tokens: list[dict],
                 units: list[dict]):
        self.scene_id = scene_id
        self.duration = duration
        self.lead = lead
        self.voice_dur = voice_dur
        self.tokens = tokens        # waktu relatif awal narasi
        self.units = units

    def find_word(self, word: str, n: int = 1, edge: str = "start") -> float:
        target = norm(word)
        hits = [t for t in self.tokens if norm(t["text"]) == target]
        if len(hits) < n:
            hits += [t for t in self.tokens if norm(t["text"]).startswith(target) and t not in hits]
        if len(hits) < n:
            words = sorted({t["text"].strip(".,;:!?—") for t in self.tokens})
            close = difflib.get_close_matches(word, words, n=4)
            raise PipelineError(f"{self.scene_id}: kata cue '{word}' (kemunculan ke-{n}) tidak ada di narasi.",
                                f"Ganti cue dengan kata yang ada di narasi{', mis. ' + ', '.join(close) if close else ''}.")
        return hits[n - 1][edge]

    def resolve(self, spec, default: float | None = None) -> float | None:
        """Kembalikan detik lokal scene."""
        if spec is None:
            return default
        if isinstance(spec, (int, float)):
            return self.lead + float(spec)
        if isinstance(spec, str):
            table = {"start": 0.0, "end": self.duration, "voice_start": self.lead,
                     "voice_end": self.lead + self.voice_dur}
            if spec not in table:
                raise PipelineError(f"{self.scene_id}: penanda waktu '{spec}' tidak dikenal.",
                                    "Gunakan start, end, voice_start, voice_end, angka, atau {word: ...}.")
            return table[spec]
        if "scene" in spec:
            v = float(spec["scene"])
            return v if v >= 0 else self.duration + v
        if "word" in spec:
            t = self.find_word(spec["word"], int(spec.get("n", 1)), spec.get("edge", "start"))
            return self.lead + t + float(spec.get("offset", 0.0))
        if "unit" in spec:
            idx = int(spec["unit"]) - 1
            if not 0 <= idx < len(self.units):
                raise PipelineError(f"{self.scene_id}: unit {spec['unit']} tidak ada.",
                                    f"Scene ini punya {len(self.units)} unit narasi.")
            return self.lead + self.units[idx]["start"] + float(spec.get("offset", 0.0))
        raise PipelineError(f"{self.scene_id}: format waktu tidak dikenal: {spec}", "Lihat dokumentasi timeline.py.")


def _resolve_elements(elements: list[dict], clock: SceneClock) -> list[dict]:
    out = []
    for i, el in enumerate(elements):
        e = copy.deepcopy(el)
        e.setdefault("id", f"{el['type']}_{i + 1}")
        e["t_in"] = round(clock.resolve(el.get("at"), 0.0), 4)
        e["t_out"] = None if el.get("until") is None else round(clock.resolve(el["until"]), 4)
        if "focus_at" in el:
            e["t_focus"] = round(clock.resolve(el.get("focus_at")), 4)
        for key in e.get("path", []):
            key["t_in"] = round(clock.resolve(key["at"]), 4)
        if el["type"] in ("morph", "strip"):
            for it in e["items"]:
                it["t_in"] = round(clock.resolve(it.get("at"), e["t_in"]), 4)
        out.append(e)
    return out


def _resolve_camera(camera: dict | None, clock: SceneClock) -> dict:
    cam = copy.deepcopy(camera or {"type": "push_in"})
    for mv in cam.get("moves", []):
        mv["at"] = round(clock.resolve(mv["at"]), 4)
    return cam


def build_timeline(scenes: list[dict], audio: dict[str, dict], project: dict, fps: int) -> dict:
    tl = project["timeline"]
    sub_cfg = project["subtitles"]
    manifest_scenes = []
    cursor_frames = 0
    prev_out = None
    for idx, sc in enumerate(scenes):
        sid = sc["scene_id"]
        meta = audio.get(sid)
        if meta is None:
            raise PipelineError(f"Audio untuk {sid} belum ada.", "Jalankan: python main.py --generate-voice")
        timing = sc.get("timing", {})
        lead = float(timing.get("lead_in", tl["first_scene_lead_in"] if idx == 0 else tl["lead_in"]))
        tail = float(timing.get("tail", tl["tail"]))
        voice_dur = float(meta["duration"])
        raw = max(lead + voice_dur + tail, tl["min_scene_duration"])
        frames = math.ceil(raw * fps - 1e-6)
        dur = frames / fps
        start = cursor_frames / fps

        t_in = dict(sc["transition"].get("in") or {"type": (prev_out or {}).get("type", "fade")})
        t_out = dict(sc["transition"].get("out") or {"type": "fade"})
        t_in.setdefault("dur", tl["transition_duration"])
        t_out.setdefault("dur", tl["transition_duration"])
        if idx == 0 and not sc["transition"].get("in"):
            t_in = {"type": "fade", "dur": min(lead, 1.0)}
        prev_out = t_out

        units = [{"index": u["index"], "start": u["start"], "end": u["end"], "text": u["text"]} for u in meta["units"]]
        clock = SceneClock(sid, dur, lead, voice_dur, meta["tokens"], units)
        elements = _resolve_elements(sc.get("elements", []), clock)

        sfx_events = []
        for ev in sc.get("sfx", []):
            at = ev.get("at", "start")
            if at == "transition_out":
                t_local = dur - t_out["dur"]
            elif at == "transition_in":
                t_local = 0.0
            else:
                t_local = clock.resolve(at)
            sfx_events.append({"name": ev["name"], "time": round(start + t_local + ev.get("offset", 0.0), 4),
                               "gain_db": ev.get("gain_db", 0.0)})

        tokens_global = [{"text": t["text"], "start": round(start + lead + t["start"], 4),
                          "end": round(start + lead + t["end"], 4), "unit": t["unit"],
                          "approx": t.get("approx", False)} for t in meta["tokens"]]
        cues = build_cues(tokens_global, sub_cfg)
        for c in cues:
            c["scene_id"] = sid
            c["position"] = {"align": "bottom_center", "margin_bottom": sub_cfg["margin_bottom"]}

        entry = {
            "index": idx, "scene_id": sid, "title": sc["title"], "chapter": sc.get("chapter", ""),
            "era": sc.get("era", ""), "accent": sc.get("accent", "cyan"), "ambience": sc.get("ambience", "none"),
            "start": round(start, 4), "end": round(start + dur, 4), "duration": round(dur, 4),
            "start_frame": cursor_frames, "n_frames": frames,
            "lead_in": lead, "tail_planned": tail, "voice_start": round(start + lead, 4),
            "voice_end": round(start + lead + voice_dur, 4), "audio_duration": voice_dur,
            "audio_file": meta["file"], "audio_hash": meta["hash"],
            "transition": {"in": t_in, "out": t_out},
            "camera": _resolve_camera(sc.get("camera"), clock),
            "elements": elements,
            "text_appearances": [{"id": e["id"], "type": e["type"], "t_in": round(start + e["t_in"], 3),
                                  "t_out": None if e["t_out"] is None else round(start + e["t_out"], 3),
                                  "text": e.get("text") or e.get("label") or e.get("title")}
                                 for e in elements],
            "units": [{"index": u["index"], "start": round(start + lead + u["start"], 4),
                       "end": round(start + lead + u["end"], 4), "text": u["text"]} for u in units],
            "sfx_events": sfx_events,
            "subtitles": cues,
            "music_pulse": bool(sc.get("music_pulse", False)),
        }
        entry["render_hash"] = stable_hash({k: v for k, v in entry.items() if k not in ("start", "start_frame")}, 16)
        manifest_scenes.append(entry)
        cursor_frames += frames

    total = cursor_frames / fps
    return {
        "version": 1, "fps": fps, "total_frames": cursor_frames, "total_duration": round(total, 4),
        "scenes": manifest_scenes,
        "subtitles": [c for s in manifest_scenes for c in s["subtitles"]],
        "chapter_markers": [s["start"] for s in manifest_scenes],
        "music_pulse_regions": [[s["start"], s["end"]] for s in manifest_scenes if s["music_pulse"]],
    }


def validate_timeline(manifest: dict) -> list[str]:
    """Pemeriksaan konsistensi: kontinuitas, narasi tidak terpotong, transisi tidak menimpa narasi."""
    problems = []
    fps = manifest["fps"]
    expected = 0
    for s in manifest["scenes"]:
        sid = s["scene_id"]
        if s["start_frame"] != expected:
            problems.append(f"{sid}: celah/tumpang tindih frame (mulai {s['start_frame']}, harusnya {expected})")
        expected = s["start_frame"] + s["n_frames"]
        if s["voice_end"] > s["end"] + 1e-6:
            problems.append(f"{sid}: narasi berakhir setelah scene selesai (narasi terpotong)")
        if s["transition"]["in"]["dur"] > s["lead_in"] + 0.35:
            problems.append(f"{sid}: transisi masuk ({s['transition']['in']['dur']}s) lebih panjang dari lead-in")
        out_start = s["end"] - s["transition"]["out"]["dur"]
        if out_start < s["voice_end"] - 0.05:
            problems.append(f"{sid}: transisi keluar dimulai {s['voice_end'] - out_start:.2f}s sebelum narasi selesai")
        for e in s["elements"]:
            if not -0.01 <= e["t_in"] <= s["duration"]:
                problems.append(f"{sid}: elemen {e['id']} muncul di luar scene (t={e['t_in']:.2f}s)")
            if e["t_out"] is not None and e["t_out"] < e["t_in"]:
                problems.append(f"{sid}: elemen {e['id']} keluar sebelum masuk")
        for ev in s["sfx_events"]:
            if not s["start"] - 0.01 <= ev["time"] <= s["end"]:
                problems.append(f"{sid}: SFX {ev['name']} di luar scene")
    if abs(expected / fps - manifest["total_duration"]) > 1e-3:
        problems.append("total durasi tidak cocok dengan jumlah frame")
    return problems
