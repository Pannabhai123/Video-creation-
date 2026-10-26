"""
livephoto.py — turn a still photo into a "living picture" with real depth motion.

Why this is different from a plain Ken Burns move
-------------------------------------------------
Ken Burns slides the whole frame, so the photo stays flat. Here a neural network
(MediaPipe selfie segmentation, running locally via LiteRT) splits the subject
from the background, and the two layers are then moved **at different speeds**.
That relative motion is what the eye reads as depth — the same trick used by
"photo to life" tools, produced entirely on-device.

Modes
-----
    parallax   subject drifts against a slower background (the classic look)
    dolly      push in on the subject while the background barely moves
    orbit      sideways arc, foreground leading the background
    breathe    slow in-and-out breathing move with a slight subject lift

Also available
--------------
* --focus face      neural face detection, keeps the face inside the safe area
* --depth-blur      background gets progressively softer (fake depth of field)
* --light-sweep     a slow highlight sweep across the frame (adds "alive" feel)
* --fit blurpad     9:16 from a landscape original, edges feathered

Usage
-----
    python livephoto.py --image images/photo.jpg --out clips/live.mp4 \
        --mode parallax --duration 6 --size 16:9

    python livephoto.py --spec spec.json --out rendered_videos/live.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile

import numpy as np
from PIL import Image, ImageFilter

import aivision
import imagetovideo
import media

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MODES = ("parallax", "dolly", "orbit", "breathe")


# ---------------------------------------------------------------- helpers
def _resize_cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return imagetovideo.fit_cover(img, size) if hasattr(imagetovideo, "fit_cover") else _fit(img, size)


def _fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                         Image.LANCZOS)
    left = (resized.width - w) // 2
    top = (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _layer_motion(mode: str, t: float, amp_fg: float, amp_bg: float) -> tuple:
    """
    Return ((scale_fg, dx_fg, dy_fg), (scale_bg, dx_bg, dy_bg)) for progress t in 0..1.
    Offsets are fractions of the frame.
    """
    s = np.sin(np.pi * t)  # eased 0 -> 1 -> 0 for breathing moves

    if mode == "parallax":
        fg = (1.0 + 0.10 * t, -amp_fg * t, -amp_fg * 0.25 * t)
        bg = (1.0 + 0.04 * t, -amp_bg * t, -amp_bg * 0.10 * t)
    elif mode == "dolly":
        fg = (1.0 + 0.18 * t, 0.0, -amp_fg * 0.4 * t)
        bg = (1.0 + 0.05 * t, 0.0, -amp_bg * 0.2 * t)
    elif mode == "orbit":
        fg = (1.0 + 0.06 * t, amp_fg * t, -amp_fg * 0.12 * t)
        bg = (1.0 + 0.06 * t, -amp_bg * t, -amp_bg * 0.05 * t)
    elif mode == "breathe":
        fg = (1.0 + 0.09 * s, 0.0, -0.012 * s)
        bg = (1.0 + 0.03 * s, 0.0, 0.0)
    else:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    return fg, bg


def _scaled(layer: Image.Image, scale: float) -> Image.Image:
    """Scale about the centre; skipped when the scale is effectively 1."""
    if abs(scale - 1.0) <= 1e-4:
        return layer
    return layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
                        Image.BILINEAR)


def _paste_at(canvas: Image.Image, layer: Image.Image, dx: float, dy: float) -> None:
    """
    Paste a layer centred on the canvas with a fractional offset, in place.

    The RGBA layer's own alpha MUST be passed as the paste mask; without it the
    transparent region is written as opaque black and the cut-out subject ends up
    surrounded by a dark halo.
    """
    cw, ch = canvas.size
    pos = ((cw - layer.width) // 2 + int(dx * cw),
           (ch - layer.height) // 2 + int(dy * ch))
    if layer.mode == "RGBA":
        canvas.paste(layer, pos, layer)
    else:
        canvas.paste(layer, pos)


def _light_sweep(arr: np.ndarray, t: float, strength: float = 0.12) -> np.ndarray:
    """A soft diagonal highlight travelling across the frame."""
    h, w = arr.shape[:2]
    xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    pos = -0.35 + 1.6 * t
    band = np.exp(-((xs * 0.8 + ys * 0.2 - pos) ** 2) / 0.012)[..., None]
    return np.clip(arr.astype(np.float32) * (1.0 + band * strength), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- renderer
def render_frames(image_path: str, size: tuple[int, int], duration: float, fps: int,
                  mode: str = "parallax", seg: aivision.PersonSegmenter | None = None,
                  depth_blur: bool = True, light_sweep: bool = False,
                  strength: float = 0.5, inpaint: bool = False) -> tuple[list[np.ndarray], dict]:
    """Render every frame of the move in memory. Returns frames + diagnostics."""
    src = Image.open(image_path).convert("RGB")
    base = _fit(src, size)

    seg = seg or aivision.PersonSegmenter()
    mask = seg.mask(base)
    coverage = float((mask > 0.5).mean())
    has_subject = 0.01 < coverage < 0.92

    if not has_subject:
        # nothing to separate: fall back to whole-frame motion so the clip still works
        mask = np.zeros_like(mask)

    fg_img = base.convert("RGBA")
    fg_alpha = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8))
    fg_img.putalpha(fg_alpha)

    if inpaint:
        # content-aware fill of the hidden area — needed only for large moves,
        # because filling a whole person-sized hole convincingly is hard
        bg_img = aivision.inpaint_behind(base, mask, strength=0.95)
    else:
        # Recommended default: keep the untouched photo as the background and move
        # the cut-out subject only slightly. The revealed strip is the subject's own
        # pixels, which reads as motion rather than as a smeared/ghosted hole.
        bg_img = base.copy()
    if depth_blur:
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=max(1.0, min(size) * 0.0016)))
    bg_img = bg_img.convert("RGBA")

    n = max(1, int(round(duration * fps)))
    amp_fg = 0.045 * strength
    amp_bg = 0.016 * strength

    frames: list[np.ndarray] = []
    for i in range(n):
        t = i / max(1, n - 1)
        (sfg, dxf, dyf), (sbg, dxb, dyb) = _layer_motion(mode, t, amp_fg, amp_bg)
        canvas = Image.new("RGB", size, (0, 0, 0))
        _paste_at(canvas, _scaled(bg_img, sbg), dxb, dyb)
        _paste_at(canvas, _scaled(fg_img, sfg), dxf, dyf)  # fg carries its own alpha
        arr = np.asarray(canvas)
        if light_sweep:
            arr = _light_sweep(arr, t)
        frames.append(arr)

    diag = {
        "subject_coverage": round(coverage, 3),
        "subject_detected": has_subject,
        "frames": n,
        "mode": mode,
    }
    return frames, diag


def build(spec: dict, out: str) -> dict:
    size = imagetovideo.parse_size(spec.get("size", "16:9"))
    fps = int(spec.get("fps", 30))
    duration = float(spec.get("duration", 6.0))
    mode = spec.get("mode", "parallax")

    image = spec["image"]
    if not os.path.isabs(image):
        image = os.path.join(spec.get("_base") or os.getcwd(), image)
    if not os.path.exists(image):
        raise SystemExit(f"image not found: {image}")

    frames, diag = render_frames(
        image, size, duration, fps, mode=mode,
        depth_blur=bool(spec.get("depth_blur", True)),
        light_sweep=bool(spec.get("light_sweep", False)),
        strength=float(spec.get("strength", 0.5)),
        inpaint=bool(spec.get("inpaint", False)),
    )

    workdir = tempfile.mkdtemp(prefix="live_")
    pipeline = os.path.join(workdir, "frames.mp4")
    media.frames_to_video(frames, pipeline, fps=fps)

    # optional text overlay, reuse the image-to-video overlay engine
    overlay = imagetovideo.text_overlay(
        {"headline": spec.get("headline"), "sub": spec.get("sub")},
        size, vertical=size[1] > size[0]) if (spec.get("headline") or spec.get("sub")) else None

    picture = pipeline
    if overlay:
        picture = os.path.join(workdir, "with_text.mp4")
        dur = media.duration_of(pipeline)
        fc = (
            f"[0:v]format=yuv420p[base];"
            f"[1:v]format=rgba,fade=t=in:st=0.35:d=0.55:alpha=1,"
            f"fade=t=out:st={max(1.0, dur - 0.6):.2f}:d=0.55:alpha=1[ov];"
            f"[base][ov]overlay=0:0:format=auto[v]"
        )
        # -t is mandatory: a "-loop 1" image input never ends on its own
        media.run(["-i", pipeline, "-loop", "1", "-i", overlay, "-t", f"{dur:.3f}",
                   "-filter_complex", fc, "-map", "[v]",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", picture], "livephoto overlay")

    audio = None
    music_spec = spec.get("music") or {}
    if music_spec:
        import music as musicmod
        mood = music_spec.get("mood", "reflective")
        bed = music_spec.get("path") or os.path.join(ROOT, "music", f"bed_{mood}_long.wav")
        if not os.path.exists(bed):
            musicmod.write_stereo(musicmod.bed(mood, duration + 8), bed)
        raw = os.path.join(workdir, "bed.wav")
        media.run(["-stream_loop", "-1", "-i", bed, "-t", f"{duration:.3f}",
                   "-c:a", "pcm_s16le", raw], "bed trim")
        mixed = os.path.join(workdir, "mix.wav")
        media.mix(None, raw, mixed, music_gain_db=float(music_spec.get("gain_db", -30)))
        trimmed = os.path.join(workdir, "final.wav")
        media.loudness_normalise(mixed, trimmed)
        audio = trimmed if os.path.exists(trimmed) else mixed

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if audio:
        media.mux(picture, audio, out, crf="18")
    else:
        media.run(["-i", picture, "-c", "copy", out], "livephoto mux")

    if overlay:
        try:
            os.unlink(overlay)
        except OSError:
            pass

    return {
        "output": os.path.abspath(out),
        "mode": mode,
        "duration": round(duration, 2),
        "size": list(size),
        "fps": fps,
        "segmentation": diag,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Neural 2.5D live-photo renderer")
    ap.add_argument("--image", help="input photo")
    ap.add_argument("--spec", help="JSON spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="parallax", choices=list(MODES))
    ap.add_argument("--duration", type=float, default=6.0)
    ap.add_argument("--size", default="16:9")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--headline")
    ap.add_argument("--sub")
    ap.add_argument("--music", default="reflective", help="mood, or 'none'")
    ap.add_argument("--no-depth-blur", action="store_true")
    ap.add_argument("--inpaint", action="store_true",
                    help="content-aware fill of the hidden area (only for large moves)")
    ap.add_argument("--strength", type=float, default=0.5,
                    help="motion amplitude multiplier (0.3 subtle .. 1.0 strong)")
    ap.add_argument("--light-sweep", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.spec:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["_base"] = os.path.dirname(os.path.abspath(args.spec))
    else:
        if not args.image:
            raise SystemExit("give --image or --spec")
        spec = {
            "image": args.image, "mode": args.mode, "duration": args.duration,
            "size": args.size, "fps": args.fps, "headline": args.headline,
            "sub": args.sub, "depth_blur": not args.no_depth_blur,
            "light_sweep": args.light_sweep, "inpaint": args.inpaint,
            "strength": args.strength,
            "music": None if args.music == "none" else {"mood": args.music, "gain_db": -30},
            "_base": os.getcwd(),
        }

    result = build(spec, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["output"])


if __name__ == "__main__":
    main()
