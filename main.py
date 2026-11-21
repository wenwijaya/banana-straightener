#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The Catalogue Photo of an Impossible Gadget.

Renders a studio catalogue photograph of the STRAIGHT-O-MATIC BS-3000, a
countertop appliance that straightens bananas: a naturally curved banana
goes in through the port on the left, and a perfectly straight banana
comes out of the port on the right. One accessory only: the curved banana
(the "before") that sharpens the joke.

Pure Python 3.13 standard library, no network, fully deterministic: the
same bytes are written on every run. Output: /output/entry.png
(1024x1024 PNG, well under 1 MiB).
"""

import math
import os
import struct
import zlib

W, H = 1024, 1024
SS = 2                      # supersample factor (render at 2048, downsample)
SW, SH = W * SS, H * SS

OUT_DIR = "/output" if os.path.isdir("/output") else "output"
OUT_PATH = os.path.join(OUT_DIR, "entry.png")


def clamp(v, lo=0, hi=255):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_c(c0, c1, t):
    return (lerp(c0[0], c1[0], t), lerp(c0[1], c1[1], t), lerp(c0[2], c1[2], t))


def blend(base, over, alpha):
    """Blend colour `over` onto `base` with alpha in [0, 1]."""
    return (lerp(base[0], over[0], alpha),
            lerp(base[1], over[1], alpha),
            lerp(base[2], over[2], alpha))


def cbytes(c):
    return bytes((clamp(int(round(c[0]))),
                  clamp(int(round(c[1]))),
                  clamp(int(round(c[2])))))


# ---------------------------------------------------------------- canvas
# rows[y] is a bytearray of SW*3 bytes (RGB) at supersampled resolution.
rows = [bytearray(SW * 3) for _ in range(SH)]


def fill_rect(x0, y0, x1, y1, color):
    x0 = max(0, int(x0)); y0 = max(0, int(y0))
    x1 = min(SW, int(x1)); y1 = min(SH, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    b = cbytes(color) * (x1 - x0)
    for y in range(y0, y1):
        rows[y][x0 * 3:x1 * 3] = b


def vgrad_rect(x0, y0, x1, y1, c_top, c_bot):
    """Fill a rectangle with a vertical gradient."""
    x0 = max(0, int(x0)); y0 = max(0, int(y0))
    x1 = min(SW, int(x1)); y1 = min(SH, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    span = max(1, y1 - y0)
    width = x1 - x0
    for y in range(y0, y1):
        c = lerp_c(c_top, c_bot, (y - y0) / span)
        rows[y][x0 * 3:x1 * 3] = cbytes(c) * width


def fill_ellipse(cx, cy, rx, ry, color):
    rx = float(rx); ry = float(ry)
    y0 = max(0, int(cy - ry)); y1 = min(SH, int(cy + ry) + 1)
    for y in range(y0, y1):
        dy = (y - cy) / ry
        if abs(dy) >= 1.0:
            continue
        dx = rx * math.sqrt(1.0 - dy * dy)
        x0 = max(0, int(cx - dx)); x1 = min(SW, int(cx + dx) + 1)
        if x1 > x0:
            rows[y][x0 * 3:x1 * 3] = cbytes(color) * (x1 - x0)


def vgrad_ellipse(cx, cy, rx, ry, c_top, c_bot):
    rx = float(rx); ry = float(ry)
    y0 = max(0, int(cy - ry)); y1 = min(SH, int(cy + ry) + 1)
    for y in range(y0, y1):
        dy = (y - cy) / ry
        if abs(dy) >= 1.0:
            continue
        dx = rx * math.sqrt(1.0 - dy * dy)
        x0 = max(0, int(cx - dx)); x1 = min(SW, int(cx + dx) + 1)
        if x1 > x0:
            c = lerp_c(c_top, c_bot, (y - (cy - ry)) / (2.0 * ry))
            rows[y][x0 * 3:x1 * 3] = cbytes(c) * (x1 - x0)


def fill_rrect(x0, y0, x1, y1, r, color):
    """Filled rounded rectangle (solid colour)."""
    x0, y0, x1, y1, r = int(x0), int(y0), int(x1), int(y1), int(r)
    fill_rect(x0 + r, y0, x1 - r, y1, color)
    fill_rect(x0, y0 + r, x1, y1 - r, color)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r),
                   (x0 + r, y1 - r), (x1 - r, y1 - r)):
        fill_ellipse(cx, cy, r, r, color)


def vgrad_rrect(x0, y0, x1, y1, r, c_top, c_bot):
    """Filled rounded rectangle with a vertical gradient."""
    x0, y0, x1, y1, r = int(x0), int(y0), int(x1), int(y1), int(r)
    vgrad_rect(x0 + r, y0, x1 - r, y1, c_top, c_bot)
    vgrad_rect(x0, y0 + r, x1, y1 - r, c_top, c_bot)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r),
                   (x0 + r, y1 - r), (x1 - r, y1 - r)):
        vgrad_ellipse(cx, cy, r, r, c_top, c_bot)


def fill_poly(points, c_top, c_bot):
    """Scanline-fill a polygon; colour is a vertical gradient over its
    own y-extent (c_top at the topmost vertex, c_bot at the bottommost)."""
    ys = [p[1] for p in points]
    ymin, ymax = min(ys), max(ys)
    y0 = max(0, int(math.floor(ymin))); y1 = min(SH, int(math.ceil(ymax)) + 1)
    n = len(points)
    for y in range(y0, y1):
        xs = []
        for i in range(n):
            x_a, y_a = points[i]
            x_b, y_b = points[(i + 1) % n]
            if (y_a <= y < y_b) or (y_b <= y < y_a):
                t = (y - y_a) / (y_b - y_a)
                xs.append(x_a + t * (x_b - x_a))
        xs.sort()
        if len(xs) < 2:
            continue
        t = (y - ymin) / max(1.0, ymax - ymin)
        c = cbytes(lerp_c(c_top, c_bot, t))
        for k in range(0, len(xs) - 1, 2):
            xa = max(0, int(xs[k])); xb = min(SW, int(xs[k + 1]) + 1)
            if xb > xa:
                rows[y][xa * 3:xb * 3] = c * (xb - xa)


def soft_ellipse(cx, cy, rx, ry, color, alpha_max, base_fn, segments=64):
    """Soft-edged ellipse (e.g. a contact shadow or a light bloom).

    The falloff is parabolic in the normalised radius. Each row is filled
    in horizontal segments blended against base_fn(y), the colour of the
    surface underneath -- exact here because shadows fall on the plain
    studio background gradient.
    """
    y0 = max(0, int(cy - ry)); y1 = min(SH, int(cy + ry) + 1)
    for y in range(y0, y1):
        ny = (y - cy) / ry
        if abs(ny) >= 1.0:
            continue
        half = rx * math.sqrt(1.0 - ny * ny)
        if half < 1:
            continue
        base = base_fn(y)
        seg_w = (2.0 * half) / segments
        for s in range(segments):
            xa = cx - half + s * seg_w
            xb = xa + seg_w
            xm = (xa + xb) / 2.0
            nx = (xm - cx) / rx
            a = alpha_max * max(0.0, 1.0 - nx * nx - ny * ny)
            if a <= 0.004:
                continue
            c = cbytes(blend(base, color, a))
            xi0 = max(0, int(xa)); xi1 = min(SW, int(xb) + 1)
            if xi1 > xi0:
                rows[y][xi0 * 3:xi1 * 3] = c * (xi1 - xi0)


def draw_line(x0, y0, x1, y1, color, width=2):
    """Thick straight line (Bresenham with a square brush)."""
    dx = x1 - x0; dy = y1 - y0
    steps = int(max(abs(dx), abs(dy))) + 1
    half = width // 2
    for i in range(steps + 1):
        t = i / max(1, steps)
        x = int(x0 + dx * t); y = int(y0 + dy * t)
        fill_rect(x - half, y - half, x + half + 1, y + half + 1, color)


# ------------------------------------------------------------- 5x7 font
# Each glyph is 7 rows of 5 bits, written as strings of 0/1.
FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'D': ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'Y': ("10001", "10001", "10001", "01110", "00100", "00100", "00100"),
    '0': ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    '3': ("11111", "00001", "00001", "01110", "00001", "00001", "11111"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
}


def text_width(text, scale):
    return len(text) * (5 * scale + scale) - scale


def draw_text(x, y, text, scale, color):
    """Draw text at supersampled coords; (x, y) is the top-left corner."""
    cx = int(x)
    for ch in text:
        glyph = FONT.get(ch, FONT[' '])
        for gy in range(7):
            bits = glyph[gy]
            for gx in range(5):
                if bits[gx] == '1':
                    fill_rect(cx + gx * scale, y + gy * scale,
                              cx + (gx + 1) * scale, y + (gy + 1) * scale,
                              color)
        cx += 5 * scale + scale


# ------------------------------------------------------------------ scene
# All scene coordinates below are in final-image (1024) space and are
# multiplied by SS when drawn.

BG_TOP = (238, 236, 232)
BG_BOT = (198, 194, 188)


def bg_at(y_ss):
    t = y_ss / SH
    return lerp_c(BG_TOP, BG_BOT, t)


def render():
    # ---- studio background: seamless sweep, light from upper left.
    vgrad_rect(0, 0, SW, SH, BG_TOP, BG_BOT)
    soft_ellipse(340 * SS, 260 * SS, 520 * SS, 400 * SS,
                 (255, 255, 255), 0.10, bg_at)

    # ---- soft contact shadows on the surface (drawn before the objects,
    #      so the objects sit on top of them).
    soft_ellipse(520 * SS, 680 * SS, 255 * SS, 26 * SS,
                 (40, 36, 30), 0.30, bg_at)
    soft_ellipse(205 * SS, 690 * SS, 105 * SS, 17 * SS,
                 (40, 36, 30), 0.26, bg_at)
    soft_ellipse(830 * SS, 690 * SS, 100 * SS, 16 * SS,
                 (40, 36, 30), 0.26, bg_at)

    # ---- curved banana (the accessory / the "before"): enters the left
    #      port still curved, tip pointing up-left.
    # Centreline: quadratic Bezier from the port (310, 545) via (185, 665)
    # to the tip (108, 542); width tapers 58 -> 30.
    p0 = (310.0, 545.0); p1 = (185.0, 668.0); p2 = (106.0, 540.0)
    centre = []
    for i in range(25):
        t = i / 24.0
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        centre.append((x, y))
    left_pts, right_pts = [], []
    for i, (x, y) in enumerate(centre):
        t = i / 24.0
        # tangent from neighbours
        xa, ya = centre[max(0, i - 1)]
        xb, yb = centre[min(24, i + 1)]
        dx, dy = xb - xa, yb - ya
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        half_w = (58.0 - 28.0 * t) / 2.0
        left_pts.append((x + nx * half_w, y + ny * half_w))
        right_pts.append((x - nx * half_w, y - ny * half_w))
    poly = [(x * SS, y * SS) for (x, y) in left_pts + right_pts[::-1]]
    fill_poly(poly, (247, 210, 66), (222, 168, 30))
    # glossy highlight along the upper edge of the curve
    for i in range(24):
        x0, y0 = centre[i]
        x1, y1 = centre[i + 1]
        draw_line((x0 - 6) * SS, (y0 - 14) * SS,
                  (x1 - 6) * SS, (y1 - 14) * SS,
                  (255, 233, 143), width=7 * SS)
    # brown tip at the far end
    fill_ellipse(106 * SS, 540 * SS, 9 * SS, 13 * SS, (122, 74, 33))

    # ---- straight banana (the "after"): emerges from the right port,
    #      perfectly straight, gently tapered.
    straight = [(736, 522), (898, 528), (908, 545), (898, 562), (736, 568)]
    fill_poly([(x * SS, y * SS) for (x, y) in straight],
              (248, 216, 79), (227, 172, 34))
    fill_rect(748 * SS, 529 * SS, 892 * SS, 537 * SS, (255, 236, 143))
    fill_ellipse(906 * SS, 545 * SS, 7 * SS, 11 * SS, (122, 74, 33))

    # ---- the machine: STRAIGHT-O-MATIC BS-3000.
    # outline, then brushed-steel front face
    vgrad_rrect(298 * SS, 428 * SS, 742 * SS, 652 * SS, 14 * SS,
                (150, 150, 150), (138, 138, 138))
    vgrad_rrect(302 * SS, 432 * SS, 738 * SS, 648 * SS, 12 * SS,
                (216, 216, 216), (168, 168, 168))
    # brushed-steel streaks
    for yy in (470, 505, 610, 628):
        fill_rect(304 * SS, yy * SS, 736 * SS, (yy + 1) * SS,
                  (190, 190, 190))
        fill_rect(304 * SS, (yy + 2) * SS, 736 * SS, (yy + 3) * SS,
                  (205, 205, 205))
    # glossy top face
    vgrad_rrect(316 * SS, 398 * SS, 724 * SS, 436 * SS, 10 * SS,
                (246, 246, 244), (222, 222, 220))
    fill_rect(316 * SS, 430 * SS, 724 * SS, 434 * SS, (196, 196, 196))
    # chrome trim along the bottom of the front face
    vgrad_rect(302 * SS, 634 * SS, 738 * SS, 646 * SS,
               (240, 240, 240), (196, 196, 196))
    # feet
    fill_rect(352 * SS, 648 * SS, 382 * SS, 666 * SS, (42, 42, 44))
    fill_rect(658 * SS, 648 * SS, 688 * SS, 666 * SS, (42, 42, 44))

    # ---- ports: chrome ring + dark opening, drawn over the banana ends
    #      so both bananas read as passing through the machine.
    for pcx in (300, 740):
        fill_ellipse(pcx * SS, 545 * SS, 27 * SS, 58 * SS, (232, 232, 232))
        fill_ellipse(pcx * SS, 545 * SS, 22 * SS, 52 * SS, (226, 226, 226))
        fill_ellipse(pcx * SS, 545 * SS, 19 * SS, 47 * SS, (26, 26, 28))

    # ---- brand plate
    fill_rrect(356 * SS, 500 * SS, 548 * SS, 572 * SS, 8 * SS, (38, 38, 42))
    label = "STRAIGHT-O-MATIC"
    lw = text_width(label, 4)
    draw_text(452 * SS - lw // 2, 516 * SS, label, 4, (245, 245, 240))
    sub = "BANANA STRAIGHTENER"
    sw = text_width(sub, 3)
    draw_text(452 * SS - sw // 2, 588 * SS, sub, 3, (74, 74, 78))
    model = "MODEL BS-3000"
    mw = text_width(model, 2)
    draw_text(452 * SS - mw // 2, 614 * SS, model, 2, (96, 96, 100))

    # ---- control dial (right of the plate)
    fill_ellipse(648 * SS, 552 * SS, 36 * SS, 36 * SS, (228, 228, 228))
    fill_ellipse(648 * SS, 552 * SS, 30 * SS, 30 * SS, (58, 58, 62))
    for k in range(9):
        ang = math.radians(-210 + k * 30)
        r0, r1 = 22, 27
        draw_line((648 + r0 * math.cos(ang)) * SS,
                  (552 + r0 * math.sin(ang)) * SS,
                  (648 + r1 * math.cos(ang)) * SS,
                  (552 + r1 * math.sin(ang)) * SS,
                  (235, 235, 235), width=2 * SS)
    pang = math.radians(-40)
    draw_line(648 * SS, 552 * SS,
              (648 + 24 * math.cos(pang)) * SS,
              (552 + 24 * math.sin(pang)) * SS,
              (255, 255, 255), width=3 * SS)
    fill_ellipse(648 * SS, 552 * SS, 4 * SS, 4 * SS, (235, 235, 235))

    # ---- ready LED (left of the dial)
    fill_ellipse(586 * SS, 552 * SS, 9 * SS, 9 * SS, (57, 211, 83))
    fill_ellipse(586 * SS, 552 * SS, 4 * SS, 4 * SS, (182, 255, 191))


def downsample_and_vignette():
    """Average each 2x2 block to 1024x1024 and apply a mild vignette."""
    fx2 = [((x - (W - 1) / 2.0) / ((W - 1) / 2.0)) ** 2 for x in range(W)]
    fy2 = [((y - (H - 1) / 2.0) / ((H - 1) / 2.0)) ** 2 for y in range(H)]
    out = []
    for y in range(H):
        r0 = rows[2 * y]
        r1 = rows[2 * y + 1]
        fy = fy2[y]
        line = bytearray(W * 3)
        for x in range(W):
            i = x * 6
            r = (r0[i] + r0[i + 3] + r1[i] + r1[i + 3]) // 4
            g = (r0[i + 1] + r0[i + 4] + r1[i + 1] + r1[i + 4]) // 4
            b = (r0[i + 2] + r0[i + 5] + r1[i + 2] + r1[i + 5]) // 4
            f = 1.0 - 0.055 * (fx2[x] + fy)
            o = x * 3
            line[o] = int(r * f)
            line[o + 1] = int(g * f)
            line[o + 2] = int(b * f)
        out.append(bytes(line))
    return out


def write_png(path, w, h, scanlines):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + line for line in scanlines)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def main():
    render()
    scanlines = downsample_and_vignette()
    os.makedirs(OUT_DIR, exist_ok=True)
    size = write_png(OUT_PATH, W, H, scanlines)
    print(f"wrote {OUT_PATH} ({W}x{H}, {size} bytes)")


if __name__ == "__main__":
    main()
