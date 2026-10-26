#!/usr/bin/env python3
"""
Step 1: Comprehensive System & Video Production Environment Inspector.
Detects hardware, OS, GPU acceleration, FFmpeg capabilities, Python/Node libraries,
rendering engines, network connectivity, and configured external AI APIs.
Saves machine-readable profile to config/system_profile.json.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = REPO_ROOT / "config" / "system_profile.json"


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


def inspect_os_and_hardware() -> dict[str, Any]:
    os_release: dict[str, str] = {}
    os_rel_file = Path("/etc/os-release")
    if os_rel_file.exists():
        for line in os_rel_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                os_release[k.strip()] = v.strip().strip('"')

    cpu_model = platform.processor() or "Unknown"
    cpu_flags: list[str] = []
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
            elif line.lower().startswith("flags") and ":" in line and not cpu_flags:
                cpu_flags = line.split(":", 1)[1].strip().split()

    simd = [f for f in ("sse4_2", "avx", "avx2", "avx512f", "avx512bw", "avx512_vnni") if f in cpu_flags]

    mem_total_bytes = 0
    mem_avail_bytes = 0
    swap_total_bytes = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                if parts[0] == "MemTotal:":
                    mem_total_bytes = int(parts[1]) * 1024
                elif parts[0] == "MemAvailable:":
                    mem_avail_bytes = int(parts[1]) * 1024
                elif parts[0] == "SwapTotal:":
                    swap_total_bytes = int(parts[1]) * 1024

    disk = shutil.disk_usage(str(REPO_ROOT))

    # GPU inspection
    nvidia_present = shutil.which("nvidia-smi") is not None
    nvidia_info = None
    if nvidia_present:
        rc, out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if rc == 0:
            nvidia_info = out
        else:
            nvidia_present = False

    dri_devices = sorted(str(p) for p in Path("/dev/dri").glob("*")) if Path("/dev/dri").exists() else []

    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "distro": os_release.get("PRETTY_NAME", platform.platform()),
            "arch": platform.machine(),
        },
        "cpu": {
            "model": cpu_model,
            "logical_cores": os.cpu_count() or 1,
            "simd_extensions": simd,
        },
        "memory": {
            "total_gb": round(mem_total_bytes / (1024**3), 2),
            "available_gb": round(mem_avail_bytes / (1024**3), 2),
            "swap_gb": round(swap_total_bytes / (1024**3), 2),
        },
        "storage": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
        },
        "gpu": {
            "hardware_gpu_available": bool(nvidia_present or dri_devices),
            "nvidia_gpu": nvidia_info,
            "dri_devices": dri_devices,
            "acceleration_mode": "nvenc" if nvidia_present else ("vaapi" if dri_devices else "cpu_simd_fallback"),
        },
    }


def inspect_ffmpeg() -> dict[str, Any]:
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffmpeg_bin:
        return {"installed": False, "ffmpeg_path": None, "ffprobe_path": ffprobe_bin}

    _, ver_out = _run([ffmpeg_bin, "-version"])
    first_line = ver_out.splitlines()[0] if ver_out else ""

    _, enc_out = _run([ffmpeg_bin, "-hide_banner", "-encoders"])
    wanted_encoders = ["libx264", "libx265", "libvpx-vp9", "libaom-av1", "aac", "libmp3lame", "libopus", "mov_text", "srt", "h264_nvenc", "h264_vaapi", "h264_qsv"]
    encoders = {e: (f" {e} " in enc_out) for e in wanted_encoders}

    _, flt_out = _run([ffmpeg_bin, "-hide_banner", "-filters"])
    wanted_filters = ["subtitles", "ass", "loudnorm", "afftdn", "sidechaincompress", "acompressor", "acrossfade", "xfade", "zoompan", "scale"]
    filters = {f: (f" {f} " in flt_out) for f in wanted_filters}

    return {
        "installed": True,
        "ffmpeg_path": ffmpeg_bin,
        "ffprobe_path": ffprobe_bin,
        "version_banner": first_line,
        "encoders": encoders,
        "filters": filters,
    }


def inspect_python_stack() -> dict[str, Any]:
    packages = [
        "moviepy",
        "opencv-python-headless",
        "Pillow",
        "numpy",
        "scipy",
        "imageio",
        "imageio-ffmpeg",
        "av",
        "soundfile",
        "librosa",
        "noisereduce",
        "pydub",
        "pyloudnorm",
        "pysrt",
        "srt",
        "webvtt-py",
        "espeakng-loader",
        "pocketsphinx",
        "faster-whisper",
        "PyYAML",
        "rich",
    ]
    installed: dict[str, str | None] = {}
    for pkg in packages:
        try:
            installed[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            installed[pkg] = None

    return {
        "python_version": platform.python_version(),
        "executable": sys.executable,
        "packages": installed,
    }


def inspect_node_and_remotion() -> dict[str, Any]:
    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm")
    chromium_bin = shutil.which("chromium")
    convert_bin = shutil.which("convert")

    node_ver = _run([node_bin, "--version"])[1] if node_bin else None
    npm_ver = _run([npm_bin, "--version"])[1] if npm_bin else None
    chrom_ver = _run([chromium_bin, "--version"])[1] if chromium_bin else None
    im_ver = _run([convert_bin, "-version"])[1].splitlines()[0] if convert_bin else None

    remotion_pkg = REPO_ROOT / "node_modules" / "remotion" / "package.json"
    remotion_ver = None
    if remotion_pkg.exists():
        remotion_ver = json.loads(remotion_pkg.read_text(encoding="utf-8")).get("version")

    fonts_dir = REPO_ROOT / "assets" / "fonts"
    fonts = sorted(p.name for p in fonts_dir.glob("*.ttf")) if fonts_dir.exists() else []

    return {
        "node_version": node_ver,
        "npm_version": npm_ver,
        "remotion_version": remotion_ver,
        "chromium_path": chromium_bin,
        "chromium_version": chrom_ver,
        "imagemagick": im_ver,
        "studio_fonts": fonts,
    }


def inspect_network_and_apis() -> dict[str, Any]:
    hosts = [
        "github.com",
        "registry.npmjs.org",
        "pypi.org",
        "deb.debian.org",
        "huggingface.co",
        "api.openai.com",
    ]
    connectivity: dict[str, bool] = {}
    for host in hosts:
        try:
            with socket.create_connection((host, 443), timeout=2.0):
                connectivity[host] = True
        except Exception:
            connectivity[host] = False
        else:
            # Verify TLS handshake since sandbox proxies may reset disallowed hosts at TLS layer
            rc, _ = _run(["curl", "-sI", "--connect-timeout", "2", f"https://{host}"], timeout=4)
            connectivity[host] = rc == 0

    api_env_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "ELEVENLABS_API_KEY",
        "PEXELS_API_KEY",
        "PIXABAY_API_KEY",
        "WHISPER_LOCAL_MODEL_PATH",
    ]
    configured_apis = {k: bool(os.environ.get(k, "").strip()) for k in api_env_keys}

    return {
        "https_reachability": connectivity,
        "configured_api_keys": configured_apis,
    }


def build_recommendations(hw: dict[str, Any]) -> dict[str, Any]:
    cores = hw["cpu"]["logical_cores"]
    ram_gb = hw["memory"]["total_gb"]
    has_gpu = hw["gpu"]["hardware_gpu_available"]
    return {
        "ffmpeg_threads": max(1, min(cores, 4)),
        "remotion_concurrency": 1 if ram_gb < 6.0 else min(cores, 4),
        "segmented_rendering_recommended": True,
        "default_export_preset": "youtube_1080p",
        "4k_practical_assessment": (
            "Supported via segmented CPU encoding (preset=veryfast/fast), "
            "but 1080p30 is recommended as default on 2-vCPU / 3.8 GiB RAM CPU-only hardware."
            if (not has_gpu and ram_gb < 8.0)
            else "4K export fully practical at full speed."
        ),
    }


def collect_system_profile() -> dict[str, Any]:
    hw = inspect_os_and_hardware()
    profile = {
        "hardware": hw,
        "ffmpeg": inspect_ffmpeg(),
        "python": inspect_python_stack(),
        "node_and_remotion": inspect_node_and_remotion(),
        "network_and_apis": inspect_network_and_apis(),
        "optimization_recommendations": build_recommendations(hw),
    }
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile


def main() -> None:
    profile = collect_system_profile()
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        hw = profile["hardware"]
        console.print("\n[bold cyan]=== YouTube Video Production System Profile ===[/bold cyan]")
        console.print(f"OS: [green]{hw['os']['distro']}[/green] ({hw['os']['arch']}, kernel {hw['os']['release']})")
        console.print(
            f"CPU: [green]{hw['cpu']['model']}[/green] | Cores: {hw['cpu']['logical_cores']} | SIMD: {', '.join(hw['cpu']['simd_extensions'])}"
        )
        console.print(
            f"Memory: [green]{hw['memory']['total_gb']} GiB total[/green] ({hw['memory']['available_gb']} GiB available) | "
            f"Disk Free: [green]{hw['storage']['free_gb']} GiB[/green]"
        )
        console.print(
            f"GPU Acceleration: [yellow]{hw['gpu']['acceleration_mode']}[/yellow] "
            f"(Hardware GPU detected: {hw['gpu']['hardware_gpu_available']})"
        )

        ff = profile["ffmpeg"]
        console.print(f"FFmpeg: [green]{ff.get('version_banner', 'Not installed')}[/green]")
        nr = profile["node_and_remotion"]
        console.print(
            f"Node: [green]{nr['node_version']}[/green] | Remotion: [green]{nr['remotion_version']}[/green] | "
            f"Chromium: [green]{nr['chromium_version']}[/green]"
        )

        tbl = Table(title="Installed Python Video, Audio & Subtitle Packages")
        tbl.add_column("Package", style="cyan")
        tbl.add_column("Version", style="green")
        for pkg, ver in profile["python"]["packages"].items():
            tbl.add_row(pkg, ver or "[red]MISSING[/red]")
        console.print(tbl)
        console.print(f"Saved machine profile -> [bold]{PROFILE_PATH}[/bold]\n")
    except ImportError:
        print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
