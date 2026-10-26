# Quality Control Report

Generated: 2026-10-26 01:40

**1 item(s) checked — 1 FAIL, 2 WARN**

## project.json

| Check | Value | Status | Expected |
|---|---|---|---|
| missing_image_assets | 0 | ✅ PASS | no missing files |
| narration_length | 0 chars ≈ 0.00 min | ⚠️ WARN | non-trivial narration |
| voiceover_files | 0/8 | ❌ FAIL | one WAV per scene for final render |
| visual_variety | 2 types: ['bullets', 'title'] | ⚠️ WARN | >= 3 scene types for retention |

**Warnings**
- 8 scenes have no narration audio — timings are estimates, not measured
