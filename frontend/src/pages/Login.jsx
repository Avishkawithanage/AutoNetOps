import { useState } from "react";
import { api, setToken } from "../api.js";
import { Field, Flash, useAction } from "../ui.jsx";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { flash, busy, run } = useAction();

  const submit = async (e) => {
    e.preventDefault();
    const r = await run(() => api.post("/auth/login", { username, password }));
    if (r) { setToken(r.access_token); onLogin(r.user); }
  };
  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <h1>AutoNetOps</h1>
        <p className="muted">Automated network configuration &amp; backup</p>
        <Field label="Username"><input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" required /></Field>
        <Field label="Password"><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></Field>
        <Flash flash={flash} />
        <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
