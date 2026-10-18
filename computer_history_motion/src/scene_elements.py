"""Elemen scene yang dapat dikonfigurasi dari JSON.

Setiap elemen menerima spesifikasi yang sudah di-resolve oleh timeline:
  t_in  : detik (lokal scene) saat elemen mulai masuk
  t_out : detik saat elemen mulai keluar (None = bertahan sampai transisi keluar scene)
Selebihnya parameter visual (pos, size, warna, teks) berasal dari naskah.
"""
from __future__ import annotations

import math
import random

import cairo

from .animation_engine import (DESIGN_W, clamp, draw_text, ease_in_out_cubic, ease_out_cubic, ease_out_expo,
                               fmt_number, lerp, progress, rounded_rect, set_font, stroke_on, text_width,
                               wrap_text)
from .illustrations import draw_icon


class RenderCtx:
    def __init__(self, theme, scene: dict, total_scenes: int):
        self.theme = theme
        self.scene = scene
        self.total = total_scenes

    @property
    def accent(self):
        return self.theme.accent

    def font(self, key: str) -> str:
        return self.theme.fonts.get(key, key)


class Element:
    defaults: dict = {}

    def __init__(self, spec: dict):
        self.s = {**self.defaults, **spec}
        self.t_in = float(spec.get("t_in", 0.0))
        self.t_out = spec.get("t_out")
        self.in_dur = float(self.s.get("in_dur", 0.8))
        self.out_dur = float(self.s.get("out_dur", 0.5))
        self.depth = float(self.s.get("depth", 1.0))

    def p_in(self, t, ease=ease_out_cubic):
        return progress(t, self.t_in, self.in_dur, ease)

    def p_out(self, t, ease=ease_in_out_cubic):
        if self.t_out is None:
            return 0.0
        return progress(t, self.t_out, self.out_dur, ease)

    def pos_at(self, t) -> tuple[float, float]:
        """Posisi dasar, digeser oleh keyframe `path` [{t_in, pos, dur}] dengan easing."""
        x, y = self.s["pos"]
        for key in self.s.get("path", []):
            q = progress(t, key["t_in"], key.get("dur", 1.0), ease_in_out_cubic)
            x, y = lerp(x, key["pos"][0], q), lerp(y, key["pos"][1], q)
        return x, y

    def visible(self, t) -> bool:
        if t < self.t_in:
            return False
        return self.t_out is None or t < self.t_out + self.out_dur

    def color(self, rc: RenderCtx, key="color", default="text"):
        return rc.theme.c(self.s.get(key, default))

    def draw(self, ctx: cairo.Context, t: float, rc: RenderCtx) -> None:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------- tipografi

class Headline(Element):
    defaults = {"size": 66, "font": "display", "align": "left", "line_height": 1.12, "color": "text",
                "max_width": 760, "in_dur": 0.9, "stagger": 0.09}

    def draw(self, ctx, t, rc):
        s = self.s
        size = s["size"]
        family = rc.font(s["font"])
        lines = wrap_text(ctx, s["text"], family, size, s["max_width"])
        x, y = self.pos_at(t)
        lh = size * s["line_height"]
        po = self.p_out(t)
        for i, ln in enumerate(lines):
            q = progress(t, self.t_in + i * s["stagger"], self.in_dur, ease_out_expo)
            if q <= 0:
                continue
            base = y + i * lh
            ctx.save()
            ctx.rectangle(x - 2000, base - size * 1.05, 4000, size * 1.38)
            ctx.clip()
            dy = (1 - q) * size * 1.1 - po * size * 0.35
            draw_text(ctx, ln, x, base + dy, family, size, self.color(rc), (1 - po) * clamp(q * 1.4),
                      align=s["align"], tracking=s.get("tracking", 0.0))
            ctx.restore()


class Text(Headline):
    defaults = {"size": 30, "font": "light", "align": "left", "line_height": 1.4, "color": "muted",
                "max_width": 700, "in_dur": 0.8, "stagger": 0.07}


class Kicker(Element):
    defaults = {"size": 20, "font": "mono", "color": "accent", "tracking": 0.16, "align": "left"}

    def draw(self, ctx, t, rc):
        s = self.s
        x, y = self.pos_at(t)
        q, po = self.p_in(t), self.p_out(t)
        a = 1 - po
        line_w = 46
        if s["align"] == "left":
            stroke_on(ctx, lambda c: (c.move_to(x, y - 7), c.line_to(x + line_w, y - 7)), q, rc.accent, 2, a)
            tx = x + line_w + 16
        else:
            tx = x
        k = progress(t, self.t_in + 0.2, 0.6, ease_out_cubic)
        draw_text(ctx, s["text"].upper(), tx + (1 - k) * 20, y, rc.font(s["font"]), s["size"], self.color(rc),
                  a * k, align=s["align"], tracking=s["tracking"])


class Title(Element):
    """Judul besar dengan tracking yang merapat dan garis aksen."""
    defaults = {"size": 104, "sub_size": 32, "in_dur": 1.6}

    def draw(self, ctx, t, rc):
        s = self.s
        x, y = self.pos_at(t)
        q = self.p_in(t, ease_out_expo)
        a = clamp(q * 1.3) * (1 - self.p_out(t))
        tracking = lerp(0.55, 0.14, q)
        draw_text(ctx, s["text"], x, y, rc.font("display"), s["size"], rc.theme.c("text"), a, "center", tracking)
        lw = 520 * progress(t, self.t_in + 0.35, 1.0, ease_in_out_cubic)
        if lw > 0:
            ctx.set_source_rgba(*rc.accent, a)
            ctx.rectangle(x - lw / 2, y + 30, lw, 2.5)
            ctx.fill()
        if s.get("sub"):
            k = progress(t, self.t_in + 0.7, 1.0)
            draw_text(ctx, s["sub"], x, y + 84 - (1 - k) * 10, rc.font("light"), s["sub_size"],
                      rc.theme.c("muted"), k * (1 - self.p_out(t)), "center", 0.02)


# --------------------------------------------------------------------------- angka

class Counter(Element):
    defaults = {"size": 120, "font": "display_light", "format": "int", "dur": 1.6, "align": "left",
                "label_size": 20, "color": "text", "in_dur": 0.5}

    def value_text(self, t):
        s = self.s
        q = progress(t, self.t_in, s["dur"], ease_out_expo)
        v = lerp(s.get("from", 0), s["to"], q)
        if s["format"] == "year":
            txt = str(int(round(v)))
        else:
            txt = fmt_number(v, s.get("decimals", 0))
        return f"{s.get('prefix', '')}{txt}{s.get('suffix', '')}"

    def draw(self, ctx, t, rc):
        s = self.s
        x, y = self.pos_at(t)
        a = self.p_in(t) * (1 - self.p_out(t))
        rise = (1 - self.p_in(t)) * 24
        draw_text(ctx, self.value_text(t), x, y + rise, rc.font(s["font"]), s["size"], self.color(rc), a,
                  s["align"], s.get("tracking", 0.0))
        if s.get("label"):
            k = progress(t, self.t_in + 0.4, 0.7)
            draw_text(ctx, s["label"].upper(), x, y + s["label_size"] * 2.1, rc.font("mono"), s["label_size"],
                      rc.accent, a * k, s["align"], 0.14)


class NumberField(Element):
    """Medan digit berkedip: 'miliaran perhitungan' atau tabel angka era Babbage."""
    defaults = {"size": [1100, 560], "cell": 46, "font_size": 18, "density": 0.55, "color": "dim",
                "highlight_every": 0, "in_dur": 1.2, "out_dur": 0.8}

    def draw(self, ctx, t, rc):
        s = self.s
        cx, cy = self.pos_at(t)
        w, h = s["size"]
        a = self.p_in(t) * (1 - self.p_out(t))
        if a <= 0:
            return
        cell = s["cell"]
        cols, rows = int(w // cell), int(h // (cell * 0.75))
        family = rc.font("mono")
        set_font(ctx, family, s["font_size"])
        speed = s.get("speed", 12)
        frame = int(t * speed)
        base = rc.theme.c(s["color"])
        for i in range(cols):
            for j in range(rows):
                rng = random.Random(i * 7919 + j * 104729 + (frame if s.get("flicker", True) else 0))
                if rng.random() > s["density"]:
                    continue
                x = cx - w / 2 + i * cell
                y = cy - h / 2 + j * cell * 0.75
                d = math.hypot((x - cx) / w, (y - cy) / h)
                fall = clamp(1.2 - d * 2.0)
                hi = s["highlight_every"] and rng.random() < 1 / s["highlight_every"]
                col = rc.accent if hi else base
                txt = "".join(str(rng.randint(0, 9)) for _ in range(s.get("digits", 1)))
                ctx.set_source_rgba(*col, a * fall * (0.9 if hi else 0.6))
                ctx.move_to(x, y)
                ctx.show_text(txt)


# --------------------------------------------------------------------------- ilustrasi

class Icon(Element):
    defaults = {"size": 380, "color": "text", "in_dur": 1.6, "out_dur": 0.7}

    def draw(self, ctx, t, rc):
        s = self.s
        p = progress(t, self.t_in, self.in_dur, ease_in_out_cubic)
        if self.t_out is not None:
            p *= 1 - progress(t, self.t_out, self.out_dur, ease_in_out_cubic)
        x, y = self.pos_at(t)
        float_y = math.sin((t - self.t_in) * 0.8) * s.get("float", 4)
        draw_icon(ctx, s["icon"], x, y + float_y, s["size"], p, t - self.t_in, rc.theme, self.color(rc),
                  rc.accent, s.get("alpha", 1.0))
        if s.get("label"):
            k = progress(t, self.t_in + 0.6, 0.7) * (1 - self.p_out(t))
            draw_text(ctx, s["label"].upper(), x, y + s["size"] * 0.62, rc.font("mono"), 18, rc.theme.c("muted"),
                      k, "center", 0.16)


class Morph(Element):
    """Rangkaian ikon yang saling berganti di posisi yang sama (draw-off lalu draw-on)."""
    defaults = {"size": 360, "color": "text"}

    def draw(self, ctx, t, rc):
        s = self.s
        items = s["items"]
        x, y = self.pos_at(t)
        end_all = self.t_out
        for i, it in enumerate(items):
            start = it["t_in"]
            nxt = items[i + 1]["t_in"] if i + 1 < len(items) else (end_all if end_all is not None else 1e9)
            span = max(nxt - start, 0.3)
            if t < start or t > nxt + 0.05:
                continue
            draw_d = min(1.1, span * 0.55)
            out_d = min(0.4, span * 0.3)
            p = progress(t, start, draw_d, ease_in_out_cubic)
            p *= 1 - progress(t, nxt - out_d, out_d, ease_in_out_cubic)
            draw_icon(ctx, it["icon"], x, y, s["size"], p, t - start, rc.theme, self.color(rc), rc.accent)
            if it.get("label"):
                k = clamp(p * 1.5)
                draw_text(ctx, it["label"].upper(), x, y + s["size"] * 0.66, rc.font("mono"), 20,
                          rc.theme.c("muted"), k, "center", 0.18)


class Strip(Element):
    """Deret ikon kecil berjajar di atas garis (rangkuman evolusi)."""
    defaults = {"y": 470, "x0": 220, "x1": 1700, "size": 120}

    def draw(self, ctx, t, rc):
        s = self.s
        po = self.p_out(t)
        lp = progress(t, self.t_in, 1.4, ease_in_out_cubic)
        y = s["y"]
        stroke_on(ctx, lambda c: (c.move_to(s["x0"], y + s["size"] * 0.75), c.line_to(s["x1"], y + s["size"] * 0.75)),
                  lp, rc.theme.c("dim"), 2, 1 - po)
        n = len(s["items"])
        for i, it in enumerate(s["items"]):
            x = lerp(s["x0"] + 60, s["x1"] - 60, i / max(n - 1, 1))
            p = progress(t, it["t_in"], 0.9, ease_in_out_cubic)
            draw_icon(ctx, it["icon"], x, y, s["size"], p, t - it["t_in"], rc.theme, rc.theme.c("text"), rc.accent,
                      1 - po)
            if it.get("label"):
                draw_text(ctx, it["label"].upper(), x, y + s["size"] * 0.75 + 34, rc.font("mono"), 15,
                          rc.theme.c("muted"), clamp(p * 1.4) * (1 - po), "center", 0.12)
            ctx.set_source_rgba(*rc.accent, clamp(p * 2) * (1 - po))
            ctx.arc(x, y + s["size"] * 0.75, 4, 0, 2 * math.pi)
            ctx.fill()


class IconGrid(Element):
    defaults = {"rows": 3, "cols": 7, "size": 70, "gap": 110, "stagger": 0.05, "icon": "person"}

    def draw(self, ctx, t, rc):
        s = self.s
        cx, cy = self.pos_at(t)
        po = self.p_out(t)
        rng = random.Random(3)
        order = list(range(s["rows"] * s["cols"]))
        rng.shuffle(order)
        for k, idx in enumerate(order):
            r, c = divmod(idx, s["cols"])
            x = cx + (c - (s["cols"] - 1) / 2) * s["gap"]
            y = cy + (r - (s["rows"] - 1) / 2) * s["gap"]
            p = progress(t, self.t_in + k * s["stagger"], 0.8, ease_in_out_cubic)
            col = rc.accent if idx % 5 == 0 else rc.theme.c("muted")
            draw_icon(ctx, s["icon"], x, y, s["size"], p, t, rc.theme, col, rc.accent, 1 - po, glow=0.0)


# --------------------------------------------------------------------------- struktur informasi

class Timeline(Element):
    """Sumbu waktu horizontal dengan penanda tahun; fokus bergeser dari focus_from ke focus_to."""
    defaults = {"y": 760, "x0": 160, "x1": 1760, "in_dur": 1.4}

    def year_x(self, year):
        s = self.s
        y0, y1 = s["years"]
        return lerp(s["x0"], s["x1"], (year - y0) / (y1 - y0))

    def draw(self, ctx, t, rc):
        s = self.s
        y = s["y"]
        a = 1 - self.p_out(t)
        lp = progress(t, self.t_in, self.in_dur, ease_in_out_cubic)
        stroke_on(ctx, lambda c: (c.move_to(s["x0"], y), c.line_to(s["x1"], y)), lp, rc.theme.c("dim"), 2, a)
        for i, m in enumerate(s.get("marks", [])):
            x = self.year_x(m["year"])
            k = progress(t, self.t_in + 0.3 + i * 0.12, 0.6)
            ctx.set_source_rgba(*rc.theme.c("muted"), a * k)
            ctx.rectangle(x - 1, y - 10, 2, 20)
            ctx.fill()
            draw_text(ctx, str(m["year"]), x, y + 40, rc.font("mono"), 17, rc.theme.c("muted"), a * k, "center")
            if m.get("label"):
                draw_text(ctx, m["label"], x, y - 26, rc.font("body"), 19, rc.theme.c("text"), a * k * 0.9, "center")
        if "focus_to" in s:
            fq = progress(t, s.get("t_focus", self.t_in + 0.6), 1.6, ease_in_out_cubic)
            fy = lerp(s.get("focus_from", s["focus_to"]), s["focus_to"], fq)
            fx = self.year_x(fy)
            ctx.set_source_rgba(*rc.accent, a * lp)
            ctx.arc(fx, y, 7, 0, 2 * math.pi)
            ctx.fill()
            ctx.set_source_rgba(*rc.accent, a * lp * 0.25)
            ctx.arc(fx, y, 16 + 3 * math.sin(t * 3), 0, 2 * math.pi)
            ctx.fill()


class Chips(Element):
    defaults = {"cols": 2, "gap": [380, 70], "size": 24, "stagger": 0.18, "font": "body"}

    def draw(self, ctx, t, rc):
        s = self.s
        x0, y0 = self.pos_at(t)
        po = self.p_out(t)
        family = rc.font(s["font"])
        for i, item in enumerate(s["items"]):
            r, c = divmod(i, s["cols"])
            x = x0 + c * s["gap"][0]
            y = y0 + r * s["gap"][1]
            k = progress(t, self.t_in + i * s["stagger"], 0.7, ease_out_expo)
            if k <= 0:
                continue
            set_font(ctx, family, s["size"])
            w = text_width(ctx, item) + 40
            a = clamp(k * 1.4) * (1 - po)
            ctx.set_source_rgba(*rc.theme.colors["panel"], 0.85 * a)
            rounded_rect(ctx, x, y - s["size"] - 10, w * k, s["size"] + 26, (s["size"] + 26) / 2)
            ctx.fill_preserve()
            ctx.set_source_rgba(*rc.accent, 0.55 * a)
            ctx.set_line_width(1.5)
            ctx.stroke()
            draw_text(ctx, item, x + 20, y + 1, family, s["size"], rc.theme.c("text"), a * clamp((k - 0.4) / 0.6))


class Card(Element):
    defaults = {"size": [620, 260], "title_size": 26, "body_size": 26}

    def draw(self, ctx, t, rc):
        s = self.s
        x, y = self.pos_at(t)
        w, h = s["size"]
        po = self.p_out(t)
        a = 1 - po
        bp = progress(t, self.t_in, 1.0, ease_in_out_cubic)
        ctx.set_source_rgba(*rc.theme.colors["panel"], 0.75 * bp * a)
        rounded_rect(ctx, x, y, w, h, 14)
        ctx.fill()
        stroke_on(ctx, lambda c: rounded_rect(c, x, y, w, h, 14), bp, rc.accent, 1.6, a * 0.8)
        k = progress(t, self.t_in + 0.4, 0.8)
        if s.get("title"):
            draw_text(ctx, s["title"].upper(), x + 30, y + 46, rc.font("mono"), 18, rc.accent, a * k, tracking=0.14)
        lines = wrap_text(ctx, s.get("body", ""), rc.font("light"), s["body_size"], w - 60)
        for i, ln in enumerate(lines):
            kk = progress(t, self.t_in + 0.55 + i * 0.08, 0.7)
            draw_text(ctx, ln, x + 30, y + 92 + i * s["body_size"] * 1.4 + (1 - kk) * 8, rc.font("light"),
                      s["body_size"], rc.theme.c("text"), a * kk)


class Diagram(Element):
    """Kotak berlabel dihubungkan panah (mill/store, program+data, contoh→model)."""
    defaults = {"node_size": [250, 96]}

    def draw(self, ctx, t, rc):
        s = self.s
        a = 1 - self.p_out(t)
        nodes = s["nodes"]
        for i, n in enumerate(nodes):
            x, y = n["pos"]
            w, h = n.get("size", s["node_size"])
            bp = progress(t, self.t_in + i * 0.35, 0.9, ease_in_out_cubic)
            ctx.set_source_rgba(*rc.theme.colors["panel"], 0.8 * bp * a)
            rounded_rect(ctx, x - w / 2, y - h / 2, w, h, 12)
            ctx.fill()
            col = rc.accent if n.get("accent", True) else rc.theme.c("muted")
            stroke_on(ctx, lambda c, x=x, y=y, w=w, h=h: rounded_rect(c, x - w / 2, y - h / 2, w, h, 12), bp, col,
                      1.8, a)
            k = progress(t, self.t_in + i * 0.35 + 0.3, 0.6)
            draw_text(ctx, n["label"], x, y + (2 if not n.get("sub") else -6), rc.font("heading"), 28,
                      rc.theme.c("text"), a * k, "center")
            if n.get("sub"):
                draw_text(ctx, n["sub"].upper(), x, y + 26, rc.font("mono"), 15, rc.theme.c("muted"), a * k,
                          "center", 0.12)
        for j, (i0, i1) in enumerate(s.get("edges", [])):
            (x0, y0), (x1, y1) = nodes[i0]["pos"], nodes[i1]["pos"]
            w0 = nodes[i0].get("size", s["node_size"])[0] / 2 + 14
            w1 = nodes[i1].get("size", s["node_size"])[0] / 2 + 14
            ang = math.atan2(y1 - y0, x1 - x0)
            horizontal = abs(math.cos(ang)) > 0.5
            h0 = nodes[i0].get("size", s["node_size"])[1] / 2 + 14
            h1 = nodes[i1].get("size", s["node_size"])[1] / 2 + 14
            sx = x0 + (w0 if horizontal else 0) * math.copysign(1, math.cos(ang))
            sy = y0 + (0 if horizontal else h0 * math.copysign(1, math.sin(ang)))
            ex = x1 - (w1 if horizontal else 0) * math.copysign(1, math.cos(ang))
            ey = y1 - (0 if horizontal else h1 * math.copysign(1, math.sin(ang)))
            ep = progress(t, self.t_in + 0.5 + j * 0.35, 0.7, ease_in_out_cubic)
            stroke_on(ctx, lambda c, sx=sx, sy=sy, ex=ex, ey=ey: (c.move_to(sx, sy), c.line_to(ex, ey)), ep,
                      rc.theme.c("muted"), 2, a)
            if ep >= 0.98:
                ctx.set_source_rgba(*rc.theme.c("muted"), a)
                ctx.move_to(ex, ey)
                ctx.line_to(ex - 12 * math.cos(ang - 0.45), ey - 12 * math.sin(ang - 0.45))
                ctx.line_to(ex - 12 * math.cos(ang + 0.45), ey - 12 * math.sin(ang + 0.45))
                ctx.close_path()
                ctx.fill()
            if ep >= 1:
                q = ((t - self.t_in) * 0.7 + j * 0.3) % 1
                ctx.set_source_rgba(*rc.accent, a * 0.9)
                ctx.arc(lerp(sx, ex, q), lerp(sy, ey, q), 3.5, 0, 2 * math.pi)
                ctx.fill()


class Network(Element):
    """Graf node yang tumbuh: jaringan komputer/internet."""
    defaults = {"size": [900, 520], "nodes": 34, "grow": 3.0}

    def draw(self, ctx, t, rc):
        s = self.s
        cx, cy = self.pos_at(t)
        w, h = s["size"]
        a = 1 - self.p_out(t)
        rng = random.Random(s.get("seed", 2))
        pts = [(cx + rng.uniform(-w / 2, w / 2), cy + rng.uniform(-h / 2, h / 2)) for _ in range(s["nodes"])]
        order = sorted(range(len(pts)), key=lambda i: math.dist(pts[i], (cx, cy)))
        g = clamp((t - self.t_in) / s["grow"])
        shown = max(1, int(len(pts) * ease_out_cubic(g)))
        active = set(order[:shown])
        edges = []
        for i in active:
            near = sorted((j for j in active if j != i), key=lambda j: math.dist(pts[i], pts[j]))[:2]
            edges += [(i, j) for j in near if i < j]
        for (i, j) in edges:
            ctx.set_source_rgba(*rc.theme.c("muted"), 0.45 * a)
            ctx.set_line_width(1.3)
            ctx.move_to(*pts[i])
            ctx.line_to(*pts[j])
            ctx.stroke()
            q = ((t - self.t_in) * 0.5 + (i * 0.13 + j * 0.07)) % 1
            ctx.set_source_rgba(*rc.accent, 0.85 * a)
            ctx.arc(lerp(pts[i][0], pts[j][0], q), lerp(pts[i][1], pts[j][1], q), 2.6, 0, 2 * math.pi)
            ctx.fill()
        for i in active:
            r = 5 if i % 4 else 8
            ctx.set_source_rgba(*rc.accent, a)
            ctx.arc(*pts[i], r, 0, 2 * math.pi)
            ctx.fill()


class MooreChart(Element):
    """Grafik jumlah transistor (skala logaritmik) — data dari spesifikasi naskah."""
    defaults = {"size": [760, 420], "years": [1965, 2025], "log_range": [3, 11]}

    def draw(self, ctx, t, rc):
        s = self.s
        x0, y0 = self.pos_at(t)
        w, h = s["size"]
        a = 1 - self.p_out(t)
        ap = progress(t, self.t_in, 1.0, ease_in_out_cubic)
        dim = rc.theme.c("dim")
        stroke_on(ctx, lambda c: (c.move_to(x0, y0), c.line_to(x0, y0 + h), c.line_to(x0 + w, y0 + h)), ap, dim, 2, a)
        lo, hi = s["log_range"]
        for e in range(lo, hi + 1, 2):
            yy = y0 + h - (e - lo) / (hi - lo) * h
            draw_text(ctx, f"10^{e}", x0 - 14, yy + 6, rc.font("mono"), 15, rc.theme.c("muted"), a * ap, "right")
            ctx.set_source_rgba(*dim, 0.35 * a * ap)
            ctx.rectangle(x0, yy, w, 1)
            ctx.fill()
        ya, yb = s["years"]

        def xy(year, count):
            return (x0 + (year - ya) / (yb - ya) * w, y0 + h - (math.log10(count) - lo) / (hi - lo) * h)
        pts = [xy(p["year"], p["count"]) for p in s["points"]]
        lp = progress(t, self.t_in + 0.6, 2.2, ease_in_out_cubic)

        def build(c):
            c.move_to(*pts[0])
            for pt in pts[1:]:
                c.line_to(*pt)
        stroke_on(ctx, build, lp, rc.accent, 2.6, a, rc.theme.glow)
        for i, (p, (px, py)) in enumerate(zip(s["points"], pts)):
            k = progress(t, self.t_in + 0.6 + 2.2 * i / max(len(pts) - 1, 1), 0.4)
            ctx.set_source_rgba(*rc.accent, a * k)
            ctx.arc(px, py, 5, 0, 2 * math.pi)
            ctx.fill()
            draw_text(ctx, p["label"], px + 10, py - 12, rc.font("body"), 16, rc.theme.c("text"), a * k * 0.9)
        draw_text(ctx, s.get("caption", "").upper(), x0, y0 + h + 44, rc.font("mono"), 15, rc.theme.c("muted"),
                  a * ap, tracking=0.12)


class Line(Element):
    def draw(self, ctx, t, rc):
        (x0, y0), (x1, y1) = self.s["from"], self.s["to"]
        stroke_on(ctx, lambda c: (c.move_to(x0, y0), c.line_to(x1, y1)), self.p_in(t, ease_in_out_cubic),
                  rc.accent, self.s.get("width", 2), 1 - self.p_out(t))


ELEMENT_TYPES = {
    "headline": Headline, "text": Text, "kicker": Kicker, "title": Title, "counter": Counter,
    "number_field": NumberField, "icon": Icon, "morph": Morph, "strip": Strip, "icon_grid": IconGrid,
    "timeline": Timeline, "chips": Chips, "card": Card, "diagram": Diagram, "network": Network,
    "moore_chart": MooreChart, "line": Line,
}


def build_element(spec: dict) -> Element:
    kind = spec.get("type")
    if kind not in ELEMENT_TYPES:
        raise KeyError(f"Tipe elemen '{kind}' tidak dikenal. Pilihan: {', '.join(sorted(ELEMENT_TYPES))}")
    return ELEMENT_TYPES[kind](spec)


# --------------------------------------------------------------------------- elemen otomatis

def draw_chapter_tag(ctx: cairo.Context, t: float, dur: float, rc: RenderCtx) -> None:
    sc = rc.scene
    a = progress(t, 0.25, 0.8) * (1 - progress(t, dur - 0.9, 0.6))
    if a <= 0:
        return
    chapter = sc.get("chapter", "")
    draw_text(ctx, chapter.upper(), 120, 104, rc.font("mono"), 16, rc.accent, a, tracking=0.2)
    set_font(ctx, rc.font("mono"), 16)
    cw = text_width(ctx, chapter.upper(), 0.2)
    draw_text(ctx, sc["title"].upper(), 120 + cw + (24 if chapter else 0), 104, rc.font("mono"), 16,
              rc.theme.c("muted"), a, tracking=0.2)
    if sc.get("era"):
        draw_text(ctx, sc["era"], DESIGN_W - 120, 104, rc.font("mono"), 16, rc.theme.c("muted"), a, "right", 0.12)


def draw_progress(ctx: cairo.Context, gt: float, total: float, markers: list[float], theme, accent) -> None:
    x0, x1, y = 120, DESIGN_W - 120, 58
    ctx.set_source_rgba(*theme.c("dim"), 0.5)
    ctx.rectangle(x0, y, x1 - x0, 1.2)
    ctx.fill()
    ctx.set_source_rgba(*accent, 0.85)
    ctx.rectangle(x0, y - 0.4, (x1 - x0) * clamp(gt / max(total, 1e-3)), 2)
    ctx.fill()
    for m in markers:
        x = lerp(x0, x1, m / max(total, 1e-3))
        ctx.set_source_rgba(*(accent if gt >= m else theme.c("dim")), 0.9)
        ctx.arc(x, y + 0.6, 3, 0, 2 * math.pi)
        ctx.fill()
