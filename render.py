#!/usr/bin/env python3
"""
Renders an 800x480 1-bit PNG for the office-door ePaper sign.

Usage:  python3 render.py schedule.json out.png [--date YYYY-MM-DD]
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 800, 480
BLACK, WHITE = 0, 255

# Look in a few places so this runs the same on a GitHub runner, a Mac, or here.
FONT_DIRS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/Library/Fonts",
    "/usr/local/share/fonts",
]


def font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise SystemExit(
        f"Could not find the font {name}. Looked in: {', '.join(FONT_DIRS)}"
    )


FONT_NAME = lambda s: font("DejaVuSans-Bold.ttf", s)
FONT_REG = lambda s: font("DejaVuSans.ttf", s)
FONT_COND = lambda s: font("DejaVuSansCondensed-Bold.ttf", s)
FONT_CONDR = lambda s: font("DejaVuSansCondensed.ttf", s)

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABEL = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

LABELS = {"office": "IN OFFICE", "remote": "REMOTE", "leave": "OUT"}

# Two visual languages. "bold" shouts from down the hall; "light" is calmer
# and keeps solid black reserved for today's column.
STYLES = {
    "bold": {"office": "solid", "remote": "none", "leave": "hatch"},
    "light": {"office": "bar", "remote": "none", "leave": "hatch"},
}


def text_w(draw, s, f):
    return draw.textbbox((0, 0), s, font=f)[2]


def centered(draw, box, s, f, color=BLACK):
    x0, y0, x1, y1 = box
    bb = draw.textbbox((0, 0), s, font=f)
    draw.text(
        (x0 + (x1 - x0 - bb[2]) / 2 - bb[0], y0 + (y1 - y0 - bb[3]) / 2 - bb[1]),
        s,
        font=f,
        fill=color,
    )


def fit_font(draw, s, maker, max_w, start, floor=11):
    """Shrink a font until the string fits the given width."""
    size = start
    while size > floor:
        f = maker(size)
        if text_w(draw, s, f) <= max_w:
            return f
        size -= 1
    return maker(floor)


def hatch(img, box, spacing=8):
    """Diagonal hatch for the OUT state. Drawn into a tile and pasted so it
    cannot bleed into the neighbouring column."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    tile = Image.new("1", (w, h), 1)
    td = ImageDraw.Draw(tile)
    for i in range(-h, w, spacing):
        td.line([(i, h), (i + h, 0)], fill=BLACK, width=1)
    img.paste(tile, (x0, y0), ImageOps.invert(tile.convert("L")).convert("1"))


def wrap(draw, s, f, max_w):
    words, lines, cur = s.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if text_w(draw, trial, f) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def resolve(cfg, d):
    """Status for one date: default week, then any override on top."""
    dk = DAY_KEYS[d.weekday()]
    base = cfg.get("default_week", {}).get(dk, {})
    cell = {
        "am": base.get("am", "office"),
        "pm": base.get("pm", "office"),
        "note_am": "",
        "note_pm": "",
    }
    ov = cfg.get("overrides", {}).get(d.isoformat())
    if ov:
        for k in ("am", "pm", "note_am", "note_pm"):
            if k in ov:
                cell[k] = ov[k]
    return cell


def plate(draw, cx, cy, w, h):
    """White knock-out behind text so it stays legible over a hatch."""
    draw.rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], fill=WHITE)


def draw_status_cell(img, draw, box, status, note, style):
    x0, y0, x1, y1 = box
    fill = STYLES[style].get(status, "none")
    label = LABELS.get(status, status.upper())
    inset = x0

    if fill == "solid":
        draw.rectangle(box, fill=BLACK)
        fg = WHITE
    else:
        draw.rectangle(box, fill=WHITE, outline=BLACK, width=2)
        fg = BLACK
        if fill == "hatch":
            hatch(img, (x0 + 3, y0 + 3, x1 - 3, y1 - 3))
        elif fill == "bar":
            draw.rectangle([x0 + 2, y0 + 2, x0 + 13, y1 - 2], fill=BLACK)
            inset = x0 + 13

    inner_w = (x1 - inset) - 14
    lf = fit_font(draw, label, FONT_COND, inner_w, 27, 12)
    tbox = (inset, y0, x1, y1 - (22 if note else 0))

    if fill == "hatch":
        bb = draw.textbbox((0, 0), label, font=lf)
        plate(
            draw,
            (inset + x1) / 2,
            (tbox[1] + tbox[3]) / 2,
            bb[2] + 16,
            bb[3] + 10,
        )
    centered(draw, tbox, label, lf, fg)

    if note:
        nf = fit_font(draw, note, FONT_CONDR, inner_w, 16, 10)
        if fill == "hatch":
            bb = draw.textbbox((0, 0), note, font=nf)
            plate(draw, (inset + x1) / 2, y1 - 17, bb[2] + 10, bb[3] + 8)
        centered(draw, (inset, y1 - 30, x1, y1 - 5), note, nf, fg)


def validate(cfg):
    """Catch the mistakes that are easy to make by hand, and say plainly what
    is wrong rather than failing with a stack trace."""
    ok = set(LABELS)
    out = []
    for day, halves in (cfg.get("default_week") or {}).items():
        if day not in DAY_KEYS:
            out.append(f"default_week has '{day}', which is not a day. Use: {', '.join(DAY_KEYS[:5])}.")
        for half in ("am", "pm"):
            v = (halves or {}).get(half)
            if v is not None and v not in ok:
                out.append(f"default_week.{day}.{half} is '{v}'. Use one of: {', '.join(sorted(ok))}.")
    for iso, ov in (cfg.get("overrides") or {}).items():
        try:
            datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            out.append(f"override date '{iso}' should look like 2026-09-17.")
        for half in ("am", "pm"):
            v = (ov or {}).get(half)
            if v is not None and v not in ok:
                out.append(f"overrides['{iso}'].{half} is '{v}'. Use one of: {', '.join(sorted(ok))}.")
    return out


def local_now(cfg):
    """The build runs on a server in UTC. Without this, the sign flips to
    'tomorrow' in the late afternoon Pacific time."""
    try:
        return datetime.now(ZoneInfo(cfg.get("timezone", "America/Los_Angeles")))
    except Exception:
        return datetime.now()


def render(cfg, today=None, style=None):
    now = local_now(cfg)
    today = today or now.date()
    style = style or cfg.get("style", "bold")
    if style not in STYLES:
        style = "light"
    img = Image.new("1", (W, H), 1)
    d = ImageDraw.Draw(img)

    days = [5, 7][bool(cfg.get("show_weekend"))]
    monday = today - timedelta(days=today.weekday())
    # On a weekend, a Mon-Fri sign should already be showing the week ahead
    # rather than the one that just ended.
    if days == 5 and today.weekday() >= 5:
        monday += timedelta(days=7)
    dates = [monday + timedelta(days=i) for i in range(days)]

    # ---- header -------------------------------------------------------
    HDR = 62
    d.text((16, 10), cfg.get("name", ""), font=FONT_NAME(32), fill=BLACK)
    sub = cfg.get("subtitle", "")
    if sub:
        nw = text_w(d, cfg.get("name", ""), FONT_NAME(32))
        d.text((16 + nw + 14, 22), sub, font=FONT_REG(19), fill=BLACK)

    if dates[0].month == dates[-1].month:
        rng = f"{dates[0]:%B %-d} – {dates[-1]:%-d, %Y}"
    else:
        rng = f"{dates[0]:%b %-d} – {dates[-1]:%b %-d, %Y}"
    rf = FONT_REG(20)
    d.text((W - 16 - text_w(d, rng, rf), 26), rng, font=rf, fill=BLACK)
    d.rectangle([0, HDR, W, HDR + 3], fill=BLACK)

    # ---- notice bar ---------------------------------------------------
    notice = (cfg.get("notice") or "").strip()
    bottom = H
    if notice:
        # Shrink the notice until it fits in at most three lines, so a long
        # message degrades gracefully instead of being silently cut off.
        for size in (22, 20, 18, 16, 14):
            nf = FONT_REG(size)
            lines = wrap(d, notice, nf, W - 40)
            if len(lines) <= 3:
                break
        lines = lines[:3]
        bar_h = 30 + (size + 6) * len(lines)
        bottom = H - bar_h
        d.rectangle([0, bottom, W, H], fill=BLACK)
        y = bottom + 13
        for ln in lines:
            bb = d.textbbox((0, 0), ln, font=nf)
            d.text(((W - bb[2]) / 2, y), ln, font=nf, fill=WHITE)
            y += size + 6
    else:
        bottom = H - 26

    # ---- footer stamp -------------------------------------------------
    if not notice:
        sf = FONT_REG(13)
        stamp = f"updated {now:%a %-d %b, %-I:%M %p}"
        d.text((W - 16 - text_w(d, stamp, sf), H - 22), stamp, font=sf, fill=BLACK)

    # ---- grid ---------------------------------------------------------
    M = 12
    top = HDR + 16
    grid_h = bottom - top - 12
    col_w = (W - 2 * M) / days
    DAYHDR = 40
    gap = 7
    cell_h = (grid_h - DAYHDR - gap) / 2

    for i, dt in enumerate(dates):
        x0 = M + i * col_w
        x1 = x0 + col_w - 6
        is_today = dt == today

        # day header
        hb = (x0, top, x1, top + DAYHDR)
        if is_today:
            d.rectangle(hb, fill=BLACK)
            lab = f"{DAY_LABEL[dt.weekday()]}  {dt.day}"
            centered(d, hb, lab, FONT_COND(24), WHITE)
        else:
            lab = f"{DAY_LABEL[dt.weekday()]}  {dt.day}"
            centered(d, hb, lab, FONT_COND(24), BLACK)
            d.rectangle([x0, top + DAYHDR - 2, x1, top + DAYHDR], fill=BLACK)

        cell = resolve(cfg, dt)
        y = top + DAYHDR + gap
        for half in ("am", "pm"):
            box = (x0, y, x1, y + cell_h)
            draw_status_cell(
                img, d, box, cell[half], cell.get(f"note_{half}", ""), style
            )
            # AM / PM tag, bottom-left, on its own white plate
            tf = FONT_COND(13)
            tag = half.upper()
            tw = text_w(d, tag, tf)
            tb = [x1 - tw - 14, y + 4, x1 - 4, y + 22]
            d.rectangle(tb, fill=WHITE, outline=BLACK, width=1)
            d.text((tb[0] + 5, tb[1] + 1), tag, font=tf, fill=BLACK)
            y += cell_h + gap

        if is_today:
            d.rectangle(
                [x0 - 3, top - 4, x1 + 3, top + grid_h + 2], outline=BLACK, width=3
            )

    return img


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "schedule.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "out.png"
    when = None
    if "--date" in sys.argv:
        when = datetime.strptime(sys.argv[sys.argv.index("--date") + 1], "%Y-%m-%d").date()
    style = None
    if "--style" in sys.argv:
        style = sys.argv[sys.argv.index("--style") + 1]
    try:
        with open(cfg_path) as fh:
            cfg = json.load(fh)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"schedule.json is not valid JSON: {e.msg} on line {e.lineno}.\n"
            "Usually this is a missing comma, a trailing comma before a } or ],\n"
            "or a quote that never got closed. The sign keeps showing the last\n"
            "good image until this is fixed."
        )

    problems = validate(cfg)
    if problems:
        raise SystemExit("schedule.json has a problem:\n  " + "\n  ".join(problems))

    render(cfg, when, style).save(out)
    print("wrote", out)
