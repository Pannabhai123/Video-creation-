# Neural models

TensorFlow Lite models copied from the `mediapipe==0.10.21` wheel. All are
**Apache-2.0**, © Google LLC. They are executed with LiteRT (`ai-edge-litert`)
on CPU — no cloud, no GPU, no API key.

| File | Size | Purpose |
|---|---|---|
| `selfie_segmentation.tflite` | 244 KB | person / background mask (portrait frames) |
| `selfie_segmentation_landscape.tflite` | 244 KB | same, tuned for wide frames |
| `face_landmark.tflite` | 1.2 MB | 468-point face mesh |
| `pose_landmark_full.tflite` | 6.3 MB | 33-point body skeleton |

Used by `automation/aivision.py` → `automation/livephoto.py` (2.5D parallax).

If these files disappear (new sandbox, clean clone):

```bash
python automation/restore_models.py
```

`bootstrap.sh` does this automatically when it detects them missing.
