from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests

from .models import SceneSpec

ACCENT_PALETTE = [
    "#38BDF8",  # Sky Cyan
    "#818CF8",  # Indigo
    "#34D399",  # Emerald
    "#FBBF24",  # Amber
    "#F472B6",  # Rose
    "#A78BFA",  # Violet
]

VISUAL_STYLES = ["diagram", "metrics", "timeline", "spotlight"]


def _clean_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_bullets(narration: str, max_bullets: int = 3) -> list[str]:
    sentences = [
        _clean_sentence(s)
        for s in re.split(r"(?<=[.!?])\s+", narration)
        if _clean_sentence(s)
    ]
    bullets: list[str] = []
    for sent in sentences:
        cleaned = re.sub(r"[.!?]+$", "", sent)
        words = cleaned.split()
        if len(words) > 10:
            cleaned = " ".join(words[:10]) + "..."
        if cleaned and len(cleaned) >= 12:
            bullets.append(cleaned)
        if len(bullets) >= max_bullets:
            break
    if not bullets and narration.strip():
        words = narration.strip().split()
        bullets.append(" ".join(words[: min(9, len(words))]))
    return bullets


def _try_openai_script(topic: str, target_duration_sec: float, language: str) -> list[dict[str, Any]] | None:
    """
    Uses OpenAI API ONLY if OPENAI_API_KEY is explicitly configured and reachable.
    Never assumes paid APIs are free or available.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    target_words = max(80, int((target_duration_sec / 60.0) * 145))
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a professional YouTube documentary scriptwriter. "
                            "Return JSON with key 'scenes': list of objects with keys "
                            "'scene_type' ('intro'|'content'|'outro'), 'chapter_title', "
                            "'headline', 'narration', 'bullets' (2-3 strings), 'stat_value', 'stat_label'."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Topic: {topic}\nLanguage: {language}\n"
                            f"Target total spoken words: ~{target_words} words (~{target_duration_sec:.0f}s)."
                        ),
                    },
                ],
                "timeout": 20,
            },
            timeout=20,
        )
        if resp.status_code == 200:
            payload = resp.json()
            import json

            parsed = json.loads(payload["choices"][0]["message"]["content"])
            if isinstance(parsed.get("scenes"), list) and parsed["scenes"]:
                return parsed["scenes"]
    except Exception:
        return None
    return None


def generate_structured_script_from_topic(
    topic: str,
    target_duration_sec: float | None = None,
    language: str = "en",
) -> list[dict[str, Any]]:
    """
    Topic research & structured YouTube script generator.
    Uses configured LLM API if available; otherwise builds a structured multi-chapter
    educational YouTube script scaled to the requested duration.
    """
    eff_duration = target_duration_sec or 45.0
    llm_scenes = _try_openai_script(topic, eff_duration, language)
    if llm_scenes:
        return llm_scenes

    clean_topic = topic.strip().rstrip(".")
    # Scale number of content chapters based on target duration
    if eff_duration <= 32:
        num_content = 2
    elif eff_duration <= 75:
        num_content = 3
    elif eff_duration <= 180:
        num_content = 5
    else:
        num_content = min(12, max(6, int(eff_duration // 35)))

    chapter_archetypes = [
        (
            "Core Fundamentals",
            f"Why {clean_topic} Matters Today",
            f"At its foundation, {clean_topic} transforms complex workflows into repeatable, measurable systems. "
            f"Understanding the core architecture helps creators and engineers avoid bottlenecks early.",
            [
                f"Foundational principles behind {clean_topic}",
                "Eliminates manual bottlenecks with structured design",
                "Scales reliably from prototypes to full production",
            ],
            "3.4x",
            "Workflow Throughput",
        ),
        (
            "System Architecture",
            "Building a Reliable Production Pipeline",
            f"A professional {clean_topic} setup separates planning, asset preparation, execution, and quality assurance. "
            f"Modular stages let every component upgrade independently without breaking downstream output.",
            [
                "Modular stages isolate errors and speed iteration",
                "Deterministic presets guarantee consistent quality",
                "Automated validation catches issues before publishing",
            ],
            "99.8%",
            "Pipeline Consistency",
        ),
        (
            "Optimization & Quality",
            "Performance Tuning & Real-World Best Practices",
            f"To get broadcast-grade results with {clean_topic}, focus on balanced pacing, clean signal processing, "
            f"and memory-efficient execution across every stage of delivery.",
            [
                "Memory-safe batching handles long-form workloads",
                "Standardized loudness and visual contrast boost retention",
                "Resumable checkpoints protect multi-scene builds",
            ],
            "-14 LUFS",
            "Broadcast Standard",
        ),
        (
            "Automation & Scaling",
            "Automating Repeatable Long-Form Output",
            f"Once your {clean_topic} templates are configured, reusable presets turn hours of repetitive setup "
            f"into a single automated command while preserving creative control.",
            [
                "Reusable project templates standardize asset folders",
                "Data-driven graphics adapt automatically to scripts",
                "Consistent branding strengthens viewer recognition",
            ],
            "1080p+",
            "Master Export Ready",
        ),
        (
            "Common Pitfalls",
            "Mistakes to Avoid in Production",
            f"Many teams struggle with {clean_topic} when they skip audio normalization, overlook caption timing, "
            f"or rely on fragile manual steps that fail under deadline pressure.",
            [
                "Never skip loudness and peak level verification",
                "Keep captions synchronized to natural phrase breaks",
                "Verify every rendered deliverable programmatically",
            ],
            "Zero",
            "Unchecked Errors",
        ),
        (
            "Future Roadmap",
            f"Where {clean_topic} Is Heading Next",
            f"Looking ahead, {clean_topic} continues to combine open-source engineering tools with smart automation, "
            f"giving independent creators studio-level capabilities right from their workstation.",
            [
                "Hybrid open-source stacks reduce recurring costs",
                "Local-first workflows protect creative ownership",
                "Extensible APIs connect optional cloud models cleanly",
            ],
            "100%",
            "Local Control",
        ),
    ]

    scenes: list[dict[str, Any]] = [
        {
            "scene_type": "intro",
            "chapter_title": "Introduction",
            "headline": clean_topic,
            "narration": (
                f"Welcome back! In this deep dive, we are exploring {clean_topic}, "
                f"breaking down the architecture, key techniques, and practical workflow step by step."
            ),
            "bullets": [
                f"Complete breakdown of {clean_topic}",
                "Practical architecture & optimization guide",
            ],
            "stat_value": "GUIDE",
            "stat_label": "Step-by-Step Breakdown",
        }
    ]

    for idx in range(num_content):
        chap, head, narr, bulls, sval, slabel = chapter_archetypes[idx % len(chapter_archetypes)]
        scenes.append(
            {
                "scene_type": "content",
                "chapter_title": chap,
                "headline": head,
                "narration": narr,
                "bullets": bulls,
                "stat_value": sval,
                "stat_label": slabel,
            }
        )

    scenes.append(
        {
            "scene_type": "outro",
            "chapter_title": "Summary & Next Steps",
            "headline": "Subscribe & Continue Exploring",
            "narration": (
                f"Thanks for watching this complete guide on {clean_topic}. "
                f"Subscribe to the channel and check out the next video on screen to keep building."
            ),
            "bullets": [
                "Subscribe for weekly engineering deep dives",
                "Watch the recommended episode on screen",
            ],
            "stat_value": "NEXT",
            "stat_label": "Watch Recommended Video",
        }
    )
    return scenes


def parse_markdown_script(script_text: str, topic: str) -> list[dict[str, Any]]:
    """
    Parses a user-supplied Markdown or plain-text script into structured scenes.
    Supports `## Heading` sections and `- bullet` lines; falls back to paragraph splitting.
    """
    lines = [ln.rstrip() for ln in script_text.strip().splitlines()]
    sections: list[dict[str, Any]] = []
    current_title = ""
    current_bullets: list[str] = []
    current_paras: list[str] = []

    def flush_section() -> None:
        nonlocal current_title, current_bullets, current_paras
        narration = " ".join(current_paras).strip()
        if not narration and not current_bullets:
            return
        if not narration and current_bullets:
            narration = ". ".join(current_bullets) + "."
        title = current_title or (f"Part {len(sections) + 1}")
        bullets = current_bullets[:] if current_bullets else _extract_bullets(narration, max_bullets=3)
        sections.append(
            {
                "chapter_title": title,
                "headline": title,
                "narration": narration,
                "bullets": bullets,
            }
        )
        current_title = ""
        current_bullets = []
        current_paras = []

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        heading_match = re.match(r"^#{1,3}\s+(.+)$", stripped)
        scene_tag_match = re.match(r"^\[SCENE[:\s-]+(.+?)\]$", stripped, flags=re.IGNORECASE)
        if heading_match or scene_tag_match:
            flush_section()
            current_title = (heading_match.group(1) if heading_match else scene_tag_match.group(1)).strip()
        elif stripped.startswith(("- ", "* ")):
            current_bullets.append(stripped[2:].strip())
        else:
            current_paras.append(stripped)

    flush_section()

    # If plain text had no headings, split paragraphs into scenes
    if len(sections) <= 1 and "\n\n" in script_text.strip():
        paras = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", script_text.strip()) if p.strip()]
        if len(paras) >= 2:
            sections = []
            for idx, para in enumerate(paras):
                title = "Introduction" if idx == 0 else ("Conclusion" if idx == len(paras) - 1 else f"Key Insight {idx}")
                sections.append(
                    {
                        "chapter_title": title,
                        "headline": title if idx > 0 else topic,
                        "narration": para,
                        "bullets": _extract_bullets(para, max_bullets=3),
                    }
                )

    if not sections:
        return generate_structured_script_from_topic(topic)

    # Tag first and last scenes appropriately if >= 3 sections
    for i, sec in enumerate(sections):
        if i == 0 and len(sections) >= 2:
            sec["scene_type"] = "intro"
            if sec["headline"].lower() in ("introduction", "intro", "part 1"):
                sec["headline"] = topic
        elif i == len(sections) - 1 and len(sections) >= 3:
            sec["scene_type"] = "outro"
        else:
            sec["scene_type"] = "content"
        sec.setdefault("stat_value", f"0{i + 1}")
        sec.setdefault("stat_label", sec["chapter_title"])

    return sections


def build_storyboard(
    topic: str,
    script_text: str | None = None,
    visual_assets: list[Path] | None = None,
    target_duration_sec: float | None = None,
    language: str = "en",
    words_per_minute: float = 150.0,
) -> list[SceneSpec]:
    """
    Converts a topic or user script + optional visual assets into a complete scene-by-scene storyboard.
    """
    raw_scenes = (
        parse_markdown_script(script_text, topic=topic)
        if (script_text and script_text.strip())
        else generate_structured_script_from_topic(topic, target_duration_sec=target_duration_sec, language=language)
    )

    assets = [str(p.resolve()) for p in (visual_assets or []) if p.exists()]
    content_asset_idx = 0

    specs: list[SceneSpec] = []
    for idx, item in enumerate(raw_scenes):
        stype = item.get("scene_type", "content")
        narration = _clean_sentence(item.get("narration", ""))
        word_count = max(1, len(narration.split()))
        est_dur = max(3.6, round((word_count / max(90.0, words_per_minute)) * 60.0 + 0.8, 2))

        assigned_asset: str | None = None
        if assets and stype == "content" and content_asset_idx < len(assets):
            assigned_asset = assets[content_asset_idx]
            content_asset_idx += 1
        elif assets and len(raw_scenes) <= 2 and idx < len(assets):
            assigned_asset = assets[idx]

        specs.append(
            SceneSpec(
                scene_id=f"scene_{idx + 1:02d}",
                index=idx,
                scene_type=stype,
                chapter_title=item.get("chapter_title", f"Chapter {idx + 1}"),
                headline=item.get("headline", topic),
                narration=narration,
                bullets=list(item.get("bullets", []))[:4],
                visual_asset=assigned_asset,
                visual_style=VISUAL_STYLES[idx % len(VISUAL_STYLES)],
                stat_value=str(item.get("stat_value", f"0{idx + 1}")),
                stat_label=str(item.get("stat_label", item.get("chapter_title", "Key Metric"))),
                accent_color=ACCENT_PALETTE[idx % len(ACCENT_PALETTE)],
                duration_sec=est_dur,
            )
        )

    # Optionally scale non-voiced padding if user requested a longer preferred duration
    if target_duration_sec and specs:
        current_total = sum(s.duration_sec for s in specs)
        if target_duration_sec > current_total * 1.05:
            extra_per_scene = (target_duration_sec - current_total) / len(specs)
            for s in specs:
                s.duration_sec = round(s.duration_sec + extra_per_scene, 2)

    cursor = 0.0
    for s in specs:
        s.start_sec = round(cursor, 3)
        cursor += s.duration_sec
        s.end_sec = round(cursor, 3)

    return specs
