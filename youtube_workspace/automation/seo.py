"""
seo.py — YouTube publishing pack for Hindi educational videos.

Generates, from a project file or plain inputs:
  * title options that respect the 100-char limit (mobile truncation ~60)
  * description: hook, value list, timestamps/chapters, sources, hashtags, CTA
  * keywords/tags under YouTube's 500-character tag budget
  * hashtags (3 shown above the title)
  * chapter markers from scene timings (YouTube needs >= 3 chapters, 10s+ each)
  * Shorts ideas derived from the strongest scenes

    python seo.py pack ../projects/demo/project.json --out ../projects/demo/publish.md
    python seo.py pack project.json --topic "2 minute rule" --title "2 मिनट का नियम"
"""

from __future__ import annotations

import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHANNEL = "Ronny Raj"


# ---------------------------------------------------------------- titles
TITLE_PATTERNS = [
    "{topic} | हिन्दी में {angle}",
    "{topic} — {promise}",
    "{topic}: {angle} (Hindi)",
    "ये {topic} का सच है — {promise}",
    "{topic} सीखने का सबसे तेज़ तरीका | {angle}",
    "{topic} | {angle} | हिन्दी बुक समरी",
]


def titles(topic: str, angle: str = "पूरी कहानी", promise: str = "आसान भाषा में",
           extra: list[str] | None = None, limit: int = 12) -> list[dict]:
    out = list(extra or [])
    for tpl in TITLE_PATTERNS:
        out.append(tpl.format(topic=topic, angle=angle, promise=promise))
    seen, result = set(), []
    for t in out:
        t = re.sub(r"\s+", " ", t).strip()
        if t in seen:
            continue
        seen.add(t)
        result.append({
            "title": t,
            "chars": len(t),
            "mobile_ok": len(t) <= 60,
            "under_limit": len(t) <= 100,
        })
    return result[:limit]


# ---------------------------------------------------------------- chapters
def chapters(scenes: list[dict], cps: float = 13.5, pad: float = 0.45) -> list[str]:
    """
    YouTube chapter list. Must start at 00:00 and every chapter needs >= 10 s,
    so short scenes are merged into the previous chapter instead of emitted.
    """
    resolved = _resolve_timings(scenes, cps, pad)
    merged: list[tuple[float, str]] = []
    for start, dur, label in resolved:
        if merged and (start - merged[-1][0]) < 10.0:
            continue  # too close to the previous marker; YouTube would drop it
        merged.append((start, label))
    return [f"{_ts(start)} {label}" for start, label in merged]


def _resolve_timings(scenes: list[dict], cps: float = 13.5,
                     pad: float = 0.45) -> list[tuple[float, float, str]]:
    """Use real timings when the project carries them, otherwise estimate speech length."""
    out: list[tuple[float, float, str]] = []
    t = 0.0
    for sc in scenes:
        start = float(sc.get("start", t))
        dur = sc.get("duration")
        if not dur:
            chars = len(str(sc.get("narration", "")).replace(" ", ""))
            dur = round(chars / cps + pad, 2) if chars else 5.0
        label = (sc.get("visual", {}).get("title")
                 or sc.get("title")
                 or _short_label(sc.get("narration", ""))
                 or sc.get("id", "भाग"))
        out.append((start, float(dur), label))
        t = start + float(dur)
    return out


def _short_label(text: str, limit: int = 42) -> str:
    """Take the first clause of the narration, cut on a word boundary."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    first = re.split(r"[।?!,;—–]", text)[0].strip() or text
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _ts(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------- keywords
BASE_TAGS = ["hindi", "book summary in hindi", "self improvement hindi", "hindi motivation",
             "personal development", "productivity hindi", "study tips hindi",
             "educational video hindi", "hindi podcast", "life lessons hindi"]


def tags(topic_tags: list[str], budget: int = 480) -> dict:
    all_tags: list[str] = []
    for t in [*topic_tags, *BASE_TAGS]:
        t = t.strip().lower()
        if t and t not in all_tags:
            all_tags.append(t)
    used, final = 0, []
    for t in all_tags:
        cost = len(t) + 1
        if used + cost > budget:
            continue
        final.append(t)
        used += cost
    return {"tags": final, "characters": used, "budget": budget}


def hashtags(topic_tags: list[str], n: int = 3) -> list[str]:
    base = ["#हिन्दी", "#BookSummary", "#SelfImprovement"]
    extra = ["#" + re.sub(r"\s+", "", t.title()) for t in topic_tags[:4]]
    seen, out = set(), []
    for h in [*base, *extra]:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:n + 3]


# ---------------------------------------------------------------- description
def description(topic: str, summary: str, project: dict | None = None,
                sources: list[str] | None = None, cta: str | None = None) -> str:
    p = (project or {}).get("project", {})
    scenes = (project or {}).get("scenes", [])
    lines = [summary.strip(), ""]
    if scenes:
        lines.append("⏱️ इस वीडियो में:")
        lines += chapters(scenes)
        lines.append("")
    if sources:
        lines.append("📚 स्रोत / References:")
        lines += [f"• {s}" for s in sources]
        lines.append("")
    lines += [
        cta or f"🔔 ऐसी ही वीडियोज़ के लिए चैनल {CHANNEL} को सब्सक्राइब करें।",
        "",
        "इस वीडियो में दी गई जानकारी शिक्षा और जागरूकता के लिए है। किताबों के विचारों को "
        "अपने शब्दों में समझाया गया है, मूल पाठ उद्धृत नहीं किया गया है।",
        "",
        " ".join(hashtags([w for w in re.split(r"[\s,]+", topic) if len(w) > 2])),
    ]
    return "\n".join(lines)


def shorts_ideas(scenes: list[dict], n: int = 5) -> list[dict]:
    ranked = sorted(scenes, key=lambda s: -len(s.get("narration", "")))
    ideas = []
    for sc in ranked[:n]:
        text = re.sub(r"\s+", " ", sc.get("narration", "")).strip()
        hook = text.split("।")[0][:70] or sc.get("id", "")
        start = float(sc.get("start", 0))
        dur = float(sc.get("duration") or 0) or round(len(text.replace(" ", "")) / 13.5, 2)
        cut = min(dur, 58)
        ideas.append({
            "scene": sc.get("id"),
            "start": _ts(start),
            "seconds": round(cut),
            "hook": hook,
            "vertical_cut": f"{_ts(start)} → {_ts(start + cut)}",
        })
    return ideas


# ---------------------------------------------------------------- pack
def build_pack(project_path: str | None, topic: str, angle: str, promise: str,
               summary: str | None = None, topic_tags: list[str] | None = None,
               sources: list[str] | None = None) -> dict:
    project = None
    if project_path:
        with open(project_path, encoding="utf-8") as fh:
            project = json.load(fh)
    raw_scenes = (project or {}).get("scenes", [])
    # enrich with resolved timings so chapters and Shorts cuts reference real times
    scenes = []
    for (start, dur, _label), sc in zip(_resolve_timings(raw_scenes), raw_scenes):
        scenes.append({**sc, "start": start, "duration": dur})
    topic_tags = topic_tags or [topic]
    pack = {
        "titles": titles(topic, angle, promise,
                         extra=[(project or {}).get("project", {}).get("title")] if project else None),
        "description": description(topic, summary or f"{topic} — {angle}। {promise}.",
                                  project, sources),
        "keywords": tags(topic_tags),
        "hashtags": hashtags(topic_tags),
        "chapters": chapters(scenes) if scenes else [],
        "shorts_ideas": shorts_ideas(scenes) if scenes else [],
    }
    return pack


def to_markdown(pack: dict, topic: str) -> str:
    md = [f"# Publish pack — {topic}", "", "## Title options", ""]
    md += ["| Title | Chars | Mobile (≤60) |", "|---|---|---|"]
    for t in pack["titles"]:
        md.append(f"| {t['title']} | {t['chars']} | {'✅' if t['mobile_ok'] else '—'} |")
    md += ["", "**Recommended:** the first option that is `mobile_ok` and contains the main "
              "keyword — the first 60 characters decide the click on mobile.", ""]
    if pack["chapters"]:
        md += ["## Chapters", "```"] + pack["chapters"] + ["```", ""]
    md += ["## Description", "```", pack["description"], "```", ""]
    k = pack["keywords"]
    md += [f"## Keywords ({k['characters']}/{k['budget']} chars)", "```",
           ", ".join(k["tags"]), "```", ""]
    md += ["## Hashtags", " ".join(pack["hashtags"]), ""]
    if pack["shorts_ideas"]:
        md += ["## Shorts ideas", "| Scene | Cut | Length | Hook |", "|---|---|---|---|"]
        for s in pack["shorts_ideas"]:
            md.append(f"| {s['scene']} | {s['vertical_cut']} | {s['seconds']}s | {s['hook']} |")
        md.append("")
    md += ["## Upload checklist", "- [ ] 1280x720 thumbnail, text readable at 168px wide",
           "- [ ] Hindi subtitles uploaded (.srt)", "- [ ] Chapters pasted in description",
           "- [ ] Hashtags (first 3 shown)", "- [ ] End screen + cards added",
           "- [ ] Playlist assigned", "- [ ] Premiere/publish time set for your audience", ""]
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a YouTube publishing pack")
    ap.add_argument("cmd", nargs="?", default="pack", choices=["pack"])
    ap.add_argument("project", nargs="?", help="project JSON (optional)")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--angle", default="पूरी कहानी")
    ap.add_argument("--promise", default="आसान भाषा में")
    ap.add_argument("--summary", default=None)
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--source", action="append", default=[])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pack = build_pack(args.project, args.topic, args.angle, args.promise,
                      args.summary, args.tag or None, args.source or None)
    md = to_markdown(pack, args.topic)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        json_path = os.path.splitext(args.out)[0] + ".json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(pack, fh, ensure_ascii=False, indent=2)
        print(args.out)
        print(json_path)
    else:
        print(md)


if __name__ == "__main__":
    main()
