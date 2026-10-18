import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fmt } from "../api.js";
import { Async, Card, Field, Flash, useAction, useLoad } from "../ui.jsx";

export function DiffView({ diff }) {
  const [onlyChanges, setOnlyChanges] = useState(true);
  const lines = onlyChanges ? diff.lines.filter((l) => l.type !== "equal") : diff.lines;
  return (
    <>
      <p>
        <span className="ok">+{diff.added} added</span> · <span className="bad">−{diff.removed} removed</span> · {diff.total_changes} total
        {Object.keys(diff.categories || {}).length > 0 && <> · {Object.entries(diff.categories).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}</>}
      </p>
      <label className="small"><input type="checkbox" checked={onlyChanges} onChange={(e) => setOnlyChanges(e.target.checked)} /> Show only changed lines</label>
      {diff.identical ? <p className="muted">The versions are identical{diff.normalized ? " (after ignoring volatile lines)" : ""}.</p> : (
        <pre className="code diff">
          {lines.map((l, i) => (
            <div key={i} className={l.type}>
              <span className="ln">{l.a_no ?? ""}</span><span className="ln">{l.b_no ?? ""}</span>
              <span className="sign">{l.type === "added" ? "+" : l.type === "removed" ? "-" : " "}</span>{l.text}
            </div>
          ))}
        </pre>
      )}
    </>
  );
}

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const devices = useLoad(() => api.get("/devices"));
  const [deviceId, setDeviceId] = useState(params.get("device") || "");
  const [type, setType] = useState("running");
  const versions = useLoad(() => (deviceId ? api.get(`/devices/${deviceId}/backups?config_type=${type}`) : Promise.resolve([])), [deviceId, type]);
  const [src, setSrc] = useState(params.get("source") || "");
  const [tgt, setTgt] = useState(params.get("target") || "");
  const [normalized, setNormalized] = useState(true);
  const [diff, setDiff] = useState(null);
  const { flash, busy, run } = useAction();

  const go = async () => {
    setParams({ device: deviceId, source: src, target: tgt });
    const r = await run(() => api.get(`/compare?source_id=${src}&target_id=${tgt}&normalized=${normalized}`));
    if (r) setDiff(r);
  };
  useEffect(() => { if (params.get("source") && params.get("target")) go(); /* eslint-disable-next-line */ }, []);

  const opts = (versions.data || []).map((v) => <option key={v.id} value={v.id}>v{v.version_number} — {fmt(v.created_at)}</option>);
  return (
    <>
      <h1>Compare versions</h1>
      <Card>
        <div className="row wrap end">
          <Field label="Device">
            <select value={deviceId} onChange={(e) => { setDeviceId(e.target.value); setSrc(""); setTgt(""); setDiff(null); }}>
              <option value="">Select…</option>
              {devices.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          <Field label="Config"><select value={type} onChange={(e) => setType(e.target.value)}><option>running</option><option>startup</option></select></Field>
          <Field label="Source (older)"><select value={src} onChange={(e) => setSrc(e.target.value)}><option value="">Select…</option>{opts}</select></Field>
          <Field label="Target (newer)"><select value={tgt} onChange={(e) => setTgt(e.target.value)}><option value="">Select…</option>{opts}</select></Field>
          <label className="small"><input type="checkbox" checked={normalized} onChange={(e) => setNormalized(e.target.checked)} /> Ignore volatile lines</label>
          <button className="btn primary" disabled={!src || !tgt || busy} onClick={go}>Compare</button>
        </div>
        <Flash flash={flash} />
      </Card>
      {diff && (
        <Card title={`v${diff.source.version_number} → v${diff.target.version_number}`}
          actions={<button className="btn" onClick={() => navigator.clipboard?.writeText(diff.unified)}>Copy unified diff</button>}>
          <p className="muted small">{fmt(diff.source.created_at)} → {fmt(diff.target.created_at)}</p>
          <DiffView diff={diff} />
        </Card>
      )}
    </>
  );
}
