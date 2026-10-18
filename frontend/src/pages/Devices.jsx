import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmt, bytes } from "../api.js";
import { Async, Badge, Card, Field, Flash, Modal, can, useAction, useAuth, useLoad } from "../ui.jsx";

const EMPTY = { name: "", ip_address: "", platform: "cisco_ios", ssh_port: 22, location: "", description: "", group_id: "", username: "", password: "", enable_secret: "" };

function DeviceForm({ groups, onDone, onClose }) {
  const [f, setF] = useState(EMPTY);
  const { flash, busy, run } = useAction();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    const r = await run(() => api.post("/devices", { ...f, ssh_port: Number(f.ssh_port), group_id: f.group_id ? Number(f.group_id) : null }));
    if (r) onDone(r);
  };
  return (
    <Modal title="Add device" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <Field label="Name"><input value={f.name} onChange={set("name")} required /></Field>
        <Field label="Management IP"><input value={f.ip_address} onChange={set("ip_address")} required /></Field>
        <Field label="Platform">
          <select value={f.platform} onChange={set("platform")}><option value="cisco_ios">Cisco IOS</option><option value="cisco_xe">Cisco IOS-XE</option></select>
        </Field>
        <Field label="SSH port"><input type="number" value={f.ssh_port} onChange={set("ssh_port")} min="1" max="65535" /></Field>
        <Field label="Location"><input value={f.location} onChange={set("location")} /></Field>
        <Field label="Group">
          <select value={f.group_id} onChange={set("group_id")}><option value="">— none —</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select>
        </Field>
        <Field label="SSH username"><input value={f.username} onChange={set("username")} autoComplete="off" required /></Field>
        <Field label="SSH password"><input type="password" value={f.password} onChange={set("password")} autoComplete="new-password" required /></Field>
        <Field label="Enable secret (optional)"><input type="password" value={f.enable_secret} onChange={set("enable_secret")} autoComplete="new-password" /></Field>
        <Flash flash={flash} />
        <p className="muted small">Credentials are encrypted at rest and never shown again. Use a least-privilege account.</p>
        <button className="btn primary" disabled={busy}>Add device</button>
      </form>
    </Modal>
  );
}

export function DeviceList() {
  const { user } = useAuth();
  const devices = useLoad(() => api.get("/devices"));
  const groups = useLoad(() => api.get("/groups"));
  const [adding, setAdding] = useState(false);
  const [newGroup, setNewGroup] = useState("");
  const { flash, run } = useAction();
  const addGroup = async () => {
    if (!newGroup.trim()) return;
    if (await run(() => api.post("/groups", { name: newGroup.trim() }))) { setNewGroup(""); groups.reload(); }
  };
  const gname = (id) => groups.data?.find((g) => g.id === id)?.name || "—";
  return (
    <>
      <div className="row between">
        <h1>Devices</h1>
        {can(user, "admin") && <button className="btn primary" onClick={() => setAdding(true)}>+ Add device</button>}
      </div>
      <Async state={devices} empty="No devices yet. Add your first Cisco device.">
        {(rows) => (
          <table>
            <thead><tr><th>Name</th><th>IP</th><th>Platform</th><th>Group</th><th>Location</th><th>Enabled</th><th>Last test</th></tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td><Link to={`/devices/${d.id}`}>{d.name}</Link></td>
                  <td>{d.ip_address}:{d.ssh_port}</td><td>{d.platform}</td><td>{gname(d.group_id)}</td><td>{d.location || "—"}</td>
                  <td>{d.is_enabled ? "Yes" : "No"}</td>
                  <td>{d.last_test_ok === null ? <span className="muted">never</span> : <Badge v={d.last_test_ok ? "SUCCESS" : "FAILED"} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      {can(user, "admin") && (
        <Card title="Device groups">
          <div className="row wrap">
            {groups.data?.map((g) => <span key={g.id} className="chip">{g.name}</span>)}
            <input placeholder="New group (e.g. Core Network)" value={newGroup} onChange={(e) => setNewGroup(e.target.value)} />
            <button className="btn" onClick={addGroup}>Add group</button>
          </div>
          <Flash flash={flash} />
        </Card>
      )}
      {adding && <DeviceForm groups={groups.data || []} onClose={() => setAdding(false)} onDone={() => { setAdding(false); devices.reload(); }} />}
    </>
  );
}

export function DeviceDetail() {
  const { deviceId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const dev = useLoad(() => api.get(`/devices/${deviceId}`), [deviceId]);
  const backups = useLoad(() => api.get(`/devices/${deviceId}/backups`), [deviceId]);
  const jobs = useLoad(() => api.get(`/devices/${deviceId}/jobs`), [deviceId]);
  const snaps = useLoad(() => api.get(`/devices/${deviceId}/snapshots`), [deviceId]);
  const { flash, busy, run } = useAction();
  const [test, setTest] = useState(null);
  const refresh = () => { dev.reload(); backups.reload(); jobs.reload(); };

  const doTest = async () => { const r = await run(() => api.post(`/devices/${deviceId}/test-connection`)); if (r) { setTest(r); dev.reload(); } };
  const doBackup = async (types) => { if (await run(() => api.post(`/devices/${deviceId}/backup`, { config_types: types }), "Backup queued")) setTimeout(refresh, 1500); };
  const toggle = async () => { if (await run(() => api.put(`/devices/${deviceId}`, { is_enabled: !dev.data.is_enabled }))) dev.reload(); };
  const remove = async () => {
    if (!window.confirm("Delete this device? (Only possible when it has no stored backups.)")) return;
    if ((await run(() => api.del(`/devices/${deviceId}`))) !== undefined) navigate("/devices");
  };
  const snapshot = async () => { if (await run(() => api.post(`/devices/${deviceId}/snapshot`), "Snapshot stored")) snaps.reload(); };
  const mockChange = async () => { await run(() => api.post(`/devices/${deviceId}/mock/change`), "Simulated a config change on the mock device"); };

  return (
    <Async state={dev}>
      {(d) => (
        <>
          <div className="row between wrap">
            <h1>{d.name} {!d.is_enabled && <span className="badge muted">disabled</span>}</h1>
            <div className="row wrap">
              {can(user, "operator") && <>
                <button className="btn" disabled={busy} onClick={doTest}>Test connection</button>
                <button className="btn primary" disabled={busy || !d.is_enabled} onClick={() => doBackup(["running"])}>Backup running</button>
                <button className="btn" disabled={busy || !d.is_enabled} onClick={() => doBackup(["startup"])}>Backup startup</button>
                <button className="btn" disabled={busy} onClick={snapshot}>State snapshot</button>
              </>}
              {can(user, "admin") && <>
                <button className="btn" onClick={toggle}>{d.is_enabled ? "Disable" : "Enable"}</button>
                <button className="btn danger" onClick={remove}>Delete</button>
                <button className="btn ghost" title="Only works with DRIVER_MODE=mock" onClick={mockChange}>Simulate change (mock)</button>
              </>}
            </div>
          </div>
          <Flash flash={flash} />
          <Card title="Details">
            <dl className="kv">
              <dt>Management IP</dt><dd>{d.ip_address}:{d.ssh_port}</dd>
              <dt>Platform</dt><dd>{d.vendor} / {d.platform}</dd>
              <dt>Location</dt><dd>{d.location || "—"}</dd>
              <dt>Last connection test</dt>
              <dd>{d.last_test_at ? <><Badge v={d.last_test_ok ? "SUCCESS" : "FAILED"} /> {fmt(d.last_test_at)}</> : "never"}</dd>
            </dl>
            {(test || d.last_test_result) && (() => {
              const t = test || d.last_test_result;
              return (
                <ul className="checks">
                  <li className={t.reachable ? "ok" : "bad"}>TCP / SSH port reachable</li>
                  <li className={t.ssh_auth ? "ok" : "bad"}>SSH authentication</li>
                  <li className={t.privileged ? "ok" : "bad"}>Privileged access</li>
                  <li>Detected platform: {t.platform || "—"}{t.platform_matches === false && <span className="error"> (does not match configured platform!)</span>}</li>
                  {t.error && <li className="error">{t.error}</li>}
                </ul>
              );
            })()}
          </Card>
          <Card title="Configuration history">
            <Async state={backups} empty="No backups yet.">
              {(rows) => (
                <table>
                  <thead><tr><th>Ver</th><th>Type</th><th>Created</th><th>By</th><th>Change</th><th>Size</th><th>SHA-256</th><th /></tr></thead>
                  <tbody>
                    {rows.map((c) => (
                      <tr key={c.id}>
                        <td>v{c.version_number}</td><td>{c.config_type}{c.source === "pre_restore" && <span className="badge muted">pre-restore</span>}{c.is_protected && " 🔒"}</td>
                        <td>{fmt(c.created_at)}</td><td>{c.created_by}</td><td><Badge v={c.change_status} /></td><td>{bytes(c.size_bytes)}</td>
                        <td className="mono small">{c.checksum_sha256.slice(0, 12)}…</td>
                        <td><Link to={`/backups/${c.id}`}>Open</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Async>
          </Card>
          <Card title="Recent jobs">
            <Async state={jobs} empty="No jobs yet.">
              {(rows) => (
                <table>
                  <thead><tr><th>#</th><th>Type</th><th>Config</th><th>Status</th><th>Change</th><th>Finished</th><th>Error</th></tr></thead>
                  <tbody>
                    {rows.slice(0, 10).map((j) => (
                      <tr key={j.id}><td>{j.id}</td><td>{j.job_type}</td><td>{j.config_type}</td><td><Badge v={j.status} /></td>
                        <td><Badge v={j.change_status} /></td><td>{fmt(j.completed_at)}</td><td className="small">{j.error_code}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Async>
          </Card>
          <Card title="Operational state snapshots (separate from config backups)">
            <Async state={snaps} empty="No snapshots.">
              {(rows) => (
                <details>
                  <summary>Latest: {fmt(rows[0].created_at)} by {rows[0].created_by}</summary>
                  {Object.entries(rows[0].data).map(([k, v]) => (<div key={k}><h3>{k}</h3><pre className="code">{v}</pre></div>))}
                </details>
              )}
            </Async>
          </Card>
        </>
      )}
    </Async>
  );
}
