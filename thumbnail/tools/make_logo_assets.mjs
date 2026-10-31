#!/usr/bin/env node
/**
 * Cut the KitaabDeep logo (gold on dark navy) into transparent PNGs for the watermark.
 *   thumbnail/brand/kitaabdeep-logo.png  ->  thumbnail/brand/emblem.png   (book + flame + ring)
 *                                        ->  thumbnail/brand/wordmark.png (gold "KitaabDeep")
 * The navy background is removed with a "goldness" key: gold pixels have R,G >> B,
 * navy pixels have B > R. Alpha ramps smoothly so the glow stays soft.
 *
 * Usage: node thumbnail/tools/make_logo_assets.mjs [logo.png]
 */
import sharp from 'sharp';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'brand');
const SRC = process.argv[2] || path.join(DIR, 'kitaabdeep-logo.png');

// crop boxes in the 1254x1254 source logo (scaled if the logo has another size)
const CROPS = {
  emblem:   { left: 215, top: 140, width: 825, height: 640 },
  wordmark: { left: 80,  top: 800, width: 1110, height: 212 },
};

// below the wordmark baseline only the "p" descender is real; the rest is floor reflection
const BASELINE = 966, P_DESC = [1055, 1120];

async function cut(name, box, scale) {
  const b = Object.fromEntries(Object.entries(box).map(([k, v]) => [k, Math.round(v * scale)]));
  const { data, info } = await sharp(SRC).extract(b).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i], g = data[i + 1], bl = data[i + 2];
    const gold = (r + g) / 2 - bl;                 // navy ≈ -35, glow ≈ 20-60, gold ≈ 150+
    const lum = Math.max(r, g);
    const clamp = v => Math.min(1, Math.max(0, v));
    let a = clamp((gold - 18) / 80) * clamp((lum - 60) / 80);
    a = Math.max(a, clamp(((r + g + bl) / 3 - 120) / 60));   // white / silver highlights stay opaque
    if (name === 'wordmark') {
      const px = (i / 4) % info.width, py = Math.floor(i / 4 / info.width);
      const sx = b.left / scale + px / scale, sy = b.top / scale + py / scale;
      if (sy > BASELINE && (sx < P_DESC[0] || sx > P_DESC[1])) a = 0;
    }
    data[i + 3] = Math.round(a * 255);
  }
  const out = path.join(DIR, `${name}.png`);
  await sharp(data, { raw: info }).trim({ threshold: 1 }).png().toFile(out);
  const m = await sharp(out).metadata();
  console.log(`✔ ${path.relative(process.cwd(), out)}  ${m.width}x${m.height}`);
}

const meta = await sharp(SRC).metadata();
const scale = meta.width / 1254;
for (const [name, box] of Object.entries(CROPS)) await cut(name, box, scale);
