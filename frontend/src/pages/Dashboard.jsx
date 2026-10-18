import { Link } from "react-router-dom";
import { api, bytes, fmt } from "../api.js";
import { Async, Badge, Card, useLoad } from "../ui.jsx";

const Stat = ({ label, value, tone }) => (
  <div className={`stat ${tone || ""}`}>
    <div className="stat-v">{value}</div>
    <div className="stat-l">{label}</div>
  </div>
);

export default function Dashboard() {
  const dash = useLoad(() => api.get("/reports/dashboard"));
  const notes = useLoad(() => api.get("/notifications?limit=8"));
  return (
    <>
      <h1>Dashboard</h1>
      <Async state={dash}>
        {(d) => (
          <>
            <div className="stats">
              <Stat label="Enabled devices" value={d.enabled_devices} />
              <Stat label="Reachable" value={d.reachable_devices} tone="ok" />
              <Stat label="Failed connection tests" value={d.failed_connection_tests} tone={d.failed_connection_tests ? "bad" : ""} />
              <Stat label="Successful backups today" value={d.backups_success_today} tone="ok" />
              <Stat label="Failed backups today" value={d.backups_failed_today} tone={d.backups_failed_today ? "bad" : ""} />
              <Stat label="Unchanged today" value={d.unchanged_today} />
              <Stat label="Changes detected today" value={d.changes_today} tone={d.changes_today ? "warn" : ""} />
              <Stat label="Jobs queued / running" value={d.pending_jobs} />
              <Stat label="Storage used" value={`${bytes(d.storage.used_bytes)} (${d.storage.percent}%)`} tone={d.storage.level === "ok" ? "" : d.storage.level === "warning" ? "warn" : "bad"} />
              <Stat label="Restores awaiting approval" value={d.restores_awaiting_approval} tone={d.restores_awaiting_approval ? "warn" : ""} />
            </div>
            <p className="muted">Latest successful backup: {fmt(d.latest_successful_backup)}</p>
          </>
        )}
      </Async>
      <Card title="Recent notifications" actions={<Link to="/reports">All reports →</Link>}>
        <Async state={notes} empty="No notifications yet.">
          {(rows) => (
            <table>
              <tbody>
                {rows.map((n) => (
                  <tr key={n.id}>
                    <td><Badge v={n.severity} /></td>
                    <td>{n.title}<div className="muted small">{n.message}</div></td>
                    <td className="muted small">{fmt(n.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>
    </>
  );
}
