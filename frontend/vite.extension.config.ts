// Сборка расширения «Проверить пост» (FE-17): npm run build:ext → dist-ext/ (папка для «Загрузить распакованное»).
// Входы: окошко, настройки, service worker. Адрес сервера по умолчанию — VITE_API_URL при сборке.
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, loadEnv, type Plugin } from "vite";

import { ICON_SIZES, iconPng } from "./scripts/ext-assets.mjs";

const DEFAULT_SERVER = "http://109.196.167.204:8080";

/** manifest.json с адресом сервера в host_permissions и значки PNG из логотипа. */
function manifest(server: string): Plugin {
  return {
    name: "mp-extension-manifest",
    generateBundle() {
      const icons = Object.fromEntries(ICON_SIZES.map((s) => [String(s), `icons/${s}.png`]));
      const m = JSON.parse(readFileSync(resolve(__dirname, "extension/manifest.json"), "utf8"));
      m.host_permissions = [`${new URL(server).origin}/*`];
      m.icons = icons;
      m.action = { ...m.action, default_icon: icons };
      this.emitFile({ type: "asset", fileName: "manifest.json", source: `${JSON.stringify(m, null, 2)}\n` });
      for (const s of ICON_SIZES) this.emitFile({ type: "asset", fileName: `icons/${s}.png`, source: iconPng(s) });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "VITE_");
  const server = (env.VITE_API_URL || DEFAULT_SERVER).replace(/\/+$/, "");
  return {
    root: resolve(__dirname, "extension"),
    base: "./",
    publicDir: resolve(__dirname, "public"), // max-logo.webp для PlatformLogo
    plugins: [react(), manifest(server)],
    define: { "import.meta.env.VITE_API_URL": JSON.stringify(server) },
    build: {
      outDir: resolve(__dirname, "dist-ext"),
      emptyOutDir: true,
      // окошко открывается с диска — модули не дробим ради кэша, но и в один файл не сливаем
      modulePreload: false,
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        input: {
          popup: resolve(__dirname, "extension/popup.html"),
          options: resolve(__dirname, "extension/options.html"),
          background: resolve(__dirname, "src/extension/background.ts"),
        },
        output: {
          // service worker указан в manifest по имени — без хеша
          entryFileNames: (chunk) => (chunk.name === "background" ? "background.js" : "assets/[name]-[hash].js"),
        },
      },
    },
  };
});
