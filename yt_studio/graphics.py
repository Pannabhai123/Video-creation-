from __future__ import annotations

import base64
import json
import math
import shutil
import subprocess
import textwrap
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import get_font_path
from .models import SceneSpec


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = _hex_to_rgb(hex_color)
    return r, g, b, alpha


def _ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def _load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(get_font_path(weight)), max(10, int(size)))


def _make_studio_backdrop(
    width: int,
    height: int,
    accent_hex: str = "#38BDF8",
    secondary_hex: str = "#818CF8",
) -> Image.Image:
    """
    Creates a rich dark-slate studio background with radial color-graded light pools
    and an architectural grid.
    """
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]

    # Base deep slate gradient (#070C18 -> #0F172A)
    base = np.zeros((height, width, 3), dtype=np.float32)
    base[..., 0] = 7 + 10 * (1.0 - y)
    base[..., 1] = 12 + 16 * (1.0 - y)
    base[..., 2] = 24 + 28 * (1.0 - y * 0.6)

    ar, ag, ab = _hex_to_rgb(accent_hex)
    sr, sg, sb = _hex_to_rgb(secondary_hex)

    dist1 = (x - 0.82) ** 2 + (y - 0.22) ** 2
    glow1 = np.exp(-dist1 / 0.14) * 0.24
    dist2 = (x - 0.15) ** 2 + (y - 0.85) ** 2
    glow2 = np.exp(-dist2 / 0.18) * 0.20

    base[..., 0] += glow1 * ar + glow2 * sr
    base[..., 1] += glow1 * ag + glow2 * sg
    base[..., 2] += glow1 * ab + glow2 * sb

    arr = np.clip(base, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB").convert("RGBA")

    grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid)
    step = max(40, int(round(68 * (height / 1080.0))))
    for gx in range(0, width, step):
        gdraw.line([(gx, 0), (gx, height)], fill=(148, 163, 184, 15), width=1)
    for gy in range(0, height, step):
        gdraw.line([(0, gy), (width, gy)], fill=(148, 163, 184, 15), width=1)

    return Image.alpha_composite(img, grid)


def build_scene_visual_panel(
    scene: SceneSpec,
    panel_w: int,
    panel_h: int,
    secondary_hex: str = "#818CF8",
) -> Image.Image:
    """
    Creates the high-resolution visual showcase panel for a scene (oversized by 12%
    so Ken Burns subpixel zoom/pan never loses sharpness).
    Uses external image asset if supplied; otherwise renders bespoke data/architecture graphics.
    """
    accent_rgb = _hex_to_rgb(scene.accent_color)
    sec_rgb = _hex_to_rgb(secondary_hex)

    # Check if visual_asset is an image file
    if scene.visual_asset:
        ap = Path(scene.visual_asset)
        if ap.exists() and ap.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            src = Image.open(ap).convert("RGB")
            # Ambient blurred background + crisp aspect-preserved foreground
            bg = src.resize((panel_w, panel_h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(24))
            bg_arr = (np.asarray(bg, dtype=np.float32) * 0.45).astype(np.uint8)
            canvas = Image.fromarray(bg_arr, mode="RGB").convert("RGBA")

            scale = min(panel_w / src.width, panel_h / src.height) * 0.92
            fg_w = max(1, int(round(src.width * scale)))
            fg_h = max(1, int(round(src.height * scale)))
            fg = src.resize((fg_w, fg_h), Image.Resampling.LANCZOS).convert("RGBA")
            ox = (panel_w - fg_w) // 2
            oy = (panel_h - fg_h) // 2
            canvas.alpha_composite(fg, (ox, oy))
            return canvas.convert("RGB")

    # Procedural studio infographic / architecture illustration
    canvas = _make_studio_backdrop(panel_w, panel_h, scene.accent_color, secondary_hex)
    draw = ImageDraw.Draw(canvas)
    s = panel_h / 560.0

    style = scene.visual_style
    if style == "diagram":
        # Architecture pipeline flowchart nodes
        nodes = [
            ("INGEST", "Script & Assets", 0.24, 0.27),
            ("PROCESS", "Audio & Captions", 0.76, 0.27),
            ("RENDER", "Motion & Presets", 0.24, 0.73),
            ("MASTER", "1080p / 4K MP4", 0.76, 0.73),
        ]
        centers = [(int(nx * panel_w), int(ny * panel_h)) for _, _, nx, ny in nodes]
        # Connect lines
        for a_i, b_i in ((0, 1), (1, 2), (2, 3), (0, 2)):
            draw.line([centers[a_i], centers[b_i]], fill=(*accent_rgb, 130), width=max(2, int(4 * s)))

        f_tag = _load_font("Bold", int(18 * s))
        f_sub = _load_font("Medium", int(16 * s))
        box_w, box_h = int(230 * s), int(112 * s)
        for (tag, desc, _, _), (cx, cy) in zip(nodes, centers):
            rect = [cx - box_w // 2, cy - box_h // 2, cx + box_w // 2, cy + box_h // 2]
            draw.rounded_rectangle(
                rect,
                radius=int(18 * s),
                fill=(15, 23, 42, 235),
                outline=(*accent_rgb, 220),
                width=max(2, int(3 * s)),
            )
            draw.text((cx - box_w // 2 + int(20 * s), cy - int(28 * s)), tag, font=f_tag, fill=(*accent_rgb, 255))
            draw.text((cx - box_w // 2 + int(20 * s), cy + int(4 * s)), desc, font=f_sub, fill=(226, 232, 240, 255))

    elif style == "metrics":
        # Illuminated bar telemetry + KPI Hero Stat
        bars = [0.42, 0.61, 0.76, 0.89, 1.0]
        base_y = int(panel_h * 0.80)
        max_bh = int(panel_h * 0.42)
        bw = int(panel_w * 0.095)
        gap = int(panel_w * 0.045)
        start_x = (panel_w - (len(bars) * bw + (len(bars) - 1) * gap)) // 2

        for idx, val in enumerate(bars):
            bx0 = start_x + idx * (bw + gap)
            bh = int(max_bh * val)
            by0 = base_y - bh
            col = accent_rgb if idx == len(bars) - 1 else sec_rgb
            draw.rounded_rectangle(
                [bx0, by0, bx0 + bw, base_y],
                radius=int(10 * s),
                fill=(*col, 215),
                outline=(255, 255, 255, 90),
                width=1,
            )

        f_big = _load_font("Black", int(64 * s))
        f_lbl = _load_font("SemiBold", int(22 * s))
        stat_v = scene.stat_value or "100%"
        stat_l = (scene.stat_label or scene.chapter_title).upper()
        bbox_v = draw.textbbox((0, 0), stat_v, font=f_big)
        bbox_l = draw.textbbox((0, 0), stat_l, font=f_lbl)
        draw.text(((panel_w - (bbox_v[2] - bbox_v[0])) // 2, int(panel_h * 0.11)), stat_v, font=f_big, fill=(*accent_rgb, 255))
        draw.text(((panel_w - (bbox_l[2] - bbox_l[0])) // 2, int(panel_h * 0.25)), stat_l, font=f_lbl, fill=(203, 213, 225, 255))

    elif style == "timeline":
        # Horizontal milestone track + waveform
        mid_y = int(panel_h * 0.56)
        margin_x = int(panel_w * 0.12)
        draw.line([(margin_x, mid_y), (panel_w - margin_x, mid_y)], fill=(*accent_rgb, 200), width=max(3, int(5 * s)))
        labels = ["Plan", "Voice", "Edit", "Export"]
        f_node = _load_font("Bold", int(20 * s))
        for i, lbl in enumerate(labels):
            px = margin_x + int((panel_w - 2 * margin_x) * (i / (len(labels) - 1)))
            r = int(20 * s)
            draw.ellipse([px - r, mid_y - r, px + r, mid_y + r], fill=(*accent_rgb, 255), outline=(15, 23, 42, 255), width=int(4 * s))
            bb = draw.textbbox((0, 0), lbl, font=f_node)
            draw.text((px - (bb[2] - bb[0]) // 2, mid_y + int(32 * s)), lbl, font=f_node, fill=(241, 245, 249, 255))

        f_big = _load_font("ExtraBold", int(52 * s))
        stat_t = scene.stat_value or f"STAGE 0{scene.index + 1}"
        bb = draw.textbbox((0, 0), stat_t, font=f_big)
        draw.text(((panel_w - (bb[2] - bb[0])) // 2, int(panel_h * 0.18)), stat_t, font=f_big, fill=(255, 255, 255, 255))

    else:
        # Spotlight concentric rings + stat callout
        cx, cy = panel_w // 2, panel_h // 2
        for ring_i in range(4, 0, -1):
            rad = int(ring_i * 56 * s)
            draw.ellipse(
                [cx - rad, cy - rad, cx + rad, cy + rad],
                outline=(*accent_rgb, 45 + (5 - ring_i) * 35),
                width=max(2, int(3 * s)),
            )
        f_big = _load_font("Black", int(72 * s))
        f_lbl = _load_font("SemiBold", int(22 * s))
        val = scene.stat_value or f"0{scene.index + 1}"
        lbl = (scene.stat_label or scene.chapter_title).upper()
        bv = draw.textbbox((0, 0), val, font=f_big)
        bl = draw.textbbox((0, 0), lbl, font=f_lbl)
        draw.text((cx - (bv[2] - bv[0]) // 2, cy - int(48 * s)), val, font=f_big, fill=(*accent_rgb, 255))
        draw.text((cx - (bl[2] - bl[0]) // 2, cy + int(38 * s)), lbl, font=f_lbl, fill=(226, 232, 240, 255))

    return canvas.convert("RGB")


def generate_youtube_thumbnail(
    title: str,
    badge_text: str,
    channel_name: str,
    out_720p: Path,
    out_1080p: Path,
    accent_hex: str = "#38BDF8",
    secondary_hex: str = "#818CF8",
    hero_image_path: Path | None = None,
) -> tuple[Path, Path]:
    """
    Generates click-worthy high-contrast 16:9 YouTube Thumbnails at both
    1920x1080 and 1280x720 (<2MB YouTube Studio upload specification).
    Uses Remotion + Chromium HarfBuzz automatically when text contains Indic/Devanagari characters.
    """
    out_1080p.parent.mkdir(parents=True, exist_ok=True)
    has_non_ascii = any(ord(ch) > 127 for ch in f"{title}{badge_text}{channel_name}")
    npx_bin = shutil.which("npx")
    repo_root = Path(__file__).resolve().parent.parent

    if has_non_ascii and npx_bin and (repo_root / "remotion_src" / "index.ts").exists():
        hero_data_uri = None
        if hero_image_path and hero_image_path.exists():
            mime = "image/jpeg" if hero_image_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            b64 = base64.b64encode(hero_image_path.read_bytes()).decode("ascii")
            hero_data_uri = f"data:{mime};base64,{b64}"

        props_file = out_1080p.parent / ".thumb_props.json"
        props_file.write_text(
            json.dumps(
                {
                    "title": title,
                    "badgeText": badge_text or "बुक समरी",
                    "channelName": channel_name,
                    "accentColor": accent_hex,
                    "secondaryColor": secondary_hex,
                    "heroImageUrl": hero_data_uri,
                }
            ),
            encoding="utf-8",
        )
        try:
            rc = subprocess.run(
                [
                    npx_bin,
                    "remotion",
                    "still",
                    str(repo_root / "remotion_src" / "index.ts"),
                    "YouTubeThumbnail",
                    str(out_1080p),
                    f"--props={props_file}",
                    "--browser-executable=/usr/local/bin/chromium",
                    "--gl=swangle",
                    "--log=error",
                ],
                cwd=str(repo_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=90,
                check=False,
            ).returncode
            if rc == 0 and out_1080p.exists():
                im_1080 = Image.open(out_1080p).convert("RGB")
                im_720 = im_1080.resize((1280, 720), Image.Resampling.LANCZOS)
                im_720.save(str(out_720p), format="PNG", optimize=True)
                return out_720p, out_1080p
        finally:
            props_file.unlink(missing_ok=True)

    w, h = 1920, 1080
    canvas = _make_studio_backdrop(w, h, accent_hex, secondary_hex)
    draw = ImageDraw.Draw(canvas)
    accent_rgb = _hex_to_rgb(accent_hex)
    sec_rgb = _hex_to_rgb(secondary_hex)

    # Diagonal dynamic accent slash on right side
    poly = [(1140, 0), (1920, 0), (1920, 1080), (960, 1080)]
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.polygon(poly, fill=(*accent_rgb, 34))
    odraw.line([(1140, 0), (960, 1080)], fill=(*accent_rgb, 190), width=6)
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    # Right-hand Hero Visual Card
    card_x, card_y, card_w, card_h = 1130, 150, 690, 780
    if hero_image_path and hero_image_path.exists():
        hero = Image.open(hero_image_path).convert("RGB")
        bg = hero.resize((card_w, card_h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(22))
        bg_arr = (np.asarray(bg, dtype=np.float32) * 0.42).astype(np.uint8)
        card_img = Image.fromarray(bg_arr, mode="RGB").convert("RGBA")

        fit_scale = min(card_w / hero.width, card_h / hero.height) * 0.94
        fw, fh = max(1, int(hero.width * fit_scale)), max(1, int(hero.height * fit_scale))
        fg = hero.resize((fw, fh), Image.Resampling.LANCZOS).convert("RGBA")
        card_img.alpha_composite(fg, ((card_w - fw) // 2, (card_h - fh) // 2))
    else:
        dummy_scene = SceneSpec(
            scene_id="thumb",
            index=0,
            scene_type="content",
            chapter_title="YouTube Production",
            headline=title,
            narration="",
            visual_style="diagram",
            accent_color=accent_hex,
        )
        card_img = build_scene_visual_panel(dummy_scene, card_w, card_h, secondary_hex).convert("RGBA")

    # Rounded mask for right visual card
    mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w, card_h], radius=36, fill=255)
    canvas.paste(card_img, (card_x, card_y), mask)
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=36,
        outline=(*accent_rgb, 235),
        width=5,
    )

    # Top Badge Pill
    f_badge = _load_font("ExtraBold", 34)
    badge = (badge_text or "COMPLETE GUIDE").upper()
    bb_b = draw.textbbox((0, 0), badge, font=f_badge)
    pill_w = (bb_b[2] - bb_b[0]) + 56
    pill_h = 68
    draw.rounded_rectangle([100, 120, 100 + pill_w, 120 + pill_h], radius=34, fill=(*accent_rgb, 255))
    draw.text((128, 132), badge, font=f_badge, fill=(8, 15, 28, 255))

    # Punchy Headline (up to 4 lines, bold display typography with shadow)
    words = title.upper().split()
    short_title = " ".join(words[:8])
    wrapped = textwrap.wrap(short_title, width=14)[:4]
    f_title = _load_font("Black", 104 if len(wrapped) <= 3 else 88)

    ty = 235
    for i, line in enumerate(wrapped):
        # Drop shadow
        draw.text((106, ty + 8), line, font=f_title, fill=(0, 0, 0, 210))
        fill_col = (250, 204, 21, 255) if i == len(wrapped) - 1 else (255, 255, 255, 255)
        draw.text((100, ty), line, font=f_title, fill=fill_col)
        ty += int(f_title.size * 1.12)

    # Bottom Channel Bar
    f_chan = _load_font("SemiBold", 34)
    draw.rounded_rectangle([100, 895, 100 + 22, 955], radius=6, fill=(*sec_rgb, 255))
    draw.text((140, 902), channel_name.upper(), font=f_chan, fill=(203, 213, 225, 255))

    out_1080p.parent.mkdir(parents=True, exist_ok=True)
    rgb_1080 = canvas.convert("RGB")
    rgb_1080.save(str(out_1080p), format="PNG", optimize=True)

    rgb_720 = rgb_1080.resize((1280, 720), Image.Resampling.LANCZOS)
    rgb_720.save(str(out_720p), format="PNG", optimize=True)
    return out_720p, out_1080p


class ContentSceneAnimator:
    """
    Memory-efficient per-frame compositor for content, intro, and outro scenes.
    Pre-renders static text layers once per scene and applies smooth OpenCV subpixel
    Ken Burns zoom/pan + staggered kinetic bullet animations per frame.
    """

    def __init__(
        self,
        scene: SceneSpec,
        total_content_scenes: int,
        content_order: int,
        width: int,
        height: int,
        channel_name: str,
        channel_tagline: str,
        episode_badge: str,
        secondary_hex: str = "#818CF8",
        ken_burns_zoom: float = 0.065,
    ) -> None:
        self.scene = scene
        self.width = width
        self.height = height
        self.scale = height / 1080.0
        self.secondary_hex = secondary_hex
        self.ken_burns_zoom = ken_burns_zoom
        self.channel_name = channel_name
        self.channel_tagline = channel_tagline
        self.episode_badge = episode_badge
        self.total_content_scenes = max(1, total_content_scenes)
        self.content_order = content_order

        self.video_cap: cv2.VideoCapture | None = None
        self.video_fps: float = 30.0
        self.video_frames: int = 0

        # Precompute base RGB backdrop
        self.backdrop_rgb = np.asarray(
            _make_studio_backdrop(width, height, scene.accent_color, secondary_hex).convert("RGB"),
            dtype=np.uint8,
        )

        if scene.scene_type == "content":
            self._init_content_layers()
        elif scene.scene_type == "intro":
            self._init_intro_layers()
        else:
            self._init_outro_layers()

    def _init_content_layers(self) -> None:
        s = self.scale
        # Visual card geometry on right half
        self.vbox_x = int(1050 * s)
        self.vbox_y = int(185 * s)
        self.vbox_w = int(766 * s)
        self.vbox_h = int(660 * s)

        if self.scene.visual_asset:
            ap = Path(self.scene.visual_asset)
            if ap.exists() and ap.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
                cap = cv2.VideoCapture(str(ap))
                if cap.isOpened():
                    self.video_cap = cap
                    self.video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    self.video_frames = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))

        overscan = 1.14
        pw = max(64, int(round(self.vbox_w * overscan)))
        ph = max(64, int(round(self.vbox_h * overscan)))
        self.panel_rgb = np.asarray(
            build_scene_visual_panel(self.scene, pw, ph, self.secondary_hex),
            dtype=np.uint8,
        )

        # Pre-render static header + headline RGBA overlay
        header_img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(header_img)
        accent_rgb = _hex_to_rgb(self.scene.accent_color)

        # Chapter pill
        f_pill = _load_font("Bold", int(21 * s))
        f_chap = _load_font("SemiBold", int(24 * s))
        pill_txt = f"CHAPTER {self.content_order:02d} / {self.total_content_scenes:02d}"
        pb = draw.textbbox((0, 0), pill_txt, font=f_pill)
        pw_box = (pb[2] - pb[0]) + int(38 * s)
        ph_box = int(44 * s)
        px, py = int(104 * s), int(74 * s)
        draw.rounded_rectangle(
            [px, py, px + pw_box, py + ph_box],
            radius=ph_box // 2,
            fill=(*accent_rgb, 42),
            outline=(*accent_rgb, 235),
            width=max(2, int(2 * s)),
        )
        draw.text((px + int(19 * s), py + int(8 * s)), pill_txt, font=f_pill, fill=(*accent_rgb, 255))
        draw.text(
            (px + pw_box + int(18 * s), py + int(6 * s)),
            self.scene.chapter_title,
            font=f_chap,
            fill=(148, 163, 184, 255),
        )

        # Headline wrapped on left column
        f_head = _load_font("ExtraBold", int(54 * s))
        wrapped_head = textwrap.wrap(self.scene.headline, width=24)[:3]
        hy = int(185 * s)
        for line in wrapped_head:
            draw.text((int(104 * s), hy), line, font=f_head, fill=(255, 255, 255, 255))
            hy += int(64 * s)

        # Frame border around right visual box
        draw.rounded_rectangle(
            [self.vbox_x - 2, self.vbox_y - 2, self.vbox_x + self.vbox_w + 2, self.vbox_y + self.vbox_h + 2],
            radius=int(24 * s),
            outline=(*accent_rgb, 180),
            width=max(2, int(3 * s)),
        )
        self.header_rgba = np.asarray(header_img, dtype=np.uint8)
        self.bullets_start_y = max(int(395 * s), hy + int(28 * s))

        # Pre-render each bullet card as a compact RGBA sprite for fast per-frame slide-in!
        self.bullet_sprites: list[tuple[np.ndarray, int, int]] = []
        f_bul = _load_font("Medium", int(27 * s))
        card_w = int(890 * s)
        for b_idx, b_text in enumerate(self.scene.bullets[:3]):
            lines = textwrap.wrap(b_text, width=42)[:2]
            card_h = int((44 + 38 * len(lines)) * s)
            b_img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
            bd = ImageDraw.Draw(b_img)
            bd.rounded_rectangle(
                [0, 0, card_w - 1, card_h - 1],
                radius=int(16 * s),
                fill=(15, 23, 42, 215),
                outline=(148, 163, 184, 55),
                width=1,
            )
            bd.rounded_rectangle(
                [0, 0, max(4, int(8 * s)), card_h - 1],
                radius=int(4 * s),
                fill=(*accent_rgb, 255),
            )
            ty = int(18 * s)
            for ln in lines:
                bd.text((int(28 * s), ty), ln, font=f_bul, fill=(226, 232, 240, 255))
                ty += int(36 * s)
            target_y = self.bullets_start_y + b_idx * (card_h + int(18 * s))
            self.bullet_sprites.append((np.asarray(b_img, dtype=np.uint8), int(104 * s), target_y))

    def _init_intro_layers(self) -> None:
        s = self.scale
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        accent_rgb = _hex_to_rgb(self.scene.accent_color)

        f_badge = _load_font("ExtraBold", int(24 * s))
        f_chan = _load_font("SemiBold", int(26 * s))
        badge_txt = self.episode_badge.upper()
        bb = draw.textbbox((0, 0), badge_txt, font=f_badge)
        pw = (bb[2] - bb[0]) + int(40 * s)
        ph = int(48 * s)
        draw.rounded_rectangle([int(140 * s), int(230 * s), int(140 * s) + pw, int(230 * s) + ph], radius=ph // 2, fill=(*accent_rgb, 255))
        draw.text((int(160 * s), int(238 * s)), badge_txt, font=f_badge, fill=(8, 15, 28, 255))
        draw.text((int(160 * s) + pw, int(237 * s)), self.channel_name.upper(), font=f_chan, fill=(148, 163, 184, 255))

        f_title = _load_font("ExtraBold", int(76 * s))
        ty = int(315 * s)
        for ln in textwrap.wrap(self.scene.headline, width=26)[:3]:
            draw.text((int(140 * s), ty), ln, font=f_title, fill=(255, 255, 255, 255))
            ty += int(88 * s)

        draw.rounded_rectangle(
            [int(140 * s), ty + int(12 * s), int(580 * s), ty + int(20 * s)],
            radius=4,
            fill=(*accent_rgb, 255),
        )
        f_sub = _load_font("Medium", int(32 * s))
        sy = ty + int(48 * s)
        for ln in textwrap.wrap(self.channel_tagline, width=52)[:2]:
            draw.text((int(140 * s), sy), ln, font=f_sub, fill=(203, 213, 225, 255))
            sy += int(44 * s)

        self.intro_rgba = np.asarray(img, dtype=np.uint8)

    def _init_outro_layers(self) -> None:
        s = self.scale
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        accent_rgb = _hex_to_rgb(self.scene.accent_color)
        sec_rgb = _hex_to_rgb(self.secondary_hex)

        f_kicker = _load_font("Bold", int(24 * s))
        f_title = _load_font("ExtraBold", int(58 * s))
        f_sub = _load_font("Medium", int(26 * s))
        f_btn = _load_font("ExtraBold", int(28 * s))

        draw.text((int(120 * s), int(92 * s)), "THANKS FOR WATCHING", font=f_kicker, fill=(*accent_rgb, 255))
        draw.text((int(120 * s), int(128 * s)), self.channel_name, font=f_title, fill=(255, 255, 255, 255))
        draw.text((int(120 * s), int(202 * s)), self.channel_tagline, font=f_sub, fill=(148, 163, 184, 255))

        # Subscribe pill button
        bx0, by0, bx1, by1 = int(1410 * s), int(118 * s), int(1800 * s), int(196 * s)
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(39 * s), fill=(239, 68, 68, 255))
        draw.text((bx0 + int(48 * s), by0 + int(20 * s)), "SUBSCRIBE + BELL", font=f_btn, fill=(255, 255, 255, 255))

        # YouTube End Screen Cards: Watch Next (Left 16:9), Channel Icon (Center Circle), Best For Viewer (Right 16:9)
        cw, ch = int(600 * s), int(338 * s)
        cy = int(325 * s)
        lx = int(120 * s)
        rx = self.width - int(120 * s) - cw

        draw.rounded_rectangle([lx, cy, lx + cw, cy + ch], radius=int(24 * s), fill=(15, 23, 42, 225), outline=(*accent_rgb, 240), width=max(2, int(3 * s)))
        draw.text((lx + int(30 * s), cy + ch - int(96 * s)), "WATCH NEXT", font=f_kicker, fill=(*accent_rgb, 255))
        draw.text((lx + int(30 * s), cy + ch - int(58 * s)), "Recommended Deep-Dive", font=f_sub, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([rx, cy, rx + cw, cy + ch], radius=int(24 * s), fill=(15, 23, 42, 225), outline=(*sec_rgb, 240), width=max(2, int(3 * s)))
        draw.text((rx + int(30 * s), cy + ch - int(96 * s)), "BEST FOR VIEWER", font=f_kicker, fill=(*sec_rgb, 255))
        draw.text((rx + int(30 * s), cy + ch - int(58 * s)), "Full Engineering Playlist", font=f_sub, fill=(255, 255, 255, 255))

        ccx, ccy, cr = self.width // 2, cy + ch // 2, int(98 * s)
        draw.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr], fill=(30, 41, 59, 235), outline=(*sec_rgb, 240), width=max(2, int(4 * s)))
        draw.text((ccx - int(62 * s), ccy - int(18 * s)), "SUBSCRIBE", font=f_kicker, fill=(255, 255, 255, 255))

        self.outro_rgba = np.asarray(img, dtype=np.uint8)

    @staticmethod
    def _alpha_blit(dst_rgb: np.ndarray, src_rgba: np.ndarray, x: int, y: int, opacity: float = 1.0) -> None:
        if opacity <= 0.005:
            return
        sh, sw = src_rgba.shape[:2]
        dh, dw = dst_rgb.shape[:2]
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(dw, x + sw)
        y1 = min(dh, y + sh)
        if x1 <= x0 or y1 <= y0:
            return
        sx0 = x0 - x
        sy0 = y0 - y
        sub_src = src_rgba[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
        alpha = (sub_src[..., 3:4].astype(np.float32) / 255.0) * min(1.0, opacity)
        roi = dst_rgb[y0:y1, x0:x1].astype(np.float32)
        dst_rgb[y0:y1, x0:x1] = (roi * (1.0 - alpha) + sub_src[..., :3].astype(np.float32) * alpha).astype(np.uint8)

    def render_frame_rgb(self, t_sec: float) -> np.ndarray:
        dur = max(0.1, self.scene.duration_sec)
        prog = max(0.0, min(1.0, t_sec / dur))
        frame = self.backdrop_rgb.copy()

        if self.scene.scene_type == "intro":
            enter = _ease_out_cubic(t_sec / 0.65)
            dy = int((1.0 - enter) * 34 * self.scale)
            self._alpha_blit(frame, self.intro_rgba, 0, dy, opacity=enter)
            return frame

        if self.scene.scene_type == "outro":
            enter = _ease_out_cubic(t_sec / 0.65)
            dy = int((1.0 - enter) * 28 * self.scale)
            self._alpha_blit(frame, self.outro_rgba, 0, dy, opacity=enter)
            return frame

        # Content scene: 1) Ken Burns visual or external video clip in right showcase panel
        if self.video_cap is not None and self.video_frames > 0:
            v_idx = int(t_sec * self.video_fps) % self.video_frames
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, v_idx)
            ok, bgr = self.video_cap.read()
            if ok and bgr is not None:
                rgb_vid = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                resized = cv2.resize(rgb_vid, (self.vbox_w, self.vbox_h), interpolation=cv2.INTER_AREA)
                frame[self.vbox_y : self.vbox_y + self.vbox_h, self.vbox_x : self.vbox_x + self.vbox_w] = resized
        else:
            ph, pw = self.panel_rgb.shape[:2]
            zoom = 1.0 + self.ken_burns_zoom * prog
            crop_w = max(32, min(pw, int(round(pw / zoom))))
            crop_h = max(32, min(ph, int(round(ph / zoom))))
            cx0 = int((pw - crop_w) * (0.35 + 0.30 * prog))
            cy0 = int((ph - crop_h) * (0.35 + 0.30 * prog))
            cropped = self.panel_rgb[cy0 : cy0 + crop_h, cx0 : cx0 + crop_w]
            vis = cv2.resize(cropped, (self.vbox_w, self.vbox_h), interpolation=cv2.INTER_LINEAR)
            frame[self.vbox_y : self.vbox_y + self.vbox_h, self.vbox_x : self.vbox_x + self.vbox_w] = vis

        # 2) Header + headline overlay
        head_op = _ease_out_cubic(t_sec / 0.45)
        self._alpha_blit(frame, self.header_rgba, 0, 0, opacity=head_op)

        # 3) Staggered kinetic bullet cards
        num_b = len(self.bullet_sprites)
        for idx, (sprite, bx, by) in enumerate(self.bullet_sprites):
            reveal_t = 0.35 + idx * min(1.1, (dur * 0.45) / max(1, num_b))
            b_prog = _ease_out_cubic((t_sec - reveal_t) / 0.50)
            offset_x = int((1.0 - b_prog) * -36 * self.scale)
            self._alpha_blit(frame, sprite, bx + offset_x, by, opacity=b_prog)

        # 4) Top progress bar
        s = self.scale
        bar_x0, bar_y0 = int(1570 * s), int(92 * s)
        bar_w, bar_h = int(246 * s), max(4, int(8 * s))
        frame[bar_y0 : bar_y0 + bar_h, bar_x0 : bar_x0 + bar_w] = (30, 41, 59)
        fill_w = max(2, int(round(bar_w * prog)))
        ar, ag, ab = _hex_to_rgb(self.scene.accent_color)
        frame[bar_y0 : bar_y0 + bar_h, bar_x0 : bar_x0 + fill_w] = (ar, ag, ab)

        return frame

    def close(self) -> None:
        if self.video_cap is not None:
            self.video_cap.release()
            self.video_cap = None
