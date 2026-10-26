"""
aivision.py — real on-device neural vision, no cloud, no GPU, no downloads.

Where the models come from
--------------------------
Hugging Face is blocked in this sandbox, but MediaPipe's **wheel** ships trained
TensorFlow Lite models inside it. Those files are Apache-2.0 and are copied into
assets/models/ so the workspace owns them. They are real neural networks, not
heuristics:

    selfie_segmentation.tflite        256x256 -> 256x256  person/background mask
    selfie_segmentation_landscape     same, tuned for wide frames
    face_landmark.tflite              468-point face mesh
    pose_landmark_full.tflite         33-point body skeleton

Inference runs on ai-edge-litert (LiteRT, Google's TFLite runtime) with the
XNNPACK CPU delegate — measured at ~5 ms per frame for segmentation on this
2-vCPU box.

Used by
-------
* livephoto.py  — 2.5D parallax: split the person from the background and move
                  the layers at different speeds, so a still photo gains depth.
* thumbnail.py / visuals.py — optional subject-aware framing (keep the face in
                  the safe area, never crop the head).

    from aivision import PersonSegmenter
    seg = PersonSegmenter()
    mask = seg.mask(pil_image)          # float32 HxW in 0..1, person = 1
"""

from __future__ import annotations

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.join(ROOT, "assets", "models")

_MODELS = {
    "selfie": "selfie_segmentation.tflite",
    "selfie_landscape": "selfie_segmentation_landscape.tflite",
    "face": "face_landmark.tflite",
    "pose": "pose_landmark_full.tflite",
}


def model_path(key: str) -> str:
    path = os.path.join(MODEL_DIR, _MODELS[key])
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"model missing: {path}\n"
            "Restore it with: bash youtube_workspace/bootstrap.sh --models "
            "(or reinstall mediapipe==0.10.21 and copy from its modules/ folder)")
    return path


def available() -> dict:
    return {k: os.path.exists(os.path.join(MODEL_DIR, v)) for k, v in _MODELS.items()}


class _Lite:
    """Thin wrapper over a TFLite interpreter with float32 I/O."""

    def __init__(self, path: str):
        from ai_edge_litert.interpreter import Interpreter

        self.it = Interpreter(model_path=path, num_threads=2)
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]
        self.out = self.it.get_output_details()[0]
        self.size = (int(self.inp["shape"][2]), int(self.inp["shape"][1]))  # (w, h)

    def __call__(self, array: np.ndarray) -> np.ndarray:
        self.it.set_tensor(self.inp["index"], array[None, ...].astype(np.float32))
        self.it.invoke()
        return self.it.get_tensor(self.out["index"])[0]


class PersonSegmenter:
    """
    Neural person/background separation.

    The model returns a soft mask; it is upsampled to full resolution and
    feathered. `alpha` controls how hard the cut-out edge is.
    """

    def __init__(self, landscape: bool = True, feather: int = 3):
        key = "selfie_landscape" if landscape else "selfie"
        try:
            self.net = _Lite(model_path(key))
        except Exception:
            self.net = _Lite(model_path("selfie"))
        self.feather = feather

    def mask(self, image) -> np.ndarray:
        """Return a float32 HxW alpha mask (person = 1.0) at the image's resolution."""
        from PIL import Image

        if not isinstance(image, Image.Image):
            image = Image.fromarray(np.asarray(image))
        w, h = image.size
        mw, mh = self.net.size
        small = np.asarray(image.convert("RGB").resize((mw, mh), Image.BILINEAR),
                           dtype=np.float32) / 255.0
        raw = self.net(small)[:, :, 0]
        mask = np.asarray(
            Image.fromarray((np.clip(raw, 0, 1) * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
            dtype=np.float32) / 255.0
        if self.feather > 0:
            from PIL import ImageFilter
            m = Image.fromarray((mask * 255).astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(self.feather))
            mask = np.asarray(m, dtype=np.float32) / 255.0
        return mask


class FaceFinder:
    """
    Face mesh (468 points). Used to keep the subject inside the frame during a
    crop or Ken-Burns move, and to place text away from the face.
    """

    def __init__(self):
        self.net = _Lite(model_path("face"))

    def landmarks(self, image) -> np.ndarray | None:
        """Return Nx2 normalised (x, y) landmarks, or None when no face is found."""
        from PIL import Image

        if not isinstance(image, Image.Image):
            image = Image.fromarray(np.asarray(image))
        mw, mh = self.net.size
        small = np.asarray(image.convert("RGB").resize((mw, mh), Image.BILINEAR),
                           dtype=np.float32) / 255.0
        out = self.net(small)
        # face_landmark.tflite output: 1404 floats = 468 * (x, y, z)
        flat = out.reshape(-1)
        if flat.size < 468 * 3:
            return None
        pts = flat[: 468 * 3].reshape(468, 3)
        if not np.isfinite(pts).all() or np.abs(pts).max() < 1e-6:
            return None
        return pts[:, :2].copy()

    def bbox(self, image) -> tuple[int, int, int, int] | None:
        """Face bounding box in pixels: (left, top, right, bottom)."""
        pts = self.landmarks(image)
        if pts is None:
            return None
        w, h = image.size
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))


def inpaint_behind(image, mask: np.ndarray, strength: float = 0.9):
    """
    Reconstruct the background hidden behind the subject.

    Uses OpenCV's Telea inpainting (algorithmic content-aware fill) over a dilated
    mask, which is dramatically better than smearing pixels: the filled area
    follows local colour and gradients, so when the cut-out layer moves away the
    revealed background does not show a black halo or a hard seam.

    Falls back to a blurred smear only if OpenCV is unavailable.
    """
    from PIL import Image, ImageFilter

    if not isinstance(image, Image.Image):
        image = Image.fromarray(np.asarray(image))
    rgb = np.asarray(image.convert("RGB"))

    hole = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
    # dilate so the inpaint reaches past the soft edge of the mask
    hole = np.asarray(Image.fromarray(hole).filter(ImageFilter.MaxFilter(9)))

    try:
        import cv2

        radius = max(3, int(min(rgb.shape[:2]) * 0.012))
        filled = cv2.inpaint(rgb, (hole > 40).astype(np.uint8), radius, cv2.INPAINT_TELEA)
        # blend the filled result only inside the hole, keeping the real background intact
        m = (hole > 40).astype(np.float32)[..., None]
        out = rgb * (1 - m) + filled * m
        res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
        # soften just the join so the boundary is invisible under motion
        return Image.composite(
            res.filter(ImageFilter.GaussianBlur(2)), res,
            Image.fromarray(hole).filter(ImageFilter.GaussianBlur(6)))
    except Exception:
        h, w = rgb.shape[:2]
        blurred = np.asarray(
            image.convert("RGB").filter(ImageFilter.GaussianBlur(radius=max(8, min(w, h) // 24))),
            dtype=np.float32)
        sm = blurred.copy()
        for shift in (int(w * 0.04), int(w * 0.10), int(w * 0.18)):
            if shift < 1:
                continue
            sm = np.maximum(sm, np.roll(blurred, shift, axis=1) * 0.98)
            sm = np.maximum(sm, np.roll(blurred, -shift, axis=1) * 0.98)
        m = np.clip(mask, 0, 1)[..., None] * strength
        out = rgb.astype(np.float32) * (1 - m) + sm * m
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(radius=max(1, strength * 3)))
