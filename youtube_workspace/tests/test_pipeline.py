"""
Fast regression tests for the production pipeline.

    /home/user/Video-creation-/.venv/bin/python -m pytest youtube_workspace/tests -q
    # or without pytest:
    /home/user/Video-creation-/.venv/bin/python youtube_workspace/tests/test_pipeline.py

These test the parts that silently break quality: Devanagari shaping, text layout,
subtitle timing, loudness math, brand loading, and timeline planning.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AUTOMATION = os.path.join(os.path.dirname(HERE), "automation")
sys.path.insert(0, AUTOMATION)

import captions
import hinditext
import imagetovideo
import livephoto
import media
import projector
import visuals

PROJECT = os.path.join(os.path.dirname(HERE), "projects", "demo_productivity", "project.json")


# ---------------------------------------------------------------- shaping
def test_shaping_changes_width():
    """A conjunct must collapse to fewer glyphs than its decomposed spelling."""
    t = hinditext.HindiText("deva-bold", 48)
    assert t.measure_line("कर्म") < t.measure_line("करम")


def test_matra_reordering_measure():
    t = hinditext.HindiText("deva-bold", 48)
    # "कि" (i-matra precedes the consonant visually) must be narrower than "की"
    assert t.measure_line("कि") < t.measure_line("की") + 5


def test_wrap_respects_width():
    t = hinditext.HindiText("deva-regular", 40)
    text = "यह एक लंबा वाक्य है जिसे हमें तोड़ना चाहिए ताकि पंक्ति चौड़ाई से बाहर न जाए"
    lines = t.wrap(text, max_width=400)
    assert len(lines) > 1
    for line in lines:
        assert t.measure_line(line) <= 400 + 40  # 40px tolerance for a single word


def test_render_produces_alpha():
    t = hinditext.HindiText("display", 72)
    img = t.render("नमस्ते", color="#FFFFFF", stroke=4)
    assert img.mode == "RGBA"
    assert img.width > 0 and img.height > 0
    assert img.getbbox() is not None


def test_split_runs_separates_scripts():
    runs = hinditext.split_runs("शुद्ध Hindi मिश्रित")
    scripts = {s for _t, s in runs}
    assert "Deva" in scripts and "Latn" in scripts


# ---------------------------------------------------------------- captions
def test_chunk_text_sizes():
    text = ("यह पहला वाक्य है। यह दूसरा वाक्य है, जिसमें दो हिस्से हैं। "
            "और यह तीसरा वाक्य है जो काफ़ी लंबा है और इसे तोड़ा जाना चाहिए।")
    cues = captions.chunk_text(text)
    assert len(cues) >= 3
    assert all(len(c) <= captions.MAX_LINE_CHARS * captions.MAX_LINES + 20 for c in cues)


def test_time_scene_covers_duration():
    text = "पहला वाक्य। दूसरा वाक्य। तीसरा वाक्य। चौथा वाक्य।"
    cues = captions.time_scene(text, start=10.0, duration=20.0)
    assert cues[0].start == 10.0
    assert cues[-1].end <= 30.0 + 0.3
    for a, b in zip(cues, cues[1:]):
        assert a.end <= b.start + 1e-6  # no overlaps


def test_srt_and_ass_written():
    cues = captions.time_scene("एक। दो। तीन।", 0.0, 6.0)
    with tempfile.TemporaryDirectory() as d:
        srt = captions.write_srt(cues, os.path.join(d, "x.srt"))
        ass = captions.write_ass(cues, os.path.join(d, "x.ass"))
        assert open(srt, encoding="utf-8").read().startswith("1\n")
        content = open(ass, encoding="utf-8").read()
        assert "[Script Info]" in content and "Noto Sans Devanagari" in content


def test_cps_report_flags_fast_cues():
    fast = [captions.Cue(0.0, 1.0, "य" * 60)]
    report = captions.cps_report(fast)
    assert report["too_fast"]


# ---------------------------------------------------------------- planning
def test_estimate_duration_scales():
    short = projector.estimate_duration("छोटा वाक्य")
    long = projector.estimate_duration("छोटा वाक्य " * 10)
    assert long > short * 5


def test_plan_is_contiguous():
    proj = projector.load_project(PROJECT)
    b = projector.Builder(PROJECT, draft=True, music=False, verbose=False)
    scenes = b.plan()
    assert len(scenes) == len(proj["scenes"])
    t = 0.0
    for sc in scenes:
        assert abs(sc.start - t) < 1e-6
        assert sc.duration > 0
        t += sc.duration


# ---------------------------------------------------------------- visuals
def test_brand_loads():
    b = visuals.brand()
    assert b["palette"]["accent"].startswith("#")
    assert b["safe_margin"] > 0


def test_every_scene_type_renders():
    with tempfile.TemporaryDirectory() as d:
        specs = [
            {"type": "title", "title": "शीर्षक", "subtitle": "उपशीर्षक", "badge": "TEST"},
            {"type": "section", "number": 2, "heading": "अध्याय", "kicker": "PART"},
            {"type": "bullets", "heading": "सूची", "items": ["एक", "दो", "तीन"]},
            {"type": "stat", "value": "37%", "label": "बढ़ोतरी", "source": "अध्ययन"},
            {"type": "quote", "quote": "छोटी शुरुआत।", "author": "लेखक"},
            {"type": "split", "heading": "तुलना", "points": ["अ", "ब"]},
        ]
        for i, spec in enumerate(specs):
            out = visuals.render_scene(spec, os.path.join(d, f"s{i}.png"), size=(640, 360))
            assert os.path.getsize(out) > 1000


def test_gradient_orientation():
    img = visuals.gradient((100, 100), "#000000", "#FFFFFF", angle=90)
    assert img.getpixel((50, 2))[0] < img.getpixel((50, 97))[0]


# ---------------------------------------------------------------- misc
def test_json_templates_parse():
    """Every shipped template must be valid JSON with real content."""
    tpl = os.path.join(os.path.dirname(HERE), "templates")
    checked = 0
    for name in sorted(os.listdir(tpl)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(tpl, name), encoding="utf-8") as fh:
            data = json.load(fh)
        if name.startswith("project."):
            assert data.get("scenes"), f"{name}: no scenes"
        elif name.startswith("imagetovideo"):
            assert data.get("shots"), f"{name}: no shots"
            for shot in data["shots"]:
                assert shot.get("image"), f"{name}: shot without image"
                assert shot.get("motion") in imagetovideo.MOTIONS, f"{name}: bad motion"
        checked += 1
    assert checked >= 4, f"expected several templates, found {checked}"


# ---------------------------------------------------------------- image -> video
def test_parse_size_presets():
    assert imagetovideo.parse_size("16:9") == (1920, 1080)
    assert imagetovideo.parse_size("9:16") == (1080, 1920)
    assert imagetovideo.parse_size("1280x720") == (1280, 720)
    assert imagetovideo.parse_size([800, 600]) == (800, 600)


def test_motion_expressions_are_valid():
    for motion in imagetovideo.MOTIONS:
        z, x, y = imagetovideo.motion_expr(motion, 5.0, 30, seed=3)
        assert z and x and y
        assert "on/" in z + x + y or motion == "static"
        # no stray placeholders that ffmpeg would reject
        assert "{" not in z + x + y


def test_motion_unknown_raises():
    try:
        imagetovideo.motion_expr("wobble", 5.0, 30)
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown motion")


def test_prepare_image_cover_and_blurpad():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "wide.png")
        visuals.gradient((1600, 500), "#203040", "#B07020").convert("RGB").save(src)
        cover = imagetovideo.prepare_image(src, (1080, 1920), fit="cover")
        assert cover.size == (1080, 1920)
        pad = imagetovideo.prepare_image(src, (1080, 1920), fit="blurpad")
        assert pad.size == (1080, 1920)


def test_text_overlay_renders_hindi():
    with tempfile.TemporaryDirectory() as d:
        p = imagetovideo.text_overlay({"headline": "रात 11 बजे की मेहतान",
                                       "sub": "नतीजा क्यों नहीं?"},
                                      (1920, 1080), vertical=False)
        assert p and os.path.exists(p)
        from PIL import Image
        im = Image.open(p)
        assert im.size == (1920, 1080)
        assert im.getbbox() is not None
        os.unlink(p)


def test_audio_codec_matches_extension():
    """Regression: AAC written into a .wav mislabelled the stream and truncated muxed video."""
    assert "pcm_s16le" in media._audio_codec_for("x.wav")
    assert "aac" in media._audio_codec_for("x.m4a")
    assert "48000" in media._audio_codec_for("x.wav")


def test_loudness_output_keeps_duration_and_rate():
    """Regression: normalisation must stay 48 kHz PCM and not change length."""
    import av
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "tone.wav")
        media.run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                   "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", src], "tone")
        out = os.path.join(d, "norm.wav")
        stats = media.loudness_normalise(src, out)
        assert stats.get("applied") is True
        with av.open(out) as c:
            a = c.streams.audio[0]
            assert a.codec_context.name == "pcm_s16le"
            assert a.codec_context.sample_rate == 48000
            dur = float(c.duration / av.time_base)
            assert abs(dur - 2.0) < 0.15


# ---------------------------------------------------------------- neural vision
def test_models_present():
    import aivision
    have = aivision.available()
    assert have["selfie"], "selfie_segmentation.tflite missing"
    assert have["selfie_landscape"]


def test_person_segmenter_returns_mask():
    import aivision
    from PIL import Image
    seg = aivision.PersonSegmenter()
    img = Image.open(os.path.join(os.path.dirname(HERE), "images", "src_study_desk.jpg")).resize((640, 360))
    mask = seg.mask(img)
    assert mask.shape == (360, 640)
    assert 0.0 <= float(mask.min()) and float(mask.max()) <= 1.0
    assert 0.01 < float((mask > 0.5).mean()) < 0.95


def test_face_finder_detects_face():
    import aivision
    from PIL import Image
    finder = aivision.FaceFinder()
    img = Image.open(os.path.join(os.path.dirname(HERE), "images", "src_study_desk.jpg")).resize((640, 360))
    pts = finder.landmarks(img)
    assert pts is not None and pts.shape == (468, 2)
    box = finder.bbox(img)
    assert box and box[2] > box[0] and box[3] > box[1]


def test_layer_motion_modes():
    for mode in livephoto.MODES:
        (sfg, dxf, dyf), (sbg, dxb, dyb) = livephoto._layer_motion(mode, 0.5, 0.04, 0.01)
        assert sfg > 0 and sbg > 0
        assert abs(sfg - 1.0) < 0.5


def test_paste_keeps_transparency():
    """Regression: pasting without the alpha mask produced a black halo."""
    from PIL import Image
    canvas = Image.new("RGB", (100, 100), (10, 120, 200))
    layer = Image.new("RGBA", (50, 50), (255, 0, 0, 0))
    livephoto._paste_at(canvas, layer, 0, 0)
    assert canvas.getpixel((50, 50)) == (10, 120, 200)


def test_frames_to_video_pipes_frames():
    """Regression: a full ffmpeg stderr pipe deadlocked the encoder."""
    import numpy as np
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "f.mp4")
        frames = [np.full((72, 128, 3), i * 10, dtype=np.uint8) for i in range(15)]
        media.frames_to_video(frames, out, fps=15)
        assert os.path.getsize(out) > 500
        assert abs(media.probe(out).duration - 1.0) < 0.2


def test_requirements_pinned():
    req = os.path.join(os.path.dirname(HERE), "requirements.txt")
    lines = [l.strip() for l in open(req, encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    assert lines and all("==" in l for l in lines)


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
