"""
captions.py — Hindi subtitle builder: narration text -> SRT + styled ASS.

Approach
--------
Because every video is scripted, subtitles are generated from the *known*
narration text instead of speech recognition. Timings are distributed across a
scene's real narration duration, weighted by syllable-ish length, and can be
refined against detected silences so cues break at natural pauses.

This gives better Hindi accuracy than ASR (Devanagari ASR needs a model that
cannot be downloaded in this sandbox) and needs no manual typing.

Outputs:
  * .srt   — YouTube upload / editing
  * .ass   — burned-in styled captions (works with FFmpeg's libass)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import pysubs2
import srt

# Devanagari reads wider than Latin; these are comfortable YouTube mobile values.
MAX_LINE_CHARS = 38
MAX_LINES = 2
MIN_CUE = 1.0
MAX_CUE = 6.0
MAX_CPS = 16.0  # characters per second (Hindi guideline ~14–17)

_SENT_END = re.compile(r"(?<=[।!?\.])\s+")
_CLAUSE = re.compile(r"(?<=[,;:—–])\s+")


def _hard_split(text: str, limit: int = MAX_LINE_CHARS * MAX_LINES) -> list[str]:
    """Split an over-long chunk at a clause boundary if possible, else at a space."""
    if len(text) <= limit:
        return [text]
    parts = _CLAUSE.split(text)
    if len(parts) > 1:
        out, cur = [], ""
        for p in parts:
            cand = f"{cur} {p}".strip()
            if len(cand) <= limit:
                cur = cand
            else:
                if cur:
                    out.append(cur)
                cur = p
        if cur:
            out.append(cur)
        result = []
        for chunk in out:
            result.extend(_hard_split(chunk, limit) if len(chunk) > limit else [chunk])
        return result
    words, out, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= limit:
            cur = cand
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def chunk_text(text: str) -> list[str]:
    """Split narration into subtitle-sized cues (sentence-first, then clauses)."""
    cues: list[str] = []
    for sentence in _SENT_END.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        cues.extend(_hard_split(sentence))
    return [c for c in cues if c]


def _weight(text: str) -> float:
    """Rough speaking-time weight: Devanagari ~= 1.0/char, digits and Latin read slower."""
    w = 0.0
    for ch in text:
        if "\u0900" <= ch <= "\u097F":
            w += 1.0
        elif ch.isdigit():
            w += 1.4
        elif ch.isalpha():
            w += 1.15
        elif ch in "।,;:—–":
            w += 1.6  # pauses
        elif ch in ".!?":
            w += 2.0
        else:
            w += 0.4
    return max(w, 1.0)


@dataclass
class Cue:
    start: float
    end: float
    text: str


def time_scene(text: str, start: float, duration: float, pause_pad: float = 0.0) -> list[Cue]:
    """Distribute one scene's narration text across its measured audio duration."""
    chunks = chunk_text(text)
    if not chunks:
        return []
    usable = max(0.5, duration - pause_pad)
    weights = [_weight(c) for c in chunks]
    total = sum(weights)
    cues: list[Cue] = []
    t = start
    for chunk, w in zip(chunks, weights):
        d = usable * w / total
        d = max(MIN_CUE, min(MAX_CUE, d))
        # respect readability: never faster than MAX_CPS
        d = max(d, len(chunk) / MAX_CPS)
        cues.append(Cue(round(t, 3), round(t + d, 3), chunk))
        t += d
    # clamp to scene window and fix overlaps
    end_limit = start + duration + 0.25
    for i, c in enumerate(cues):
        if c.end > end_limit:
            c.end = end_limit
        if i and c.start < cues[i - 1].end:
            c.start = cues[i - 1].end
        if c.end <= c.start:
            c.end = c.start + 0.6
    return cues


def refine_with_silences(cues: list[Cue], silences: list[tuple[float, float]],
                         scene_start: float, tolerance: float = 0.45) -> list[Cue]:
    """Snap cue boundaries onto the nearest detected pause (keeps audio and text in sync)."""
    if not silences:
        return cues
    mids = [((a + b) / 2.0) for a, b in silences]
    for i in range(len(cues) - 1):
        boundary = cues[i].end
        nearest = min(mids, key=lambda m: abs(m - boundary), default=None)
        if nearest is not None and abs(nearest - boundary) <= tolerance and nearest > cues[i].start + 0.5:
            cues[i].end = round(nearest, 3)
            cues[i + 1].start = round(nearest, 3)
    return cues


def write_srt(cues: list[Cue], dst: str) -> str:
    subs = [
        srt.Subtitle(index=i + 1, start=srt.timedelta(seconds=c.start),
                     end=srt.timedelta(seconds=c.end), content=c.text)
        for i, c in enumerate(cues)
    ]
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(srt.compose(subs))
    return dst


def write_ass(cues: list[Cue], dst: str, style: dict | None = None,
              play_res: tuple[int, int] = (1920, 1080)) -> str:
    """Styled ASS for burn-in. Defaults: Devanagari-safe font, outline, bottom-centre."""
    s = {
        "font": "Noto Sans Devanagari",
        "size": 64,
        "primary": "&H00FFFFFF",   # white
        "secondary": "&H0000D7FF", # yellow (highlight)
        "outline_colour": "&H00140A0A",
        "back_colour": "&H80000000",
        "bold": 1,
        "outline": 3.2,
        "shadow": 1.2,
        "margin_v": 66,
        "margin_h": 96,
        "border_style": 1,
        "alignment": 2,
    }
    s.update(style or {})
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"], subs.info["PlayResY"] = play_res
    subs.info["WrapStyle"] = "0"
    subs.info["ScaledBorderAndShadow"] = "yes"
    st = pysubs2.SSAStyle()
    st.fontname = s["font"]
    st.fontsize = s["size"]
    st.primarycolor = _ass_color(s["primary"])
    st.secondarycolor = _ass_color(s["secondary"])
    st.outlinecolor = _ass_color(s["outline_colour"])
    st.backcolor = _ass_color(s["back_colour"])
    st.bold = bool(s["bold"])
    st.outline = float(s["outline"])
    st.shadow = float(s["shadow"])
    st.borderstyle = int(s["border_style"])
    st.alignment = int(s["alignment"])
    st.marginv = int(s["margin_v"])
    st.marginl = int(s["margin_h"])
    st.marginr = int(s["margin_h"])
    subs.styles["Default"] = st
    for c in cues:
        ev = pysubs2.SSAEvent(start=int(c.start * 1000), end=int(c.end * 1000),
                              text=c.text.replace("\n", r"\N"), style="Default")
        subs.append(ev)
    subs.save(dst, format_="ass")
    return dst


def _ass_color(value: str) -> "pysubs2.Color":
    """Parse ASS colour (&HAABBGGRR) into a pysubs2.Color (alpha 0 = opaque)."""
    h = value.strip().lstrip("&").lstrip("H")
    a = int(h[0:2], 16) if len(h) >= 8 else 0
    b = int(h[-6:-4], 16); g = int(h[-4:-2], 16); r = int(h[-2:], 16)
    return pysubs2.Color(r, g, b, a)


def cps_report(cues: list[Cue]) -> dict:
    bad = [c.text for c in cues if c.end > c.start and len(c.text) / (c.end - c.start) > MAX_CPS + 2]
    return {
        "cues": len(cues),
        "total_chars": sum(len(c.text) for c in cues),
        "mean_cps": round(sum(len(c.text) / max(c.end - c.start, 0.01) for c in cues) / max(len(cues), 1), 2),
        "too_fast": bad,
        "overlong_lines": [c.text for c in cues if any(len(l) > MAX_LINE_CHARS + 8 for l in c.text.split("\n"))],
    }


def build_for_scenes(scenes: list[dict], dst_dir: str, scene_audio: dict[str, str] | None = None,
                     style: dict | None = None, play_res: tuple[int, int] = (1920, 1080),
                     refine: bool = True) -> dict:
    """
    scenes: [{id, narration, start, duration}]  (already on the final timeline)
    Returns paths + a validation report.
    """
    import media  # local import to avoid a hard dependency at import time

    os.makedirs(dst_dir, exist_ok=True)
    all_cues: list[Cue] = []
    for sc in scenes:
        cues = time_scene(sc["narration"], sc["start"], sc["duration"])
        if refine and scene_audio and sc["id"] in scene_audio:
            path = scene_audio[sc["id"]]
            if path and os.path.exists(path):
                sil = [(a + sc["start"], b + sc["start"]) for a, b in media.silence_points(path)]
                cues = refine_with_silences(cues, sil, sc["start"])
        all_cues.extend(cues)

    srt_path = os.path.join(dst_dir, "hindi.srt")
    ass_path = os.path.join(dst_dir, "hindi.ass")
    write_srt(all_cues, srt_path)
    write_ass(all_cues, ass_path, style=style, play_res=play_res)
    return {"srt": srt_path, "ass": ass_path, "cues": len(all_cues), "report": cps_report(all_cues)}
