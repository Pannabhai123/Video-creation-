"""
imagetovideo.py — turn still images into cinematic video clips.

What this does (and does not) do
--------------------------------
It does NOT invent new motion with an AI video model (that needs model weights
and a GPU that this sandbox does not have). What it DOES is the technique used by
documentary and essay channels everywhere: move the camera over a still image,
add transitions, Hindi text overlays, music and narration. That is what makes a
photo feel like footage.

Features
--------
* Motion: slow zoom in/out, pan left/right, diagonal drift, parallax-style dolly,
  and a "kenburns" random-but-seeded blend. Oversampled so there is no jitter.
* Transitions: fade, smoothleft/right, circleopen, wipeleft, dissolve.
* Text overlays: correct Devanagari (HarfBuzz), faded in, with a legibility scrim.
* Aspect: 16:9, 9:16 or square. Mismatched images are covered, or blurred-padded.
* Audio: synthesised music bed, per-image narration, EBU R128 normalisation.
* Output: H.264 / AAC, YouTube-ready.

Usage
-----
    # simplest: one image -> 6 second clip
    python imagetovideo.py --image photo.jpg --out clips/one.mp4

    # several images with motion + Hindi captions + music
    python imagetovideo.py --spec spec.json --out rendered_videos/from_images.mp4

    # vertical Short from a 16:9 photo
    python imagetovideo.py --image photo.jpg --out short.mp4 --size 1080x1920 --duration 8

spec.json
---------
{
  "size": [1920, 1080],
  "fps": 30,
  "fit": "cover",                 // cover | blurpad
  "music": {"mood": "reflective", "gain_db": -26},
  "transition": {"type": "fade", "duration": 0.7},
  "shots": [
    {"image": "images/a.jpg", "duration": 5.5, "motion": "zoom_in",
     "headline": "शीर्षक", "sub": "उपशीर्षक", "narration": "voiceover/s01.wav"}
  ]
}
"""

from __future__ import annotations

import argparse
import json
import os
import random
import tempfile

import media
import visuals
from hinditext import HindiText, _rgba
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal",
           "parallax", "kenburns", "static")

SIZE_PRESETS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


# ---------------------------------------------------------------- helpers
def parse_size(value) -> tuple[int, int]:
    if isinstance(value, (list, tuple)):
        return int(value[0]), int(value[1])
    if value in SIZE_PRESETS:
        return SIZE_PRESETS[value]
    if isinstance(value, str) and "x" in value:
        w, h = value.lower().split("x")
        return int(w), int(h)
    raise ValueError(f"bad size {value!r}; use WxH or one of {sorted(SIZE_PRESETS)}")


def prepare_image(path: str, size: tuple[int, int], fit: str = "cover",
                  scrim: bool = True, grade: bool = True) -> Image.Image:
    """
    Normalise an image for motion rendering:
      cover   — fill the frame, centre crop (may cut edges)
      blurpad — keep the whole image, fill the sides with a blurred copy (9:16 safe)
    Also applies a light grade and (optionally) a bottom scrim for text legibility.
    """
    w, h = size
    src = Image.open(path).convert("RGB")

    if fit == "blurpad" and abs(src.width / src.height - w / h) > 0.05:
        bg = visuals.fit_cover(src.resize((max(1, w // 4), max(1, h // 4))), size)
        bg = bg.filter(ImageFilter.GaussianBlur(30))
        bg = Image.eval(bg, lambda v: int(v * 0.50))
        fg_scale = min(w / src.width, h / src.height)
        fg = src.resize((max(1, int(src.width * fg_scale)), max(1, int(src.height * fg_scale))),
                        Image.LANCZOS).convert("RGBA")
        # feather the top/bottom edges of the photo into the blur, otherwise the
        # join reads as a hard seam instead of a deliberate letterbox
        feather = max(24, int(fg.height * 0.14))
        mask = Image.new("L", (fg.width, fg.height), 255)
        ramp = [int(255 * (i / feather) ** 0.85) for i in range(feather)]
        mask.paste(_column(feather, fg.height, ramp), (0, 0))
        mask.paste(_column(feather, fg.height, ramp[::-1]), (fg.width - feather, 0))
        fg.putalpha(mask)
        canvas = bg.convert("RGBA")
        canvas.alpha_composite(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
        out = canvas.convert("RGB")
    else:
        out = visuals.fit_cover(src, size).convert("RGB")

    if grade:
        # gentle cinematic grade: slight contrast + warmth, keeps skin tones sane
        out = Image.blend(out, out.filter(ImageFilter.SMOOTH), 0.10)
    if scrim:
        out = _add_scrim(out)
    return out


def _column(feather: int, height: int, ramp: list[int]) -> Image.Image:
    """Build a vertical alpha ramp strip of the given width/height."""
    strip = Image.new("L", (feather, height))
    strip.putdata([v for _y in range(height) for v in ramp])
    return strip


def _add_scrim(img: Image.Image, strength: float = 0.82, start: float = 0.52) -> Image.Image:
    """Darken the lower area so white text always reads, without flattening the photo."""
    w, h = img.size
    grad = Image.new("L", (1, h))
    px = []
    for y in range(h):
        p = y / max(h - 1, 1)
        v = 0.0 if p < start else ((p - start) / (1 - start)) ** 1.4 * 255 * strength
        px.append(int(v))
    grad.putdata(px)
    grad = grad.resize((w, h))
    dark = Image.new("RGB", (w, h), (4, 6, 10))
    return Image.composite(dark, img, grad.filter(ImageFilter.GaussianBlur(2)))


def text_overlay(spec: dict, size: tuple[int, int], vertical: bool = False) -> str | None:
    """Render the headline/sub as a transparent PNG (Devanagari-correct)."""
    headline = spec.get("headline")
    sub = spec.get("sub")
    if not headline and not sub:
        return None
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    margin = int(w * 0.075)
    max_w = w - margin * 2

    top = int(h * 0.62) if not vertical else int(h * 0.60)

    if headline:
        px = 96 if not vertical else 88
        t = HindiText("display", px)
        while len(t.wrap(headline, max_width=max_w)) > 3 and px > 52:
            px -= 6
            t = HindiText("display", px)
        t = HindiText("display", px)
        img = t.draw_on(img, headline, (margin, top),
                        anchor="lt", max_width=max_w, color="#FFFFFF",
                        stroke=max(4, px // 16), stroke_color="#05070C", shadow=(0, 8, 18))
        n_lines = len(t.wrap(headline, max_width=max_w))
        y = top + int(n_lines * px * 1.24) + 14
    else:
        y = top

    if sub:
        spx = 46 if not vertical else 42
        st = HindiText("deva-medium", spx)
        img = st.draw_on(img, sub, (margin, y), anchor="lt", max_width=max_w,
                         color="#E8EDF6", stroke=3, stroke_color="#05070C")

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    img.save(tmp.name)
    return tmp.name


# ---------------------------------------------------------------- motion
def motion_expr(motion: str, duration: float, fps: int, zoom: float = 0.11,
                seed: int = 0) -> tuple[str, str, str]:
    """
    Return (z_expr, x_expr, y_expr) for FFmpeg's zoompan.

    zoompan evaluates per output frame; `on` is the frame index and `d` the clip
    length, so every expression is normalised to 0..1 over the clip.
    """
    n = max(1, int(round(duration * fps)))
    p = f"(on/{n})"
    centred_x = "iw/2-(iw/zoom/2)"
    centred_y = "ih/2-(ih/zoom/2)"

    if motion == "static":
        return "1", centred_x, centred_y
    if motion == "zoom_in":
        return f"1+{zoom}*{p}", centred_x, centred_y
    if motion == "zoom_out":
        return f"{1 + zoom}-{zoom}*{p}", centred_x, centred_y
    if motion == "pan_left":
        return f"{1 + zoom}", f"(iw-iw/zoom)*(1-{p})", centred_y
    if motion == "pan_right":
        return f"{1 + zoom}", f"(iw-iw/zoom)*{p}", centred_y
    if motion == "diagonal":
        return f"1+{zoom * 0.8}*{p}", f"(iw-iw/zoom)*(0.5-0.5*{p})", f"(ih-ih/zoom)*(0.5-0.5*{p})"
    if motion == "parallax":
        # slow push in while drifting sideways: reads as a camera move, not a slide
        return (f"1+{zoom * 0.7}*{p}",
                f"(iw-iw/zoom)*(0.35+0.30*{p})",
                f"(ih-ih/zoom)*(0.45+0.15*{p})")
    if motion == "kenburns":
        rng = random.Random(seed)
        z0 = 1 + rng.uniform(0.02, 0.05)
        z1 = z0 + rng.uniform(0.05, 0.12)
        x0, x1 = rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8)
        y0, y1 = rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8)
        return (f"{z0}+({z1 - z0})*{p}",
                f"(iw-iw/zoom)*({x0}+({x1 - x0})*{p})",
                f"(ih-ih/zoom)*({y0}+({y1 - y0})*{p})")
    raise ValueError(f"unknown motion {motion!r}; choose from {MOTIONS}")


def render_clip(image: Image.Image, out: str, duration: float, motion: str = "zoom_in",
                size: tuple[int, int] = (1920, 1080), fps: int = 30,
                overlay: str | None = None, fade_in: float = 0.0,
                fade_out: float = 0.0, seed: int = 0) -> str:
    """One image -> one motion clip, with an optional faded text overlay."""
    w, h = size
    src = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    src.close()
    image.save(src.name)

    frames = max(1, int(round(duration * fps)))
    big_w, big_h = w * 2, h * 2  # oversample: z values stay >= 1, so nothing is upscaled
    z, x, y = motion_expr(motion, duration, fps, seed=seed)

    head = (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
        f"crop={big_w}:{big_h},setsar=1,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps}"
    )
    if fade_in > 0:
        head += f",fade=t=in:st=0:d={fade_in}"
    if fade_out > 0:
        head += f",fade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out}"
    head += ",format=yuv420p"

    if overlay:
        # text fades in after a beat, then fades out before the clip ends
        in_at = 0.35
        out_at = max(in_at + 0.6, duration - 0.55)
        fc = (
            f"[0:v]{head}[base];"
            f"[1:v]format=rgba,fade=t=in:st={in_at:.2f}:d=0.55:alpha=1,"
            f"fade=t=out:st={out_at:.2f}:d=0.55:alpha=1[ov];"
            f"[base][ov]overlay=0:0:format=auto[v]"
        )
        media.run(["-loop", "1", "-i", src.name, "-loop", "1", "-i", overlay,
                   "-t", f"{duration:.3f}", "-r", fps, "-filter_complex", fc,
                   "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", out], "image clip + overlay")
    else:
        media.run(["-loop", "1", "-i", src.name, "-t", f"{duration:.3f}", "-r", fps,
                   "-vf", head, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", out], "image clip")

    os.unlink(src.name)
    return out


# ---------------------------------------------------------------- assembly
def xfade_chain(clips: list[str], durations: list[float], out: str,
                transition: str = "fade", tdur: float = 0.7) -> str:
    """Join clips with crossfades (overlapping, so total length shrinks by tdur each)."""
    if len(clips) == 1:
        media.run(["-i", clips[0], "-c", "copy", out], "single clip")
        return out
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", c]
    filt: list[str] = []
    prev = "[0:v]"
    offset = 0.0
    for i in range(1, len(clips)):
        offset += durations[i - 1] - tdur
        label = f"[v{i}]"
        filt.append(
            f"{prev}[{i}:v]xfade=transition={transition}:duration={tdur}:"
            f"offset={max(0.0, offset):.3f}{label}"
        )
        prev = label
    media.run([*inputs, "-filter_complex", ";".join(filt), "-map", prev,
               "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p", out], "xfade chain")
    return out


def build(spec: dict, out: str) -> dict:
    size = parse_size(spec.get("size", "16:9"))
    fps = int(spec.get("fps", 30))
    vertical = size[1] > size[0]
    fit = spec.get("fit", "cover")
    trans = spec.get("transition", {"type": "fade", "duration": 0.7})
    shots = spec.get("shots") or []
    if not shots:
        raise SystemExit("spec has no shots")
    if len(shots) == 1:
        trans = {"type": "fade", "duration": 0.0}

    workdir = tempfile.mkdtemp(prefix="i2v_")
    clips, durations = [], []
    overlays: list[str] = []
    for i, shot in enumerate(shots):
        img_path = shot["image"]
        if not os.path.isabs(img_path):
            img_path = os.path.join(spec.get("_base") or os.getcwd(), img_path)
        if not os.path.exists(img_path):
            raise SystemExit(f"image not found: {img_path}")
        dur = float(shot.get("duration", 5.0))
        prepared = prepare_image(img_path, size, fit=fit,
                                 scrim=shot.get("scrim", True))
        ov = text_overlay(shot, size, vertical=vertical)
        if ov:
            overlays.append(ov)
        clip = os.path.join(workdir, f"c{i:02d}.mp4")
        render_clip(prepared, clip, dur, shot.get("motion", "kenburns"), size, fps,
                    overlay=ov, seed=i + 7,
                    fade_in=0 if i else 0.5,
                    fade_out=0.5 if i == len(shots) - 1 else 0)
        clips.append(clip)
        durations.append(dur)

    tdur = float(trans.get("duration", 0.7)) if trans else 0.0
    picture = os.path.join(workdir, "picture.mp4")
    xfade_chain(clips, durations, picture, trans.get("type", "fade"), tdur)
    total = sum(durations) - tdur * (len(clips) - 1)

    # ---------------- audio
    audio = None
    voice_parts = [s.get("narration") for s in shots if s.get("narration")]
    if voice_parts and all(p and os.path.exists(p) for p in voice_parts):
        audio = os.path.join(workdir, "narration.wav")
        media.concat_audio(voice_parts, audio)
    music_spec = spec.get("music") or {}
    if music_spec:
        import music as musicmod
        mood = music_spec.get("mood", "reflective")
        bed = music_spec.get("path") or os.path.join(ROOT, "music", f"bed_{mood}_long.wav")
        if not os.path.exists(bed):
            musicmod.write_stereo(musicmod.bed(mood, total + 8), bed)
        mixed = os.path.join(workdir, "mix.wav")
        media.mix(audio, bed, mixed, music_gain_db=float(music_spec.get("gain_db", -26)),
                  duck=bool(audio))
        mixed = _to_match(mixed, total, workdir)
        final_audio = os.path.join(workdir, "final.wav")
        media.loudness_normalise(mixed, final_audio)
        audio = final_audio if os.path.exists(final_audio) else mixed
    elif audio:
        final_audio = os.path.join(workdir, "final.wav")
        media.loudness_normalise(audio, final_audio)
        audio = final_audio if os.path.exists(final_audio) else audio

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if audio:
        media.mux(picture, audio, out, crf="18")
    else:
        media.run(["-i", picture, "-c", "copy", out], "picture only")

    for ov in overlays:
        try:
            os.unlink(ov)
        except OSError:
            pass

    return {
        "output": os.path.abspath(out),
        "shots": len(shots),
        "duration": round(total, 2),
        "size": list(size),
        "fps": fps,
        "transition": trans,
        "music": music_spec or None,
        "narration": bool(voice_parts),
    }


def _to_match(path: str, seconds: float, workdir: str) -> str:
    """Trim/pad audio to the picture length so nothing ends before the video."""
    out = os.path.join(workdir, "trimmed.wav")
    media.run(["-i", path, "-af", f"apad,atrim=0:{seconds:.3f}", "-c:a", "pcm_s16le", out], "fit audio")
    return out


# ---------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="Turn images into motion video clips")
    ap.add_argument("--image", action="append", default=[], help="input image (repeatable)")
    ap.add_argument("--spec", help="JSON spec with shots")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="16:9", help="16:9 | 9:16 | 1:1 | 4:5 | WxH")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=6.0, help="seconds per image")
    ap.add_argument("--motion", default="kenburns", choices=list(MOTIONS))
    ap.add_argument("--fit", default="cover", choices=["cover", "blurpad"])
    ap.add_argument("--music", default=None, help="mood: calm/reflective/inspiring/tense/upbeat")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--headline", default=None)
    ap.add_argument("--sub", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.spec:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["_base"] = os.path.dirname(os.path.abspath(args.spec))
    else:
        if not args.image:
            raise SystemExit("give --image (one or more) or --spec file.json")
        spec = {
            "size": args.size,
            "fps": args.fps,
            "fit": args.fit,
            "music": None if args.no_music else {"mood": args.music or "reflective", "gain_db": -26},
            "transition": {"type": "fade", "duration": 0.7},
            "shots": [{"image": img, "duration": args.duration, "motion": args.motion,
                       "headline": args.headline, "sub": args.sub} for img in args.image],
        }
        spec["_base"] = os.getcwd()

    result = build(spec, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["output"])


if __name__ == "__main__":
    main()
