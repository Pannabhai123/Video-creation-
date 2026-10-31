#!/usr/bin/env node
/**
 * KitaabDeep thumbnail renderer
 * ------------------------------------------------------------
 * Takes an AI-generated background (book / brain / tree 3D asset already
 * placed on one side) and draws pixel-perfect Hindi + English hook text,
 * effects and the KitaabDeep watermark on top of it.
 *
 * Why not let the AI write the Hindi text?  Image models garble Devanagari
 * (broken matras, wrong conjuncts).  Here the text is shaped by
 * HarfBuzz with real OpenType fonts, so every मात्रा / संयुक्ताक्षर is correct.
 *
 * Usage:  node thumbnail/render.mjs thumbnail/topics/<topic>.json
 */
import { Resvg } from '@resvg/resvg-js';
import * as hb from 'harfbuzzjs';
import sharp from 'sharp';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const W = 1280, H = 720;

// ---------- fonts ---------------------------------------------------------
// Text is shaped with HarfBuzz (correct मात्रा / संयुक्ताक्षर / nukta placement) and
// converted to vector outlines, so the final SVG contains only <path>s.
const HINDI_FONTS = {
  'noto-black': 'NotoSansDeva-Black',          // closest to the reference thumbnails
  'noto-extrabold': 'NotoSansDeva-ExtraBold',
  'yatra': 'YatraOne-Deva',                    // brush / festive look
  'rozha': 'RozhaOne-Deva',                    // high-contrast serif
  'baloo': 'Baloo2-Deva-ExtraBold',            // rounded heavy
  'mukta': 'Mukta-Deva-ExtraBold',
  'khand': 'Khand-Deva-Bold',                  // condensed, fits long words
};
const ENGLISH_FONTS = {
  'poppins-black': 'Poppins-Black',
  'poppins-extrabold': 'Poppins-ExtraBold',
  'montserrat-black': 'Montserrat-Black',
  'montserrat-extrabold': 'Montserrat-ExtraBold',
};
const fontCache = new Map();
function loadFont(name) {
  if (!fontCache.has(name)) {
    const file = path.join(ROOT, 'fonts', `${name}.ttf`);
    if (!fs.existsSync(file)) throw new Error(`Font not found: ${file}`);
    const face = new hb.Face(new hb.Blob(fs.readFileSync(file)));
    const font = new hb.Font(face);
    fontCache.set(name, { face, font, upem: face.upem, paths: new Map() });
  }
  return fontCache.get(name);
}

// ---------- colour presets (vertical gradients, top -> bottom) -------------
const FILLS = {
  gold:   ['#FFF6B0', '#FFD700', '#F5A623', '#C97A00'],
  yellow: ['#FFF8A6', '#FFE01A', '#FFD700', '#FFB800'],
  white:  ['#FFFFFF', '#FFFFFF', '#F1F1F1', '#CFCFCF'],
  cyan:   ['#E6FFFF', '#7FE9FF', '#2FC8FF', '#0098E0'],
  green:  ['#F2FFB0', '#B6FF3B', '#6BE81E', '#2FA800'],
  orange: ['#FFE0A0', '#FFAE2B', '#FF8A00', '#D95E00'],
  red:    ['#FFB3A6', '#FF4A3A', '#E8231A', '#A80F0A'],
  black:  ['#2A2A2A', '#111111', '#000000', '#000000'],
};

// ---------- helpers ----------------------------------------------------------
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const isDeva = ch => /[\u0900-\u097F\u1CD0-\u1CFF\uA8E0-\uA8FF\u20B9\u200C\u200D]/.test(ch);

/** Split a line into runs: Devanagari -> Hindi font, Latin words -> English font.
 *  Spaces / digits / punctuation stay with the previous run (digits inside a Hindi
 *  phrase like "5 आदतें" use the Hindi font's own numerals). */
function runs(text) {
  const out = [];
  for (const ch of text) {
    const deva = isDeva(ch);
    const neutral = !deva && /[\s0-9.,!?'"\-–—:;()|%₹]/.test(ch);
    const last = out[out.length - 1];
    if (last && (neutral || last.deva === deva)) last.t += ch;
    else out.push({ t: ch, deva: neutral ? null : deva });
    if (out[out.length - 1].deva === null && !neutral) out[out.length - 1].deva = deva;
  }
  // a run made only of neutral chars (e.g. leading "5 ") joins the next run's script
  for (let i = 0; i < out.length; i++)
    if (out[i].deva === null) out[i].deva = out[i + 1]?.deva ?? out[i - 1]?.deva ?? false;
  return out;
}

/** Shape a line. Returns glyphs in em units (1 = font size) + ink bbox (y down, baseline 0). */
function shape(text, hindiFont, engFont, tracking = 0) {
  const glyphs = [];
  let pen = 0, x0 = Infinity, x1 = -Infinity, top = Infinity, bottom = -Infinity;
  for (const r of runs(text)) {
    const f = loadFont(r.deva ? hindiFont : engFont);
    const buf = new hb.Buffer();
    buf.addText(r.t);
    buf.guessSegmentProperties();
    hb.shape(f.font, buf);
    const infos = buf.getGlyphInfos(), pos = buf.getGlyphPositions();
    infos.forEach((g, i) => {
      const p = pos[i], gid = g.codepoint;
      const gx = pen + p.xOffset / f.upem, gy = -p.yOffset / f.upem;
      glyphs.push({ f, gid, x: gx, y: gy });
      const e = f.font.glyphExtents(gid);
      if (e && e.width !== 0 && e.height !== 0) {
        x0 = Math.min(x0, gx + e.xBearing / f.upem);
        x1 = Math.max(x1, gx + (e.xBearing + e.width) / f.upem);
        top = Math.min(top, gy - e.yBearing / f.upem);
        bottom = Math.max(bottom, gy - (e.yBearing + e.height) / f.upem);
      }
      pen += p.xAdvance / f.upem + (p.xAdvance ? tracking : 0);
    });
    buf.destroy?.();
  }
  if (!glyphs.length || x0 === Infinity) throw new Error(`Nothing to draw for line "${text}"`);
  return { glyphs, x: x0, top, bottom, w: x1 - x0, h: bottom - top, advance: pen };
}

/** Convert shaped glyphs to one SVG path string at given size / origin (baseline). */
function toPath(shaped, size, ox, oy) {
  const parts = [];
  for (const g of shaped.glyphs) {
    let d = g.f.paths.get(g.gid);
    if (d === undefined) { d = g.f.font.glyphToPath(g.gid); g.f.paths.set(g.gid, d); }
    if (!d) continue;
    const k = size / g.f.upem, bx = ox + g.x * size, by = oy + g.y * size;
    let isX = true;
    parts.push(d.replace(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi, n => {
      const v = isX ? bx + parseFloat(n) * k : by - parseFloat(n) * k;
      isX = !isX;
      return v.toFixed(2);
    }).replace(/([MLQCZ])/g, ' $1').trim());
  }
  return parts.join(' ');
}

function render(svg) {
  return new Resvg(svg, { fitTo: { mode: 'original' }, font: { loadSystemFonts: false } });
}

function gradientDef(id, stops) {
  const n = stops.length - 1;
  return `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">${
    stops.map((c, i) => `<stop offset="${(i / n).toFixed(2)}" stop-color="${c}"/>`).join('')}</linearGradient>`;
}

// ---------- main -------------------------------------------------------------
async function main() {
  const cfgPath = process.argv[2];
  if (!cfgPath) { console.error('Usage: node thumbnail/render.mjs <config.json>'); process.exit(1); }
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  const base = path.dirname(path.resolve(cfgPath));
  const rel = p => path.isAbsolute(p) ? p : path.resolve(base, p);

  const layout = cfg.layout || 'text-left';           // text-left | text-right
  const hindiFam = HINDI_FONTS[cfg.hindi_font || 'noto-black'] || cfg.hindi_font;
  const engFam = ENGLISH_FONTS[cfg.english_font || 'poppins-black'] || cfg.english_font;
  const brand = cfg.brand ?? 'KitaabDeep';

  // text zone (can be overridden in config)
  const area = cfg.text_area || (layout === 'text-left'
    ? { x: 40, y: 40, w: 660, h: 560 }
    : { x: 580, y: 40, w: 660, h: 560 });

  // ---- background
  const bgBuf = await sharp(rel(cfg.background)).resize(W, H, { fit: 'cover', position: cfg.bg_position || 'centre' }).png().toBuffer();
  const bgData = `data:image/png;base64,${bgBuf.toString('base64')}`;

  const defs = [];
  const layers = [];
  layers.push(`<image href="${bgData}" x="0" y="0" width="${W}" height="${H}"/>`);

  // readability gradient on text side (हल्का ब्लैक ग्रेडिएंट)
  const shade = cfg.text_shade ?? 0.6;
  if (shade > 0) {
    const [x1, x2] = layout === 'text-left' ? [0, 1] : [1, 0];
    defs.push(`<linearGradient id="shade" x1="${x1}" y1="0" x2="${x2}" y2="0">
      <stop offset="0" stop-color="#000" stop-opacity="${shade}"/>
      <stop offset="0.45" stop-color="#000" stop-opacity="${shade * 0.7}"/>
      <stop offset="0.70" stop-color="#000" stop-opacity="0"/></linearGradient>`);
    layers.push(`<rect width="${W}" height="${H}" fill="url(#shade)"/>`);
  }
  if (cfg.vignette ?? true) {
    defs.push(`<radialGradient id="vig" cx="0.5" cy="0.5" r="0.75">
      <stop offset="0.6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.55"/></radialGradient>`);
    layers.push(`<rect width="${W}" height="${H}" fill="url(#vig)"/>`);
  }

  // ---- filters
  defs.push(`<filter id="blurShadow" x="-20%" y="-30%" width="140%" height="160%"><feGaussianBlur stdDeviation="5"/></filter>`);
  defs.push(`<filter id="glow" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="16"/></filter>`);
  defs.push(`<filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>`);

  // ---- measure + fit lines
  const lines = cfg.lines.map((l, i) => {
    const m = shape(l.text, hindiFam, engFam, l.tracking ?? cfg.tracking ?? 0);
    const scale = l.scale ?? 1;                       // fraction of zone width
    let size = (area.w * scale) / m.w;
    if (l.max_size) size = Math.min(size, l.max_size);
    size = Math.min(size, cfg.max_size ?? 190);
    return { ...l, i, m, size };
  });
  const gapRatio = cfg.line_gap ?? 0.10;
  const heightAt = k => lines.reduce((s, l) => s + l.m.h * l.size * k, 0)
    + lines.slice(1).reduce((s, l) => s + gapRatio * l.size * k, 0);
  let k = 1;
  if (heightAt(1) > area.h) k = area.h / heightAt(1);
  lines.forEach(l => { l.size *= k; });

  let cursor = area.y + (area.h - heightAt(1)) / 2;
  const cx = area.x + area.w / 2;
  for (const l of lines) {
    const s = l.size;
    if (l !== lines[0]) cursor += gapRatio * l.size;
    l.baseline = cursor - l.m.top * s;
    const align = l.align || cfg.align || 'center';
    const inkW = l.m.w * s;
    const left = align === 'left' ? area.x : align === 'right' ? area.x + area.w - inkW : cx - inkW / 2;
    l.x = left - l.m.x * s;
    l.box = { x: left, y: cursor, w: inkW, h: l.m.h * s };
    cursor += l.m.h * s;
  }

  // ---- accents behind text
  for (const l of lines) {
    if (l.band) {          // solid highlight band (Life-Upgrade style)
      const p = l.size * 0.12;
      layers.push(`<rect x="${l.box.x - p * 1.6}" y="${l.box.y - p}" width="${l.box.w + p * 3.2}" height="${l.box.h + p * 2}" rx="${p * 0.6}" fill="${l.band}"/>`);
    }
    if (l.ring) {          // glowing swoosh ring around a word (Book-Gallery style)
      const c = FILLS[l.ring]?.[2] || l.ring;
      const rx = l.box.w / 2 + l.size * 0.28, ry = l.box.h / 2 + l.size * 0.30;
      const ex = l.box.x + l.box.w / 2, ey = l.box.y + l.box.h / 2;
      const pt = a => [ex + rx * Math.cos(a), ey + ry * Math.sin(a)].map(v => v.toFixed(1)).join(' ');
      // open swoosh: starts lower-left, sweeps over the top, ends lower-right
      const a0 = Math.PI * 0.80, a1 = Math.PI * 2.28;
      const arc = `M ${pt(a0)} A ${rx.toFixed(1)} ${ry.toFixed(1)} 0 1 1 ${pt(a1)}`;
      layers.push(`<path d="${arc}" fill="none" stroke="${c}" stroke-width="${(l.size * 0.10).toFixed(1)}" stroke-linecap="round" filter="url(#glow)"/>`);
      layers.push(`<path d="${arc}" fill="none" stroke="${c}" stroke-width="${(l.size * 0.05).toFixed(1)}" stroke-linecap="round"/>`);
      layers.push(`<path d="${arc}" fill="none" stroke="#FFFFFF" stroke-width="${(l.size * 0.018).toFixed(1)}" stroke-linecap="round" opacity="0.95"/>`);
    }
  }

  // ---- text layers
  lines.forEach((l, idx) => {
    const fillKey = l.color || ['yellow', 'white', 'gold'][idx % 3];
    const stops = FILLS[fillKey] || [l.color, l.color];
    const gid = `fill${idx}`;
    defs.push(gradientDef(gid, stops));
    const d = toPath(l.m, l.size, l.x, l.baseline);
    const sw = l.size * (l.stroke ?? cfg.stroke ?? 0.085);
    const P = (attrs, dx = 0, dy = 0) =>
      `<path d="${d}" ${attrs}${dx || dy ? ` transform="translate(${dx.toFixed(1)} ${dy.toFixed(1)})"` : ''}/>`;
    const outline = l.outline_color || '#000';

    if (l.glow) {
      const gc = FILLS[l.glow]?.[2] || l.glow;
      layers.push(P(`fill="${gc}" stroke="${gc}" stroke-width="${sw * 2}" filter="url(#glow)" opacity="0.75"`));
    }
    // drop shadow
    const sd = l.size * 0.045;
    layers.push(P(`fill="#000" stroke="#000" stroke-width="${sw * 1.2}" stroke-linejoin="round" filter="url(#blurShadow)" opacity="0.85"`, sd, sd * 1.3));
    // 3D extrusion
    const depth = l.extrude ?? cfg.extrude ?? 0;
    if (depth > 0) {
      const ec = l.extrude_color || '#3a2400';
      const steps = Math.ceil(l.size * depth);
      for (let t = steps; t >= 1; t--)
        layers.push(P(`fill="${ec}" stroke="${outline}" stroke-width="${sw}" stroke-linejoin="round"`, t * 0.6, t));
    }
    // main: thick outline (own layer, so overlapping Devanagari glyphs such as
    // matras never get a stroke painted over the neighbouring letter) + gradient fill
    layers.push(P(`fill="${outline}" stroke="${outline}" stroke-width="${sw}" stroke-linejoin="round"`));
    layers.push(P(`fill="url(#${gid})"`));
    // thin inner highlight edge for punch
    if (l.inner_edge ?? cfg.inner_edge ?? false)
      layers.push(P(`fill="none" stroke="#ffffff" stroke-opacity="0.18" stroke-width="${Math.max(1, l.size * 0.008)}"`));
  });

  // ---- underline brush swoosh
  for (const l of lines.filter(l => l.underline)) {
    const c = FILLS[l.underline]?.[1] || l.underline;
    const y = l.box.y + l.box.h + l.size * 0.10;
    const x1 = l.box.x + l.box.w * 0.05, x2 = l.box.x + l.box.w * 0.95;
    const d = `M ${x1} ${y + 6} Q ${(x1 + x2) / 2} ${y - 10} ${x2} ${y - 2}`;
    layers.push(`<path d="${d}" stroke="#000" stroke-opacity="0.6" stroke-width="16" fill="none" stroke-linecap="round"/>`);
    layers.push(`<path d="${d}" stroke="${c}" stroke-width="9" fill="none" stroke-linecap="round"/>`);
  }

  // ---- optional red arrow pointing at the asset
  if (cfg.arrow) {
    const a = cfg.arrow;  // {x,y,len,angle}
    const len = a.len ?? 130, ang = a.angle ?? (layout === 'text-left' ? 0 : 180);
    layers.push(`<g transform="translate(${a.x} ${a.y}) rotate(${ang})">
      <path d="M0 -11 L${len - 46} -11 L${len - 46} -30 L${len} 0 L${len - 46} 30 L${len - 46} 11 L0 11 Z" fill="#E8231A" stroke="#fff" stroke-width="5" stroke-linejoin="round" filter="url(#softGlow)" opacity="0.6"/>
      <path d="M0 -11 L${len - 46} -11 L${len - 46} -30 L${len} 0 L${len - 46} 30 L${len - 46} 11 L0 11 Z" fill="#E8231A" stroke="#fff" stroke-width="5" stroke-linejoin="round"/></g>`);
  }

  // ---- KitaabDeep watermark (bottom-left, small gold)
  if (brand) {
    const bs = cfg.brand_size ?? 30;
    const bm = shape(brand, hindiFam, ENGLISH_FONTS['poppins-extrabold']);
    const tw = bm.w * bs, th = bs * 1.0;
    const pad = bs * 0.45, flameW = bs * 0.85;
    const bw = pad + flameW + bs * 0.3 + tw + pad * 1.2, bh = th + pad * 1.4;
    const bx = cfg.brand_x ?? 32, by = cfg.brand_y ?? (H - bh - 28);
    defs.push(gradientDef('brandGold', FILLS.gold));
    defs.push(`<linearGradient id="flame" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#FF3D00"/><stop offset="0.55" stop-color="#FF9100"/><stop offset="1" stop-color="#FFE14D"/></linearGradient>`);
    const fx = bx + pad, fy = by + bh / 2, fs = flameW;
    const flame = `M ${fx + fs * 0.5} ${fy - fs * 0.62}
      C ${fx + fs * 0.62} ${fy - fs * 0.28}, ${fx + fs * 1.0} ${fy - fs * 0.18}, ${fx + fs * 0.95} ${fy + fs * 0.2}
      C ${fx + fs * 0.92} ${fy + fs * 0.5}, ${fx + fs * 0.7} ${fy + fs * 0.62}, ${fx + fs * 0.5} ${fy + fs * 0.62}
      C ${fx + fs * 0.25} ${fy + fs * 0.62}, ${fx + fs * 0.05} ${fy + fs * 0.45}, ${fx + fs * 0.06} ${fy + fs * 0.18}
      C ${fx + fs * 0.08} ${fy - fs * 0.05}, ${fx + fs * 0.25} ${fy - fs * 0.12}, ${fx + fs * 0.3} ${fy - fs * 0.3}
      C ${fx + fs * 0.4} ${fy - fs * 0.15}, ${fx + fs * 0.42} ${fy - fs * 0.05}, ${fx + fs * 0.45} ${fy}
      C ${fx + fs * 0.55} ${fy - fs * 0.2}, ${fx + fs * 0.55} ${fy - fs * 0.4}, ${fx + fs * 0.5} ${fy - fs * 0.62} Z`;
    layers.push(`<g>
      <rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="${bh / 2}" fill="#000" fill-opacity="0.62" stroke="url(#brandGold)" stroke-width="2.5"/>
      <path d="${flame}" fill="url(#flame)"/>
      <path d="${toPath(bm, bs, bx + pad + flameW + bs * 0.3 - bm.x * bs, fy - (bm.top + bm.h / 2) * bs)}" fill="url(#brandGold)"/>
    </g>`);
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<defs>${defs.join('\n')}</defs>
${layers.join('\n')}
</svg>`;

  const png = render(svg).render().asPng();
  const out = rel(cfg.output || `../output/${path.basename(cfgPath, '.json')}.jpg`);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  if (out.endsWith('.png')) fs.writeFileSync(out, png);
  else await sharp(png).jpeg({ quality: 92, chromaSubsampling: '4:4:4' }).toFile(out);
  if (cfg.debug_svg) fs.writeFileSync(out.replace(/\.\w+$/, '.svg'), svg);
  const kb = (fs.statSync(out).size / 1024).toFixed(0);
  console.log(`✔ ${path.relative(ROOT, out)}  (${W}x${H}, ${kb} KB)`);
}

main().catch(e => { console.error(e); process.exit(1); });
