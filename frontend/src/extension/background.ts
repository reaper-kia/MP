// Service worker расширения (FE-17): контекстное меню, запуск поиска и опрос до финала.
// Состояние — в chrome.storage.session (state.ts), окошко только показывает его.
import { api, ApiError, setApiServer, unwrap, type S } from "../api/client";
import { presetPeriod } from "../features/search/period";
import { isFinal } from "../features/search/status";
import { errorText } from "../lib/errors";
import { loadSettings } from "./settings";
import { loadRun, NO_CONNECTION, saveRun, type ExtMessage, type RunState } from "./state";

const MENU_ID = "mp-find";
const ALARM = "mp-poll";
const POLL_MS = 2000;

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: MENU_ID, title: "Найти размещения в МедиаПульс", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) return;
  // openPopup — Chrome 127+ и только по жесту пользователя; не сработало — останется бейдж
  chrome.action.openPopup?.().catch(() => {});
  void loadSettings().then((s) => start(info.selectionText!.trim(), s.mode, s.days));
});

chrome.runtime.onMessage.addListener((msg: ExtMessage, _sender, reply) => {
  const done = () => reply(true);
  if (msg.type === "start") start(msg.query, msg.mode, msg.days).then(done);
  else if (msg.type === "cancel") cancel().then(done);
  else if (msg.type === "reset") reset().then(done);
  return true; // ответ асинхронный
});

// service worker засыпает через ~30 с без событий — будильник раз в 30 с продолжит опрос
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === ALARM) void poll();
});
chrome.runtime.onStartup.addListener(() => void poll());

async function start(query: string, mode: RunState["mode"], days: RunState["days"]) {
  const settings = await loadSettings();
  setApiServer(settings.server);
  const [from, to] = presetPeriod(days === 7 ? "7d" : "30d");
  const run: RunState = {
    query,
    mode,
    days,
    periodFrom: from!,
    periodTo: to!,
    server: settings.server,
    searchId: null,
    search: null,
    error: null,
    startedAt: Date.now(),
  };
  await saveRun(run);
  await setBadge("…", "#979b8d");
  try {
    // как форма на сайте: площадки — все доступные, источники — активные из каталога
    const platforms = (await unwrap(api.GET("/api/v1/platforms")))
      .filter((p) => p.status !== "unavailable")
      .map((p) => p.code);
    let sourceIds: string[] = [];
    if (mode === "selected") {
      const catalog = await unwrap(api.GET("/api/v1/sources", { params: { query: { limit: 200, offset: 0 } } }));
      sourceIds = catalog.items.filter((s) => s.is_active && platforms.includes(s.platform)).map((s) => s.id);
      if (sourceIds.length === 0) throw new Error("В каталоге нет активных источников — включите их на сайте или выберите «Везде»");
    }
    if (platforms.length === 0) throw new Error("Сейчас ни одна площадка не подключена");
    const search = await unwrap(
      api.POST("/api/v1/searches", {
        body: { query, period_from: from!, period_to: to!, mode, platforms, source_ids: sourceIds },
      }),
    );
    await update({ searchId: search.id, search });
    schedule();
  } catch (err) {
    await fail(err);
  }
}

async function poll() {
  const run = await loadRun();
  if (!run?.searchId || run.error || (run.search && isFinal(run.search.status))) {
    await chrome.alarms.clear(ALARM);
    return;
  }
  setApiServer(run.server);
  try {
    const search = await unwrap(
      api.GET("/api/v1/searches/{search_id}", { params: { path: { search_id: run.searchId } } }),
    );
    const cur = await loadRun();
    if (cur?.searchId !== run.searchId) return; // пока ждали ответ, запустили новый поиск
    await update({ search });
    if (isFinal(search.status)) await finish(search);
    else schedule();
  } catch (err) {
    await fail(err);
  }
}

let timer: ReturnType<typeof setTimeout> | undefined;
function schedule() {
  clearTimeout(timer);
  timer = setTimeout(() => void poll(), POLL_MS);
  void chrome.alarms.create(ALARM, { periodInMinutes: 0.5 });
}

async function finish(search: S["Search"]) {
  clearTimeout(timer);
  await chrome.alarms.clear(ALARM);
  const n = search.counts.total;
  if (search.status === "failed") await setBadge("!", "#f87171");
  else await setBadge(n > 999 ? "999+" : String(n), n > 0 ? "#84cc16" : "#979b8d");
}

async function cancel() {
  const run = await loadRun();
  if (!run?.searchId) return reset();
  setApiServer(run.server);
  try {
    const search = await unwrap(
      api.POST("/api/v1/searches/{search_id}/cancel", { params: { path: { search_id: run.searchId } } }),
    );
    await update({ search });
    await finish(search);
  } catch (err) {
    await fail(err);
  }
}

async function reset() {
  clearTimeout(timer);
  await chrome.alarms.clear(ALARM);
  await saveRun(null);
  await setBadge("", "#84cc16");
}

async function update(patch: Partial<RunState>) {
  const run = await loadRun();
  if (run) await saveRun({ ...run, ...patch });
}

async function fail(err: unknown) {
  clearTimeout(timer);
  await chrome.alarms.clear(ALARM);
  // ошибки API — текстами сайта; сеть / адрес — «Нет связи»; свои (нет источников) — как есть
  const text =
    err instanceof ApiError ? errorText(err) : err instanceof TypeError ? NO_CONNECTION : err instanceof Error ? err.message : errorText(err);
  await update({ error: text });
  await setBadge("!", "#f87171");
}

async function setBadge(text: string, color: string) {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}
