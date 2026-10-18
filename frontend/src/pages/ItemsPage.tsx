import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, items, type Item } from "../api";
import type { WsMessage } from "../api/ws";

// Образец экрана: список + создание + смена статуса + удаление.
export function ItemsPage({ lastEvent }: { lastEvent?: WsMessage }) {
  const [list, setList] = useState<Item[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handle = (err: unknown) => setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));

  const load = useCallback(async () => {
    try {
      const page = await items.list();
      setList(page.items);
      setCursor(page.next_cursor);
    } catch (err) {
      handle(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // item.created прилетает по WebSocket (в т.ч. из другой вкладки)
  useEffect(() => {
    if (lastEvent?.type === "item.created") void load();
  }, [lastEvent, load]);

  const loadMore = async () => {
    if (!cursor) return;
    const page = await items.list(cursor).catch((err) => (handle(err), null));
    if (!page) return;
    setList((prev) => [...prev, ...page.items]);
    setCursor(page.next_cursor);
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await items.create(title);
      setTitle("");
    } catch (err) {
      handle(err);
    }
  };

  const toggle = async (item: Item) => {
    try {
      const updated = await items.update(item.id, { status: item.status === "open" ? "done" : "open" });
      setList((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch (err) {
      handle(err); // done → open вернёт 409 ITEM_IS_DONE — так и задумано
    }
  };

  const remove = async (item: Item) => {
    try {
      await items.remove(item.id);
      setList((prev) => prev.filter((x) => x.id !== item.id));
    } catch (err) {
      handle(err);
    }
  };

  return (
    <section className="card">
      <h3>Items</h3>
      <form className="row" onSubmit={create}>
        <input placeholder="Новый item" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button>Добавить</button>
      </form>
      {error && <p className="error">{error}</p>}
      <ul className="list">
        {list.map((item) => (
          <li key={item.id} className={item.status}>
            <label>
              <input type="checkbox" checked={item.status === "done"} onChange={() => toggle(item)} />
              {item.title}
            </label>
            <button className="ghost" onClick={() => remove(item)}>
              ✕
            </button>
          </li>
        ))}
      </ul>
      {cursor && (
        <button className="ghost" onClick={loadMore}>
          Ещё
        </button>
      )}
    </section>
  );
}
