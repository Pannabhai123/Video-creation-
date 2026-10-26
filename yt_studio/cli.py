from __future__ import annotations

from pathlib import Path

import click
from PIL import Image, ImageDraw
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import REPO_ROOT, get_font_path, load_export_presets
from .pipeline import (
    build_from_manifest,
    organize_and_build_video,
    scaffold_project_template,
    slugify,
)

console = Console()


def _print_artifacts_summary(artifacts) -> None:
    status = "[bold green]PASSED[/bold green]" if artifacts.verification_passed else "[bold red]FAILED[/bold red]"
    tbl = Table(title="YouTube Production Deliverables", show_lines=False)
    tbl.add_column("Artifact", style="cyan")
    tbl.add_column("Path", style="white")
    tbl.add_row("Final Master MP4", str(artifacts.final_video_path))
    tbl.add_row("YouTube Thumbnail (720p)", str(artifacts.thumbnail_720p_path))
    tbl.add_row("YouTube Thumbnail (1080p)", str(artifacts.thumbnail_1080p_path))
    tbl.add_row("SRT Subtitles", str(artifacts.srt_path))
    tbl.add_row("WebVTT Subtitles", str(artifacts.vtt_path))
    tbl.add_row("Styled ASS Subtitles", str(artifacts.ass_path))
    tbl.add_row("Storyboard & Timing JSON", str(artifacts.storyboard_json_path))
    tbl.add_row("YouTube Chapters & Metadata", str(artifacts.metadata_txt_path))
    tbl.add_row("QA Verification Report", f"{artifacts.verification_report_path} ({status})")
    console.print(tbl)


def _create_sample_visual_image(out_png: Path) -> Path:
    """
    Generates a crisp custom studio visual diagram PNG using Pillow so Step 5 tests
    real external image ingestion alongside procedural graphics and Remotion animations.
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    w, h = 1600, 900
    img = Image.new("RGB", (w, h), (10, 18, 36))
    draw = ImageDraw.Draw(img)

    # Radial rings & architecture schematic
    for r in range(420, 60, -70):
        draw.ellipse([w // 2 - r, h // 2 - r, w // 2 + r, h // 2 + r], outline=(56, 189, 248), width=3)

    from PIL import ImageFont

    f_title = ImageFont.truetype(str(get_font_path("ExtraBold")), 52)
    f_sub = ImageFont.truetype(str(get_font_path("SemiBold")), 30)

    boxes = [
        (140, 140, 560, 320, "SCRIPT & STORYBOARD", "Scene Pacing + Chapters", (56, 189, 248)),
        (1040, 140, 1460, 320, "AUDIO MASTERING", "Voiceover + -14 LUFS Mix", (129, 140, 248)),
        (140, 580, 560, 760, "REMOTION + PYTHON", "React & OpenCV Motion", (52, 211, 153)),
        (1040, 580, 1460, 760, "YOUTUBE EXPORT", "1080p/4K H.264 + Subtitles", (250, 204, 21)),
    ]
    for x0, y0, x1, y1, head, sub, col in boxes:
        draw.line([(w // 2, h // 2), ((x0 + x1) // 2, (y0 + y1) // 2)], fill=col, width=5)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=24, fill=(15, 23, 42), outline=col, width=4)
        draw.text((x0 + 28, y0 + 42), head, font=ImageFont.truetype(str(get_font_path("Bold")), 26), fill=col)
        draw.text((x0 + 28, y0 + 96), sub, font=f_sub, fill=(226, 232, 240))

    draw.rounded_rectangle([560, 370, 1040, 530], radius=30, fill=(14, 116, 144), outline=(255, 255, 255), width=4)
    core_txt = "AI STUDIO CORE"
    cb = draw.textbbox((0, 0), core_txt, font=f_title)
    draw.text(((w - (cb[2] - cb[0])) // 2, 418), core_txt, font=f_title, fill=(255, 255, 255))
    img.save(str(out_png), format="PNG")
    return out_png


@click.group()
def main() -> None:
    """Complete YouTube Long-Form Video Creation & Automation CLI."""


@main.command("presets")
def list_presets() -> None:
    """List configured YouTube export presets."""
    data = load_export_presets()
    tbl = Table(title="Configured YouTube Export Presets")
    tbl.add_column("Preset", style="cyan")
    tbl.add_column("Resolution / FPS", style="green")
    tbl.add_column("Codecs", style="yellow")
    tbl.add_column("Description", style="white")
    for name, cfg in data["presets"].items():
        marker = " (default)" if name == data.get("default_preset") else ""
        tbl.add_row(
            f"{name}{marker}",
            f"{cfg['width']}x{cfg['height']} @ {cfg['fps']}fps ({cfg['aspect_ratio']})",
            f"{cfg['video']['codec']} / {cfg['audio']['codec']} ({cfg['audio']['target_lufs']} LUFS)",
            cfg["description"],
        )
    console.print(tbl)


@main.command("init")
@click.argument("name")
@click.option("--topic", default="Deep-Dive Engineering Guide", help="Initial video topic.")
def init_cmd(name: str, topic: str) -> None:
    """Create a reusable YouTube project folder under projects/<name>."""
    proj_dir = REPO_ROOT / "projects" / slugify(name)
    manifest = scaffold_project_template(proj_dir, topic=topic)
    console.print(
        Panel(
            f"Created reusable YouTube project workspace:\n[bold cyan]{proj_dir}[/bold cyan]\n\n"
            f"1. Edit script: [green]{proj_dir / 'script.md'}[/green]\n"
            f"2. Optional: drop voiceover in [green]assets/voiceover/[/green] & visuals in [green]assets/visuals/[/green]\n"
            f"3. Render video: [bold yellow]python3 -m yt_studio run {manifest}[/bold yellow]",
            title="Project Initialized",
        )
    )


@main.command("run")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
def run_cmd(manifest: Path) -> None:
    """Build and render a YouTube project from its project.yaml manifest."""
    console.print(f"[bold cyan]Building YouTube project from manifest:[/bold cyan] {manifest}")
    artifacts = build_from_manifest(manifest)
    _print_artifacts_summary(artifacts)
    if not artifacts.verification_passed:
        raise SystemExit(1)


@main.command("build")
@click.option("--topic", required=True, help="Video topic.")
@click.option("--project-name", default=None, help="Project folder name under projects/.")
@click.option("--script", "script_path", default=None, help="Path to Markdown/TXT script or inline script text.")
@click.option("--voiceover", type=click.Path(exists=True, path_type=Path), default=None, help="Optional voiceover audio file.")
@click.option("--music", type=click.Path(exists=True, path_type=Path), default=None, help="Optional background music file.")
@click.option("--assets", multiple=True, type=click.Path(exists=True, path_type=Path), help="Images, video clips, or directory of visuals.")
@click.option("--duration", type=float, default=None, help="Preferred video duration in seconds.")
@click.option("--language", default="hi", show_default=True, help="Subtitle & narration language code (default: hi for Hindi).")
@click.option("--resolution", default="1080p", show_default=True, help="Output preset/resolution: 1080p, 1080p60, 4k, 720p.")
@click.option("--engine", type=click.Choice(["auto", "hybrid", "python", "remotion"]), default="auto", show_default=True)
@click.option("--output-dir", type=click.Path(path_type=Path), default=None, help="Custom project output directory.")
def build_cmd(
    topic: str,
    project_name: str | None,
    script_path: str | None,
    voiceover: Path | None,
    music: Path | None,
    assets: tuple[Path, ...],
    duration: float | None,
    language: str,
    resolution: str,
    engine: str,
    output_dir: Path | None,
) -> None:
    """Organize supplied assets and render a complete YouTube long-form video."""
    proj_slug = slugify(project_name or topic)
    proj_dir = output_dir or (REPO_ROOT / "projects" / proj_slug)
    console.print(f"[bold cyan]Starting YouTube Video Production Build ->[/bold cyan] {proj_dir}")
    artifacts = organize_and_build_video(
        topic=topic,
        project_dir=proj_dir,
        script_text_or_path=script_path,
        voiceover_path=voiceover,
        music_path=music,
        visual_paths=list(assets),
        preferred_duration_sec=duration,
        subtitle_language=language,
        output_resolution=resolution,
        engine=engine,
    )
    _print_artifacts_summary(artifacts)
    if not artifacts.verification_passed:
        raise SystemExit(1)


@main.command("demo")
@click.option("--resolution", default="1080p", show_default=True, help="Export resolution preset (1080p or 4k).")
def demo_cmd(resolution: str) -> None:
    """
    Step 5 End-to-End System Verification Test:
    Builds, renders, and verifies a multi-scene YouTube video exercising
    Remotion React, MoviePy, OpenCV, Pillow, FFmpeg, Voiceover, Music & Subtitles.
    """
    sample_dir = REPO_ROOT / "renders" / "sample_youtube_video"
    sample_vis = _create_sample_visual_image(sample_dir / "assets" / "visuals" / "studio_architecture.png")

    demo_script = """# Title & Introduction
Welcome to the Automated YouTube Video Production System. Let us tour the complete rendering workflow in action.
- Automated storyboarding and scene timing
- Hybrid React Remotion and Python FFmpeg rendering

## Visuals & Motion Graphics
Scene one integrates external visual diagrams with MoviePy, OpenCV Ken Burns motion, and staggered text animations.
- Smooth subpixel Ken Burns zoom and pan
- Kinetic bullet callouts synchronized to narration

## Broadcast Audio & Subtitles
Scene two demonstrates voiceover synthesis, auto-ducked copyright-safe background music, and frame-accurate captions.
- Integrated -14 LUFS loudness normalization
- Burned-in styled ASS plus embedded MP4 SRT track

## Outro & End Screen
Everything exports to broadcast-ready Full HD H.264 MP4. Subscribe and watch the next guide on screen!
- Compliant YouTube 16:9 end screen layout
- Ready for automated long-form production
"""
    console.print("[bold cyan]Running End-to-End Sample YouTube Video Production Test...[/bold cyan]")
    artifacts = organize_and_build_video(
        topic="Automated YouTube Video Production System",
        project_dir=sample_dir,
        script_text_or_path=demo_script,
        visual_paths=[sample_vis],
        subtitle_language="en",
        output_resolution=resolution,
        engine="hybrid",
        video_title="Automated YouTube Production Pipeline",
        video_subtitle="Hybrid Remotion + Python + FFmpeg Broadcast Mastering",
        episode_badge="SYSTEM VERIFIED",
        final_filename="final_youtube_1080p.mp4" if resolution == "1080p" else f"final_youtube_{resolution}.mp4",
        clean_work_segments=True,
    )
    _print_artifacts_summary(artifacts)
    if not artifacts.verification_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
