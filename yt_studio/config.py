from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
FONTS_DIR = REPO_ROOT / "assets" / "fonts"

load_dotenv(REPO_ROOT / ".env")

PRESET_ALIASES = {
    "1080p": "youtube_1080p",
    "1920x1080": "youtube_1080p",
    "fhd": "youtube_1080p",
    "1080p30": "youtube_1080p",
    "1080p60": "youtube_1080p60",
    "4k": "youtube_4k",
    "2160p": "youtube_4k",
    "3840x2160": "youtube_4k",
    "uhd": "youtube_4k",
    "720p": "youtube_720p_draft",
    "1280x720": "youtube_720p_draft",
    "draft": "youtube_720p_draft",
}

ISO639_2_MAP = {
    "en": "eng",
    "en-us": "eng",
    "en-gb": "eng",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "hi": "hin",
    "pt": "por",
    "it": "ita",
    "ja": "jpn",
    "ko": "kor",
    "zh": "zho",
    "ar": "ara",
    "ru": "rus",
}


def load_export_presets() -> dict[str, Any]:
    path = CONFIG_DIR / "export_presets.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_workflow_defaults() -> dict[str, Any]:
    path = CONFIG_DIR / "workflow_defaults.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_system_profile() -> dict[str, Any]:
    path = CONFIG_DIR / "system_profile.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def resolve_preset_name(name_or_res: str | None) -> str:
    data = load_export_presets()
    default_name = data.get("default_preset", "youtube_1080p")
    if not name_or_res:
        return default_name
    key = name_or_res.strip().lower()
    if key in data["presets"]:
        return key
    if key in PRESET_ALIASES:
        return PRESET_ALIASES[key]
    raise ValueError(
        f"Unknown export preset or resolution '{name_or_res}'. "
        f"Available presets: {', '.join(data['presets'].keys())} (or aliases 1080p, 1080p60, 4k, 720p)."
    )


def get_resolved_export_preset(name_or_res: str | None = None) -> dict[str, Any]:
    """
    Loads the requested YouTube export preset and adapts encoder/thread/speed settings
    to the detected hardware (GPU acceleration when supported, CPU SIMD fallback otherwise).
    """
    data = load_export_presets()
    preset_name = resolve_preset_name(name_or_res)
    preset = dict(data["presets"][preset_name])
    preset["name"] = preset_name

    profile = load_system_profile()
    hw = profile.get("hardware", {})
    ff = profile.get("ffmpeg", {})

    logical_cores = int(hw.get("cpu", {}).get("logical_cores", os.cpu_count() or 2))
    ram_gb = float(hw.get("memory", {}).get("total_gb", 4.0))
    has_gpu = bool(hw.get("gpu", {}).get("hardware_gpu_available", False))
    available_encoders = ff.get("encoders", {})

    video_cfg = dict(preset["video"])
    selected_encoder = video_cfg["codec"]
    hw_used = False

    if has_gpu:
        for hw_enc in video_cfg.get("hw_codecs_priority", []):
            if available_encoders.get(hw_enc):
                # Quick smoke test that hardware device actually initializes
                rc = subprocess.run(
                    [
                        shutil.which("ffmpeg") or "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=black:s=256x256:d=0.1",
                        "-c:v",
                        hw_enc,
                        "-f",
                        "null",
                        "-",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                if rc == 0:
                    selected_encoder = hw_enc
                    hw_used = True
                    break

    video_cfg["selected_encoder"] = selected_encoder
    video_cfg["hardware_accelerated"] = hw_used
    video_cfg["threads"] = max(1, min(logical_cores, 4))

    # Practicality tuning for 4K on low-RAM CPU-only machines
    warnings: list[str] = []
    req = preset.get("practical_requirements", {})
    if preset_name == "youtube_4k" and not hw_used:
        min_ram = float(req.get("min_recommended_ram_gb", 8.0))
        if ram_gb < min_ram:
            override = req.get("low_ram_cpu_preset_override", "veryfast")
            video_cfg["preset"] = override
            warnings.append(
                f"4K CPU fallback on {ram_gb:.1f} GiB RAM / {logical_cores} vCPUs: "
                f"using libx264 preset='{override}' and segmented rendering to prevent OOM."
            )

    preset["video"] = video_cfg
    preset["runtime_warnings"] = warnings
    return preset


def get_font_path(weight: str = "Bold") -> Path:
    candidates = {
        "Regular": FONTS_DIR / "Poppins-Regular.ttf",
        "Medium": FONTS_DIR / "Poppins-Medium.ttf",
        "SemiBold": FONTS_DIR / "Poppins-SemiBold.ttf",
        "Bold": FONTS_DIR / "Poppins-Bold.ttf",
        "ExtraBold": FONTS_DIR / "Poppins-ExtraBold.ttf",
        "Black": FONTS_DIR / "Poppins-Black.ttf",
        "Display": FONTS_DIR / "BebasNeue-Regular.ttf",
        "Mono": FONTS_DIR / "JetBrainsMono-Regular.ttf",
    }
    chosen = candidates.get(weight, candidates["Bold"])
    if chosen.exists():
        return chosen
    fallback = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if fallback.exists():
        return fallback
    return Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def get_iso639_2_lang(lang_code: str) -> str:
    clean = (lang_code or "en").strip().lower()
    if clean in ISO639_2_MAP:
        return ISO639_2_MAP[clean]
    base = clean.split("-")[0]
    return ISO639_2_MAP.get(base, "eng")


def detect_configured_apis() -> dict[str, bool]:
    keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "ELEVENLABS_API_KEY",
        "PEXELS_API_KEY",
        "PIXABAY_API_KEY",
    ]
    return {k: bool(os.environ.get(k, "").strip()) for k in keys}
