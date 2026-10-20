// Боковая панель: сервис в iframe + «Добавить эту страницу как источник» (адрес вкладки → /sources?add=…).
const $ = (id) => document.getElementById(id);
const app = $("app");
const add = $("add");
const page = $("page");
const settings = $("settings");
const serverInput = $("server");

let server = self.MP_DEFAULT_SERVER;
let tabUrl = null;

const trimSlash = (s) => s.replace(/\/+$/, "");
const open = (path) => {
  app.src = trimSlash(server) + path;
};

// Источником может быть только обычная веб-страница — не chrome://, не сам сервис
function isCandidate(url) {
  if (!url || !/^https?:\/\//i.test(url)) return false;
  try {
    return new URL(url).origin !== new URL(server).origin;
  } catch {
    return true;
  }
}

async function refreshTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  tabUrl = tab?.url ?? null;
  const ok = isCandidate(tabUrl);
  add.disabled = !ok;
  page.textContent = ok ? tabUrl.replace(/^https?:\/\/(www\.)?/i, "") : "Откройте страницу группы или канала";
  page.title = ok ? tabUrl : "";
}

add.addEventListener("click", () => {
  if (isCandidate(tabUrl)) open(`/sources?add=${encodeURIComponent(tabUrl)}`);
});

$("toggle-settings").addEventListener("click", (e) => {
  settings.hidden = !settings.hidden;
  e.currentTarget.setAttribute("aria-expanded", String(!settings.hidden));
  if (!settings.hidden) serverInput.focus();
});

settings.addEventListener("submit", async (e) => {
  e.preventDefault();
  server = trimSlash(serverInput.value.trim());
  await chrome.storage.local.set({ server });
  settings.hidden = true;
  open("/");
  refreshTab();
});

chrome.tabs.onActivated.addListener(refreshTab);
chrome.tabs.onUpdated.addListener((_id, info, tab) => {
  if (tab.active && (info.url || info.status === "complete")) refreshTab();
});
chrome.windows.onFocusChanged.addListener(refreshTab);

chrome.storage.local.get("server").then(({ server: saved }) => {
  if (saved) server = saved;
  serverInput.value = server;
  open("/");
  refreshTab();
});
