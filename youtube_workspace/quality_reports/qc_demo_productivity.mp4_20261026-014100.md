# Quality Control Report

Generated: 2026-10-26 01:41

**1 item(s) checked — 2 FAIL, 0 WARN**

## demo_productivity.mp4
- 1920x1080 · 30.0 fps · 79.8s · h264/aac · 37.7 MB
- Loudness -56.7 LUFS, TP -37.7 dBTP, LRA 2.2 LU

| Check | Value | Status | Expected |
|---|---|---|---|
| resolution | 1920x1080 | ✅ PASS | 1920x1080 (16:9) or 1080x1920 (9:16) |
| aspect_ratio | 1.7778 | ✅ PASS | 16:9 or 9:16 |
| frame_rate | 30.0 | ✅ PASS | integer fps (25/30/60) |
| duration | 79.75s | ✅ PASS | > 20s |
| video_codec | h264 | ✅ PASS | h264 (YouTube-friendly) |
| audio_stream | aac | ✅ PASS | aac 48 kHz stereo |
| sample_rate | 48000 | ✅ PASS | 48000 Hz |
| decode_integrity | 0 errors | ✅ PASS | no decode errors |
| loudness | -56.7 LUFS | ❌ FAIL | -14.0 ±1.5 LUFS (YouTube) |
| true_peak | -37.7 dBTP | ✅ PASS | <= -1.0 dBTP (no clipping) |
| black_frames | 1 runs (1 long) | ❌ FAIL | no black run > 1.2s |
| static_picture | 0 freeze starts > 3s | ✅ PASS | visual motion throughout |
| subtitle_stream | burned-in only | ✅ PASS | burned-in or soft subs |

**Warnings**
- long black stretches at [(0.0, 79.7)]
