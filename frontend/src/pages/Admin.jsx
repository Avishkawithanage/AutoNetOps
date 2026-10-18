import { useState } from "react";
import { api, bytes, fmt } from "../api.js";
import { Async, Badge, Card, Field, Flash, can, useAction, useAuth, useLoad } from "../ui.jsx";

export function Audit() {
  const [action, setAction] = useState("");
  const logs = useLoad(() => api.get(`/audit-logs?limit=300${action ? `&action=${encodeURIComponent(action)}` : ""}`), [action]);
  return (
    <>
      <h1>Audit logs</h1>
      <div className="row"><input placeholder="Filter by action (e.g. restore, login)" value={action} onChange={(e) => setAction(e.target.value)} /><button className="btn" onClick={logs.reload}>Refresh</button></div>
      <Async state={logs} empty="No audit entries.">
        {(rows) => (
          <table>
            <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Device</th><th>Result</th><th>Details</th><th>Source IP</th></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}><td>{fmt(a.timestamp)}</td><td>{a.username}</td><td>{a.action}</td><td>{a.device_id ?? "—"}</td>
                  <td><Badge v={a.result} /></td><td className="small">{a.details}</td><td className="small">{a.source_ip}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
    </>
  );
}

export function Reports() {
  const daily = useLoad(() => api.get("/reports/daily-backups?days=14"));
  const storage = useLoad(() => api.get("/reports/storage"));
  const notes = useLoad(() => api.get("/notifications?limit=100"));
  const { flash, run } = useAction();
  return (
    <>
      <h1>Reports</h1>
      <Flash flash={flash} />
      <Card title="Daily backup summary" actions={<button className="btn" onClick={() => run(() => api.download("/reports/daily-backups?format=csv", "daily-backups.csv"))}>Export CSV</button>}>
        <Async state={daily} empty="No jobs in the last 14 days.">
          {(rows) => (
            <table>
              <thead><tr><th>Date</th><th>Jobs</th><th>Successful</th><th>Failed</th><th>Unchanged</th><th>Changed</th><th>Devices not reached</th></tr></thead>
              <tbody>{rows.map((r) => <tr key={r.date}><td>{r.date}</td><td>{r.jobs}</td><td>{r.success}</td><td>{r.failed}</td><td>{r.unchanged}</td><td>{r.changed}</td><td>{r.devices_not_reached}</td></tr>)}</tbody>
            </table>
          )}
        </Async>
      </Card>
      <Card title="Storage">
        <Async state={storage}>
          {(s) => (
            <>
              <div className="meter" role="progressbar" aria-valuenow={s.percent} aria-valuemin="0" aria-valuemax="100"><div className={s.level} style={{ width: `${Math.min(s.percent, 100)}%` }} /></div>
              <p>{bytes(s.used_bytes)} of {bytes(s.capacity_bytes)} ({s.percent}%) <Badge v={s.level} /></p>
              <table><thead><tr><th>Device</th><th>Versions</th><th>Size</th></tr></thead>
                <tbody>{s.per_device.map((d) => <tr key={d.device}><td>{d.device}</td><td>{d.versions}</td><td>{bytes(d.bytes)}</td></tr>)}</tbody></table>
            </>
          )}
        </Async>
      </Card>
      <Card title="Notifications" actions={<button className="btn" onClick={async () => { await run(() => api.post("/notifications/read-all")); notes.reload(); }}>Mark all read</button>}>
        <Async state={notes} empty="No notifications.">
          {(rows) => (
            <table><tbody>
              {rows.map((n) => (
                <tr key={n.id} className={n.is_read ? "dim" : ""}><td><Badge v={n.severity} /></td><td>{n.title}<div className="muted small">{n.message}</div></td>
                  <td className="small">{fmt(n.created_at)}</td><td className="small muted">{n.delivery}</td></tr>
              ))}
            </tbody></table>
          )}
        </Async>
      </Card>
    </>
  );
}

export function Users() {
  const users = useLoad(() => api.get("/users"));
  const { user: me } = useAuth();
  const [f, setF] = useState({ username: "", password: "", role: "viewer" });
  const { flash, busy, run } = useAction();
  const create = async (e) => {
    e.preventDefault();
    if (await run(() => api.post("/users", f), "User created")) { setF({ username: "", password: "", role: "viewer" }); users.reload(); }
  };
  const update = async (u, patch) => { await run(() => api.put(`/users/${u.id}`, patch)); users.reload(); };
  return (
    <>
      <h1>Users</h1>
      <Flash flash={flash} />
      <Async state={users}>
        {(rows) => (
          <table>
            <thead><tr><th>Username</th><th>Role</th><th>Active</th><th>Last login</th><th /></tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}><td>{u.username}</td>
                  <td><select value={u.role} disabled={u.id === me.id} onChange={(e) => update(u, { role: e.target.value })}>{["viewer", "operator", "admin"].map((r) => <option key={r}>{r}</option>)}</select></td>
                  <td>{u.is_active ? "Yes" : "No"}</td><td>{fmt(u.last_login_at)}</td>
                  <td>{u.id !== me.id && <button className="btn ghost" onClick={() => update(u, { is_active: !u.is_active })}>{u.is_active ? "Disable" : "Enable"}</button>}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      <Card title="New user">
        <form className="form grid" onSubmit={create}>
          <Field label="Username"><input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} required minLength={3} /></Field>
          <Field label="Password (min 10 chars)"><input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required minLength={10} autoComplete="new-password" /></Field>
          <Field label="Role"><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{["viewer", "operator", "admin"].map((r) => <option key={r}>{r}</option>)}</select></Field>
          <div><button className="btn primary" disabled={busy}>Create user</button></div>
        </form>
        <p className="muted small">viewer: read-only · operator: run backups, compare, download · admin: everything incl. restore, devices, schedules, users</p>
      </Card>
    </>
  );
}

export function Settings() {
  const { user } = useAuth();
  const admin = can(user, "admin");
  const policy = useLoad(() => api.get("/settings/retention"));
  const [p, setP] = useState(null);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [dry, setDry] = useState(null);
  const a1 = useAction();
  const a2 = useAction();
  const cur = p || policy.data;
  return (
    <>
      <h1>Settings</h1>
      <Card title="Change my password">
        <form className="form" onSubmit={async (e) => { e.preventDefault(); if (await a2.run(() => api.post("/auth/change-password", pw), "Password changed")) setPw({ current_password: "", new_password: "" }); }}>
          <Field label="Current password"><input type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} autoComplete="current-password" required /></Field>
          <Field label="New password (min 10 chars)"><input type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} autoComplete="new-password" minLength={10} required /></Field>
          <Flash flash={a2.flash} />
          <button className="btn primary" disabled={a2.busy}>Change password</button>
        </form>
      </Card>
      <Card title="Retention policy">
        <Async state={policy}>
          {() => (
            <div className="form">
              <Field label="Max versions per device &amp; config type"><input type="number" min="1" disabled={!admin} value={cur.max_versions_per_device} onChange={(e) => setP({ ...cur, max_versions_per_device: Number(e.target.value) })} /></Field>
              <Field label="Max age in days (0 = unlimited)"><input type="number" min="0" disabled={!admin} value={cur.max_age_days} onChange={(e) => setP({ ...cur, max_age_days: Number(e.target.value) })} /></Field>
              <p className="muted small">The latest version, protected versions and versions referenced by a restore are never deleted.</p>
              <Flash flash={a1.flash} />
              {admin && (
                <div className="row">
                  <button className="btn primary" onClick={() => a1.run(() => api.put("/settings/retention", p || policy.data), "Saved")}>Save policy</button>
                  <button className="btn" onClick={async () => setDry(await a1.run(() => api.post("/settings/retention/run?dry_run=true")))}>Preview cleanup</button>
                  {dry && dry.deleted_configuration_ids.length > 0 && (
                    <button className="btn danger" onClick={async () => { if (window.confirm(`Delete ${dry.deleted_configuration_ids.length} old versions?`)) { await a1.run(() => api.post("/settings/retention/run?dry_run=false"), "Cleanup done"); setDry(null); } }}>Run cleanup ({dry.deleted_configuration_ids.length})</button>
                  )}
                  {dry && dry.deleted_configuration_ids.length === 0 && <span className="muted">Nothing to clean up.</span>}
                </div>
              )}
            </div>
          )}
        </Async>
      </Card>
    </>
  );
}
