"""
thumbnail.py — YouTube thumbnails with correct Hindi typography.

Design rules baked in (mobile-first, 1280x720, safe margins, max ~4 words):
  * one dominant statement, huge type, thick outline for contrast at 200px wide
  * strong left-text / right-subject split, or full-bleed statement
  * accent bar + channel mark for recognisability
  * optional photo subject with an automatic scrim so text always wins

    python thumbnail.py --spec spec.json --out ../thumbnails/t1.png
    python thumbnail.py --demo --out ../thumbnails/demo
"""

from __future__ import annotations

import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFilter

from hinditext import HindiText, _rgba
from visuals import (add_glow, add_grain, add_vignette, backdrop, brand, fit_cover,
                     gradient)

THUMB_SIZE = (1280, 720)


def _shadowed_text(img: Image.Image, text: str, font: str, size: int,
                   xy: tuple[int, int], anchor: str = "lt", max_width: int | None = None,
                   colour: str = "#FFFFFF", stroke: int = 10,
                   shadow=(0, 10, 18)) -> Image.Image:
    t = HindiText(font, size)
    return t.draw_on(img, text, xy, anchor=anchor, max_width=max_width, colour=colour,
                     stroke=stroke, stroke_color="#0A0A0A", shadow=shadow,
                     line_spacing=1.04) if False else _draw(t, img, text, xy, anchor,
                                                            max_width, colour, stroke, shadow)


def _draw(t: HindiText, img, text, xy, anchor, max_width, colour, stroke, shadow):
    return t.draw_on(img, text, xy, anchor=anchor, max_width=max_width, color=colour,
                     stroke=stroke, stroke_color="#0A0A0A", shadow=shadow, line_spacing=1.04)


def _photo(img: Image.Image, path: str, side: str = "right", scale: float = 1.0,
           feather: int = 90) -> Image.Image:
    """Place a subject photo on one half with a soft feathered edge and colour grade."""
    w, h = img.size
    ph = Image.open(path).convert("RGB")
    pw = int(w * 0.52 * scale)
    ph = fit_cover(ph, (pw, h)).convert("RGBA")
    # desaturate/grade slightly so text and subject stay balanced
    ph = Image.blend(ph, ph.convert("L").convert("RGBA"), 0.12)
    # feather the inner edge
    mask = Image.new("L", (pw, h), 255)
    grad = Image.new("L", (feather, h))
    ramp = [int(255 * (i / feather) ** 0.8) for i in range(feather)]
    grad.putdata([v for y in range(h) for v in ramp])
    if side == "right":
        mask.paste(grad, (0, 0))
        x = w - pw
    else:
        mask.paste(grad.rotate(180), (pw - feather, 0))
        x = 0
    ph.putalpha(mask)
    return Image.alpha_composite(img, ph) if False else _paste(img, ph, x)


def _paste(img, layer, x):
    img.alpha_composite(layer, (x, 0))
    return img


def build(
    headline: str,
    kicker: str | None = None,
    badge: str | None = None,
    sub: str | None = None,
    photo: str | None = None,
    layout: str = "split",
    accent: str | None = None,
    size: tuple[int, int] = THUMB_SIZE,
    seed: int = 3,
) -> Image.Image:
    b = brand()
    p = b["palette"]
    accent = accent or p["accent"]
    w, h = size
    if layout == "statement" or not photo:
        img = backdrop(size)
    else:
        img = gradient(size, p["bg_mid"], p["bg_dark"], angle=110)
        img = add_glow(img, (0.78 if photo else 0.5, 0.3), 0.5, accent, 0.35)

    if photo and layout in ("split", "subject"):
        img = _photo(img, photo, side="right")
        text_w = int(w * 0.58)
        tx = 64
    else:
        text_w = int(w * 0.86)
        tx = 64

    # left accent bar
    bar = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle([40, 92, 54, h - 120], radius=7, fill=_rgba(accent))
    img = Image.alpha_composite(img, bar)

    y = 96
    if kicker:
        t = HindiText("deva-bold", 40)
        k = t.render(kicker, color=accent, stroke=5, stroke_color="#0A0A0A")
        img.alpha_composite(k, (tx + 12, y))
        y += k.height + 18

    # headline: shrink to fit the box, never more than 3 lines
    size_px = 132
    while size_px > 62:
        t = HindiText("display", size_px)
        lines = t.wrap(headline, max_width=text_w)
        if len(lines) <= 3:
            break
        size_px -= 8
    t = HindiText("display", size_px)
    img = _draw(t, img, headline, (tx + 10, y), "lt", text_w, "#FFFFFF", max(8, size_px // 12),
                (0, 12, 20))

    if sub:
        st = HindiText("deva-bold", 40)
        sy = min(h - 150, y + int(len(t.wrap(headline, text_w)) * t.line_height * 1.04) + 26)
        img = _draw(st, img, sub, (tx + 12, sy), "lt", text_w, p["text_muted"], 5, (0, 8, 12))

    if badge:
        bt = HindiText("display", 44)
        lab = bt.render(badge, color="#0B0F1A", pad=6)
        pad_x, pad_y = 26, 14
        bw, bh = lab.width + pad_x * 2, lab.height + pad_y * 2
        chip = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(chip).rounded_rectangle([w - bw - 54, 46, w - 54, 46 + bh],
                                               radius=bh // 2, fill=_rgba(accent))
        img = Image.alpha_composite(img, chip)
        img.alpha_composite(lab, (w - bw - 54 + pad_x, 46 + pad_y))

    img = add_vignette(img, 0.28)
    img = add_grain(img, 2.5, seed=seed)
    return img.convert("RGB")


def contact_sheet(path: str, dst: str, mobile_width: int = 168) -> str:
    """Preview at YouTube mobile size to prove the text is readable."""
    src = Image.open(path).convert("RGB")
    w = mobile_width
    h = int(w * src.height / src.width)
    sheet = Image.new("RGB", (w + 24, h + 24), (245, 245, 245))
    sheet.paste(src.resize((w, h), Image.LANCZOS), (12, 12))
    sheet.save(dst)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", help="JSON file with thumbnail fields")
    ap.add_argument("--out", required=True)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        os.makedirs(args.out, exist_ok=True)
        samples = [
            dict(headline="2 मिनट का नियम", kicker="PRODUCTIVITY", badge="हिन्दी",
                 sub="टालमटोल खत्म करने का सबसे आसान तरीका", layout="statement"),
            dict(headline="रोज़ 10 पेज पढ़ो", kicker="BOOK SUMMARY", badge="नई वीडियो",
                 sub="1 साल में 12 किताबें", layout="statement"),
            dict(headline="सुबह 5 बजे क्यों?", kicker="DISCIPLINE", badge="हिन्दी",
                 layout="statement"),
        ]
        for i, s in enumerate(samples, 1):
            img = build(**s)
            path = os.path.join(args.out, f"demo_{i}.png")
            img.save(path, quality=95)
            contact_sheet(path, os.path.join(args.out, f"demo_{i}_mobile.png"))
            print(path)
        return

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec.pop("note", None)
    img = build(**spec)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.save(args.out, quality=95)
    print(args.out)


if __name__ == "__main__":
    main()
