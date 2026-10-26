"""
visuals.py — frame generator for the video pipeline.

Produces 1920x1080 (or any size) PNG frames with correct Devanagari typography:
gradient backgrounds, title/section cards, quote cards, stat cards, bullet
cards, lower-thirds and image-backed scenes. No browser or Remotion needed,
so rendering stays fast on 2 vCPU.

All colours/typography come from presets/brand.json so the channel look stays
consistent across videos.
"""

from __future__ import annotations

import json
import math
import os
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from hinditext import HindiText, _rgba

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRAND_PATH = os.path.join(ROOT, "presets", "brand.json")

DEFAULT_BRAND = {
    "palette": {
        "bg_dark": "#0B0F1A",
        "bg_mid": "#141C2E",
        "accent": "#FFB020",
        "accent2": "#2ED3B7",
        "text": "#FFFFFF",
        "text_muted": "#C7D0E0",
        "danger": "#FF5A5F",
    },
    "fonts": {"display": "display", "heading": "deva-bold", "body": "deva-regular",
              "latin": "latin-bold"},
    "safe_margin": 120,
    "watermark": "Ronny Raj",
}


@lru_cache(maxsize=1)
def brand() -> dict:
    data = dict(DEFAULT_BRAND)
    if os.path.exists(BRAND_PATH):
        with open(BRAND_PATH, encoding="utf-8") as fh:
            loaded = json.load(fh)
        data["palette"] = {**DEFAULT_BRAND["palette"], **loaded.get("palette", {})}
        data["fonts"] = {**DEFAULT_BRAND["fonts"], **loaded.get("fonts", {})}
        for k in ("safe_margin", "watermark", "handle"):
            if k in loaded:
                data[k] = loaded[k]
    return data


# ---------------------------------------------------------------- backgrounds
def gradient(size: tuple[int, int], top: str, bottom: str, angle: float = 90.0) -> Image.Image:
    """Linear gradient at any angle, computed with numpy (fast, smooth)."""
    w, h = size
    c1 = np.array(_rgba(top)[:3], dtype=np.float32)
    c2 = np.array(_rgba(bottom)[:3], dtype=np.float32)
    xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    rad = math.radians(angle)
    t = np.clip(xs * math.cos(rad) + ys * math.sin(rad), 0, 1)
    # normalise so the gradient always spans the full 0..1 range
    t = (t - t.min()) / max(float(np.ptp(t)), 1e-6)
    arr = c1[None, None, :] + (c2 - c1)[None, None, :] * t[:, :, None]
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


def add_glow(img: Image.Image, center: tuple[float, float], radius: float,
             colour: str, strength: float = 0.55) -> Image.Image:
    """Radial accent glow — cheap 'cinematic lighting' look."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - center[0] * w) ** 2 + (yy - center[1] * h) ** 2) / max(radius * w, 1)
    mask = np.clip(1.0 - d, 0, 1) ** 2 * strength
    glow = Image.new("RGBA", (w, h), _rgba(colour))
    glow.putalpha(Image.fromarray((mask * 255).astype(np.uint8), "L"))
    return Image.alpha_composite(img, glow)


def add_vignette(img: Image.Image, strength: float = 0.35) -> Image.Image:
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    mask = np.clip((d - 0.55) / 1.1, 0, 1) ** 1.5 * strength * 255
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    dark.putalpha(Image.fromarray(mask.astype(np.uint8), "L"))
    return Image.alpha_composite(img, dark)


def add_grain(img: Image.Image, amount: float = 5.0, seed: int = 7) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = np.array(img.convert("RGB"), dtype=np.int16)
    noise = rng.normal(0, amount, arr.shape[:2])[:, :, None]
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def backdrop(size: tuple[int, int], accent_side: str = "right") -> Image.Image:
    """Channel default background: deep gradient + accent glow + vignette + grain."""
    b = brand()
    p = b["palette"]
    img = gradient(size, p["bg_mid"], p["bg_dark"], angle=115)
    cx = 0.82 if accent_side == "right" else 0.18
    img = add_glow(img, (cx, 0.22), 0.42, p["accent"], 0.30)
    img = add_glow(img, (1 - cx, 0.85), 0.5, p["accent2"], 0.22)
    img = add_vignette(img, 0.45)
    return add_grain(img, 3.0)


def fit_cover(src: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    sw, sh = src.size
    scale = max(w / sw, h / sh)
    im = src.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.LANCZOS)
    left = (im.width - w) // 2
    top = (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


# ---------------------------------------------------------------- helpers
def _pill(img: Image.Image, xy: tuple[int, int], text: str, font: str, size: int,
          fg: str, bg: str, pad: tuple[int, int] = (28, 14), radius: int | None = None,
          alpha: int = 235) -> Image.Image:
    t = HindiText(font, size)
    label = t.render(text, color=fg, pad=2)
    w, h = label.width + pad[0] * 2, label.height + pad[1] * 2
    r = radius if radius is not None else h // 2
    bg_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(bg_layer)
    x, y = xy
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=_rgba(bg)[:3] + (alpha,))
    img.alpha_composite(bg_layer)
    img.alpha_composite(label, (x + pad[0], y + pad[1]))
    return img


def _accent_bar(img: Image.Image, xy: tuple[int, int], w: int, h: int = 8, colour: str | None = None,
                radius: int | None = None) -> Image.Image:
    p = brand()["palette"]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius if radius is not None else h // 2,
                        fill=_rgba(colour or p["accent"]))
    return Image.alpha_composite(img, layer)


def _watermark(img: Image.Image) -> Image.Image:
    b = brand()
    mark = b.get("watermark")
    if not mark:
        return img
    t = HindiText("latin-semibold", 30)
    label = t.render(mark, color="#FFFFFF")
    layer = Image.new("RGBA", (label.width, label.height), (255, 255, 255, 0))
    layer.putalpha(label.getchannel("A").point(lambda a: int(a * 0.32)))
    label.putalpha(label.getchannel("A").point(lambda a: int(a * 0.32)))
    img.alpha_composite(label, (img.width - label.width - 56, img.height - label.height - 44))
    return img


# ---------------------------------------------------------------- card types
def title_card(title: str, subtitle: str | None = None, badge: str | None = None,
               size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    b = brand()
    p, f = b["palette"], b["fonts"]
    img = backdrop(size)
    m = b["safe_margin"]
    y = int(size[1] * 0.30)
    if badge:
        img = _pill(img, (m, y - 92), badge, f["heading"], 34, "#0B0F1A", p["accent"])
    img = HindiText(f["display"], 108).draw_on(
        img, title, (m, y), anchor="lt", max_width=size[0] - m * 2,
        align="left", color=p["text"], stroke=3, stroke_color="#05070C", line_spacing=1.06)
    img = _accent_bar(img, (m + 4, y + 190), 150, 10)
    if subtitle:
        HindiText(f["body"], 46).draw_on(
            img, subtitle, (m + 4, y + 232), anchor="lt", max_width=int(size[0] * 0.74),
            align="left", color=p["text_muted"])
    return _watermark(img)


def section_card(number: int | str, heading: str, kicker: str | None = None,
                 size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    b = brand()
    p, f = b["palette"], b["fonts"]
    img = backdrop(size, accent_side="left")
    m = b["safe_margin"]
    HindiText("latin-bold", 210).draw_on(
        img, str(number), (m, int(size[1] * 0.24)), anchor="lt", color=p["accent"],
        stroke=0)
    y = int(size[1] * 0.52)
    if kicker:
        HindiText(f["heading"], 32).draw_on(img, kicker.upper(), (m + 6, y - 58), anchor="lt",
                                            color=p["accent2"])
    img = HindiText(f["display"], 84).draw_on(
        img, heading, (m + 6, y), anchor="lt", max_width=size[0] - m * 2 - 60,
        align="left", color=p["text"], stroke=2, stroke_color="#05070C", line_spacing=1.08)
    return _watermark(img)


def bullet_card(heading: str, items: list[str], size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    b = brand()
    p, f = b["palette"], b["fonts"]
    img = backdrop(size)
    m = b["safe_margin"]
    img = HindiText(f["display"], 68).draw_on(img, heading, (m, int(size[1] * 0.16)), anchor="lt",
                                              max_width=size[0] - m * 2, color=p["text"],
                                              stroke=2, stroke_color="#05070C")
    img = _accent_bar(img, (m + 2, int(size[1] * 0.16) + 118), 110, 8)
    y = int(size[1] * 0.16) + 190
    body = HindiText(f["body"], 50)
    for item in items:
        r = 13
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([m + 8, y + 26, m + 8 + r * 2, y + 26 + r * 2], fill=_rgba(p["accent"]))
        img = Image.alpha_composite(img, layer)
        txt = body.render(item, max_width=size[0] - m * 2 - 80, color=p["text"])
        img.alpha_composite(txt, (m + 66, y))
        y += max(txt.height, 60) + 34
        if y > size[1] - 220:
            break
    return _watermark(img)


def stat_card(value: str, label: str, source: str | None = None,
              size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    b = brand()
    p, f = b["palette"], b["fonts"]
    img = backdrop(size)
    img = add_glow(img, (0.5, 0.5), 0.55, p["accent2"], 0.18)
    val = HindiText(f["display"], 190).render(value, color=p["accent"], stroke=4,
                                              stroke_color="#05070C")
    img.alpha_composite(val, ((size[0] - val.width) // 2, int(size[1] * 0.30)))
    lab = HindiText(f["heading"], 56).render(label, max_width=size[0] - 400, align="center",
                                             color=p["text"])
    img.alpha_composite(lab, ((size[0] - lab.width) // 2, int(size[1] * 0.53)))
    if source:
        src = HindiText(f["body"], 28).render(f"स्रोत: {source}", color=p["text_muted"])
        img.alpha_composite(src, ((size[0] - src.width) // 2, size[1] - 130))
    return _watermark(img)


def quote_card(quote: str, author: str | None = None,
               size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    b = brand()
    p, f = b["palette"], b["fonts"]
    img = backdrop(size)
    img = add_glow(img, (0.5, 0.42), 0.5, p["accent"], 0.16)
    mark = HindiText("latin-bold", 200).render("“", color=p["accent"])
    img.alpha_composite(mark, (b["safe_margin"], int(size[1] * 0.13)))
    body = HindiText(f["display"], 76).render(quote, max_width=size[0] - 420, align="center",
                                              color=p["text"], line_spacing=1.14)
    img.alpha_composite(body, ((size[0] - body.width) // 2, int(size[1] * 0.30)))
    if author:
        a = HindiText(f["body"], 38).render("— " + author, color=p["accent2"])
        img.alpha_composite(a, ((size[0] - a.width) // 2, int(size[1] * 0.30) + body.height + 48))
    return _watermark(img)


def image_scene(image_path: str, headline: str | None = None, sub: str | None = None,
                side: str = "left", size: tuple[int, int] = (1920, 1080),
                scrim: float = 0.72) -> Image.Image:
    """Photo/B-roll still with a readable scrim + optional headline."""
    b = brand()
    p, f = b["palette"], b["fonts"]
    src = Image.open(image_path).convert("RGB")
    img = fit_cover(src, size).convert("RGBA")
    # directional scrim for text legibility
    w, h = size
    grad = gradient(size, "#000000", "#000000", angle=0 if side == "left" else 180)
    alpha = np.linspace(scrim * 255, 0, w, dtype=np.float32)
    a_arr = np.tile(alpha, (h, 1))
    if side != "left":
        a_arr = np.fliplr(a_arr)
    grad.putalpha(Image.fromarray(a_arr.astype(np.uint8), "L"))
    img = Image.alpha_composite(img, grad)
    img = add_vignette(img, 0.25)
    m = b["safe_margin"]
    x = m if side == "left" else w - m
    anchor = "lt" if side == "left" else "rt"
    if headline:
        img = HindiText(f["display"], 82).draw_on(
            img, headline, (x, int(h * 0.42)), anchor=anchor,
            max_width=int(w * 0.5), align="left" if side == "left" else "right",
            color=p["text"], stroke=3, stroke_color="#05070C")
    if sub:
        HindiText(f["body"], 42).draw_on(
            img, sub, (x, int(h * 0.62)), anchor=anchor, max_width=int(w * 0.46),
            align="left" if side == "left" else "right", color=p["text_muted"])
    return _watermark(img)


def split_card(heading: str, image_path: str | None = None, points: list[str] | None = None,
               image_side: str = "right", size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """Half image / half text card — useful for explainer scenes."""
    b = brand()
    p, f = b["palette"], b["fonts"]
    w, h = size
    img = backdrop(size, accent_side="left" if image_side == "right" else "right")
    if image_path and os.path.exists(image_path):
        half = (w // 2, h)
        ph = fit_cover(Image.open(image_path).convert("RGB"), half).convert("RGBA")
        x = w // 2 if image_side == "right" else 0
        img.alpha_composite(ph, (x, 0))
        fade = gradient((120, h), "#000000", "#000000", angle=0)
        a = np.linspace(255, 0, 120, dtype=np.float32) if image_side == "right" else np.linspace(0, 255, 120, dtype=np.float32)
        fade.putalpha(Image.fromarray(np.tile(a, (h, 1)).astype(np.uint8), "L"))
        img.alpha_composite(fade, (w // 2 - 120 if image_side == "right" else w // 2, 0))
    m = b["safe_margin"]
    text_w = w // 2 - m - 60
    img = HindiText(f["display"], 66).draw_on(img, heading, (m, int(h * 0.24)), anchor="lt",
                                              max_width=text_w, color=p["text"],
                                              stroke=2, stroke_color="#05070C")
    if points:
        y = int(h * 0.24) + 150
        body = HindiText(f["body"], 40)
        for pt in points[:4]:
            t = body.render("• " + pt, max_width=text_w, color=p["text_muted"])
            img.alpha_composite(t, (m, y))
            y += t.height + 26
    return _watermark(img)


def lower_third(name: str, role: str | None = None, size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """Transparent overlay PNG for names/citations."""
    b = brand()
    p, f = b["palette"], b["fonts"]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    name_img = HindiText(f["heading"], 52).render(name, color=p["text"])
    w = name_img.width + 90
    h = name_img.height + (70 if role else 40)
    x, y = b["safe_margin"], size[1] - h - 150
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([x, y, x + w, y + h], radius=18,
                                            fill=(10, 14, 24, 210))
    img = Image.alpha_composite(img, panel)
    img = _accent_bar(img, (x, y), 8, h, colour=b["palette"]["accent"], radius=4)
    img.alpha_composite(name_img, (x + 40, y + 20))
    if role:
        r = HindiText(f["body"], 30).render(role, color=p["text_muted"])
        img.alpha_composite(r, (x + 40, y + 22 + name_img.height))
    return img


def progress_bar(progress: float, size: tuple[int, int] = (1920, 1080), height: int = 8) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, size[1] - height, size[0], size[1]], fill=(255, 255, 255, 40))
    d.rectangle([0, size[1] - height, int(size[0] * max(0.0, min(1.0, progress))), size[1]],
                fill=_rgba(brand()["palette"]["accent"]))
    return img


SCENES = {
    "title": title_card,
    "section": section_card,
    "bullets": bullet_card,
    "stat": stat_card,
    "quote": quote_card,
    "image": image_scene,
    "split": split_card,
}


def render_scene(spec: dict, dst: str, size: tuple[int, int] = (1920, 1080)) -> str:
    """Dispatch a scene spec (from project timeline JSON) to a PNG frame."""
    kind = spec.get("type", "title")
    fn = SCENES.get(kind)
    if fn is None:
        raise ValueError(f"unknown scene type {kind!r}; choose from {sorted(SCENES)}")
    kw = {k: v for k, v in spec.items() if k not in ("type",)}
    img = fn(size=size, **kw) if "size" not in kw else fn(**kw)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    img.convert("RGB").save(dst, quality=95)
    return dst
