"""Ilustrasi line-art prosedural (tanpa aset eksternal).

Setiap ikon digambar di kotak lokal ±100 unit. Fungsi ikon mengisi `Pen` dengan stroke, fill,
dan teks; `Pen.render` menggambar stroke secara berurutan (draw-on) sesuai progress 0..1,
sehingga ikon bisa muncul, menghilang (retract), atau bermorf ke ikon lain.
Parameter `t` (detik) dipakai untuk gerak idle: roda gigi berputar, lampu berkedip, dsb.
"""
from __future__ import annotations

import math
import random

import cairo

from .animation_engine import clamp, draw_text, rounded_rect, stroke_on

TAU = 2 * math.pi


class Pen:
    def __init__(self):
        self.items = []

    def stroke(self, build, w: float = 1.0, color: str | None = None, alpha: float = 1.0):
        self.items.append(("stroke", build, w, color, alpha))

    def fill(self, build, color: str | None = "accent", alpha: float = 1.0):
        self.items.append(("fill", build, 0, color, alpha))

    def text(self, x, y, s, size=12, color=None, font="mono", align="center", alpha=1.0):
        self.items.append(("text", (x, y, s, size, font, align), 0, color, alpha))

    def render(self, ctx: cairo.Context, p: float, theme, color, accent, alpha: float, scale: float,
               glow: float = 0.0) -> None:
        if p <= 0 or alpha <= 0:
            return

        def col(name):
            if name is None:
                return color
            if name == "accent":
                return accent
            return theme.c(name)

        strokes = [it for it in self.items if it[0] == "stroke"]
        n = len(strokes)
        k = 0
        fill_a = clamp((p - 0.55) / 0.45)
        for kind, build, w, cname, a in self.items:
            if kind == "stroke":
                start = 0.55 * k / max(n - 1, 1)
                local = clamp((p - start) / 0.45)
                k += 1
                stroke_on(ctx, build, local, col(cname), theme.stroke_width * w / scale, alpha * a,
                          glow if cname == "accent" else glow * 0.4)
            elif kind == "fill" and fill_a > 0:
                ctx.new_path()
                build(ctx)
                ctx.set_source_rgba(*col(cname), alpha * a * fill_a)
                ctx.fill()
            elif kind == "text" and fill_a > 0:
                x, y, s, size, font, align = build
                family = theme.fonts.get(font, font)
                draw_text(ctx, s, x, y, family, size, col(cname), alpha * a * fill_a, align=align)


# --------------------------------------------------------------------------- helper geometri

def rect(x, y, w, h, r=0):
    def b(ctx):
        if r:
            rounded_rect(ctx, x, y, w, h, r)
        else:
            ctx.rectangle(x, y, w, h)
    return b


def line(*pts):
    def b(ctx):
        ctx.move_to(*pts[0])
        for pt in pts[1:]:
            ctx.line_to(*pt)
    return b


def circle(x, y, r):
    def b(ctx):
        ctx.new_sub_path()
        ctx.arc(x, y, r, 0, TAU)
    return b


def ellipse(x, y, rx, ry, a0=0.0, a1=TAU):
    def b(ctx):
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(max(rx, 0.01), max(ry, 0.01))
        ctx.new_sub_path()
        ctx.arc(0, 0, 1, a0, a1)
        ctx.restore()
    return b


def gear_path(cx, cy, r_in, r_out, teeth, angle):
    def b(ctx):
        steps = teeth * 4
        for i in range(steps + 1):
            a = angle + TAU * i / steps
            rr = r_out if (i % 4) in (1, 2) else r_in
            x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
            (ctx.move_to if i == 0 else ctx.line_to)(x, y)
        ctx.close_path()
    return b


def curve(p0, c1, c2, p1):
    def b(ctx):
        ctx.move_to(*p0)
        ctx.curve_to(*c1, *c2, *p1)
    return b


# --------------------------------------------------------------------------- ikon

def icon_phone(pen: Pen, t, o):
    pen.stroke(rect(-55, -100, 110, 200, 18), 1.2)
    pen.stroke(rect(-45, -84, 90, 162, 6), 0.8, "muted")
    pen.stroke(line((-12, -92), (12, -92)), 0.8)
    pen.stroke(line((-16, 90), (16, 90)), 0.8)
    for i in range(6):
        w = 30 + 40 * (0.5 + 0.5 * math.sin(t * 2.2 + i * 1.3))
        pen.fill(rect(-34, -66 + i * 22, w, 9, 3), "accent", 0.55 + 0.08 * i)
    pen.fill(circle(26, 66, 6), "accent", 0.8)


def icon_abacus(pen: Pen, t, o):
    pen.stroke(rect(-100, -72, 200, 144, 8), 1.3)
    pen.stroke(line((-100, -30), (100, -30)), 1.0)
    xs = [-75 + 25 * i for i in range(7)]
    for x in xs:
        pen.stroke(line((x, -66), (x, 66)), 0.6, "muted")
    step = int(t * 1.6)
    for i, x in enumerate(xs):
        rng = random.Random(i * 97 + step // (i + 1))
        up = rng.random() < 0.5
        pen.fill(rect(x - 10, (-38 if up else -60) - 5, 20, 10, 5), "amber", 0.95)
        lower_up = rng.randint(0, 4)
        for b in range(4):
            y = (-18 + b * 12) if b < lower_up else (66 - (4 - b) * 12)
            pen.fill(rect(x - 10, y, 20, 10, 5), "accent", 0.85)


def icon_tally(pen: Pen, t, o):
    for g in range(3):
        x0 = -88 + g * 62
        for k in range(4):
            x = x0 + k * 10
            pen.stroke(line((x, -50), (x + 2, 10)), 1.1)
        pen.stroke(line((x0 - 8, -12), (x0 + 42, -32)), 1.1, "accent")
    for i, (x, y, r) in enumerate([(-70, 52, 9), (-44, 60, 7), (-20, 50, 8), (8, 58, 9), (34, 52, 6), (58, 61, 8)]):
        pen.stroke(circle(x, y, r), 0.8, "muted")
        pen.fill(circle(x, y, r * 0.6), "amber", 0.5)


def icon_gears(pen: Pen, t, o):
    a = t * 0.6
    pen.stroke(gear_path(-20, -5, 52, 64, 14, a), 1.1)
    pen.stroke(circle(-20, -5, 14), 0.9, "accent")
    pen.stroke(gear_path(66, -40, 26, 36, 8, -a * 1.75 + 0.2), 1.0)
    pen.stroke(circle(66, -40, 8), 0.8, "accent")
    pen.stroke(gear_path(52, 62, 30, 41, 9, -a * 1.55 + 0.1), 1.0)
    pen.stroke(circle(52, 62, 9), 0.8, "accent")


def icon_pascaline(pen: Pen, t, o):
    pen.stroke(rect(-105, -55, 210, 110, 8), 1.3)
    pen.stroke(line((-105, -22), (105, -22)), 0.7, "muted")
    for i in range(6):
        cx = -80 + i * 32
        pen.stroke(circle(cx, 18, 13), 0.9)
        ang = t * (0.4 + 0.25 * i) + i
        pen.stroke(line((cx, 18), (cx + 11 * math.cos(ang), 18 + 11 * math.sin(ang))), 0.8, "accent")
        pen.stroke(rect(cx - 8, -48, 16, 20, 3), 0.6, "muted")
        digit = str(int(t * (0.6 + i * 0.3) + i * 3) % 10)
        pen.text(cx, -33, digit, 14, "amber")


def icon_difference_engine(pen: Pen, t, o):
    for c in range(3):
        x = -80 + c * 55
        pen.stroke(line((x, -85), (x, 85)), 0.7, "muted")
        for k in range(6):
            y = -70 + k * 27
            pen.stroke(rect(x - 20, y, 40, 16, 4), 0.9)
            d = str(int(t * (1 + c * 0.5) + k * 7 + c) % 10)
            pen.text(x, y + 13, d, 12, "amber")
    pen.stroke(line((-100, -92), (90, -92)), 1.2)
    pen.stroke(line((-100, 92), (90, 92)), 1.2)
    a = t * 1.2
    pen.stroke(circle(85, 0, 16), 1.0, "accent")
    pen.stroke(line((85, 0), (85 + 32 * math.cos(a), 32 * math.sin(a))), 1.0, "accent")


def icon_analytical_engine(pen: Pen, t, o):
    pen.stroke(rect(-105, -70, 120, 140, 6), 0.8, "muted")
    for i in range(7):
        x = -92 + i * 16
        pen.stroke(line((x, -60), (x, 60)), 0.7)
        for k in range(5):
            pen.stroke(line((x - 5, -48 + k * 24), (x + 5, -48 + k * 24)), 0.6, "amber")
    pen.stroke(circle(62, 0, 46), 1.0)
    for i in range(8):
        ang = TAU * i / 8 + t * 0.25
        pen.stroke(circle(62 + 34 * math.cos(ang), 34 * math.sin(ang), 6), 0.7)
    pen.stroke(gear_path(62, 0, 15, 21, 8, t * 0.8), 0.9, "accent")
    pen.stroke(line((15, 0), (40, 0)), 1.2, "accent")
    pen.text(-45, 88, "STORE", 13, "muted")
    pen.text(62, 66, "MILL", 13, "muted")


def icon_punched_card(pen: Pen, t, o):
    def card(ctx):
        ctx.move_to(-82, -55)
        ctx.line_to(100, -55)
        ctx.line_to(100, 55)
        ctx.line_to(-100, 55)
        ctx.line_to(-100, -37)
        ctx.close_path()
    pen.stroke(card, 1.2)
    rng = random.Random(5)
    for c in range(14):
        for r in range(6):
            x, y = -84 + c * 12.5, -38 + r * 15
            on = rng.random() < 0.38
            if on:
                pen.fill(rect(x - 3, y - 5, 6, 10, 1.5), "accent", 0.9)
            else:
                pen.fill(rect(x - 1.5, y - 1, 3, 2), "dim", 0.9)
    scan = -84 + ((t * 40) % 175)
    pen.fill(rect(scan - 1, -50, 2, 100), "amber", 0.5)


def icon_notes(pen: Pen, t, o):
    def page(ctx):
        ctx.move_to(-70, -95)
        ctx.line_to(45, -95)
        ctx.line_to(70, -70)
        ctx.line_to(70, 95)
        ctx.line_to(-70, 95)
        ctx.close_path()
    pen.stroke(page, 1.2)
    pen.stroke(line((45, -95), (45, -70), (70, -70)), 0.8)
    pen.text(-52, -66, "Note G", 15, "accent", align="left")
    widths = [100, 84, 108, 64, 96, 110, 72, 90]
    for i, w in enumerate(widths):
        pen.stroke(line((-52, -42 + i * 15), (-52 + w, -42 + i * 15)), 0.6, "muted")
    pen.stroke(rect(-52, 50, 104, 30, 2), 0.7, "amber")
    for k in range(1, 4):
        pen.stroke(line((-52 + k * 26, 50), (-52 + k * 26, 80)), 0.5, "amber")


def icon_music_wave(pen: Pen, t, o):
    for i in range(5):
        y = -40 + i * 16
        pen.stroke(line((-100, y), (-10, y)), 0.6, "muted")
    for i, (x, y) in enumerate([(-82, 8), (-60, -16), (-38, 0), (-20, -32)]):
        pen.fill(ellipse(x, y, 8, 6), "amber", 0.95)
        pen.stroke(line((x + 7, y), (x + 7, y - 36)), 0.8, "amber")

    def wave(ctx):
        for i in range(91):
            x = -5 + i * 1.15
            y = math.sin(i * 0.22 + t * 3) * 34 * math.sin(math.pi * i / 90)
            (ctx.move_to if i == 0 else ctx.line_to)(x, y)
    pen.stroke(wave, 1.3, "accent")


def icon_spark(pen: Pen, t, o):
    pen.stroke(circle(0, 0, 88), 0.8, "muted")

    def bolt(ctx):
        for i, (x, y) in enumerate([(12, -70), (-30, 6), (2, 6), (-14, 70), (34, -12), (2, -12), (12, -70)]):
            (ctx.move_to if i == 0 else ctx.line_to)(x, y)
    pen.stroke(bolt, 1.4, "accent")
    for i in range(8):
        a = TAU * i / 8 + t * 0.2
        r0, r1 = 96, 110 + 6 * math.sin(t * 4 + i)
        pen.stroke(line((r0 * math.cos(a), r0 * math.sin(a)), (r1 * math.cos(a), r1 * math.sin(a))), 0.7, "amber")


def icon_turing_tape(pen: Pen, t, o):
    pen.stroke(line((-110, -18), (110, -18)), 1.0)
    pen.stroke(line((-110, 18), (110, 18)), 1.0)
    syms = "0110100110"
    shift = (t * 12) % 22
    for i in range(11):
        x = -110 + i * 22 - shift
        if -110 <= x <= 110:
            pen.stroke(line((x, -18), (x, 18)), 0.6, "muted")
        cx = x + 11
        if -100 < cx < 100:
            pen.text(cx, 6, syms[i % len(syms)], 15, "text")

    def head(ctx):
        ctx.move_to(-14, -64)
        ctx.line_to(14, -64)
        ctx.line_to(14, -38)
        ctx.line_to(0, -24)
        ctx.line_to(-14, -38)
        ctx.close_path()
    pen.stroke(head, 1.2, "accent")
    pen.stroke(rect(-11, -20, 22, 40, 2), 1.0, "accent")
    pen.text(0, 54, "MESIN TURING", 12, "muted")


def icon_eniac(pen: Pen, t, o):
    for p_i in range(5):
        x = -110 + p_i * 45
        pen.stroke(rect(x, -80, 38, 150, 3), 1.0)
        for r in range(7):
            for c in range(3):
                on = math.sin(t * (3 + p_i) + r * 1.7 + c * 2.3 + p_i) > 0.2
                pen.fill(circle(x + 9 + c * 10, -66 + r * 14, 2.6), "amber" if on else "dim", 0.95)
        pen.stroke(line((x + 6, 40), (x + 32, 40)), 0.6, "muted")
        pen.stroke(line((x + 6, 52), (x + 32, 52)), 0.6, "muted")
    for i in range(4):
        x = -91 + i * 45
        pen.stroke(curve((x, 70), (x + 4, 98), (x + 41, 98), (x + 45, 70)), 0.8, "accent")


def icon_vacuum_tube(pen: Pen, t, o):
    def envelope(ctx):
        ctx.move_to(-38, 60)
        ctx.line_to(-38, -40)
        ctx.arc(0, -40, 38, math.pi, 0)
        ctx.line_to(38, 60)
    pen.stroke(envelope, 1.3)
    pen.stroke(rect(-46, 60, 92, 22, 4), 1.1)
    for x in (-24, -8, 8, 24):
        pen.stroke(line((x, 82), (x, 100)), 0.9, "muted")
    pen.stroke(rect(-20, -38, 40, 74, 2), 0.8, "muted")

    def grid(ctx):
        for i in range(9):
            y = -32 + i * 8
            (ctx.move_to if i == 0 else ctx.line_to)(-12 if i % 2 == 0 else 12, y)
    pen.stroke(grid, 0.7, "accent")
    flick = 0.55 + 0.25 * math.sin(t * 9) + 0.1 * math.sin(t * 23)
    pen.fill(rect(-3, -30, 6, 62, 3), "amber", flick)


def icon_transistor(pen: Pen, t, o):
    def body(ctx):
        ctx.move_to(-40, 10)
        ctx.line_to(-40, -40)
        ctx.arc(0, -40, 40, math.pi, 0)
        ctx.line_to(40, 10)
        ctx.close_path()
    pen.stroke(body, 1.3)
    pen.stroke(line((-40, -6), (40, -6)), 0.5, "muted")
    for x in (-22, 0, 22):
        pen.stroke(line((x, 10), (x, 92)), 1.1, "accent")
    pulse = (t * 0.8) % 1
    pen.fill(circle(0, 10 + 82 * pulse, 4), "amber", 0.9)
    for i, s in enumerate("EBC"):
        pen.text(-22 + i * 22, 108, s, 12, "muted")


def icon_chip(pen: Pen, t, o):
    pen.stroke(rect(-70, -70, 140, 140, 8), 1.4)
    for i in range(7):
        k = -54 + i * 18
        pen.stroke(line((k, -70), (k, -92)), 0.8, "muted")
        pen.stroke(line((k, 70), (k, 92)), 0.8, "muted")
        pen.stroke(line((-70, k), (-92, k)), 0.8, "muted")
        pen.stroke(line((70, k), (92, k)), 0.8, "muted")
    pen.stroke(rect(-34, -34, 68, 68, 3), 1.0, "accent")
    traces = [((-34, -14), (-56, -14), (-56, -54)), ((34, 10), (54, 10), (54, 50)),
              ((-10, 34), (-10, 54), (-40, 54)), ((12, -34), (12, -54), (40, -54))]
    for tr in traces:
        pen.stroke(line(*tr), 0.7, "accent")
    for i in range(4):
        for j in range(4):
            on = math.sin(t * 4 + i * 1.3 + j * 2.1) > 0.3
            pen.fill(rect(-26 + i * 14, -26 + j * 14, 9, 9, 1), "accent" if on else "dim", 0.85)


def icon_die(pen: Pen, t, o):
    pen.stroke(rect(-95, -80, 190, 160, 4), 1.3)
    blocks = [(-85, -70, 70, 50), (-8, -70, 50, 32), (48, -70, 38, 70), (-85, -14, 40, 84), (-38, -30, 80, 46),
              (-38, 22, 52, 48), (20, 22, 66, 48), (48, 6, 38, 10)]
    for i, (x, y, w, h) in enumerate(blocks):
        pen.stroke(rect(x, y, w, h, 2), 0.8, "accent" if i % 3 == 0 else None)
        lit = (math.sin(t * 2.5 - i * 0.9) + 1) / 2
        pen.fill(rect(x + 3, y + 3, w - 6, h - 6, 1), "accent", 0.10 + 0.25 * lit)
    for k in range(6):
        pen.stroke(line((-38 + k * 13, -30), (-38 + k * 13, 16)), 0.4, "muted")


def icon_altair(pen: Pen, t, o):
    pen.stroke(rect(-110, -50, 220, 100, 6), 1.3)
    pen.stroke(line((-110, -18), (110, -18)), 0.5, "muted")
    for i in range(16):
        x = -96 + i * 12.8
        on = math.sin(t * 5 + i * 0.9) > 0
        pen.fill(circle(x, -32, 3.2), "amber" if on else "dim", 1.0)
        up = math.sin(t * 0.7 + i * 2.1) > 0
        pen.stroke(line((x, 18), (x, 4 if up else 32)), 0.9)
        pen.fill(circle(x, 18, 2.4), "muted", 1.0)
    pen.text(-96, -2, "ALTAIR 8800", 11, "muted", align="left")


def icon_desktop_pc(pen: Pen, t, o):
    pen.stroke(rect(-78, -96, 156, 118, 10), 1.3)
    pen.stroke(rect(-64, -84, 128, 92, 6), 0.8, "muted")
    pen.stroke(line((-24, 22), (-32, 40), (32, 40), (24, 22)), 1.0)
    pen.stroke(rect(-100, 52, 200, 40, 5), 1.1)
    for r in range(3):
        for c in range(12):
            pen.fill(rect(-92 + c * 15.5, 58 + r * 11, 11, 7, 1.5), "dim", 1.0)
    pen.text(-54, -60, "C:\\> _" if int(t * 2) % 2 == 0 else "C:\\>", 13, "accent", align="left")
    pen.fill(rect(-54, -48, 70, 4, 1), "muted", 0.6)
    pen.fill(rect(-54, -38, 50, 4, 1), "muted", 0.6)


def icon_gui_window(pen: Pen, t, o):
    pen.stroke(rect(-105, -80, 210, 150, 8), 1.3)
    pen.stroke(line((-105, -58), (105, -58)), 0.8)
    for i in range(3):
        pen.fill(circle(-92 + i * 11, -69, 3.2), "accent" if i == 0 else "muted", 1.0)
    for i in range(3):
        x = -80 + i * 58
        pen.stroke(rect(x, -40, 34, 28, 4), 0.9, "accent")
        pen.fill(rect(x + 2, -6, 30, 5, 1.5), "muted", 0.7)
    pen.stroke(rect(-80, 14, 160, 40, 4), 0.7, "muted")
    mx = -20 + 50 * math.sin(t * 0.9)
    my = 20 + 18 * math.cos(t * 1.3)

    def cursor(ctx):
        ctx.move_to(mx, my)
        ctx.line_to(mx, my + 26)
        ctx.line_to(mx + 7, my + 19)
        ctx.line_to(mx + 13, my + 31)
        ctx.line_to(mx + 17, my + 29)
        ctx.line_to(mx + 11, my + 17)
        ctx.line_to(mx + 20, my + 17)
        ctx.close_path()
    pen.fill(cursor, "text", 1.0)


def icon_laptop(pen: Pen, t, o):
    pen.stroke(rect(-84, -78, 168, 112, 8), 1.3)
    pen.stroke(rect(-74, -68, 148, 92, 4), 0.8, "muted")

    def base(ctx):
        ctx.move_to(-104, 40)
        ctx.line_to(104, 40)
        ctx.line_to(116, 56)
        ctx.line_to(-116, 56)
        ctx.close_path()
    pen.stroke(base, 1.2)
    pen.stroke(line((-20, 46), (20, 46)), 0.6, "muted")
    for i in range(4):
        w = 40 + 60 * (0.5 + 0.5 * math.sin(t * 1.5 + i))
        pen.fill(rect(-62, -54 + i * 18, w, 8, 2), "accent", 0.55)


def icon_globe(pen: Pen, t, o):
    r = 90
    pen.stroke(circle(0, 0, r), 1.3)
    for k in range(-2, 3):
        y = k * 30
        rx = math.sqrt(max(r * r - y * y, 0))
        pen.stroke(ellipse(0, y, rx, rx * 0.18), 0.5, "muted")
    for k in range(6):
        ph = (t * 0.25 + k / 6) % 1
        rx = abs(math.cos(ph * math.pi)) * r
        pen.stroke(ellipse(0, 0, max(rx, 0.5), r), 0.5, "muted")
    rng = random.Random(4)
    pts = [(rng.uniform(-70, 70), rng.uniform(-60, 60)) for _ in range(7)]
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2 - 30
        pen.stroke(curve((x0, y0), (mx, my), (mx, my), (x1, y1)), 0.9, "accent")
        q = (t * 0.7 + i * 0.3) % 1
        bx = (1 - q) ** 2 * x0 + 2 * (1 - q) * q * mx + q * q * x1
        by = (1 - q) ** 2 * y0 + 2 * (1 - q) * q * my + q * q * y1
        pen.fill(circle(bx, by, 3), "amber", 0.95)
    for (x, y) in pts:
        pen.fill(circle(x, y, 4), "accent", 1.0)


def icon_go_board(pen: Pen, t, o):
    pen.stroke(rect(-90, -90, 180, 180, 4), 1.2)
    for i in range(1, 9):
        k = -90 + i * 20
        pen.stroke(line((k, -90), (k, 90)), 0.5, "muted")
        pen.stroke(line((-90, k), (90, k)), 0.5, "muted")
    rng = random.Random(12)
    n = min(26, int(t * 3))
    for i in range(n):
        x, y = -70 + 20 * rng.randint(0, 7), -70 + 20 * rng.randint(0, 7)
        pen.fill(circle(x, y, 8.5), "text" if i % 2 else "accent", 0.95)


def icon_code_rules(pen: Pen, t, o):
    pen.stroke(rect(-110, -80, 220, 160, 8), 1.2)
    lines = ["jika suhu > 30:", "    nyalakan_kipas()", "lainnya jika hujan:", "    tutup_jendela()",
             "lainnya:", "    tunggu()"]
    shown = int(t * 4)
    for i, s in enumerate(lines):
        pen.text(-94, -50 + i * 24, s[: max(0, shown - i * 4) * 3], 13,
                 "accent" if not s.startswith(" ") else "text", align="left")


def icon_neural_net(pen: Pen, t, o):
    layers = [3, 5, 5, 2]
    pos = []
    for li, n in enumerate(layers):
        x = -90 + li * 60
        pos.append([(x, (j - (n - 1) / 2) * 34) for j in range(n)])
    for li in range(len(layers) - 1):
        for a in pos[li]:
            for b in pos[li + 1]:
                pen.stroke(line(a, b), 0.35, "muted", 0.7)
    rng = random.Random(9)
    for k in range(14):
        li = rng.randint(0, len(layers) - 2)
        a, b = rng.choice(pos[li]), rng.choice(pos[li + 1])
        q = (t * 0.9 + k * 0.37) % 1
        pen.fill(circle(a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q, 2.6), "amber", 0.9)
    for li, col in enumerate(pos):
        for (x, y) in col:
            pen.stroke(circle(x, y, 9), 1.0, "accent")
            act = 0.5 + 0.5 * math.sin(t * 2 + x * 0.05 + y * 0.09)
            pen.fill(circle(x, y, 5), "accent", 0.25 + 0.6 * act)


def icon_qubit(pen: Pen, t, o):
    r = 85
    pen.stroke(circle(0, 0, r), 1.2)
    pen.stroke(ellipse(0, 0, r, 24), 0.7, "muted")
    pen.stroke(line((0, -r - 10), (0, r + 10)), 0.6, "muted")
    a = t * 0.8
    tip = (r * 0.8 * math.cos(a) * 0.9, -r * 0.55 + 18 * math.sin(a))
    pen.stroke(line((0, 0), tip), 1.4, "accent")
    pen.fill(circle(*tip, 6), "accent", 1.0)
    pen.text(0, -r - 16, "|0⟩", 14, "muted")
    pen.text(0, r + 28, "|1⟩", 14, "muted")


def icon_tangle(pen: Pen, t, o):
    rng = random.Random(21)
    left = [(-95, -80 + i * 20) for i in range(9)]
    right = [(95, -80 + i * 20) for i in range(9)]
    for (x, y) in left + right:
        pen.stroke(rect(x - 6, y - 4, 12, 8, 1.5), 0.6)
    for i in range(16):
        a, b = rng.choice(left), rng.choice(right)
        c1 = (rng.uniform(-60, 0), rng.uniform(-100, 100))
        c2 = (rng.uniform(0, 60), rng.uniform(-100, 100))
        pen.stroke(curve((a[0] + 6, a[1]), c1, c2, (b[0] - 6, b[1])), 0.6, "accent" if i % 4 == 0 else "muted")


def icon_person(pen: Pen, t, o):
    pen.stroke(circle(0, -40, 26), 1.3)

    def shoulders(ctx):
        ctx.new_sub_path()
        ctx.arc(0, 60, 58, math.pi, 0)
    pen.stroke(shoulders, 1.3)


ICONS = {
    "phone": icon_phone, "abacus": icon_abacus, "tally": icon_tally, "gears": icon_gears,
    "pascaline": icon_pascaline, "difference_engine": icon_difference_engine,
    "analytical_engine": icon_analytical_engine, "punched_card": icon_punched_card, "notes": icon_notes,
    "music_wave": icon_music_wave, "spark": icon_spark, "turing_tape": icon_turing_tape, "eniac": icon_eniac,
    "vacuum_tube": icon_vacuum_tube, "transistor": icon_transistor, "chip": icon_chip, "die": icon_die,
    "altair": icon_altair, "desktop_pc": icon_desktop_pc, "gui_window": icon_gui_window, "laptop": icon_laptop,
    "globe": icon_globe, "go_board": icon_go_board, "code_rules": icon_code_rules, "neural_net": icon_neural_net,
    "qubit": icon_qubit, "tangle": icon_tangle, "person": icon_person,
}


def draw_icon(ctx: cairo.Context, name: str, x: float, y: float, size: float, p: float, t: float, theme,
              color, accent, alpha: float = 1.0, glow: float | None = None, opts: dict | None = None) -> None:
    """Gambar ikon `name` berpusat di (x, y) dengan lebar kotak `size` px."""
    if name not in ICONS:
        raise KeyError(f"Ikon '{name}' tidak dikenal. Pilihan: {', '.join(sorted(ICONS))}")
    if p <= 0 or alpha <= 0:
        return
    pen = Pen()
    ICONS[name](pen, t, opts or {})
    scale = size / 200.0
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale, scale)
    pen.render(ctx, p, theme, color, accent, alpha, scale, theme.glow if glow is None else glow)
    ctx.restore()
