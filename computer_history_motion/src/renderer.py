"""Render frame Cairo → FFmpeg (H.264), paralel per potongan frame, lalu concat + mux audio.

Frame setiap mode (preview/final) diturunkan dari waktu global: frame ke-k mewakili t = k/fps.
Batas scene dibulatkan di skala waktu global sehingga preview 15 fps pun tidak mengalami drift.
"""
from __future__ import annotations

import math
import multiprocessing as mp
import os
import subprocess
import time
from pathlib import Path

import cairo
import numpy as np

from .animation_engine import (Background, Theme, camera_at, clip_for_transition, content_alpha, draw_subtitle,
                               draw_transition_overlay, draw_vignette, transition_camera, transition_state)
from .scene_elements import RenderCtx, build_element, draw_chapter_tag, draw_progress
from .subtitle_generator import cue_at
from .utils import PipelineError, Paths, log, run, stable_hash

RENDER_MODULES = ("animation_engine.py", "illustrations.py", "scene_elements.py", "renderer.py")
CHUNK_SECONDS = 8.0


def code_hash() -> str:
    src = Path(__file__).parent
    return stable_hash([(m, (src / m).read_text(encoding="utf-8")) for m in RENDER_MODULES], 12)


def mode_settings(project: dict, mode: str, overrides: dict | None = None) -> dict:
    v = project["video"]
    cfg = dict(v[mode])
    cfg.update({k: val for k, val in (overrides or {}).items() if val is not None})
    w = int(round(v["width"] * cfg["scale"] / 2) * 2)
    h = int(round(v["height"] * cfg["scale"] / 2) * 2)
    cfg.update({"mode": mode, "width": w, "height": h, "pixel_format": v["pixel_format"]})
    return cfg


def scene_frame_range(scene: dict, fps: int) -> tuple[int, int]:
    return int(round(scene["start"] * fps)), int(round(scene["end"] * fps))


# --------------------------------------------------------------------------- worker

class FrameRenderer:
    def __init__(self, job: dict):
        self.job = job
        self.scene = job["scene"]
        self.mode = job["mode"]
        self.W, self.H = self.mode["width"], self.mode["height"]
        self.scale = self.W / 1920.0
        self.theme = Theme.from_config(job["theme"])
        self.theme.accent_name = self.scene.get("accent", "cyan")
        self.bg = Background(self.theme)
        self.rc = RenderCtx(self.theme, self.scene, job["total_scenes"])
        self.elements = [build_element(e) for e in self.scene["elements"]]
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)
        self.ctx = cairo.Context(self.surface)
        self.cues = job["cues"]
        self.cue_hint = 0
        self.grain = self._make_grain() if self.mode.get("grain") else None

    def _make_grain(self):
        rng = np.random.default_rng(1)
        tiles = []
        for _ in range(4):
            n = rng.integers(0, 255, (self.H, self.W), dtype=np.uint8)
            arr = np.empty((self.H, self.W, 4), np.uint8)
            arr[..., 0] = arr[..., 1] = arr[..., 2] = n
            arr[..., 3] = 255
            surf = cairo.ImageSurface.create_for_data(memoryview(arr), cairo.FORMAT_ARGB32, self.W, self.H,
                                                      self.W * 4)
            tiles.append((surf, arr))
        return tiles

    def draw(self, t: float) -> None:
        sc, ctx, th = self.scene, self.ctx, self.theme
        dur = sc["duration"]
        gt = sc["start"] + t
        ts = transition_state(t, dur, sc["transition"]["in"], sc["transition"]["out"])
        cam = transition_camera(ts, camera_at(sc["camera"], t, dur))
        ctx.save()
        ctx.scale(self.scale, self.scale)
        self.bg.draw(ctx, gt, cam, th.accent)

        ctx.push_group()
        clip_for_transition(ctx, ts)
        for el in self.elements:
            if el.visible(t):
                ctx.save()
                cam.apply(ctx, el.depth)
                el.draw(ctx, t, self.rc)
                ctx.restore()
        if th.show_chapter_tag:
            draw_chapter_tag(ctx, t, dur, self.rc)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(content_alpha(ts))

        draw_transition_overlay(ctx, ts, th, th.accent)
        draw_vignette(ctx, 0.55)
        if th.show_progress:
            draw_progress(ctx, gt, self.job["total_duration"], self.job["chapter_markers"], th, th.accent)
        if self.job["burn_subtitles"]:
            cue, self.cue_hint = cue_at(self.cues, gt, self.cue_hint)
            draw_subtitle(ctx, cue, gt, self.job["subtitle_cfg"], th)
        if ts and ts.kind == "fade_black" and ts.phase == "out":
            ctx.set_source_rgba(0, 0, 0, ts.p)
            ctx.paint()
        ctx.restore()
        if self.grain:
            surf, _ = self.grain[int(gt * 24) % len(self.grain)]
            ctx.set_operator(cairo.OPERATOR_OVERLAY)
            ctx.set_source_surface(surf, 0, 0)
            ctx.paint_with_alpha(0.045)
            ctx.set_operator(cairo.OPERATOR_OVER)
        self.surface.flush()

    def frame_bytes(self) -> memoryview:
        return self.surface.get_data()


def render_chunk(job: dict) -> dict:
    """Dijalankan di proses worker. Merender frame [f0, f1) dari scene ke file MP4."""
    t0 = time.time()
    fr = FrameRenderer(job)
    fps = job["mode"]["fps"]
    m = job["mode"]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{fr.W}x{fr.H}",
           "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", m["preset"], "-crf", str(m["crf"]),
           "-tune", "animation", "-pix_fmt", m["pixel_format"], "-g", str(fps * 2), "-r", str(fps), job["out"]]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(job["f0"], job["f1"]):
            t = f / fps - job["scene"]["start"]
            fr.draw(t)
            proc.stdin.write(fr.frame_bytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="ignore")
        code = proc.wait()
    except BrokenPipeError:
        err = proc.stderr.read().decode(errors="ignore")
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"FFmpeg encode gagal untuk {job['out']}: {err[-500:]}")
    return {"out": job["out"], "frames": job["f1"] - job["f0"], "seconds": time.time() - t0,
            "scene_id": job["scene"]["scene_id"]}


# --------------------------------------------------------------------------- orkestrasi

def render_video(paths: Paths, manifest: dict, project: dict, mode: str, workers: int | None = None,
                 overrides: dict | None = None, use_cache: bool = True) -> tuple[Path, dict]:
    """Render semua scene di manifest menjadi satu video tanpa audio. Mengembalikan (path, info)."""
    m = mode_settings(project, mode, overrides)
    fps = m["fps"]
    burn = project["subtitles"]["burn_in"]
    chash = code_hash()
    cache_dir = paths.render_cache / f"{mode}_{m['width']}x{m['height']}_{fps}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    shared = {"total_duration": manifest["total_duration"], "chapter_markers": manifest["chapter_markers"],
              "total_scenes": len(manifest["scenes"])}

    scene_files, jobs, pending = [], [], {}
    for sc in manifest["scenes"]:
        f0, f1 = scene_frame_range(sc, fps)
        cues = [c for c in manifest["subtitles"] if c["end"] >= sc["start"] - 1 and c["start"] <= sc["end"] + 1]
        key = stable_hash([sc["render_hash"], sc["start"], f0, f1, m, project["theme"], project["subtitles"], burn,
                           chash, shared], 16)
        out = cache_dir / f"{sc['scene_id']}_{key}.mp4"
        scene_files.append(out)
        if use_cache and out.exists():
            log(f"  • {sc['scene_id']}: pakai cache render")
            continue
        n_chunks = max(1, math.ceil((f1 - f0) / (CHUNK_SECONDS * fps)))
        bounds = [f0 + round(i * (f1 - f0) / n_chunks) for i in range(n_chunks + 1)]
        parts = []
        for i in range(n_chunks):
            part = cache_dir / f"{sc['scene_id']}_{key}_part{i:03d}.mp4"
            parts.append(part)
            jobs.append({"scene": sc, "f0": bounds[i], "f1": bounds[i + 1], "out": str(part), "mode": m,
                         "theme": project["theme"], "subtitle_cfg": project["subtitles"], "burn_subtitles": burn,
                         "cues": cues, **shared})
        pending[out] = parts

    if jobs:
        workers = workers or max(1, (os.cpu_count() or 2))
        total_frames = sum(j["f1"] - j["f0"] for j in jobs)
        log(f"  • Render {len(jobs)} potongan, {total_frames} frame @ {m['width']}x{m['height']} {fps} fps, "
            f"{min(workers, len(jobs))} proses")
        t0 = time.time()
        done = 0
        try:
            with mp.get_context("spawn" if os.name == "nt" else "fork").Pool(min(workers, len(jobs))) as pool:
                for res in pool.imap_unordered(render_chunk, jobs):
                    done += res["frames"]
                    elapsed = time.time() - t0
                    log(f"    {res['scene_id']}: {res['frames']} frame ({res['frames'] / res['seconds']:.1f} fps/proses)"
                        f"  total {done}/{total_frames}  {elapsed:.0f}s")
        except RuntimeError as e:
            raise PipelineError(str(e), "Periksa ruang disk dan instalasi libx264 pada FFmpeg.")
        for out, parts in pending.items():
            concat_files(parts, out)
            for p in parts:
                p.unlink(missing_ok=True)
        log(f"  ✓ Render selesai dalam {time.time() - t0:.1f}s")

    video = paths.render_cache / f"_joined_{mode}.mp4"
    concat_files(scene_files, video)
    return video, m


def concat_files(files: list[Path], out: Path) -> Path:
    if len(files) == 1:
        if Path(files[0]) != out:
            out.write_bytes(Path(files[0]).read_bytes())
        return out
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(f).resolve().as_posix()}'\n" for f in files), encoding="utf-8")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
        f"Gabung {len(files)} klip video")
    lst.unlink(missing_ok=True)
    return out


def mux(video: Path, audio: Path, out: Path, srt: Path | None = None, faststart: bool = True) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio)]
    if srt:
        cmd += ["-i", str(srt)]
    cmd += ["-map", "0:v", "-map", "1:a"]
    if srt:
        cmd += ["-map", "2:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=ind"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    if faststart:
        cmd += ["-movflags", "+faststart"]
    cmd += [str(out)]
    run(cmd, f"Mux audio+video → {out.name}")
    return out


def render_still(paths: Paths, manifest: dict, project: dict, scene_index: int, t: float, out: Path,
                 mode: str = "final") -> Path:
    """Render satu frame PNG (untuk inspeksi visual/QC tanpa encode video)."""
    m = mode_settings(project, mode)
    sc = manifest["scenes"][scene_index]
    job = {"scene": sc, "mode": m, "theme": project["theme"], "subtitle_cfg": project["subtitles"],
           "burn_subtitles": project["subtitles"]["burn_in"], "cues": manifest["subtitles"],
           "total_duration": manifest["total_duration"], "chapter_markers": manifest["chapter_markers"],
           "total_scenes": len(manifest["scenes"])}
    fr = FrameRenderer(job)
    fr.draw(t)
    out.parent.mkdir(parents=True, exist_ok=True)
    fr.surface.write_to_png(str(out))
    return out
