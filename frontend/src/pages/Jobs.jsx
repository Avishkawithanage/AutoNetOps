import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt } from "../api.js";
import { Async, Badge, Card, Flash, can, useAction, useAuth, useLoad } from "../ui.jsx";

function useAutoRefresh(reload, active) {
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(reload, 4000);
    return () => clearInterval(t);
  }, [reload, active]);
}

export function Jobs() {
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const devices = useLoad(() => api.get("/devices"));
  const jobs = useLoad(() => api.get(`/jobs?limit=200${status ? `&status=${status}` : ""}${type ? `&job_type=${type}` : ""}`), [status, type]);
  const { flash, run } = useAction();
  useAutoRefresh(jobs.reload, (jobs.data || []).some((j) => ["PENDING", "RUNNING"].includes(j.status)));
  const dname = (id) => devices.data?.find((d) => d.id === id)?.name || `#${id}`;
  return (
    <>
      <h1>Job history</h1>
      <div className="row wrap">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {["PENDING", "RUNNING", "SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option>
          {["manual", "scheduled", "pre_restore", "safety"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <button className="btn" onClick={jobs.reload}>Refresh</button>
      </div>
      <Flash flash={flash} />
      <Async state={jobs} empty="No jobs match.">
        {(rows) => (
          <table>
            <thead><tr><th>#</th><th>Device</th><th>Type</th><th>Config</th><th>Status</th><th>Change</th><th>Requested by</th><th>Started</th><th>Finished</th><th>Retries</th><th>Error</th><th /></tr></thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.id}>
                  <td>{j.id}</td><td><Link to={`/devices/${j.device_id}`}>{dname(j.device_id)}</Link></td><td>{j.job_type}</td><td>{j.config_type}</td>
                  <td><Badge v={j.status} /></td><td><Badge v={j.change_status} /></td><td>{j.requested_by}</td>
                  <td>{fmt(j.started_at)}</td><td>{fmt(j.completed_at)}</td><td>{j.retry_count}</td>
                  <td className="small" title={j.error_message || ""}>{j.error_code}</td>
                  <td>
                    {j.configuration_id && <Link to={`/backups/${j.configuration_id}`}>View</Link>}
                    {j.status === "PENDING" && can(user, "operator") && <button className="btn ghost" onClick={async () => { await run(() => api.post(`/jobs/${j.id}/cancel`)); jobs.reload(); }}>Cancel</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
    </>
  );
}

export function Restores() {
  const { user } = useAuth();
  const restores = useLoad(() => api.get("/restores"));
  const devices = useLoad(() => api.get("/devices"));
  const { flash, run } = useAction();
  useAutoRefresh(restores.reload, (restores.data || []).some((r) => ["PENDING", "RUNNING", "PENDING_APPROVAL"].includes(r.status)));
  const dname = (id) => devices.data?.find((d) => d.id === id)?.name || `#${id}`;
  const act = async (id, verb, extra = "") => {
    await run(() => api.post(`/restores/${id}/${verb}${extra}`));
    restores.reload();
  };
  return (
    <>
      <h1>Restores</h1>
      <Flash flash={flash} />
      <Async state={restores} empty="No restore operations yet. Open a backup version to start one.">
        {(rows) => rows.map((r) => (
          <Card key={r.id} title={`Restore #${r.id} — ${dname(r.device_id)}${r.is_recovery ? " (recovery)" : ""}`} actions={<Badge v={r.status} />}>
            <dl className="kv">
              <dt>Target</dt><dd><Link to={`/backups/${r.target_configuration_id}`}>configuration #{r.target_configuration_id}</Link> · mode {r.mode}{r.save_startup && " · save to startup"}</dd>
              <dt>Pre-restore backup</dt><dd>{r.pre_restore_configuration_id ? <Link to={`/backups/${r.pre_restore_configuration_id}`}>configuration #{r.pre_restore_configuration_id}</Link> : "—"}</dd>
              <dt>Requested by</dt><dd>{r.performed_by} at {fmt(r.created_at)}{r.approved_by && <> · approved by {r.approved_by}</>}</dd>
              <dt>Finished</dt><dd>{fmt(r.completed_at)}</dd>
              {r.error_message && <><dt>Message</dt><dd className="error">{r.error_message}</dd></>}
              {r.recovery_status && <><dt>Recovery</dt><dd>{r.recovery_status}</dd></>}
            </dl>
            {r.validation_warnings?.length > 0 && <p className="warn small">Acknowledged warnings: {r.validation_warnings.join(" | ")}</p>}
            {r.verification_result && (
              <details>
                <summary>Verification: {r.verification_result.missing_count ?? 0} missing, {r.verification_result.extra_count ?? 0} extra lines</summary>
                {r.verification_result.cli_errors?.length > 0 && <pre className="code">{r.verification_result.cli_errors.join("\n")}</pre>}
                {r.verification_result.missing?.length > 0 && <><h3>Missing on device</h3><pre className="code">{r.verification_result.missing.join("\n")}</pre></>}
                {r.verification_result.extra?.length > 0 && <><h3>Extra on device</h3><pre className="code">{r.verification_result.extra.join("\n")}</pre></>}
              </details>
            )}
            {can(user, "admin") && (
              <div className="row">
                {r.status === "PENDING_APPROVAL" && <>
                  <button className="btn primary" onClick={() => act(r.id, "approve")}>Approve &amp; run</button>
                  <button className="btn" onClick={() => act(r.id, "reject")}>Reject</button>
                </>}
                {["FAILED", "NEEDS_REVIEW", "UNCERTAIN"].includes(r.status) && r.pre_restore_configuration_id && !r.is_recovery && (
                  <button className="btn danger" onClick={() => window.confirm("Restore the pre-restore backup to roll back?") && act(r.id, "recover", "?acknowledge_risks=true")}>Roll back to pre-restore backup</button>
                )}
              </div>
            )}
          </Card>
        ))}
      </Async>
    </>
  );
}
