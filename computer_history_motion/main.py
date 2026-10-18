#!/usr/bin/env python3
"""Sejarah Komputer — pipeline motion graphics dokumenter (Edge-TTS + Cairo + FFmpeg).

Contoh:
  python main.py --check
  python main.py --list-voices
  python main.py --generate-voice --scenes s01
  python main.py --render-preview --scenes s01
  python main.py --all
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict
from pathlib import Path

from src import qc
from src.audio_mixer import encode_mp3, mix_master, voice_only_preview
from src.renderer import mode_settings, mux, render_still, render_video
from src.scene_manager import (estimate_duration, export_script_docs, load_script, narration_units, select_scenes,
                               selection_tag)
from src.subtitle_generator import write_subtitles
from src.timeline import build_timeline, validate_timeline
from src.tts_engine import (generate_voice, list_voices, load_scene_audio_meta, load_voice_presets, normalize_units,
                            resolve_voice, synth_test_phrase)
from src.utils import PipelineError, Paths, load_json, log, save_json, stable_hash


class Pipeline:
    def __init__(self, args):
        self.args = args
        out = Path(args.output_dir).resolve() if args.output_dir else None
        self.paths = Paths(output=out) if out else Paths()
        self.paths.ensure()
        self.project = load_json(self.paths.config / "project.json")
        if args.no_burn_subtitles:
            self.project["subtitles"]["burn_in"] = False
        self.presets = load_voice_presets(self.paths)
        self.voice = resolve_voice(self.presets, args.preset or self.project["tts"].get("preset"),
                                   rate=args.rate, pitch=args.pitch, volume=args.volume, voice=args.voice)
        self.script = load_script(self.paths, args.script)
        self.all_scenes = self.script["scenes"]
        self.scenes = select_scenes(self.all_scenes, args.scenes)
        self.tag = selection_tag(self.scenes, self.all_scenes)
        self.base = f"{self.project['project']['output_basename']}_{self.tag}"
        self.use_cache = not args.no_cache
        self._manifest = None
        self._master = None

    # ------------------------------------------------------------------ naskah
    def generate_script(self):
        log("\n▶ Naskah: validasi dan ekspor storyboard")
        files = export_script_docs(self.paths, self.script, self.scenes)
        total = 0.0
        for sc in self.scenes:
            est = estimate_duration(sc)
            total += est
            log(f"  {sc['scene_id']:<18} {len(narration_units(sc)):>2} unit  ≈{est:5.1f}s  "
                f"{len(sc['historical_sources'])} sumber")
        log(f"  Estimasi total ≈ {total:.0f}s ({total / 60:.1f} menit) — durasi final diukur dari audio.")
        for f in files:
            log(f"  ✓ {f.relative_to(self.paths.root)}")

    # ------------------------------------------------------------------ voice
    def _voice_stale(self, sc) -> bool:
        meta = load_scene_audio_meta(self.paths, sc["scene_id"])
        if meta is None or not (self.paths.root / meta["file"]).exists():
            return True
        texts = [u["text"] for u in normalize_units(sc)]
        v = meta["voice"]
        return texts != [u["text"] for u in meta["units"]] or any(
            v.get(k) != getattr(self.voice, k) for k in ("voice", "rate", "pitch", "volume", "unit_pause")) or any(
            float(u.get("pause_after", self.voice.unit_pause)) != m["pause_after"]
            for u, m in list(zip(normalize_units(sc), meta["units"]))[:-1])

    def generate_voice(self, force: bool = False):
        todo = [sc for sc in self.scenes if force or self._voice_stale(sc)]
        log(f"\n▶ Voice-over: {len(todo)} dari {len(self.scenes)} scene perlu dibuat")
        if todo:
            generate_voice(self.paths, todo, self.voice, self.presets, self.project, use_cache=self.use_cache)
        self._manifest = None

    def ensure_voice(self):
        if any(self._voice_stale(sc) for sc in self.scenes):
            self.generate_voice()

    # ------------------------------------------------------------------ timeline
    def manifest(self) -> dict:
        if self._manifest is None:
            self.ensure_voice()
            audio = {sc["scene_id"]: load_scene_audio_meta(self.paths, sc["scene_id"]) for sc in self.scenes}
            m = build_timeline(self.scenes, audio, self.project, self.project["video"]["fps"])
            m["voice"] = asdict(self.voice)
            m["selection"] = self.tag
            m["hash"] = stable_hash(m, 16)
            probs = validate_timeline(m)
            if probs:
                raise PipelineError("Timeline tidak valid:\n    - " + "\n    - ".join(probs),
                                    "Sesuaikan lead_in/tail/transisi di naskah atau config/project.json.")
            path = self.paths.manifest if self.tag == "full" else \
                self.paths.output / f"timing_manifest_{self.tag}.json"
            save_json(path, m)
            log(f"  ✓ Timing manifest: {path.relative_to(self.paths.root)}  "
                f"({m['total_duration']:.2f}s, {len(m['scenes'])} scene, {len(m['subtitles'])} cue)")
            self._manifest = m
        return self._manifest

    # ------------------------------------------------------------------ subtitle
    def generate_subtitles(self):
        log("\n▶ Subtitle")
        m = self.manifest()
        v = self.project["video"]
        files = write_subtitles(m["subtitles"], self.project["subtitles"], self.paths.subtitles / self.base,
                                v["width"], v["height"])
        for f in files:
            log(f"  ✓ {f.relative_to(self.paths.root)}")
        return files

    # ------------------------------------------------------------------ audio
    def master_audio(self) -> dict:
        if self._master:
            return self._master
        m = self.manifest()
        wav = self.paths.audio / f"{self.base}_master.wav"
        rep_path = self.paths.audio / f"{self.base}_master.json"
        audio_key = stable_hash([m["hash"], self.project["audio"]], 16)
        if self.use_cache and wav.exists() and rep_path.exists() and load_json(rep_path).get("key") == audio_key:
            self._master = load_json(rep_path)
            log("  • Master audio: pakai cache")
            return self._master
        log("\n▶ Mixing audio (voice + musik ber-ducking + ambience + SFX)")
        rep = mix_master(self.paths, m, self.project, wav)
        rep["key"] = audio_key
        save_json(rep_path, rep)
        self._master = rep
        return rep

    def preview_audio(self):
        rep = self.master_audio()
        m = self.manifest()
        wav = self.paths.root / rep["file"]
        mp3 = encode_mp3(wav, self.paths.previews / f"{self.base}_audio_preview.mp3")
        vo = voice_only_preview(self.paths, self.paths.previews / f"{self.base}_voice_only.mp3")
        log("\n  Scene               narasi   scene   kata  kata/menit  perkiraan")
        for s, sc in zip(m["scenes"], self.scenes):
            words = sum(len(t.split()) for t in narration_units(sc))
            wpm = words / max(s["audio_duration"], 0.1) * 60
            log(f"  {s['scene_id']:<18} {s['audio_duration']:6.2f}s {s['duration']:6.2f}s  {words:4d}  {wpm:8.0f}"
                f"   {sc['estimated_duration']:>5}s")
        log(f"  ✓ {mp3.relative_to(self.paths.root)}\n  ✓ {vo.relative_to(self.paths.root)}")

    # ------------------------------------------------------------------ video
    def render(self, mode: str):
        t0 = time.time()
        m = self.manifest()
        srt, _ = self.generate_subtitles()
        rep = self.master_audio()
        log(f"\n▶ Render {mode}")
        overrides = {}
        if mode == "preview":
            overrides = {"scale": self.args.preview_scale, "fps": self.args.preview_fps}
        video, settings = render_video(self.paths, m, self.project, mode, self.args.workers, overrides,
                                       use_cache=self.use_cache)
        target_dir = self.paths.previews if mode == "preview" else self.paths.final
        out = target_dir / (f"{self.base}_preview.mp4" if mode == "preview" else f"{self.base}.mp4")
        soft = None if self.project["subtitles"]["burn_in"] else srt
        mux(video, self.paths.root / rep["file"], out, soft)
        log(f"  ✓ {out.relative_to(self.paths.root)}  ({out.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f}s)")
        r = qc.Report()
        qc.check_video(r, out, m, settings, expect_fade_end=self.scenes[-1]["transition"].get("out", {}).get("type")
                       == "fade_black")
        qc.check_master_audio(r, rep, self.project["audio"])
        r.print(f"QC {mode}")
        r.save(self.paths.output / f"qc_{self.base}_{mode}.json")
        if r.failed:
            raise PipelineError(f"QC {mode} gagal.", "Lihat butir ✗ di atas.")
        return out

    def stills(self, times_per_scene: int = 4):
        """Render beberapa still per scene + contact sheet untuk review visual cepat."""
        m = self.manifest()
        frames = []
        for i, s in enumerate(m["scenes"]):
            for k in range(times_per_scene):
                t = s["duration"] * (k + 0.5) / times_per_scene
                out = self.paths.previews / "stills" / f"{s['scene_id']}_{t:05.1f}s.png"
                frames.append(render_still(self.paths, m, self.project, i, t, out, "preview"))
        sheet = qc.contact_sheet(frames, self.paths.previews / f"{self.base}_contact_sheet.png")
        log(f"  ✓ {sheet.relative_to(self.paths.root)} ({len(frames)} frame)")
        return sheet

    def run_qc(self):
        r = qc.check_dependencies(self.project["theme"]["fonts"])
        if not self.args.offline:
            qc.check_voice(r, self.voice.voice)
        qc.check_scene_audio(r, self.paths, [s["scene_id"] for s in self.scenes])
        if not r.failed:
            m = self.manifest()
            qc.check_timeline(r, m)
            qc.check_subtitles(r, m, self.project["subtitles"])
            rep_path = self.paths.audio / f"{self.base}_master.json"
            if rep_path.exists():
                qc.check_master_audio(r, load_json(rep_path), self.project["audio"])
            for mode, d, name in (("final", self.paths.final, f"{self.base}.mp4"),
                                  ("preview", self.paths.previews, f"{self.base}_preview.mp4")):
                if (d / name).exists():
                    over = {"scale": self.args.preview_scale, "fps": self.args.preview_fps} if mode == "preview" else {}
                    qc.check_video(r, d / name, m, mode_settings(self.project, mode, over),
                                   expect_fade_end=self.scenes[-1]["transition"].get("out", {}).get("type") == "fade_black",
                                   blackdetect=not self.args.fast_qc)
        r.print()
        r.save(self.paths.output / f"qc_{self.base}.json")
        return r


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Pipeline video dokumenter 'Sejarah Komputer'.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    g = p.add_argument_group("perintah")
    g.add_argument("--check", action="store_true", help="periksa dependency (Python, FFmpeg, modul, font)")
    g.add_argument("--list-voices", action="store_true", help="tampilkan voice Edge-TTS (default: id-)")
    g.add_argument("--generate-script", action="store_true", help="validasi naskah + ekspor storyboard/narasi")
    g.add_argument("--generate-voice", action="store_true", help="generate voice-over per scene")
    g.add_argument("--preview-audio", action="store_true", help="mix audio lengkap + preview MP3")
    g.add_argument("--generate-subtitles", action="store_true", help="buat SRT + ASS dari timing aktual")
    g.add_argument("--render-preview", action="store_true", help="render video preview cepat")
    g.add_argument("--render-final", action="store_true", help="render video final 1080p")
    g.add_argument("--stills", action="store_true", help="render still + contact sheet untuk review visual")
    g.add_argument("--qc", action="store_true", help="jalankan quality control atas output yang ada")
    g.add_argument("--all", action="store_true", help="naskah → voice → subtitle → audio → final → QC")
    g.add_argument("--say", metavar="TEKS", help="render satu kalimat uji ke output/previews/say.mp3")
    o = p.add_argument_group("opsi")
    o.add_argument("--scenes", help="pilih scene: 's01', '1,3', 's02-s05' (default semua)")
    o.add_argument("--preset", help="preset voice: natural | warm_documentary | dramatic_subtle")
    o.add_argument("--voice", help="override nama voice, mis. id-ID-GadisNeural")
    o.add_argument("--rate", help="override rate, mis. -5%%")
    o.add_argument("--pitch", help="override pitch, mis. +0Hz")
    o.add_argument("--volume", help="override volume, mis. +0%%")
    o.add_argument("--locale", default="id-", help="filter --list-voices (default 'id-')")
    o.add_argument("--preview-scale", type=float, help="skala resolusi preview (default dari config: 0.5)")
    o.add_argument("--preview-fps", type=int, help="fps preview (default dari config: 15)")
    o.add_argument("--output-dir", help="folder output alternatif")
    o.add_argument("--no-cache", action="store_true", help="abaikan cache TTS/render/mix")
    o.add_argument("--force-voice", action="store_true", help="generate ulang voice walau tidak berubah")
    o.add_argument("--no-burn-subtitles", action="store_true", help="subtitle sebagai track terpisah, bukan burn-in")
    o.add_argument("--workers", type=int, help="jumlah proses render paralel (default: jumlah CPU)")
    o.add_argument("--script", default="documentary_id.json", help="file naskah di folder scripts/")
    o.add_argument("--offline", action="store_true", help="QC tanpa memeriksa daftar voice online")
    o.add_argument("--fast-qc", action="store_true", help="QC tanpa deteksi frame hitam (lebih cepat)")
    args = p.parse_args(argv)
    commands = ("check", "list_voices", "generate_script", "generate_voice", "preview_audio", "generate_subtitles",
                "render_preview", "render_final", "stills", "qc", "all", "say")
    if not any(getattr(args, c) for c in commands):
        p.print_help()
        sys.exit(0)
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.check:
            paths = Paths()
            project = load_json(paths.config / "project.json")
            r = qc.check_dependencies(project["theme"]["fonts"])
            r.print("Dependency")
            if r.failed:
                return 1
        if args.list_voices:
            voices = list_voices(args.locale or None)
            log(f"\n{'Voice':<28}{'Gender':<9}{'Locale':<8}Kepribadian")
            for v in voices:
                pers = ", ".join(v.get("VoiceTag", {}).get("VoicePersonalities", []))
                log(f"{v['ShortName']:<28}{v['Gender']:<9}{v['Locale']:<8}{pers}")
        if not any(getattr(args, c) for c in ("generate_script", "generate_voice", "preview_audio", "generate_subtitles",
                                              "render_preview", "render_final", "stills", "qc", "all", "say")):
            return 0
        pl = Pipeline(args)
        if args.say:
            out = synth_test_phrase(pl.paths, args.say, pl.voice, pl.presets, pl.paths.previews / "say.mp3")
            log(f"✓ {out.relative_to(pl.paths.root)}  ({pl.voice.voice} {pl.voice.rate} {pl.voice.pitch})")
        if args.generate_script or args.all:
            pl.generate_script()
        if args.generate_voice or args.all:
            pl.generate_voice(force=args.force_voice)
            pl.manifest()
        if args.generate_subtitles or args.all:
            pl.generate_subtitles()
        if args.preview_audio or args.all:
            pl.preview_audio()
        if args.stills:
            pl.stills()
        if args.render_preview:
            pl.render("preview")
        if args.render_final or args.all:
            pl.render("final")
        if args.qc or args.all:
            if pl.run_qc().failed:
                return 1
        return 0
    except PipelineError as e:
        log(f"\n✗ {e}")
        return 1
    except KeyboardInterrupt:
        log("\nDibatalkan.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
