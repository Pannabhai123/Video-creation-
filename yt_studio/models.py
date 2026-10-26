from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WordTiming:
    word: str
    start_sec: float
    end_sec: float


@dataclass
class SubtitleEntry:
    index: int
    start_sec: float
    end_sec: float
    text: str


@dataclass
class SceneSpec:
    scene_id: str
    index: int
    scene_type: str  # "intro" | "content" | "outro"
    chapter_title: str
    headline: str
    narration: str
    bullets: list[str] = field(default_factory=list)
    visual_asset: str | None = None  # Optional path to image or video clip
    visual_style: str = "diagram"    # diagram | metrics | timeline | spotlight
    stat_value: str = ""
    stat_label: str = ""
    accent_color: str = "#38BDF8"
    duration_sec: float = 5.0
    start_sec: float = 0.0
    end_sec: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectSpec:
    project_name: str
    topic: str
    video_title: str
    video_subtitle: str
    channel_name: str = "Nexus Tech Studio"
    channel_tagline: str = "Deep-Dive Engineering & Automation"
    episode_badge: str = "LONG-FORM GUIDE"
    language: str = "en"
    target_duration_sec: float | None = None
    export_preset: str = "youtube_1080p"
    engine: str = "hybrid"  # "hybrid" | "python" | "remotion"
    accent_color: str = "#38BDF8"
    secondary_color: str = "#818CF8"
    voiceover_path: str | None = None
    music_path: str | None = None
    burn_subtitles: bool = True
    embed_soft_subtitles: bool = True
    scenes: list[SceneSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RenderArtifacts:
    project_dir: Path
    final_video_path: Path
    thumbnail_720p_path: Path
    thumbnail_1080p_path: Path
    srt_path: Path
    vtt_path: Path
    ass_path: Path
    master_audio_path: Path
    voiceover_audio_path: Path
    storyboard_json_path: Path
    metadata_txt_path: Path
    verification_report_path: Path
    verification_passed: bool
