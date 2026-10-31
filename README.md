# Video-creation- · KitaabDeep

Hindi book-summary YouTube channel **KitaabDeep** ke liye tools.

## Thumbnail generator

Reference-style (Book Gallery / Life Upgrade) thumbnails: AI-generated glowing 3D book on one side +
pixel-perfect Hindi hook text (HarfBuzz shaping, so मात्रा / संयुक्ताक्षर kabhi nahi tootenge) + KitaabDeep watermark.

```bash
npm install
npm run thumbnail -- thumbnail/topics/5-life-changing-habits.json
# -> output/5-life-changing-habits.jpg (1280x720)
```

- Style analysis + rules + AI prompt template: [`thumbnail/STYLE_GUIDE.md`](thumbnail/STYLE_GUIDE.md)
- Reference thumbnails: `thumbnail/references/`
- Topic configs: `thumbnail/topics/` · AI assets: `thumbnail/assets/` · Results: `output/`
- Fonts (OFL): [`fonts/README.md`](fonts/README.md)
