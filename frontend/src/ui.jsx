import { createContext, useCallback, useContext, useEffect, useState } from "react";

export const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);
const RANK = { viewer: 0, operator: 1, admin: 2 };
export const can = (user, min) => user && RANK[user.role] >= RANK[min];

/** Load data with loading/error state; `reload()` refetches. */
export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    fn().then(
      (data) => setState({ data, error: null, loading: false }),
      (error) => setState({ data: null, error, loading: false })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { ...state, reload };
}

export function Async({ state, children, empty }) {
  if (state.loading && !state.data) return <p className="muted">Loading…</p>;
  if (state.error) return <p className="error">Error: {state.error.message}</p>;
  if (empty && Array.isArray(state.data) && state.data.length === 0) return <p className="muted">{empty}</p>;
  return children(state.data);
}

const COLORS = {
  SUCCESS: "ok", UNCHANGED: "ok", ok: "ok", info: "ok",
  CHANGED: "warn", NEEDS_REVIEW: "warn", PENDING: "warn", PENDING_APPROVAL: "warn", RUNNING: "warn", warning: "warn", NOT_COMPARABLE: "muted",
  FAILED: "bad", TIMEOUT: "bad", UNCERTAIN: "bad", critical: "bad", REJECTED: "bad", CANCELLED: "muted",
};
export const Badge = ({ v }) => (v ? <span className={`badge ${COLORS[v] || "muted"}`}>{v}</span> : <span className="muted">—</span>);

export function Card({ title, actions, children }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <h2>{title}</h2>
          <div className="row">{actions}</div>
        </header>
      )}
      {children}
    </section>
  );
}

export function Modal({ title, onClose, children }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="card-head">
          <h2>{title}</h2>
          <button className="btn ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Flash({ flash }) {
  if (!flash) return null;
  return <p className={flash.type === "error" ? "error" : "okmsg"} role="status">{flash.text}</p>;
}

/** Run an async action and surface errors as a flash message. */
export function useAction() {
  const [flash, setFlash] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn, okText) => {
    setBusy(true);
    setFlash(null);
    try {
      const r = await fn();
      if (okText) setFlash({ type: "ok", text: okText });
      return r;
    } catch (e) {
      setFlash({ type: "error", text: e.message });
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { flash, busy, run, setFlash };
}
