// Подмена chrome.* для разработки окошка без установки расширения: npm run dev → /extension/dev.html.
// Service worker и окошко работают в одной странице; запросы идут через прокси Vite (/api → gateway).
type Listener = (...args: never[]) => unknown;

function makeEvent() {
  const ls = new Set<Listener>();
  return {
    addListener: (l: Listener) => void ls.add(l),
    removeListener: (l: Listener) => void ls.delete(l),
    emit: (...args: unknown[]) => [...ls].map((l) => (l as (...a: unknown[]) => unknown)(...args)),
  };
}

const onChanged = makeEvent();

function area(name: string) {
  const data: Record<string, unknown> = {};
  return {
    async get(key: string) {
      return key in data ? { [key]: structuredClone(data[key]) } : {};
    },
    async set(items: Record<string, unknown>) {
      const changes: Record<string, { oldValue?: unknown; newValue?: unknown }> = {};
      for (const [k, v] of Object.entries(items)) {
        changes[k] = { oldValue: data[k], newValue: structuredClone(v) };
        data[k] = structuredClone(v);
      }
      onChanged.emit(changes, name);
    },
    async remove(key: string) {
      const changes = { [key]: { oldValue: data[key] } };
      delete data[key];
      onChanged.emit(changes, name);
    },
  };
}

const onMessage = makeEvent();
const badge = { text: "", color: "" };

const fake = {
  storage: { local: area("local"), session: area("session"), onChanged },
  runtime: {
    onMessage,
    onInstalled: makeEvent(),
    onStartup: makeEvent(),
    sendMessage: (msg: unknown) =>
      new Promise((resolve) => {
        onMessage.emit(msg, {}, resolve);
      }),
    openOptionsPage: () => window.open("/extension/dev.html?page=options", "_blank"),
  },
  contextMenus: { create: () => undefined, onClicked: makeEvent() },
  alarms: { create: async () => undefined, clear: async () => true, onAlarm: makeEvent() },
  action: {
    setBadgeText: async ({ text }: { text: string }) => {
      badge.text = text;
      document.title = text ? `[${text}] МедиаПульс` : "МедиаПульс";
    },
    setBadgeBackgroundColor: async ({ color }: { color: string }) => void (badge.color = color),
    openPopup: async () => undefined,
  },
  tabs: {
    query: async () => [{ id: 1, url: new URLSearchParams(location.search).get("tab") ?? "https://vk.com/krsk_overhear" }],
    create: ({ url }: { url: string }) => window.open(url, "_blank"),
  },
  scripting: {
    executeScript: async () => [{ result: new URLSearchParams(location.search).get("selection") ?? "" }],
  },
  permissions: { request: async () => true },
};

(globalThis as unknown as { chrome: unknown }).chrome = fake;

// сервер — сам dev-сервер: /api проксируется в gateway (VITE_API_TARGET)
await fake.storage.local.set({ settings: { server: location.origin, mode: "selected", days: 30 } });
export {};
