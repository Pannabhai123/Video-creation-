from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from .audio_engine import build_voiceover_and_master_audio
from .config import (
    REPO_ROOT,
    get_resolved_export_preset,
    load_workflow_defaults,
    resolve_preset_name,
)
from .graphics import generate_youtube_thumbnail
from .models import ProjectSpec, RenderArtifacts, SceneSpec
from .renderer import render_project_video
from .scriptwriter import build_storyboard
from .subtitles import generate_subtitles_for_project

# Import QA verifier from scripts/verify_video.py
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from verify_video import verify_video  # noqa: E402


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug[:48] or "youtube_video"


def _format_yt_chapter_ts(sec: float) -> str:
    total = max(0, int(round(sec)))
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    if hh > 0:
        return f"{hh}:{mm:02d}:{ss:02d}"
    return f"{mm:02d}:{ss:02d}"


def write_youtube_metadata(
    project: ProjectSpec,
    scenes: list[SceneSpec],
    preset: dict[str, Any],
    out_path: Path,
) -> Path:
    chapters = [f"{_format_yt_chapter_ts(s.start_sec)} {s.chapter_title}" for s in scenes]
    # YouTube requires first chapter to start at 00:00
    if chapters and not chapters[0].startswith("00:00"):
        chapters[0] = "00:00 " + (scenes[0].chapter_title if scenes else "Introduction")

    tags = [w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", project.topic)][:12]
    tags_line = ", ".join(dict.fromkeys([*tags, "tutorial", "engineering", "automation"]))

    content = f"""TITLE:
{project.video_title}

SUBTITLE:
{project.video_subtitle}

DESCRIPTION:
{project.video_subtitle}

In this video from {project.channel_name}, we cover {project.topic} step by step with practical insights and architecture breakdowns.

CHAPTERS:
{chr(10).join(chapters)}

EXPORT SPECIFICATION:
Preset: {preset['name']} ({preset['width']}x{preset['height']} @ {preset['fps']} FPS, H.264 + AAC, -14 LUFS)
Subtitle Language: {project.language}

TAGS:
{tags_line}
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path


def scaffold_project_template(project_dir: Path, topic: str = "My Next YouTube Deep Dive") -> Path:
    """
    Creates a clean reusable folder structure for a new YouTube long-form project.
    """
    for sub in ("assets/voiceover", "assets/visuals", "assets/music", "subtitles", "thumbnails", "exports"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    sample_script = f"""# Introduction
Welcome back to the channel! Today we are exploring {topic} from first principles to real-world execution.
- Complete architectural overview of {topic}
- Practical techniques you can apply immediately

## Core Architecture
Every reliable workflow separates planning, asset organization, automated processing, and quality verification.
- Clean separation of concerns across stages
- Repeatable configuration eliminates manual mistakes
- Built-in diagnostics keep long-form builds reliable

## Optimization & Delivery
Balancing visual clarity, crisp vocal intelligibility, and standardized loudness ensures strong viewer retention.
- Broadcast -14 LUFS audio normalization
- Synchronized captions improve accessibility and retention
- High-profile H.264 MP4 export for fast YouTube processing

## Conclusion & Next Steps
Thanks for watching this breakdown of {topic}! Subscribe and check out the recommended video on screen to continue learning.
- Subscribe for upcoming long-form tutorials
- Watch the next deep dive on screen
"""
    script_file = project_dir / "script.md"
    if not script_file.exists():
        script_file.write_text(sample_script, encoding="utf-8")

    manifest = {
        "project_name": project_dir.name,
        "topic": topic,
        "video_title": topic,
        "video_subtitle": f"A Complete Step-by-Step Guide to {topic}",
        "script_file": "script.md",
        "voiceover_file": None,  # Place .wav/.mp3 in assets/voiceover/ and reference here, or leave null for local TTS
        "music_file": None,      # Place royalty-free track in assets/music/, or leave null for procedural ambient music
        "visuals_dir": "assets/visuals",
        "preferred_duration_sec": None,
        "subtitle_language": "hi",
        "output_resolution": "1080p",
        "engine": "auto",
        "burn_subtitles": True,
        "embed_soft_subtitles": True,
    }
    manifest_path = project_dir / "project.yaml"
    if not manifest_path.exists():
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    return manifest_path


def organize_and_build_video(
    topic: str,
    project_dir: Path,
    script_text_or_path: str | Path | None = None,
    voiceover_path: Path | None = None,
    music_path: Path | None = None,
    visual_paths: list[Path] | None = None,
    preferred_duration_sec: float | None = None,
    subtitle_language: str = "hi",
    output_resolution: str = "1080p",
    engine: str | None = None,
    video_title: str | None = None,
    video_subtitle: str | None = None,
    episode_badge: str = "COMPLETE GUIDE",
    burn_subtitles: bool = True,
    embed_soft_subtitles: bool = True,
    final_filename: str | None = None,
    clean_work_segments: bool = False,
) -> RenderArtifacts:
    """
    End-to-end automated YouTube video production pipeline:
    1. Organizes supplied script, voiceover, music, and visual assets into `project_dir`
    2. Generates/parses script & builds scene-by-scene storyboard
    3. Synthesizes or denoises/integrates voiceover + auto-ducked copyright-safe music (-14 LUFS)
    4. Generates synchronized SRT, WebVTT & styled ASS subtitles
    5. Generates 1280x720 & 1920x1080 YouTube thumbnails
    6. Renders video via Hybrid Remotion + MoviePy + OpenCV + FFmpeg engine using YouTube Export Preset
    7. Runs automated QA verification on the rendered MP4
    """
    defaults = load_workflow_defaults()
    preset_name = resolve_preset_name(output_resolution)
    preset = get_resolved_export_preset(preset_name)

    # Create organized directory layout
    vo_dir = project_dir / "assets" / "voiceover"
    vis_dir = project_dir / "assets" / "visuals"
    mus_dir = project_dir / "assets" / "music"
    sub_dir = project_dir / "subtitles"
    thumb_dir = project_dir / "thumbnails"
    export_dir = project_dir / "exports"
    work_dir = project_dir / "work"

    for d in (vo_dir, vis_dir, mus_dir, sub_dir, thumb_dir, export_dir, work_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. Organize supplied assets cleanly into project workspace
    script_text: str | None = None
    if script_text_or_path is not None:
        is_file_ref = isinstance(script_text_or_path, Path) or (
            "\n" not in str(script_text_or_path) and len(str(script_text_or_path)) < 255
        )
        p_candidate = Path(str(script_text_or_path)) if is_file_ref else None
        if p_candidate is not None and p_candidate.exists() and p_candidate.is_file():
            script_text = p_candidate.read_text(encoding="utf-8")
            dst_script = project_dir / "script.md"
            if p_candidate.resolve() != dst_script.resolve():
                shutil.copy2(p_candidate, dst_script)
        else:
            script_text = str(script_text_or_path)
            (project_dir / "script.md").write_text(script_text, encoding="utf-8")

    organized_vo: Path | None = None
    if voiceover_path and voiceover_path.exists():
        organized_vo = vo_dir / voiceover_path.name
        if voiceover_path.resolve() != organized_vo.resolve():
            shutil.copy2(voiceover_path, organized_vo)

    organized_music: Path | None = None
    if music_path and music_path.exists():
        organized_music = mus_dir / music_path.name
        if music_path.resolve() != organized_music.resolve():
            shutil.copy2(music_path, organized_music)

    organized_visuals: list[Path] = []
    valid_vis_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".mp4", ".mov", ".mkv", ".webm"}
    for idx, vp in enumerate(visual_paths or []):
        if vp.exists() and vp.is_dir():
            for child in sorted(vp.iterdir()):
                if child.is_file() and child.suffix.lower() in valid_vis_exts:
                    dst = vis_dir / child.name
                    if child.resolve() != dst.resolve():
                        shutil.copy2(child, dst)
                    organized_visuals.append(dst)
        elif vp.exists() and vp.is_file() and vp.suffix.lower() in valid_vis_exts:
            dst = vis_dir / f"{idx + 1:02d}_{vp.name}" if vp.parent.resolve() != vis_dir.resolve() else vp
            if vp.resolve() != dst.resolve():
                shutil.copy2(vp, dst)
            organized_visuals.append(dst)

    # 2. Build Storyboard
    scenes = build_storyboard(
        topic=topic,
        script_text=script_text,
        visual_assets=organized_visuals,
        target_duration_sec=preferred_duration_sec,
        language=subtitle_language,
        words_per_minute=float(defaults["narration"].get("words_per_minute", 150)),
    )

    if not script_text:
        # Save generated script as Markdown for user inspection/reuse
        md_lines = [f"# {video_title or topic}", ""]
        for s in scenes:
            md_lines.append(f"## {s.chapter_title}")
            md_lines.append(s.narration)
            for b in s.bullets:
                md_lines.append(f"- {b}")
            md_lines.append("")
        (project_dir / "script.md").write_text("\n".join(md_lines), encoding="utf-8")

    chan = defaults.get("channel", {})
    selected_engine = engine or defaults.get("rendering", {}).get("engine", "hybrid")

    project = ProjectSpec(
        project_name=project_dir.name,
        topic=topic,
        video_title=video_title or topic,
        video_subtitle=video_subtitle or f"Complete Guide & Architecture Breakdown: {topic}",
        channel_name=chan.get("name", "Nexus Tech Studio"),
        channel_tagline=chan.get("tagline", "Deep-Dive Engineering & Automation"),
        episode_badge=episode_badge,
        language=subtitle_language,
        target_duration_sec=preferred_duration_sec,
        export_preset=preset_name,
        engine=selected_engine,
        accent_color=chan.get("accent_color", "#38BDF8"),
        secondary_color=chan.get("secondary_color", "#818CF8"),
        voiceover_path=str(organized_vo) if organized_vo else None,
        music_path=str(organized_music) if organized_music else None,
        burn_subtitles=burn_subtitles,
        embed_soft_subtitles=embed_soft_subtitles,
        scenes=scenes,
    )

    # 3. Audio Engine: Voiceover + Noise Reduction + Auto-Ducked Copyright-Safe Music + -14 LUFS Master
    vo_wav, master_wav, word_timings, vo_source = build_voiceover_and_master_audio(
        scenes=project.scenes,
        work_dir=work_dir,
        language=subtitle_language,
        voiceover_file=organized_vo,
        music_file=organized_music,
        music_enabled=bool(defaults.get("music", {}).get("enabled", True)),
        narration_cfg=defaults.get("narration", {}),
        music_cfg=defaults.get("music", {}),
        target_lufs=float(preset["audio"].get("target_lufs", -14.0)),
    )

    # 4. Subtitle Engine: SRT + WebVTT + Broadcast Styled ASS
    sub_entries, srt_path, vtt_path, ass_path = generate_subtitles_for_project(
        scenes=project.scenes,
        voiceover_wav=vo_wav,
        word_timings=word_timings,
        out_dir=sub_dir,
        language=subtitle_language,
        width=int(preset["width"]),
        height=int(preset["height"]),
        sub_cfg=defaults.get("subtitles", {}),
    )

    # 5. Thumbnail Engine: 1280x720 & 1920x1080 YouTube Thumbnails
    first_img = next(
        (p for p in organized_visuals if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}),
        None,
    )
    thumb_720, thumb_1080 = generate_youtube_thumbnail(
        title=project.video_title,
        badge_text=project.episode_badge,
        channel_name=project.channel_name,
        out_720p=thumb_dir / "thumbnail_1280x720.png",
        out_1080p=thumb_dir / "thumbnail_1920x1080.png",
        accent_hex=project.accent_color,
        secondary_hex=project.secondary_color,
        hero_image_path=first_img,
    )

    # 6. Save Storyboard JSON (compatible with both Python & Remotion)
    storyboard_path = project_dir / "storyboard.json"
    storyboard_payload: dict[str, Any] = {
        "project": project.to_dict(),
        "voiceover_source": vo_source,
        "subtitle_count": len(sub_entries),
        "subtitles": [
            {"index": e.index, "startSec": e.start_sec, "endSec": e.end_sec, "text": e.text}
            for e in sub_entries
        ],
    }

    # 7. Render Final Video
    out_mp4_name = final_filename or f"{slugify(project.project_name)}_{preset_name}.mp4"
    final_mp4 = export_dir / out_mp4_name
    render_info = render_project_video(
        project=project,
        preset=preset,
        master_audio_wav=master_wav,
        srt_path=srt_path,
        ass_path=ass_path,
        subtitles=sub_entries,
        work_dir=work_dir,
        final_mp4_path=final_mp4,
        resumable=bool(defaults.get("rendering", {}).get("resumable_segments", True)),
    )
    storyboard_payload["render_info"] = render_info
    storyboard_path.write_text(json.dumps(storyboard_payload, indent=2), encoding="utf-8")

    # 8. Write YouTube Upload Metadata & Chapters
    metadata_txt = write_youtube_metadata(
        project=project,
        scenes=project.scenes,
        preset=preset,
        out_path=export_dir / "youtube_metadata.txt",
    )

    # 9. Automated QA Verification
    expected_total_dur = sum(s.duration_sec for s in project.scenes)
    qa_report = verify_video(
        video_path=final_mp4,
        expected_width=int(preset["width"]),
        expected_height=int(preset["height"]),
        expected_fps=float(preset["fps"]),
        expected_duration=expected_total_dur,
        duration_tolerance=1.5,
        srt_path=srt_path,
        require_audio=True,
        require_subtitles=True,
    )
    qa_report_path = export_dir / "verification_report.json"
    qa_report_path.write_text(json.dumps(qa_report, indent=2), encoding="utf-8")

    # Record stage completion checkpoints for resumable workflows
    checkpoints_path = project_dir / "checkpoints.json"
    checkpoints_path.write_text(
        json.dumps(
            {
                "project_name": project.project_name,
                "language": subtitle_language,
                "stages": {
                    "1_script_and_storyboard": {"completed": True, "scenes": len(project.scenes)},
                    "2_audio_voiceover_music_sfx": {"completed": True, "source": vo_source},
                    "3_subtitles": {"completed": True, "cues": len(sub_entries), "srt": str(srt_path)},
                    "4_thumbnail": {"completed": True, "path": str(thumb_720)},
                    "5_video_render": {"completed": True, "path": str(final_mp4), "engine": render_info.get("segment_engines")},
                    "6_qa_verification": {"completed": True, "passed": bool(qa_report["passed"])},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Keep workspace tidy if requested (preserve master audio & deliverables, drop intermediate segments)
    if clean_work_segments:
        shutil.rmtree(work_dir / "segments", ignore_errors=True)
        (work_dir / "concatenated_visual.mp4").unlink(missing_ok=True)
        (work_dir / "remotion_full_visual.mp4").unlink(missing_ok=True)

    return RenderArtifacts(
        project_dir=project_dir,
        final_video_path=final_mp4,
        thumbnail_720p_path=thumb_720,
        thumbnail_1080p_path=thumb_1080,
        srt_path=srt_path,
        vtt_path=vtt_path,
        ass_path=ass_path,
        master_audio_path=master_wav,
        voiceover_audio_path=vo_wav,
        storyboard_json_path=storyboard_path,
        metadata_txt_path=metadata_txt,
        verification_report_path=qa_report_path,
        verification_passed=bool(qa_report["passed"]),
    )


def build_from_manifest(manifest_path: Path) -> RenderArtifacts:
    project_dir = manifest_path.resolve().parent
    cfg = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    def _resolve_opt(rel: str | None) -> Path | None:
        if not rel:
            return None
        p = Path(rel)
        return p if p.is_absolute() else (project_dir / p)

    script_p = _resolve_opt(cfg.get("script_file"))
    vo_p = _resolve_opt(cfg.get("voiceover_file"))
    if vo_p is None:
        # Auto-discover single voiceover file in assets/voiceover if user dropped one there
        vo_candidates = [
            f
            for f in (project_dir / "assets" / "voiceover").glob("*")
            if f.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
        ]
        if len(vo_candidates) == 1:
            vo_p = vo_candidates[0]

    mus_p = _resolve_opt(cfg.get("music_file"))
    vis_dir = _resolve_opt(cfg.get("visuals_dir", "assets/visuals"))
    vis_list = [vis_dir] if (vis_dir and vis_dir.exists()) else []

    return organize_and_build_video(
        topic=cfg["topic"],
        project_dir=project_dir,
        script_text_or_path=script_p if (script_p and script_p.exists()) else cfg.get("script_text"),
        voiceover_path=vo_p,
        music_path=mus_p,
        visual_paths=vis_list,
        preferred_duration_sec=cfg.get("preferred_duration_sec"),
        subtitle_language=cfg.get("subtitle_language", "en"),
        output_resolution=cfg.get("output_resolution", "1080p"),
        engine=cfg.get("engine", "hybrid"),
        video_title=cfg.get("video_title"),
        video_subtitle=cfg.get("video_subtitle"),
        burn_subtitles=bool(cfg.get("burn_subtitles", True)),
        embed_soft_subtitles=bool(cfg.get("embed_soft_subtitles", True)),
    )
