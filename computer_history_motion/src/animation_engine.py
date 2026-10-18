"""Primitif motion graphics berbasis Cairo: easing, kamera, tipografi, draw-on, latar, transisi.

Semua koordinat memakai ruang desain 1920×1080. Renderer menskalakan konteks Cairo sesuai
resolusi output, sehingga preview 960×540 dan final 1920×1080 memakai tata letak yang sama.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import cairo

DESIGN_W, DESIGN_H = 1920, 1080


# --------------------------------------------------------------------------- easing

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p


def linear(p): return clamp(p)
def ease_in_out_cubic(p):
    p = clamp(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
def ease_out_cubic(p): return 1 - (1 - clamp(p)) ** 3
def ease_in_cubic(p): return clamp(p) ** 3
def ease_out_expo(p):
    p = clamp(p)
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)
def ease_in_out_sine(p): return -(math.cos(math.pi * clamp(p)) - 1) / 2
def ease_out_back(p, s: float = 1.2):
    p = clamp(p) - 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


EASINGS = {"linear": linear, "in_out_cubic": ease_in_out_cubic, "out_cubic": ease_out_cubic,
           "in_cubic": ease_in_cubic, "out_expo": ease_out_expo, "in_out_sine": ease_in_out_sine,
           "out_back": ease_out_back}


def progress(t: float, start: float, dur: float, ease=ease_out_cubic) -> float:
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return ease((t - start) / dur)


# --------------------------------------------------------------------------- warna

def hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def mix(c1, c2, p):
    return tuple(lerp(a, b, p) for a, b in zip(c1, c2))


@dataclass
class Theme:
    colors: dict
    fonts: dict
    stroke_width: float = 2.4
    glow: float = 0.18
    grid_spacing: int = 80
    particles: int = 70
    safe_bottom: int = 860
    show_chapter_tag: bool = True
    show_progress: bool = True
    accent_name: str = "cyan"

    @classmethod
    def from_config(cls, cfg: dict) -> "Theme":
        data = dict(cfg)
        colors = {k: hex_rgb(v) for k, v in data.pop("colors").items()}
        return cls(colors=colors, **data)

    def c(self, name: str):
        if name == "accent":
            return self.colors[self.accent_name]
        if name.startswith("#"):
            return hex_rgb(name)
        return self.colors.get(name, self.colors["text"])

    @property
    def accent(self):
        return self.colors[self.accent_name]


# --------------------------------------------------------------------------- kamera

@dataclass
class Camera:
    zoom: float = 1.0
    x: float = 0.0
    y: float = 0.0
    rot: float = 0.0

    def apply(self, ctx: cairo.Context, depth: float = 1.0) -> None:
        z = 1 + (self.zoom - 1) * depth
        ctx.translate(DESIGN_W / 2, DESIGN_H / 2)
        if self.rot:
            ctx.rotate(self.rot * depth)
        ctx.scale(z, z)
        ctx.translate(-DESIGN_W / 2 - self.x * depth, -DESIGN_H / 2 - self.y * depth)


def camera_at(spec: dict | None, t: float, dur: float) -> Camera:
    """Gerak kamera scene: push_in (default), pull_out, track, drift, static."""
    spec = spec or {"type": "push_in"}
    kind = spec.get("type", "push_in")
    p = ease_in_out_sine(t / max(dur, 1e-3))
    z0, z1 = spec.get("zoom", {"push_in": [1.0, 1.06], "pull_out": [1.08, 1.0], "track": [1.03, 1.03],
                               "drift": [1.02, 1.04], "static": [1.0, 1.0]}.get(kind, [1.0, 1.06]))
    (x0, y0), (x1, y1) = spec.get("pan", {"track": [[-60, 0], [60, 0]], "drift": [[0, 10], [0, -10]]}
                                 .get(kind, [[0, 0], [0, 0]]))
    cam = Camera(lerp(z0, z1, p), lerp(x0, x1, p), lerp(y0, y1, p))
    for key in spec.get("moves", []):  # dorongan tambahan pada waktu tertentu (sudah di-resolve)
        q = progress(t, key["at"], key.get("dur", 1.2), ease_in_out_cubic)
        cam.zoom *= lerp(1.0, key.get("zoom", 1.0), q)
        cam.x += lerp(0, key.get("x", 0), q)
        cam.y += lerp(0, key.get("y", 0), q)
    return cam


# --------------------------------------------------------------------------- tipografi

_FONT_OPTS = cairo.FontOptions()
_FONT_OPTS.set_antialias(cairo.ANTIALIAS_GRAY)
_FONT_OPTS.set_hint_style(cairo.HINT_STYLE_NONE)
_FONT_OPTS.set_hint_metrics(cairo.HINT_METRICS_OFF)


def set_font(ctx: cairo.Context, family: str, size: float) -> None:
    ctx.select_font_face(family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ctx.set_font_options(_FONT_OPTS)


def text_width(ctx: cairo.Context, text: str, tracking: float = 0.0) -> float:
    if not text:
        return 0.0
    if not tracking:
        return ctx.text_extents(text).x_advance
    size = ctx.get_font_matrix().xx
    return sum(ctx.text_extents(ch).x_advance for ch in text) + tracking * size * (len(text) - 1)


def draw_text(ctx: cairo.Context, text: str, x: float, y: float, family: str, size: float, color,
              alpha: float = 1.0, align: str = "left", tracking: float = 0.0, chars: int | None = None) -> float:
    """Gambar teks pada baseline y. Mengembalikan lebar. `chars` membatasi jumlah karakter (typewriter)."""
    if alpha <= 0.001 or not text:
        return 0.0
    set_font(ctx, family, size)
    w = text_width(ctx, text, tracking)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    shown = text if chars is None else text[:max(0, chars)]
    ctx.set_source_rgba(*color, alpha)
    if not tracking:
        ctx.move_to(x, y)
        ctx.show_text(shown)
    else:
        cx = x
        for ch in shown:
            ctx.move_to(cx, y)
            ctx.show_text(ch)
            cx += ctx.text_extents(ch).x_advance + tracking * size
    return w


def wrap_text(ctx: cairo.Context, text: str, family: str, size: float, max_w: float) -> list[str]:
    set_font(ctx, family, size)
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if cur and text_width(ctx, trial) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines


def fmt_number(value: float, decimals: int = 0) -> str:
    """Format angka Indonesia: 17.468 / 2,5."""
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "#").replace(".", ",").replace("#", ".")


# --------------------------------------------------------------------------- path & draw-on

def path_length(ctx: cairo.Context) -> float:
    total, last, first = 0.0, None, None
    for kind, pts in ctx.copy_path_flat():
        if kind == cairo.PATH_MOVE_TO:
            last = first = pts
        elif kind == cairo.PATH_LINE_TO and last is not None:
            total += math.dist(last, pts)
            last = pts
        elif kind == cairo.PATH_CLOSE_PATH and last is not None and first is not None:
            total += math.dist(last, first)
            last = first
    return total


def stroke_on(ctx: cairo.Context, build, p: float, color, width: float, alpha: float = 1.0,
              glow: float = 0.0) -> None:
    """Bangun path dengan `build(ctx)` lalu stroke sebagian (0..1) sepanjang path."""
    if p <= 0 or alpha <= 0:
        return
    ctx.new_path()
    build(ctx)
    length = path_length(ctx)
    path = ctx.copy_path()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    if p < 1 and length > 0:
        ctx.set_dash([length * p, length + 1], 0)
    if glow > 0:
        ctx.set_source_rgba(*color, alpha * glow)
        ctx.set_line_width(width * 4.5)
        ctx.stroke_preserve()
    ctx.set_source_rgba(*color, alpha)
    ctx.set_line_width(width)
    ctx.stroke()
    ctx.set_dash([])
    ctx.new_path()
    del path


def rounded_rect(ctx: cairo.Context, x, y, w, h, r) -> None:
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


# --------------------------------------------------------------------------- latar (kontinu)

class Background:
    """Gradien, grid perspektif ringan, dan partikel. Digerakkan waktu global → mulus antarscene."""

    def __init__(self, theme: Theme, seed: int = 3):
        self.theme = theme
        rng = random.Random(seed)
        self.particles = [(rng.random() * DESIGN_W, rng.random() * DESIGN_H, rng.uniform(0.6, 2.2),
                           rng.uniform(4, 16), rng.random() * 6.28, rng.uniform(0.15, 0.55))
                          for _ in range(theme.particles)]
        self._cache: dict = {}

    def _static_layer(self, ctx: cairo.Context, accent) -> cairo.ImageSurface:
        """Gradien + cahaya aksen dirender sekali per resolusi/aksen (gradien layar penuh itu mahal)."""
        target = ctx.get_target()
        w, h = target.get_width(), target.get_height()
        key = (w, h, accent)
        if key not in self._cache:
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            c = cairo.Context(surf)
            c.scale(w / DESIGN_W, h / DESIGN_H)
            th = self.theme
            grad = cairo.LinearGradient(0, 0, 0, DESIGN_H)
            grad.add_color_stop_rgb(0, *th.colors["bg_top"])
            grad.add_color_stop_rgb(1, *th.colors["bg_bottom"])
            c.set_source(grad)
            c.paint()
            glow = cairo.RadialGradient(DESIGN_W * 0.32, DESIGN_H * 0.42, 0, DESIGN_W * 0.32, DESIGN_H * 0.42, 900)
            glow.add_color_stop_rgba(0, *accent, 0.07)
            glow.add_color_stop_rgba(1, *accent, 0.0)
            c.set_source(glow)
            c.paint()
            self._cache[key] = surf
        return self._cache[key]

    def draw(self, ctx: cairo.Context, gt: float, cam: Camera, accent) -> None:
        th = self.theme
        layer = self._static_layer(ctx, accent)
        ctx.save()
        ctx.identity_matrix()
        ctx.set_source_surface(layer, 0, 0)
        ctx.paint()
        ctx.restore()

        ctx.save()
        cam.apply(ctx, 0.35)
        sp = th.grid_spacing
        drift = (gt * 6) % sp
        ctx.set_line_width(1.0)
        for i in range(-2, DESIGN_W // sp + 3):
            x = i * sp - drift
            a = 0.16 + 0.10 * math.sin(i * 0.7 + gt * 0.2)
            ctx.set_source_rgba(*th.colors["grid"], a)
            ctx.move_to(x, -100)
            ctx.line_to(x, DESIGN_H + 100)
            ctx.stroke()
        for j in range(-2, DESIGN_H // sp + 3):
            y = j * sp + drift * 0.5
            ctx.set_source_rgba(*th.colors["grid"], 0.16)
            ctx.move_to(-100, y)
            ctx.line_to(DESIGN_W + 100, y)
            ctx.stroke()
        # titik persilangan kecil sebagai tekstur editorial
        ctx.set_source_rgba(*th.colors["dim"], 0.35)
        for i in range(0, DESIGN_W // sp + 2, 3):
            for j in range(0, DESIGN_H // sp + 2, 3):
                ctx.rectangle(i * sp - drift - 1.5, j * sp + drift * 0.5 - 1.5, 3, 3)
        ctx.fill()
        ctx.restore()

        ctx.save()
        cam.apply(ctx, 0.6)
        for (x, y, r, speed, ph, a) in self.particles:
            yy = (y - gt * speed) % (DESIGN_H + 40) - 20
            xx = x + math.sin(gt * 0.3 + ph) * 12
            tw = 0.6 + 0.4 * math.sin(gt * 1.3 + ph * 3)
            ctx.set_source_rgba(*mix(th.colors["muted"], accent, 0.4), a * tw)
            ctx.arc(xx, yy, r, 0, 2 * math.pi)
            ctx.fill()
        ctx.restore()


_VIGNETTE_CACHE: dict = {}


def draw_vignette(ctx: cairo.Context, strength: float = 0.6) -> None:
    target = ctx.get_target()
    w, h = target.get_width(), target.get_height()
    key = (w, h, strength)
    if key not in _VIGNETTE_CACHE:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        c = cairo.Context(surf)
        c.scale(w / DESIGN_W, h / DESIGN_H)
        g = cairo.RadialGradient(DESIGN_W / 2, DESIGN_H / 2, DESIGN_H * 0.35, DESIGN_W / 2, DESIGN_H / 2,
                                 DESIGN_W * 0.62)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, strength)
        c.set_source(g)
        c.paint()
        _VIGNETTE_CACHE[key] = surf
    ctx.save()
    ctx.identity_matrix()
    ctx.set_source_surface(_VIGNETTE_CACHE[key], 0, 0)
    ctx.paint()
    ctx.restore()


# --------------------------------------------------------------------------- transisi

TRANSITIONS = ("fade", "iris", "line_wipe", "bars", "zoom", "slide", "fade_black", "cut")


@dataclass
class TransitionState:
    kind: str
    phase: str      # "in" | "out"
    p: float        # 0..1 kemajuan transisi (1 = selesai)


def transition_state(t: float, dur: float, tin: dict, tout: dict) -> TransitionState | None:
    din, dout = tin.get("dur", 0.7), tout.get("dur", 0.7)
    if tin.get("type", "fade") != "cut" and t < din:
        return TransitionState(tin.get("type", "fade"), "in", ease_in_out_cubic(t / din))
    if tout.get("type", "fade") != "cut" and t > dur - dout:
        return TransitionState(tout.get("type", "fade"), "out", ease_in_out_cubic((t - (dur - dout)) / dout))
    return None


def transition_camera(ts: TransitionState | None, cam: Camera) -> Camera:
    if ts and ts.kind == "zoom":
        if ts.phase == "out":
            cam.zoom *= lerp(1.0, 1.35, ts.p)
        else:
            cam.zoom *= lerp(0.9, 1.0, ts.p)
    if ts and ts.kind == "slide":
        cam.x += lerp(0, 220, ts.p) if ts.phase == "out" else lerp(-220, 0, ts.p)
    return cam


def content_alpha(ts: TransitionState | None) -> float:
    if not ts:
        return 1.0
    if ts.kind in ("fade", "zoom", "slide", "fade_black"):
        return ts.p if ts.phase == "in" else 1 - ts.p
    return 1.0


def clip_for_transition(ctx: cairo.Context, ts: TransitionState | None) -> None:
    if not ts:
        return
    if ts.kind == "iris":
        r = math.hypot(DESIGN_W, DESIGN_H) / 2 * (ts.p if ts.phase == "in" else 1 - ts.p)
        ctx.new_path()
        ctx.arc(DESIGN_W / 2, DESIGN_H / 2, max(r, 0.01), 0, 2 * math.pi)
        ctx.clip()
    elif ts.kind == "line_wipe":
        x = DESIGN_W * ts.p
        ctx.new_path()
        if ts.phase == "in":
            ctx.rectangle(0, 0, x, DESIGN_H)
        else:
            ctx.rectangle(x, 0, DESIGN_W - x, DESIGN_H)
        ctx.clip()


def draw_transition_overlay(ctx: cairo.Context, ts: TransitionState | None, theme: Theme, accent) -> None:
    if not ts:
        return
    if ts.kind == "line_wipe":
        x = DESIGN_W * ts.p
        a = math.sin(math.pi * ts.p)
        ctx.set_source_rgba(*accent, 0.9 * a)
        ctx.rectangle(x - 1.5, 0, 3, DESIGN_H)
        ctx.fill()
        g = cairo.LinearGradient(x - 120, 0, x, 0)
        g.add_color_stop_rgba(0, *accent, 0)
        g.add_color_stop_rgba(1, *accent, 0.12 * a)
        ctx.set_source(g)
        ctx.rectangle(x - 120, 0, 120, DESIGN_H)
        ctx.fill()
    elif ts.kind == "iris":
        r = math.hypot(DESIGN_W, DESIGN_H) / 2 * (ts.p if ts.phase == "in" else 1 - ts.p)
        if 1 < r < 1200:
            ctx.set_source_rgba(*accent, 0.7 * math.sin(math.pi * ts.p))
            ctx.set_line_width(2.5)
            ctx.new_path()
            ctx.arc(DESIGN_W / 2, DESIGN_H / 2, r, 0, 2 * math.pi)
            ctx.stroke()
    elif ts.kind == "bars":
        n = 6
        bw = DESIGN_W / n
        for i in range(n):
            stagger = i * 0.06
            q = clamp((ts.p - stagger) / (1 - stagger * (n - 1) / n - 0.0001))
            q = ease_in_out_cubic(q)
            if ts.phase == "out":
                h = DESIGN_H * q
                y = 0
            else:
                h = DESIGN_H * (1 - q)
                y = DESIGN_H - h
            if h <= 0:
                continue
            ctx.set_source_rgb(*theme.colors["panel"])
            ctx.rectangle(i * bw - 0.5, y, bw + 1, h)
            ctx.fill()
            edge_y = y + h if ts.phase == "out" else y
            ctx.set_source_rgba(*accent, 0.85)
            ctx.rectangle(i * bw, edge_y - 1.5, bw, 3)
            ctx.fill()
    elif ts.kind == "fade_black" and ts.phase == "out":
        ctx.set_source_rgba(0, 0, 0, ts.p)
        ctx.paint()


# --------------------------------------------------------------------------- subtitle

def draw_subtitle(ctx: cairo.Context, cue: dict | None, gt: float, cfg: dict, theme: Theme) -> None:
    if not cue:
        return
    fade = 0.12
    a = clamp(min((gt - cue["start"]) / fade, (cue["end"] - gt) / fade))
    if a <= 0:
        return
    family, size = cfg.get("font", "Inter Medium"), cfg.get("font_size", 38)
    lines = cue["lines"]
    set_font(ctx, family, size)
    line_h = size * 1.32
    widths = [text_width(ctx, ln) for ln in lines]
    pad_x, pad_y = 22, 12
    box_w = max(widths) + pad_x * 2
    box_h = line_h * len(lines) + pad_y * 2 - (line_h - size) * 0.6
    y_bottom = DESIGN_H - cfg.get("margin_bottom", 58)
    x = DESIGN_W / 2 - box_w / 2
    y = y_bottom - box_h
    ctx.set_source_rgba(*theme.colors["subtitle_box"], cfg.get("box_alpha", 0.62) * a)
    rounded_rect(ctx, x, y, box_w, box_h, 10)
    ctx.fill()
    for i, ln in enumerate(lines):
        base = y + pad_y + size * 0.92 + i * line_h
        draw_text(ctx, ln, DESIGN_W / 2, base, family, size, theme.colors["text"], a, align="center")
