// npm run zip:ext — dist-ext/ (после npm run build:ext) → dist-ext.zip для релиза и «Загрузить распакованное».
import { existsSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { zip } from "./ext-assets.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = join(root, "dist-ext");
if (!existsSync(join(dir, "manifest.json"))) {
  console.error("Нет dist-ext/manifest.json — сначала npm run build:ext");
  process.exit(1);
}
writeFileSync(join(root, "dist-ext.zip"), zip(dir));
console.log("Архив: dist-ext.zip");
