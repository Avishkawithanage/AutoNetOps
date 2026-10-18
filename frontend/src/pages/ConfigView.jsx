import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmt, bytes } from "../api.js";
import { Async, Badge, Card, Flash, Modal, can, useAction, useAuth, useLoad } from "../ui.jsx";

function RestoreDialog({ cfg, device, onClose }) {
  const navigate = useNavigate();
  const preview = useLoad(() => api.get(`/configurations/${cfg.id}/restore-preview`), [cfg.id]);
  const [mode, setMode] = useState("merge");
  const [saveStartup, setSaveStartup] = useState(false);
  const [ack, setAck] = useState(false);
  const [typed, setTyped] = useState("");
  const { flash, busy, run } = useAction();

  const submit = async () => {
    const r = await run(() => api.post(`/configurations/${cfg.id}/restore`, { confirm: true, mode, save_startup: saveStartup, acknowledge_risks: ack }));
    if (r) navigate("/restores");
  };
  return (
    <Modal title={`Restore ${device.name} to v${cfg.version_number}`} onClose={onClose}>
      <p className="warnbox"><b>WARNING:</b> this operation changes a live network device and can disconnect it. Review the diff and make sure you have a recovery plan (console / out-of-band access).</p>
      <Async state={preview}>
        {(p) => (
          <>
            <p>Current version: <b>{p.current_version ? `v${p.current_version}` : "—"}</b> → Target: <b>v{p.target_version}</b>. A protected <b>pre-restore backup</b> is taken automatically and the restore is aborted if it fails.</p>
            {p.validation.errors.map((e) => <p key={e} className="error">✕ {e}</p>)}
            {p.validation.warnings.map((w) => <p key={w} className="warn">⚠ {w}</p>)}
            {(p.validation.notes || []).map((w) => <p key={w} className="muted">ℹ {w}</p>)}
            {p.diff && (
              <p>Changes the device will see: <span className="ok">+{p.diff.added}</span> / <span className="bad">−{p.diff.removed}</span>{" "}
                {Object.entries(p.diff.categories).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}
</p>
            )}
            {p.requires_approval && <p className="muted">This environment requires <b>second-person approval</b>; the restore will wait for another administrator.</p>}
            {!p.validation.errors.length && (
              <div className="form">
                <label className="field"><span>Mode</span>
                  <select value={mode} onChange={(e) => setMode(e.target.value)}>
                    <option value="merge">Merge — apply lines (cannot remove extra lines; result will need review)</option>
                    <option value="replace">Replace — configure replace (needs SCP + validated in lab)</option>
                  </select>
                </label>
                <label className="small"><input type="checkbox" checked={saveStartup} onChange={(e) => setSaveStartup(e.target.checked)} /> Save to startup-config after a verified success</label>
                {p.validation.warnings.length > 0 && (
                  <label className="small"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand and accept the warnings above</label>
                )}
                <label className="field"><span>Type the device name <b>{device.name}</b> to confirm</span>
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
                </label>
                <Flash flash={flash} />
                <div className="row">
                  <button className="btn" onClick={onClose}>Cancel</button>
                  <button className="btn danger" disabled={busy || typed !== device.name || (p.validation.warnings.length > 0 && !ack)} onClick={submit}>Confirm restore</button>
                </div>
              </div>
            )}
            <p className="muted small">{p.note}</p>
          </>
        )}
      </Async>
    </Modal>
  );
}

export default function ConfigView() {
  const { configId } = useParams();
  const { user } = useAuth();
  const cfg = useLoad(() => api.get(`/configurations/${configId}`), [configId]);
  const content = useLoad(() => api.get(`/configurations/${configId}/content`), [configId]);
  const integrity = useLoad(() => api.get(`/configurations/${configId}/integrity`), [configId]);
  const device = useLoad(async () => api.get(`/devices/${(await api.get(`/configurations/${configId}`)).device_id}`), [configId]);
  const [q, setQ] = useState("");
  const [restoring, setRestoring] = useState(false);
  const { flash, run } = useAction();

  const lines = (content.data?.content || "").split("\n");
  const shown = lines.map((t, i) => [i + 1, t]).filter(([, t]) => !q || t.toLowerCase().includes(q.toLowerCase()));
  const canRestore = cfg.data?.config_type === "running" && can(user, "operator");

  return (
    <Async state={cfg}>
      {(c) => (
        <>
          <div className="row between wrap">
            <h1>{device.data?.name} — v{c.version_number} <span className="muted">({c.config_type})</span></h1>
            <div className="row wrap">
              <Link className="btn" to={`/compare?device=${c.device_id}&target=${c.id}`}>Compare…</Link>
              {can(user, "operator") && <button className="btn" onClick={() => run(() => api.download(`/configurations/${c.id}/download`, `${device.data?.name}_v${c.version_number}.cfg`))}>Download</button>}
              {canRestore && <button className="btn danger" onClick={() => setRestoring(true)}>Restore this version…</button>}
            </div>
          </div>
          <Flash flash={flash} />
          <Card>
            <dl className="kv">
              <dt>Created</dt><dd>{fmt(c.created_at)} by {c.created_by}</dd>
              <dt>Change status</dt><dd><Badge v={c.change_status} /> {c.source === "pre_restore" && <span className="badge muted">pre-restore backup</span>} {c.is_protected && "🔒 protected"}</dd>
              <dt>Size</dt><dd>{bytes(c.size_bytes)}</dd>
              <dt>SHA-256</dt><dd className="mono small">{c.checksum_sha256}</dd>
              <dt>Integrity</dt><dd>{integrity.data ? <Badge v={integrity.data.ok ? "SUCCESS" : "FAILED"} /> : "…"}</dd>
            </dl>
          </Card>
          <Card title="Configuration (read-only)" actions={<input placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />}>
            <Async state={content}>
              {() => (
                <pre className="code">
                  {shown.map(([n, t]) => <div key={n}><span className="ln">{n}</span>{t}</div>)}
                </pre>
              )}
            </Async>
          </Card>
          {restoring && device.data && <RestoreDialog cfg={c} device={device.data} onClose={() => setRestoring(false)} />}
        </>
      )}
    </Async>
  );
}
