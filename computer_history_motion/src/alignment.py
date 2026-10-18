"""Penyelarasan timing kata Edge-TTS (WordBoundary) dengan token teks asli.

Edge-TTS mengirim batas kata tanpa tanda baca, dan teks yang dikirim bisa berbeda dari teks
tampilan karena leksikon pengucapan ("4004" → "empat nol nol empat"). Penyelarasan dilakukan
di tingkat karakter ternormalisasi dengan difflib, lalu dipetakan balik ke token tampilan.
Token yang tidak bisa dicocokkan diberi timing interpolasi dan ditandai `approx=True`.
"""
from __future__ import annotations

import difflib
import re

_NORM_RE = re.compile(r"[\W_]+", re.UNICODE)
_EDGE_PUNCT = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.UNICODE)


def norm(text: str) -> str:
    return _NORM_RE.sub("", text.lower())


def _tts_form(token: str, lexicon: dict) -> str:
    core = _EDGE_PUNCT.match(token).group(2)
    return lexicon.get(core, core) if lexicon else core


def align_tokens(text: str, words: list[dict], lexicon: dict | None, duration: float) -> list[dict]:
    """Kembalikan [{text, start, end, approx}] untuk setiap token (dipisah spasi) di `text`."""
    tokens = text.split()
    if not tokens:
        return []
    lexicon = lexicon or {}

    # karakter tampilan → indeks token
    d_chars, d_owner = [], []
    for ti, tok in enumerate(tokens):
        for ch in norm(_tts_form(tok, lexicon)):
            d_chars.append(ch)
            d_owner.append(ti)

    # karakter boundary → (waktu mulai, waktu akhir) per karakter
    b_chars, b_times = [], []
    for w in words:
        wn = norm(w["text"])
        if not wn:
            continue
        span = max(w["end"] - w["start"], 1e-3)
        for k, ch in enumerate(wn):
            b_chars.append(ch)
            b_times.append((w["start"] + span * k / len(wn), w["start"] + span * (k + 1) / len(wn)))

    starts: list[float | None] = [None] * len(tokens)
    ends: list[float | None] = [None] * len(tokens)
    if d_chars and b_chars:
        sm = difflib.SequenceMatcher(None, "".join(d_chars), "".join(b_chars), autojunk=False)
        for block in sm.get_matching_blocks():
            for k in range(block.size):
                ti = d_owner[block.a + k]
                t0, t1 = b_times[block.b + k]
                starts[ti] = t0 if starts[ti] is None else min(starts[ti], t0)
                ends[ti] = t1 if ends[ti] is None else max(ends[ti], t1)

    approx = [s is None for s in starts]
    if all(approx):
        # Tanpa data kata: bagi proporsional panjang karakter (batasan terdokumentasi).
        lengths = [max(len(norm(t)), 1) for t in tokens]
        total = sum(lengths)
        lead = words[0]["start"] if words else 0.05
        speech = max((words[-1]["end"] if words else duration) - lead, 0.1)
        pos = lead
        out = []
        for tok, n in zip(tokens, lengths):
            dur = speech * n / total
            out.append({"text": tok, "start": pos, "end": pos + dur, "approx": True})
            pos += dur
        return out

    # Interpolasi token yang tidak tercocokkan di antara tetangga yang tercocokkan.
    known = [i for i, a in enumerate(approx) if not a]
    for i, a in enumerate(approx):
        if not a:
            continue
        prev_i = max((k for k in known if k < i), default=None)
        next_i = min((k for k in known if k > i), default=None)
        lo = ends[prev_i] if prev_i is not None else (words[0]["start"] if words else 0.0)
        hi = starts[next_i] if next_i is not None else max(lo + 0.3, words[-1]["end"] if words else duration)
        first = (prev_i + 1) if prev_i is not None else 0
        last = (next_i - 1) if next_i is not None else len(tokens) - 1
        n = last - first + 1
        step = max(hi - lo, 0.05) / n
        starts[i] = lo + step * (i - first)
        ends[i] = starts[i] + step

    # Pastikan monoton
    out, cursor = [], 0.0
    for tok, s, e, a in zip(tokens, starts, ends, approx):
        s = max(s, cursor)
        e = max(e, s + 0.05)
        out.append({"text": tok, "start": s, "end": e, "approx": a})
        cursor = s
    return out
