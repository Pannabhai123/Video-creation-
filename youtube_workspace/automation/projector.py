"""
projector.py — timeline -> finished video.

Reads a project JSON (see templates/project.example.json), renders every scene
frame, animates it, concatenates, mixes narration + music + SFX, builds Hindi
subtitles, and muxes the deliverable — plus a manifest with every path and
timestamp so production is reproducible.

    python projector.py build ../projects/demo/project.json
    python projector.py build project.json --draft       # fast 720p preview
    python projector.py build project.json --no-music
    python projector.py shorts project.json              # cut 9:16 versions

Design notes
------------
* Scene timing comes from the real narration audio when present; otherwise from
  a calibrated Hindi speaking-rate estimate, so the timeline always matches the
  voice-over the editor records later.
* Every intermediate artefact is written under the project folder, so a rebuild
  only redoes what is missing when `--incremental` is used.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from dataclasses import dataclass, field

import media
import visuals
from captions import build_for_scenes
from hinditext import HindiText

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Hindi documentary pace: ~13.5 Devanagari chars/second, plus a breath per scene.
CHARS_PER_SECOND = 13.5
SCENE_PAD = 0.45


# ---------------------------------------------------------------- helpers
def estimate_duration(text: str, cps: float = CHARS_PER_SECOND) -> float:
    n = len("".join(ch for ch in text if not ch.isspace()))
    return round(n / cps + SCENE_PAD, 2)


def load_project(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        proj = json.load(fh)
    if "scenes" not in proj or not proj["scenes"]:
        raise ValueError("project must contain a non-empty 'scenes' list")
    for i, sc in enumerate(proj["scenes"], 1):
        sc.setdefault("id", f"s{i:02d}")
        sc.setdefault("narration", "")
        sc.setdefault("visual", {"type": "title", "title": sc.get("title") or f"दृश्य {i}"})
        sc.setdefault("motion", "zoom_in")
        sc.setdefault("sfx", [])
    return proj


@dataclass
class Scene:
    id: str
    narration: str
    visual: dict
    start: float
    duration: float
    motion: str = "zoom_in"
    audio: str | None = None
    sfx: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(id=self.id, narration=self.narration, start=round(self.start, 3),
                    duration=round(self.duration, 3), visual=self.visual,
                    motion=self.motion, audio=self.audio)


# ---------------------------------------------------------------- pipeline
class Builder:
    def __init__(self, project_path: str, draft: bool = False, music: bool = True,
                 burn_subs: bool = False, workdir: str | None = None, verbose: bool = True):
        self.project_path = os.path.abspath(project_path)
        self.proj = load_project(self.project_path)
        pid = self.proj.get("project", {}).get("id") or os.path.basename(
            os.path.dirname(self.project_path))
        self.pid = pid
        self.draft = draft
        self.use_music = music
        self.burn_subs = burn_subs
        self.verbose = verbose
        self.workdir = os.path.abspath(workdir or os.path.dirname(self.project_path))
        self.frames = os.path.join(ROOT, "generated_assets", pid, "frames")
        self.clips = os.path.join(self.workdir, "clips")
        self.renders = os.path.join(self.workdir, "render")
        for d in (self.frames, self.clips, self.renders,
                  os.path.join(ROOT, "rendered_videos"), os.path.join(ROOT, "subtitles", pid)):
            os.makedirs(d, exist_ok=True)

        p = self.proj.get("project", {})
        self.preset_name = "draft_720p" if draft else p.get("preset", "longform_1080p30")
        self.cfg = media.preset(self.preset_name)
        self.size = (self.cfg["width"], self.cfg["height"])
        self.fps = self.cfg["fps"]
        self.vertical = p.get("format") == "short"

    def log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # -- timing ---------------------------------------------------------
    def plan(self) -> list[Scene]:
        base = os.path.join(self.workdir, "voiceover")
        scenes: list[Scene] = []
        t = 0.0
        for raw in self.proj["scenes"]:
            sid = raw["id"]
            audio = raw.get("audio")
            if audio:
                audio = os.path.expanduser(audio)
                if not os.path.isabs(audio):
                    audio = os.path.join(os.path.dirname(self.project_path), audio)
            if not audio or not os.path.exists(audio):
                guess = os.path.join(base, f"{sid}.wav")
                audio = guess if os.path.exists(guess) else None

            if raw.get("duration"):
                dur = float(raw["duration"])
            elif audio:
                dur = media.duration_of(audio)
            else:
                dur = estimate_duration(raw["narration"])

            scenes.append(Scene(
                id=sid,
                narration=raw["narration"],
                visual=raw.get("visual", {}),
                start=t,
                duration=round(dur, 3),
                motion=raw.get("motion", "zoom_in"),
                audio=audio,
                sfx=raw.get("sfx", []),
            ))
            t += round(dur, 3)
        return scenes

    # -- video ----------------------------------------------------------
    def render_clip(self, sc: Scene, incremental: bool = True) -> str:
        clip = os.path.join(self.clips, f"{sc.id}.mp4")
        if incremental and os.path.exists(clip):
            info = media.probe(clip)
            if abs(info.duration - sc.duration) < 0.12:
                return clip
        frame = os.path.join(self.frames, f"{sc.id}.png")
        spec = dict(sc.visual)
        if self.vertical:
            spec = _to_vertical(spec)
        visuals.render_scene(spec, frame, size=self.size)
        return media.still_to_video(
            frame, clip, sc.duration, fps=self.fps,
            width=self.size[0], height=self.size[1],
            motion=sc.motion, fade=0.45 if not self.vertical else 0.25,
        )

    def build_video(self, scenes: list[Scene], incremental: bool = True) -> str:
        clips = []
        for sc in scenes:
            self.log(f"  scene {sc.id}: {sc.duration:6.2f}s  {sc.visual.get('type')}")
            clips.append(self.render_clip(sc, incremental))
        visual_track = os.path.join(self.renders, "picture.mp4")
        media.concat_videos(clips, visual_track, workdir=self.renders)
        return visual_track

    # -- audio ----------------------------------------------------------
    def build_audio(self, scenes: list[Scene]) -> tuple[str | None, dict]:
        have_any = any(sc.audio for sc in scenes)
        voice_track = os.path.join(self.renders, "narration.wav")
        if have_any:
            parts = []
            tmp = os.path.join(self.renders, "silence.wav")
            if not os.path.exists(tmp):
                media.run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                           "-t", "1", tmp], "silence")
            for sc in scenes:
                if sc.audio:
                    parts.append(sc.audio)
                else:  # keep the timeline aligned when a scene has no recording yet
                    gap = os.path.join(self.renders, f"gap_{sc.id}.wav")
                    media.run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                               "-t", f"{sc.duration:.3f}", gap], "gap")
                    parts.append(gap)
            media.concat_audio(parts, voice_track)
        else:
            total = sum(sc.duration for sc in scenes)
            media.run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                       "-t", f"{total:.3f}", voice_track], "silent narration")
            self.log("  ! no narration audio found — building a silent voice track")

        info: dict = {"narration_present": have_any}
        mixed = voice_track
        if self.use_music:
            mood = self.proj.get("project", {}).get("music", {}).get("mood", "reflective")
            gain = float(self.proj.get("project", {}).get("music", {}).get("gain_db", -26))
            total = media.duration_of(voice_track)
            bed = self.proj.get("project", {}).get("music", {}).get("path")
            if not bed or not os.path.exists(bed):
                bed = os.path.join(ROOT, "music", f"bed_{mood}_long.wav")
                if not os.path.exists(bed):
                    import music as musicmod
                    self.log(f"  synthesising {mood} music bed ({int(total)+10}s)…")
                    musicmod.write_stereo(musicmod.bed(mood, total + 10), bed)
            mixed = os.path.join(self.renders, "mix.wav")
            media.mix(voice_track, bed, mixed, music_gain_db=gain, duck=have_any)
            info["music"] = {"path": bed, "mood": mood, "gain_db": gain}
        return (mixed if os.path.exists(mixed) else None), info

    # -- assembly -------------------------------------------------------
    def build(self, incremental: bool = True) -> dict:
        t0 = time.time()
        self.log(f"\n▶ {self.pid}  [{self.preset_name}]")
        scenes = self.plan()
        total = sum(s.duration for s in scenes)
        self.log(f"  timeline: {len(scenes)} scenes, {total/60:.2f} min")

        picture = self.build_video(scenes, incremental)
        self.log("  mixing audio…")
        audio, audio_info = self.build_audio(scenes)

        self.log("  building Hindi subtitles…")
        sub_dir = os.path.join(ROOT, "subtitles", self.pid)
        voice_map = {s.id: s.audio for s in scenes if s.audio}
        subs = build_for_scenes([s.as_dict() for s in scenes], sub_dir,
                               scene_audio=voice_map, play_res=self.size,
                               style=_subtitle_style(self.vertical))

        out_name = f"{self.pid}{'_draft' if self.draft else ''}.mp4"
        out_path = os.path.join(ROOT, "rendered_videos", out_name)
        ass = subs["ass"]
        media.mux(picture, audio, out_path, subs=ass, burn_subs=True,
                  a_bitrate=self.cfg["a_bitrate"],
                  crf="23" if self.draft else "18")
        self.log(f"  ✓ {out_path}")

        manifest = {
            "project": self.proj.get("project", {}),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "preset": self.preset_name,
            "resolution": list(self.size),
            "fps": self.fps,
            "duration_seconds": round(total, 3),
            "output": out_path,
            "picture": picture,
            "audio_info": audio_info,
            "subtitles": {k: v for k, v in subs.items() if k != "report"},
            "subtitle_report": subs["report"],
            "scenes": [s.as_dict() for s in scenes],
            "elapsed_seconds": round(time.time() - t0, 1),
        }
        man_path = os.path.join(self.workdir, "build_manifest.json")
        with open(man_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        self.log(f"  manifest: {man_path}  ({manifest['elapsed_seconds']}s total)\n")
        return manifest

    # -- shorts ---------------------------------------------------------
    def shorts(self, count: int = 3) -> list[str]:
        """Cut vertical clips from the strongest scenes of a completed build."""
        man_path = os.path.join(self.workdir, "build_manifest.json")
        with open(man_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        scenes = sorted(manifest["scenes"], key=lambda s: -s["duration"])
        outs = []
        for i, sc in enumerate(scenes[:count], 1):
            dur = min(sc["duration"], 58)
            if dur < 8:
                continue
            dst = os.path.join(ROOT, "shorts", f"{self.pid}_short{i:02d}.mp4")
            media.make_short_vertical(manifest["output"], dst, sc["start"],
                                      sc["start"] + dur)
            outs.append(dst)
            self.log(f"  ✓ {dst}")
        return outs


def _subtitle_style(vertical: bool) -> dict:
    return {
        "size": 66 if vertical else 64,
        "margin_v": 220 if vertical else 66,
        "margin_h": 60 if vertical else 96,
        "outline": 3.6,
    }


def _to_vertical(spec: dict) -> dict:
    """Adapt a 16:9 scene spec for 9:16 (bigger type, fewer words per line)."""
    spec = dict(spec)
    for key in ("max_width",):
        spec.pop(key, None)
    return spec


# ---------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble a video from a project timeline")
    ap.add_argument("cmd", choices=["build", "shorts", "plan", "frames"])
    ap.add_argument("project")
    ap.add_argument("--draft", action="store_true", help="720p fast preview")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--burn-subs", action="store_true", default=True)
    ap.add_argument("--incremental", action="store_true", default=True)
    ap.add_argument("--count", type=int, default=3, help="number of shorts to cut")
    args = ap.parse_args()

    b = Builder(args.project, draft=args.draft, music=not args.no_music,
                burn_subs=args.burn_subs)
    if args.cmd == "build":
        man = b.build(incremental=args.incremental)
        print(json.dumps({"output": man["output"], "duration": man["duration_seconds"]},
                         ensure_ascii=False))
    elif args.cmd == "plan":
        for s in b.plan():
            print(f"{s.id:>6} {s.start:7.2f} +{s.duration:5.2f}  audio={'yes' if s.audio else 'no '}  {s.visual.get('type')}")
    elif args.cmd == "frames":
        for s in b.plan():
            spec = _to_vertical(s.visual) if b.vertical else s.visual
            print(visuals.render_scene(spec, os.path.join(b.frames, f"{s.id}.png"), b.size))
    else:
        for p in b.shorts(args.count):
            print(p)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
