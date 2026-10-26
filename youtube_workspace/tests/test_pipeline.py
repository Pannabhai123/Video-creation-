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
    tpl = os.path.join(os.path.dirname(HERE), "templates")
    for name in os.listdir(tpl):
        if name.endswith(".json"):
            with open(os.path.join(tpl, name), encoding="utf-8") as fh:
                data = json.load(fh)
            assert "scenes" in data and data["scenes"]


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
