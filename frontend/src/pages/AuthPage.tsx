import { useState, type FormEvent } from "react";

import { ApiError, login, register, type User } from "../api";

export function AuthPage({ onAuth }: { onAuth: (user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAuth(mode === "login" ? await login(email, password) : await register(email, name, password));
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center">
      <form className="card auth" onSubmit={submit}>
        <h2>{mode === "login" ? "Вход" : "Регистрация"}</h2>
        <input placeholder="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        {mode === "register" && (
          <input placeholder="имя" value={name} onChange={(e) => setName(e.target.value)} required />
        )}
        <input
          placeholder="пароль (от 8 символов)"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>{mode === "login" ? "Войти" : "Создать аккаунт"}</button>
        <button type="button" className="ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Нет аккаунта? Регистрация" : "Уже есть аккаунт? Войти"}
        </button>
      </form>
    </div>
  );
}
