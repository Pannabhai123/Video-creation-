"""
restore_models.py — put the neural models back into assets/models/.

The TFLite models live inside the mediapipe wheel (Apache-2.0). They are copied
into the workspace so the pipeline does not depend on mediapipe's Python API
(whose native bindings do not import cleanly here). If assets/models is ever
emptied — a new sandbox, a clean clone — this script restores them.

    python automation/restore_models.py
    python automation/restore_models.py --check     # exit 1 if anything is missing
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(os.path.dirname(HERE), "assets", "models")
MEDIAPIPE_PIN = "mediapipe==0.10.21"

WANTED = {
    "selfie_segmentation.tflite": "selfie_segmentation/selfie_segmentation.tflite",
    "selfie_segmentation_landscape.tflite": "selfie_segmentation/selfie_segmentation_landscape.tflite",
    "face_landmark.tflite": "face_landmark/face_landmark.tflite",
    "pose_landmark_full.tflite": "pose_landmark/pose_landmark_full.tflite",
}


def find_modules_dir() -> str | None:
    try:
        import mediapipe  # noqa: F401
        base = os.path.dirname(mediapipe.__file__)
    except Exception:
        # even an unimportable install still has the files on disk
        try:
            import site
            for sp in site.getsitepackages() + [site.getusersitepackages()]:
                cand = os.path.join(sp, "mediapipe")
                if os.path.isdir(cand):
                    base = cand
                    break
            else:
                return None
        except Exception:
            return None
    mod = os.path.join(base, "modules")
    return mod if os.path.isdir(mod) else None


def restore(verbose: bool = True) -> dict:
    os.makedirs(DEST, exist_ok=True)
    have = {k: os.path.exists(os.path.join(DEST, k)) for k in WANTED}
    if all(have.values()):
        if verbose:
            print(f"models: all {len(WANTED)} present in {DEST}")
        return have

    mod = find_modules_dir()
    if mod is None:
        if verbose:
            print("models: mediapipe is not installed; installing the pinned wheel…")
        py = sys.executable
        subprocess.run([py, "-m", "pip", "install", "--quiet", "--force-reinstall",
                        "--no-deps", MEDIAPIPE_PIN], check=False)
        mod = find_modules_dir()

    if mod is None:
        raise SystemExit(
            "could not locate mediapipe/models. Install it with:\n"
            f"  pip install {MEDIAPIPE_PIN}\n"
            "and re-run this script.")

    copied = 0
    for name, rel in WANTED.items():
        src = os.path.join(mod, rel)
        dst = os.path.join(DEST, name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
            copied += 1
            if verbose:
                print(f"  restored {name} ({os.path.getsize(dst) // 1024} KB)")
    have = {k: os.path.exists(os.path.join(DEST, k)) for k in WANTED}
    if verbose:
        print(f"models: {sum(have.values())}/{len(WANTED)} available"
              + (f", {copied} copied" if copied else ""))
    return have


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if a model is missing")
    args = ap.parse_args()
    have = restore(verbose=not args.check)
    if args.check and not all(have.values()):
        missing = [k for k, v in have.items() if not v]
        print(f"missing models: {missing}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
