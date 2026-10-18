"""Memuat, memvalidasi, memilih, dan mendokumentasikan scene dari naskah JSON."""
from __future__ import annotations

import re
from pathlib import Path

from .utils import PipelineError, Paths, load_json

REQUIRED_FIELDS = ("scene_id", "title", "narration", "estimated_duration", "visual_description",
                   "animation_style", "transition", "sfx", "historical_sources")

WORDS_PER_SECOND = 1.5  # terukur: id-ID-GadisNeural, rate -5%, termasuk jeda alami (859 kata ≈ 575 s)


def load_script(paths: Paths, name: str = "documentary_id.json") -> dict:
    script = load_json(paths.scripts / name)
    problems = validate_script(script)
    if problems:
        raise PipelineError("Naskah tidak valid:\n    - " + "\n    - ".join(problems),
                            f"Perbaiki scripts/{name}. Field wajib per scene: {', '.join(REQUIRED_FIELDS)}")
    return script


def narration_units(scene: dict) -> list[str]:
    return [u if isinstance(u, str) else u["text"] for u in scene.get("narration", [])]


def validate_script(script: dict) -> list[str]:
    problems = []
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return ["'scenes' harus berupa daftar yang tidak kosong"]
    seen = set()
    for i, sc in enumerate(scenes):
        sid = sc.get("scene_id", f"#{i + 1}")
        for f in REQUIRED_FIELDS:
            if f not in sc:
                problems.append(f"{sid}: field '{f}' tidak ada")
        if sid in seen:
            problems.append(f"{sid}: scene_id duplikat")
        seen.add(sid)
        units = sc.get("narration", [])
        if not isinstance(units, list) or not units:
            problems.append(f"{sid}: 'narration' harus daftar unit (string atau {{text, pause_after}})")
            continue
        for k, u in enumerate(units):
            text = u if isinstance(u, str) else (u.get("text") if isinstance(u, dict) else None)
            if not text or not text.strip():
                problems.append(f"{sid}: unit narasi {k + 1} kosong")
            elif len(text) > 600:
                problems.append(f"{sid}: unit narasi {k + 1} terlalu panjang ({len(text)} karakter, maks 600)")
        if not isinstance(sc.get("historical_sources", []), list):
            problems.append(f"{sid}: 'historical_sources' harus daftar")
    return problems


def _parse_range(token: str, ids: list[str]) -> list[str]:
    def to_index(x: str) -> int:
        if x in ids:
            return ids.index(x)
        m = re.fullmatch(r"s?0*(\d+)", x)
        if m and 1 <= int(m.group(1)) <= len(ids):
            return int(m.group(1)) - 1
        matches = [i for i, sid in enumerate(ids) if sid.startswith(x)]
        if len(matches) == 1:
            return matches[0]
        raise PipelineError(f"Scene '{x}' tidak ditemukan.", f"Scene tersedia: {', '.join(ids)}")
    if "-" in token and not token.startswith("-"):
        a, b = token.split("-", 1)
        ia, ib = to_index(a), to_index(b)
        return ids[min(ia, ib): max(ia, ib) + 1]
    return [ids[to_index(token)]]


def select_scenes(scenes: list[dict], selection: str | None) -> list[dict]:
    """Pilihan: None/'all', '1,3', 's01-s03', 's05_elektronik', atau prefix unik."""
    if not selection or selection == "all":
        return scenes
    ids = [s["scene_id"] for s in scenes]
    chosen: list[str] = []
    for tok in selection.split(","):
        tok = tok.strip()
        if tok:
            chosen += [x for x in _parse_range(tok, ids) if x not in chosen]
    return [s for s in scenes if s["scene_id"] in chosen]


def selection_tag(selected: list[dict], all_scenes: list[dict]) -> str:
    if len(selected) == len(all_scenes):
        return "full"
    ids = [s["scene_id"].split("_")[0] for s in selected]
    return ids[0] if len(ids) == 1 else f"{ids[0]}-{ids[-1]}"


def estimate_duration(scene: dict, wps: float = WORDS_PER_SECOND, unit_pause: float = 0.0) -> float:
    words = sum(len(t.split()) for t in narration_units(scene))
    return round(words / wps + unit_pause * (len(scene["narration"]) - 1), 1)


def export_script_docs(paths: Paths, script: dict, scenes: list[dict]) -> list[Path]:
    """Tulis storyboard (Markdown) dan naskah narasi polos untuk dibaca/direvisi."""
    out_dir = paths.output / "script"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# {script['meta']['title']}", "", f"_{script['meta'].get('subtitle', '')}_", "",
          "Durasi aktual ditentukan oleh audio TTS. Kolom 'perkiraan' hanya estimasi dari jumlah kata.", "",
          "| # | Scene | Kata | Perkiraan (naskah) | Estimasi kata/detik |", "|---|---|---|---|---|"]
    total_words, total_est = 0, 0.0
    for i, sc in enumerate(scenes, 1):
        words = sum(len(t.split()) for t in narration_units(sc))
        est = estimate_duration(sc)
        total_words += words
        total_est += est
        md.append(f"| {i} | {sc['scene_id']} — {sc['title']} | {words} | {sc['estimated_duration']} s | {est} s |")
    md += [f"| | **Total** | **{total_words}** | | **{total_est:.0f} s ≈ {total_est / 60:.1f} menit** |", ""]
    plain = []
    for sc in scenes:
        md += [f"## {sc['scene_id']} — {sc['title']}", "",
               f"**Bab:** {sc.get('chapter', '-')}  ·  **Era:** {sc.get('era', '-')}  ·  "
               f"**Transisi keluar:** {sc['transition'].get('out', {}).get('type', '-')}", "",
               "**Narasi**", ""]
        for k, u in enumerate(sc["narration"]):
            text = u if isinstance(u, str) else u["text"]
            extra = "" if isinstance(u, str) else "  " + ", ".join(f"`{k2}={v}`" for k2, v in u.items() if k2 != "text")
            md.append(f"{k + 1}. {text}{extra}")
        md += ["", f"**Visual:** {sc['visual_description']}", "", f"**Gaya animasi:** {sc['animation_style']}", "",
               "**SFX:** " + (", ".join(e['name'] for e in sc['sfx']) or "-"), "", "**Sumber sejarah**", ""]
        md += [f"- {src['title']}" + (f" — {src['url']}" if src.get("url") else "") for src in sc["historical_sources"]]
        md.append("")
        plain += [f"[{sc['scene_id']}] {sc['title']}", ""] + narration_units(sc) + [""]
    p_md = out_dir / "storyboard.md"
    p_txt = out_dir / "narasi.txt"
    p_md.write_text("\n".join(md), encoding="utf-8")
    p_txt.write_text("\n".join(plain), encoding="utf-8")
    return [p_md, p_txt]
