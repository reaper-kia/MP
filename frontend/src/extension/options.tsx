// Настройки расширения (FE-17): адрес сервера (проверка — GET /health/ready), режим и период по умолчанию.
import { Button, SegmentedControl, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { Icon } from "../components/Icon";
import classes from "./options.module.css";
import { DEFAULT_SERVER, loadSettings, originPattern, saveSettings, type ExtSettings } from "./settings";
import { mount } from "./shared";

type Check = { state: "idle" | "checking" | "ok" | "fail"; text?: string };

function Options() {
  const [s, setS] = useState<ExtSettings | null>(null);
  const [server, setServer] = useState("");
  const [check, setCheck] = useState<Check>({ state: "idle" });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void loadSettings().then((x) => {
      setS(x);
      setServer(x.server);
    });
  }, []);
  if (!s) return null;

  const normalized = server.trim().replace(/\/+$/, "");
  const valid = /^https?:\/\/[^/\s]+/i.test(normalized);

  async function verify(): Promise<boolean> {
    setCheck({ state: "checking" });
    try {
      // без разрешения на этот адрес запрос заблокирует CORS — спрашиваем его здесь, по клику
      const granted = await chrome.permissions.request({ origins: [originPattern(normalized)] });
      if (!granted) {
        setCheck({ state: "fail", text: "Без разрешения на этот адрес расширение не сможет искать" });
        return false;
      }
      const r = await fetch(`${normalized}/health/ready`, { signal: AbortSignal.timeout(8000) });
      // 200 со страницей вместо JSON — это не МедиаПульс (или адрес фронта без прокси /health)
      const body = (await r.json().catch(() => null)) as { status?: string } | null;
      if (!r.ok || !body?.status) throw new Error(String(r.status));
      setCheck({ state: "ok", text: "Сервер отвечает" });
      return true;
    } catch {
      setCheck({ state: "fail", text: "Сервер не отвечает — проверьте адрес и порт" });
      return false;
    }
  }

  async function save() {
    if (!(await verify())) return;
    const next = { ...s!, server: normalized };
    await saveSettings(next);
    setS(next);
    setSaved(true);
  }

  return (
    <div className={classes.page}>
      <h1 className={classes.title}>
        <span className={classes.logo}>
          <Icon name="logo" size={18} />
        </span>
        МедиаПульс — настройки расширения
      </h1>

      <section className={classes.card}>
        <TextInput
          label="Адрес сервера"
          description={`Например, ${DEFAULT_SERVER}`}
          value={server}
          onChange={(e) => {
            setServer(e.currentTarget.value);
            setCheck({ state: "idle" });
            setSaved(false);
          }}
          error={server && !valid ? "Нужен адрес вида http://адрес:порт" : undefined}
        />
        <div className={classes.row}>
          <Button variant="default" size="xs" disabled={!valid} loading={check.state === "checking"} onClick={() => void verify()}>
            Проверить связь
          </Button>
          {check.text && (
            <span className={classes.check} data-state={check.state}>
              {check.text}
            </span>
          )}
        </div>
      </section>

      <section className={classes.card}>
        <p className={classes.label}>По умолчанию для поиска из контекстного меню</p>
        <div className={classes.row}>
          <SegmentedControl
            size="xs"
            value={s.mode}
            onChange={(v) => {
              setS({ ...s, mode: v as ExtSettings["mode"] });
              setSaved(false);
            }}
            data={[
              { value: "selected", label: "Мои источники" },
              { value: "global", label: "Везде" },
            ]}
          />
          <SegmentedControl
            size="xs"
            value={String(s.days)}
            onChange={(v) => {
              setS({ ...s, days: v === "7" ? 7 : 30 });
              setSaved(false);
            }}
            data={[
              { value: "7", label: "7 дней" },
              { value: "30", label: "30 дней" },
            ]}
          />
        </div>
      </section>

      <div className={classes.row}>
        <Button disabled={!valid} onClick={() => void save()} loading={check.state === "checking"}>
          Сохранить
        </Button>
        {saved && <span className={classes.check} data-state="ok">Сохранено</span>}
      </div>
    </div>
  );
}

mount(<Options />);
