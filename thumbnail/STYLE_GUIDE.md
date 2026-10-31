# KitaabDeep Thumbnail Style Guide

Yeh guide 11 reference thumbnails (`thumbnail/references/ref-01…11.jpg`) ke analysis se banayi gayi hai.
Ye thumbnails **Book Gallery**, **Life Upgrade** aur **Audiobook 365** jaise Hindi book-summary channels ke hain.
Har naye topic ka thumbnail isi formula se banega.

---

## 1. Reference analysis – kya common hai

| # | Thumbnail | Book / Asset | Hook text (lines → colours) | Background | Extra element |
|---|-----------|--------------|-----------------------------|------------|---------------|
| 1 | The Power of Self-Discipline | Book, neon-green glow | – (book only) | Forest + mountains, dark | Neon green rim light |
| 2 | Focus on What Matters | Light-blue book | जो जरुरी है (yellow) / सिर्फ उसी पर (white) / फोकस करो! (yellow) | Dark navy + blue glow | Blue light streak |
| 3 | Mental Discipline | Black-gold book, stoic statue | खुद को (yellow) / **CONTROL** (white, English) / करना सीखो (cyan) | Black + orange/yellow glow | – |
| 4–5 | 8 Way to Stay Consistent | Book, sunrise hiker cover | सारा खेल (white) / **CONSISTENCY** (cyan, English) / का - ही - है (white) | Blurred desk, headphones, notebook | Lens flare |
| 6 | Tao Te Ching | Cream book, ink-wash art | जो होता है (white) / होने दो (gold) | Misty lake, bamboo, zen stones | Doodle characters, gold brush stroke, "ACCEPT • FLOW • LET GO" strip |
| 7, 9 | Power of Self-Discipline | Neon green book | सबसे पहले (yellow-gold) / खुद (white) / को सुधारो (green) | Dark forest/mountains | Glowing green swoosh ring around "खुद" |
| 8 | Book Gallery channel grid | Yellow/black books | हर चीज पर / React / करना बंद करो, दिमाग का / 100% USE … | Yellow-orange fire glow | **Red arrow pointing at book**, highlight bands |
| 10–11 | Life Upgrade channel grid | Clean book mockups | दिमाग बदलो / जिंदगी बदल जाएगी … | Plain dark gradient, spotlight | Yellow/orange highlight band behind last line, red arrow |

### Pattern jo har hit thumbnail me hai
1. **2-zone split (16:9):** ek side 40–45% me *3D book mockup*, dusri side 55–60% me *bada Hindi hook text*.
   (References me book left hai; KitaabDeep layout me hum **text left / asset right** rakhte hain – `layout` se flip ho jata hai.)
2. **Hook text = 2-3 lines, 3-6 shabd total.** Bolchaal ki Hindi, command form: *करो / सीखो / सुधारो / छोड़ो / बदलो*.
   Ek "power word" aksar English me hota hai (CONTROL, CONSISTENCY, FOCUS, React, 100% USE).
3. **Har line ki width almost same** (text block ek solid rectangle jaisa dikhta hai) – isliye renderer har line ko zone width tak auto-scale karta hai.
4. **Colours alternate:** Yellow/Gold → White → Gold/Cyan/Green. Main hook word hamesha sabse bada + golden/colour, baaki white.
5. **Mota black outline + drop shadow** – mobile par 100% readable. Kabhi-kabhi halka 3D extrusion / glow.
6. **Book glow hota hai** (gold, neon green, blue) aur background dark hota hai – book "pop" karti hai.
7. **Background = dark + ek warm/neon radial glow**, particles, sparks, lens flare, ya cinematic scene (pahaad, jungle, desk).
8. **Bottom-right corner khaali** – wahan YouTube ka duration badge (47:10 etc.) aata hai.
9. **Optional accents:** red arrow → book, glowing swoosh ring ek word ke around, golden brush underline, highlight band.

---

## 2. KitaabDeep layout

```
┌──────────────────────────────────────────────────────────────┐
│  TEXT ZONE (x 40–700)                 │  AI 3D ASSET (right)  │
│  Line 1  – white  (supporting)        │  Glowing book / brain │
│  Line 2  – white                      │  / tree               │
│  Line 3  – GOLD #F5A623 / #FFD700     │                       │
│           (main hook, biggest, glow)  │                       │
│  [📖🔥 KitaabDeep logo] ← bottom-left  │        (keep clear) ▢ │
└──────────────────────────────────────────────────────────────┘
```

| Element | Spec |
|---------|------|
| Canvas | 1280 × 720 JPG, < 2 MB |
| Hindi font | Noto Sans Devanagari Black (default) · Yatra One · Rozha One · Baloo 2 · Mukta · Khand |
| English font | Poppins Black (default) · Montserrat Black/ExtraBold |
| Main hook word | Deep Gold `#F5A623` / Bright Yellow `#FFD700` (gradient) |
| Supporting text | White `#FFFFFF` |
| Readability | Black outline (≈8.5% of font size) + blurred black drop shadow + left-side black gradient |
| Watermark | Bottom-left dark-navy pill with gold border: **official KitaabDeep logo** (book + flame emblem + gold wordmark), auto-cut from `thumbnail/brand/kitaabdeep-logo.png`. `"brand_style": "text"` = flame icon + typed text fallback |

---

## 3. Workflow (har naye topic ke liye)

1. **Hook likho** – 2-3 lines, max ~6 shabd. Main word gold.
2. **AI asset generate karo** (prompt template neeche) → `thumbnail/assets/<slug>.jpg`.
   AI ko *Hindi text mat likhwao* – sirf book cover ka English title.
3. **Config banao** → `thumbnail/topics/<slug>.json` (example: `5-life-changing-habits.json`).
4. **Render:** `npm run thumbnail -- thumbnail/topics/<slug>.json` → `output/<slug>.jpg`.

### AI asset prompt template

```
Wide 16:9 YouTube thumbnail background, cinematic, ultra sharp. On the RIGHT side of the
frame (right 40%): a realistic 3D hardcover book mockup standing upright, slightly angled
so its spine is visible, glowing bright {GLOW_COLOUR} rim light and aura behind it, sparks
and light particles. Book cover: big bold title "{ENGLISH_TITLE}" in white and gold
sans-serif, cover art of {COVER_ART}, small author name at bottom "{AUTHOR}".
The LEFT 60% of the frame is mostly empty dark space: deep black gradient with a soft
{GLOW_COLOUR} radial glow, subtle bokeh, faint light rays and floating embers, no text,
no objects on the left. High contrast, dramatic lighting, professional book summary
channel thumbnail style.
```

Glow colour ideas: **gold** (habits, success, money), **neon green** (discipline, growth),
**electric blue** (focus, brain, mind), **orange-fire** (motivation, control), **soft cream/ink** (stoic, zen, Tao).

---

## 4. Config reference (`thumbnail/topics/*.json`)

```jsonc
{
  "background": "../assets/<slug>.jpg",     // AI asset
  "output": "../../output/<slug>.jpg",
  "layout": "text-left",                    // or "text-right" (reference style, book left)
  "hindi_font": "noto-black",               // noto-black | noto-extrabold | yatra | rozha | baloo | mukta | khand
  "english_font": "poppins-black",          // poppins-black | montserrat-black | ...
  "text_area": { "x": 40, "y": 60, "w": 660, "h": 540 },  // optional
  "line_gap": 0.12,                         // gap between lines (× font size)
  "text_shade": 0.6,                        // black gradient on text side (0 = off)
  "lines": [
    { "text": "खुद को",     "color": "yellow", "scale": 0.7 },
    { "text": "CONTROL",    "color": "white",  "ring": "gold" },
    { "text": "करना सीखो!", "color": "gold", "glow": "gold", "extrude": 0.05, "underline": "gold" }
  ],
  "arrow": { "x": 610, "y": 640, "len": 120, "angle": 0 },   // optional red arrow
  "brand": "KitaabDeep"
}
```

Per-line options: `color` (gold · yellow · white · cyan · green · orange · red · or any hex),
`scale` (fraction of zone width, default 1), `max_size` (px), `glow`, `extrude` (3D depth, e.g. 0.05),
`underline`, `ring`, `band` (highlight box colour), `align` (left · center · right), `stroke`.

### Logo update
Naya logo aaye to `thumbnail/brand/kitaabdeep-logo.png` replace karo aur chalao:
`node thumbnail/tools/make_logo_assets.mjs` → `emblem.png` + `wordmark.png` (transparent) ban jayenge.
