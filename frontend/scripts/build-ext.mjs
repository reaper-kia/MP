// npm run build:ext — расширение Chrome (FE-10): extension/ → dist-ext/mediapulse/ + dist-ext/mediapulse-extension.zip.
// MP_SERVER=http://адрес-стенда npm run build:ext — адрес сервера по умолчанию (в панели его можно сменить).
// Значки PNG рисуются здесь же из логотипа (public/favicon.svg): в manifest Chrome не принимает SVG.
import { cpSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { crc32, deflateRawSync, deflateSync } from "node:zlib";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "dist-ext");
const dir = join(out, "mediapulse");
const server = (process.env.MP_SERVER ?? "http://localhost").replace(/\/+$/, "");

rmSync(out, { recursive: true, force: true });
mkdirSync(join(dir, "icons"), { recursive: true });
cpSync(join(root, "extension"), dir, { recursive: true });

writeFileSync(
  join(dir, "config.js"),
  `// Адрес сервера по умолчанию (собрано npm run build:ext). В панели его можно поменять (⚙).\nself.MP_DEFAULT_SERVER = ${JSON.stringify(server)};\n`,
);

const SIZES = [16, 32, 48, 128];
for (const size of SIZES) writeFileSync(join(dir, "icons", `${size}.png`), png(size, renderLogo(size)));

const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8"));
const icons = Object.fromEntries(SIZES.map((s) => [String(s), `icons/${s}.png`]));
manifest.icons = icons;
manifest.action = { ...manifest.action, default_icon: icons };
writeFileSync(join(dir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

const zipPath = join(out, "mediapulse-extension.zip");
writeFileSync(zipPath, zip(dir));
console.log(`Расширение: ${relative(root, dir)} (адрес сервера ${server})\nАрхив: ${relative(root, zipPath)}`);

// ── логотип: тёмный скруглённый квадрат, лаймовые «P», квадрат и круг (координаты favicon.svg, 24×24) ──

function renderLogo(size) {
  const BG = [0x17, 0x19, 0x14];
  const FG = [0xbe, 0xf2, 0x64];
  const SS = 4; // суперсэмплинг для сглаживания краёв
  const px = new Uint8Array(size * size * 4);
  // точка в системе фигур favicon: translate(3 3) scale(0.75)
  const inShape = (x, y) => {
    const u = (x - 3) / 0.75;
    const v = (y - 3) / 0.75;
    const p = (u >= 5 && u <= 12 && v >= 4 && v <= 12) || ((u - 12) ** 2 + (v - 8) ** 2 <= 16 && u >= 12);
    const sq = u >= 12 && u <= 19 && v >= 12 && v <= 20;
    const circle = (u - 8.5) ** 2 + (v - 16.5) ** 2 <= 3.5 ** 2;
    return p || sq || circle;
  };
  const inRounded = (x, y) => {
    const r = 6;
    const cx = Math.min(Math.max(x, r), 24 - r);
    const cy = Math.min(Math.max(y, r), 24 - r);
    return x >= 0 && x <= 24 && y >= 0 && y <= 24 && (x - cx) ** 2 + (y - cy) ** 2 <= r * r;
  };
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) {
      let bg = 0;
      let fg = 0;
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const x = ((i + (sx + 0.5) / SS) * 24) / size;
          const y = ((j + (sy + 0.5) / SS) * 24) / size;
          if (!inRounded(x, y)) continue;
          if (inShape(x, y)) fg++;
          else bg++;
        }
      }
      const n = SS * SS;
      const a = (bg + fg) / n;
      const k = (j * size + i) * 4;
      for (let c = 0; c < 3; c++) px[k + c] = bg + fg ? Math.round((BG[c] * bg + FG[c] * fg) / (bg + fg)) : 0;
      px[k + 3] = Math.round(a * 255);
    }
  }
  return px;
}

// ── PNG (RGBA, 8 бит) ──

function png(size, rgba) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0; // фильтр None
    Buffer.from(rgba.buffer, y * size * 4, size * 4).copy(raw, y * (size * 4 + 1) + 1);
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(td));
    return Buffer.concat([len, td, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ── ZIP (deflate, без каталогов-записей; имена в UTF-8) ──

function listFiles(base, sub = "") {
  return readdirSyncSorted(join(base, sub)).flatMap((e) =>
    e.isDirectory() ? listFiles(base, join(sub, e.name)) : [join(sub, e.name).split("\\").join("/")],
  );
}

function readdirSyncSorted(p) {
  return readdirSync(p, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
}

function zip(base) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const name of listFiles(base)) {
    const data = readFileSync(join(base, name));
    const packed = deflateRawSync(data);
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(data);
    const head = Buffer.alloc(30);
    head.writeUInt32LE(0x04034b50, 0);
    head.writeUInt16LE(20, 4);
    head.writeUInt16LE(0x0800, 6); // UTF-8 имена
    head.writeUInt16LE(8, 8); // deflate
    head.writeUInt32LE(0, 10); // время/дата
    head.writeUInt32LE(crc, 14);
    head.writeUInt32LE(packed.length, 18);
    head.writeUInt32LE(data.length, 22);
    head.writeUInt16LE(nameBuf.length, 26);
    locals.push(head, nameBuf, packed);

    const cen = Buffer.alloc(46);
    cen.writeUInt32LE(0x02014b50, 0);
    cen.writeUInt16LE(20, 4);
    cen.writeUInt16LE(20, 6);
    cen.writeUInt16LE(0x0800, 8);
    cen.writeUInt16LE(8, 10);
    cen.writeUInt32LE(0, 12);
    cen.writeUInt32LE(crc, 16);
    cen.writeUInt32LE(packed.length, 20);
    cen.writeUInt32LE(data.length, 24);
    cen.writeUInt16LE(nameBuf.length, 28);
    cen.writeUInt32LE(offset, 42);
    centrals.push(cen, nameBuf);
    offset += head.length + nameBuf.length + packed.length;
  }
  const cdir = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(centrals.length / 2, 8);
  end.writeUInt16LE(centrals.length / 2, 10);
  end.writeUInt32LE(cdir.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cdir, end]);
}
