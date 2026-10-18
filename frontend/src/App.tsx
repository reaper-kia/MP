import { useEffect, useState } from "react";

import { getAccessToken, logout, restoreSession, type User } from "./api";
import { connectWs, type WsMessage } from "./api/ws";
import { AuthPage } from "./pages/AuthPage";
import { ItemsPage } from "./pages/ItemsPage";

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState<WsMessage[]>([]);

  useEffect(() => {
    restoreSession()
      .then(setUser)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    const ws = connectWs(getAccessToken, (msg) => setEvents((prev) => [msg, ...prev].slice(0, 5)));
    return () => ws.close();
  }, [user]);

  if (loading) return <div className="center muted">Загрузка…</div>;
  if (!user) return <AuthPage onAuth={setUser} />;

  return (
    <div className="layout">
      <header className="header">
        <strong>MP</strong>
        <span className="muted">
          {user.name} · {user.role}
        </span>
        <button
          className="ghost"
          onClick={async () => {
            await logout();
            setUser(null);
          }}
        >
          Выйти
        </button>
      </header>
      <main>
        <ItemsPage lastEvent={events[0]} />
        <section className="card">
          <h3>WebSocket события</h3>
          {events.length === 0 && <p className="muted">Пока пусто — создай item</p>}
          {events.map((e, i) => (
            <pre key={i} className="event">
              {e.type} {JSON.stringify(e.payload)}
            </pre>
          ))}
        </section>
      </main>
    </div>
  );
}
