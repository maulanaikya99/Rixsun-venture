"""Subtitle Bahasa Indonesia (SRT + ASS) dari timing kata aktual hasil Edge-TTS.

Batasan: timing kata berasal dari event WordBoundary Edge-TTS, bukan forced alignment akustik.
Token yang tidak bisa dicocokkan (mis. angka yang dieja ulang) diberi timing interpolasi dan
ditandai `approx` di metadata. Pemenggalan cue mengikuti tanda baca, batas karakter, batas durasi,
dan tidak pernah melintasi batas unit narasi (karena di sana ada jeda).
"""
from __future__ import annotations

from pathlib import Path

WEAK_ENDINGS = {"dan", "yang", "di", "ke", "dari", "untuk", "dengan", "atau", "sebuah", "seorang", "para",
                "dalam", "pada", "oleh", "tetapi", "tapi", "bahwa", "itu", "adalah", "bisa", "akan", "lebih"}
SENTENCE_END = (".", "?", "!", "…")
CLAUSE_END = (",", ";", ":", "—")


def _join(tokens: list[dict]) -> str:
    return " ".join(t["text"] for t in tokens)


def wrap_lines(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
    """Bagi teks menjadi ≤ max_lines baris yang seimbang. Lebih suka memotong setelah tanda baca."""
    if len(text) <= max_chars or max_lines < 2:
        return [text]
    words = text.split()
    best, best_score = None, None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > max_chars or len(b) > max_chars:
            continue
        score = abs(len(a) - len(b)) - (8 if a.endswith(CLAUSE_END + SENTENCE_END) else 0) \
            + (6 if words[i - 1].lower() in WEAK_ENDINGS else 0)
        if best_score is None or score < best_score:
            best, best_score = [a, b], score
    if best:
        return best
    # fallback: potong rakus
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return lines


def build_cues(tokens: list[dict], cfg: dict) -> list[dict]:
    """tokens: [{text, start, end, unit}] dalam detik global, berurutan."""
    max_line = cfg.get("max_chars_per_line", 42)
    max_total = max_line * cfg.get("max_lines", 2)
    max_dur = cfg.get("max_cue_duration", 5.5)
    groups: list[list[dict]] = []
    cur: list[dict] = []

    def flush(adjust_weak: bool = False):
        nonlocal cur
        if not cur:
            return
        carry = []
        if adjust_weak and len(cur) > 2 and cur[-1]["text"].lower().strip(",.") in WEAK_ENDINGS:
            carry = [cur.pop()]
        groups.append(cur)
        cur = carry

    for tok in tokens:
        if cur and tok.get("unit") != cur[-1].get("unit"):
            flush()
        if cur:
            too_long = len(_join(cur + [tok])) > max_total
            too_slow = tok["end"] - cur[0]["start"] > max_dur
            if too_long or too_slow:
                flush(adjust_weak=True)
        cur.append(tok)
        text = _join(cur)
        if tok["text"].endswith(SENTENCE_END) and len(text) >= 14:
            flush()
        elif tok["text"].endswith(CLAUSE_END) and len(text) >= max_total * 0.55:
            flush()
    flush()

    cues = []
    lead, hold, min_dur = cfg.get("lead_s", 0.05), cfg.get("hold_s", 0.2), cfg.get("min_cue_duration", 1.0)
    for g in groups:
        text = _join(g)
        cues.append({"start": g[0]["start"] - lead, "end": g[-1]["end"] + hold, "text": text,
                     "lines": wrap_lines(text, max_line, cfg.get("max_lines", 2)),
                     "approx": any(t.get("approx") for t in g)})
    gap = 0.04
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else None
        if i > 0:
            c["start"] = max(c["start"], cues[i - 1]["end"] + gap)
        if c["end"] - c["start"] < min_dur:
            c["end"] = c["start"] + min_dur
        if nxt is not None and c["end"] > nxt - gap:
            c["end"] = max(nxt - gap, c["start"] + 0.3)
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
    return cues


def validate_cues(cues: list[dict], total: float, cfg: dict) -> list[str]:
    problems = []
    max_line = cfg.get("max_chars_per_line", 42)
    for i, c in enumerate(cues, 1):
        if not c["text"].strip():
            problems.append(f"cue {i} kosong")
        if c["start"] < 0 or c["end"] > total + 1e-3:
            problems.append(f"cue {i} di luar durasi video ({c['start']:.2f}–{c['end']:.2f} / {total:.2f}s)")
        if c["end"] <= c["start"]:
            problems.append(f"cue {i} durasi tidak valid")
        if len(c["lines"]) > cfg.get("max_lines", 2) or any(len(ln) > max_line + 6 for ln in c["lines"]):
            problems.append(f"cue {i} terlalu panjang: {c['text'][:50]}…")
        if i > 1 and c["start"] < cues[i - 2]["end"] - 1e-3:
            problems.append(f"cue {i} tumpang tindih dengan cue sebelumnya")
    return problems


def _ts(sec: float, sep: str = ",") -> str:
    ms = int(round(max(sec, 0) * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[dict]) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out += [str(i), f"{_ts(c['start'])} --> {_ts(c['end'])}", *c["lines"], ""]
    return "\n".join(out)


def _ass_ts(sec: float) -> str:
    cs = int(round(max(sec, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def to_ass(cues: list[dict], cfg: dict, width: int = 1920, height: int = 1080) -> str:
    alpha = format(int(255 * (1 - cfg.get("box_alpha", 0.62))), "02X")
    font = cfg.get("font", "Inter Medium")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{cfg.get('font_size', 38)},&H00F7F2EE,&H000000FF,&H{alpha}0E0805,&H{alpha}0E0805,0,0,0,0,100,100,0,0,3,10,0,2,120,120,{cfg.get('margin_bottom', 58)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 0,{_ass_ts(c['start'])},{_ass_ts(c['end'])},Default,,0,0,0,,{{\\fad(120,120)}}"
             + "\\N".join(c["lines"]) for c in cues]
    return header + "\n".join(lines) + "\n"


def write_subtitles(cues: list[dict], cfg: dict, out_base: Path, width: int = 1920, height: int = 1080
                    ) -> list[Path]:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    srt, ass = out_base.with_suffix(".srt"), out_base.with_suffix(".ass")
    srt.write_text(to_srt(cues), encoding="utf-8")
    ass.write_text(to_ass(cues, cfg, width, height), encoding="utf-8")
    return [srt, ass]


def cue_at(cues: list[dict], t: float, hint: int = 0) -> tuple[dict | None, int]:
    """Cari cue aktif pada waktu t (dengan petunjuk indeks untuk pencarian berurutan cepat)."""
    i = max(0, min(hint, len(cues) - 1)) if cues else 0
    while i > 0 and cues[i]["start"] > t:
        i -= 1
    while i < len(cues) and cues[i]["end"] < t:
        i += 1
    if i < len(cues) and cues[i]["start"] <= t <= cues[i]["end"]:
        return cues[i], i
    return None, i
