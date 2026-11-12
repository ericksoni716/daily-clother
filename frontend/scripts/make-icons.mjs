// Draws the app icon (a coat hanger on deep green) as PNGs with no dependencies.
// Run with `npm run icons`; the output in public/icons is committed.
import { mkdirSync, writeFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons');
mkdirSync(out, { recursive: true });

const BG = [0x3c, 0x52, 0x4a];
const FG = [0xf6, 0xf2, 0xea];

// Shapes in a 0..1 unit square. `pad` shrinks the glyph for maskable icons.
function shapes(pad) {
  const s = (v) => pad + v * (1 - 2 * pad);
  return {
    segments: [
      // shoulders and bar of the hanger
      [s(0.5), s(0.40), s(0.14), s(0.66)],
      [s(0.5), s(0.40), s(0.86), s(0.66)],
      [s(0.14), s(0.66), s(0.86), s(0.66)],
      // neck down from the hook
      [s(0.5), s(0.33), s(0.5), s(0.40)],
    ],
    // hook: arc centred above the neck
    arc: { cx: s(0.5), cy: s(0.255), r: 0.075 * (1 - 2 * pad), from: Math.PI * 0.5, to: Math.PI * 2.05 },
    width: 0.045 * (1 - 2 * pad),
  };
}

function distSeg(px, py, [x1, y1, x2, y2]) {
  const dx = x2 - x1, dy = y2 - y1;
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

function distArc(px, py, { cx, cy, r, from, to }) {
  let a = Math.atan2(py - cy, px - cx);
  while (a < from) a += Math.PI * 2;
  if (a <= to) return Math.abs(Math.hypot(px - cx, py - cy) - r);
  const end = (ang) => Math.hypot(px - (cx + r * Math.cos(ang)), py - (cy + r * Math.sin(ang)));
  return Math.min(end(from), end(to));
}

function draw(size, { pad = 0.08, rounded = false } = {}) {
  const sh = shapes(pad);
  const px = Buffer.alloc(size * size * 4);
  const radius = 0.22;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let cov = 0, bgCov = 0;
      // 4x4 supersampling
      for (let sy = 0; sy < 4; sy++) {
        for (let sx = 0; sx < 4; sx++) {
          const u = (x + (sx + 0.5) / 4) / size, v = (y + (sy + 0.5) / 4) / size;
          let inBg = true;
          if (rounded) {
            const qx = Math.max(Math.abs(u - 0.5) - (0.5 - radius), 0);
            const qy = Math.max(Math.abs(v - 0.5) - (0.5 - radius), 0);
            inBg = Math.hypot(qx, qy) <= radius;
          }
          if (!inBg) continue;
          bgCov++;
          let d = distArc(u, v, sh.arc);
          for (const seg of sh.segments) d = Math.min(d, distSeg(u, v, seg));
          if (d <= sh.width / 2) cov++;
        }
      }
      const a = cov / 16, i = (y * size + x) * 4;
      for (let c = 0; c < 3; c++) px[i + c] = Math.round(BG[c] * (1 - a) + FG[c] * a);
      px[i + 3] = Math.round((bgCov / 16) * 255);
    }
  }
  return png(size, px);
}

function crc32(buf) {
  let c, crc = 0xffffffff;
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

function png(size, rgba) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0;
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0)),
  ]);
}

const files = {
  'apple-touch-icon.png': draw(180, { pad: 0.1 }),
  'icon-192.png': draw(192, { pad: 0.1 }),
  'icon-512.png': draw(512, { pad: 0.1 }),
  'maskable-512.png': draw(512, { pad: 0.2 }),
  'favicon-32.png': draw(32, { pad: 0.02, rounded: true }),
};
for (const [name, data] of Object.entries(files)) writeFileSync(join(out, name), data);
console.log(`wrote ${Object.keys(files).length} icons to ${out}`);
