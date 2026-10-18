import { useState } from "react";
import { api, fmt } from "../api.js";
import { Async, Badge, Card, Field, Flash, can, useAction, useAuth, useLoad } from "../ui.jsx";

const EMPTY = { name: "", frequency: "daily", time_of_day: "02:00", interval_hours: 6, days_of_week: "mon", day_of_month: 1, cron_expression: "0 2 * * *", timezone: "UTC", config_types: "running,startup", target_group_id: "", enabled: true };

function describe(s) {
  const t = s.time_of_day;
  switch (s.frequency) {
    case "hourly": return `Every hour at :${t.split(":")[1]}`;
    case "every_n_hours": return `Every ${s.interval_hours} hours`;
    case "daily": return `Daily at ${t}`;
    case "weekly": return `Weekly on ${s.days_of_week} at ${t}`;
    case "monthly": return `Monthly on day ${s.day_of_month} at ${t}`;
    default: return `Cron: ${s.cron_expression}`;
  }
}

export default function Schedules() {
  const { user } = useAuth();
  const admin = can(user, "admin");
  const list = useLoad(() => api.get("/schedules"));
  const groups = useLoad(() => api.get("/groups"));
  const [f, setF] = useState(EMPTY);
  const { flash, busy, run } = useAction();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const create = async (e) => {
    e.preventDefault();
    const body = { ...f, interval_hours: Number(f.interval_hours), day_of_month: Number(f.day_of_month), target_group_id: f.target_group_id ? Number(f.target_group_id) : null };
    if (await run(() => api.post("/schedules", body), "Schedule created")) { setF(EMPTY); list.reload(); }
  };
  const toggle = async (s) => { await run(() => api.put(`/schedules/${s.id}`, { ...s, enabled: !s.enabled })); list.reload(); };
  const remove = async (s) => { if (window.confirm(`Delete schedule "${s.name}"?`)) { await run(() => api.del(`/schedules/${s.id}`)); list.reload(); } };
  const runNow = async (s) => { const r = await run(() => api.post(`/schedules/${s.id}/run`)); if (r) { setF((x) => x); alert(`${r.jobs_created} job(s) queued`); list.reload(); } };

  return (
    <>
      <h1>Schedules</h1>
      <Flash flash={flash} />
      <Async state={list} empty="No schedules yet.">
        {(rows) => (
          <table>
            <thead><tr><th>Name</th><th>When</th><th>Timezone</th><th>Configs</th><th>Target</th><th>Enabled</th><th>Last run</th><th /></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td>{s.name}</td><td>{describe(s)}</td><td>{s.timezone}</td><td>{s.config_types}</td>
                  <td>{groups.data?.find((g) => g.id === s.target_group_id)?.name || "All enabled devices"}</td>
                  <td><Badge v={s.enabled ? "SUCCESS" : "CANCELLED"} /></td><td>{fmt(s.last_run_at)}</td>
                  <td>{admin && <div className="row">
                    <button className="btn ghost" onClick={() => runNow(s)}>Run now</button>
                    <button className="btn ghost" onClick={() => toggle(s)}>{s.enabled ? "Disable" : "Enable"}</button>
                    <button className="btn ghost" onClick={() => remove(s)}>Delete</button></div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      {admin && (
        <Card title="New schedule">
          <form className="form grid" onSubmit={create}>
            <Field label="Name"><input value={f.name} onChange={set("name")} required /></Field>
            <Field label="Frequency">
              <select value={f.frequency} onChange={set("frequency")}>
                {["hourly", "every_n_hours", "daily", "weekly", "monthly", "cron"].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
            {f.frequency !== "cron" && f.frequency !== "every_n_hours" && <Field label="Time (HH:MM)"><input value={f.time_of_day} onChange={set("time_of_day")} pattern="\d{2}:\d{2}" /></Field>}
            {f.frequency === "every_n_hours" && <Field label="Every N hours"><input type="number" min="1" max="168" value={f.interval_hours} onChange={set("interval_hours")} /></Field>}
            {f.frequency === "weekly" && <Field label="Days (mon,thu)"><input value={f.days_of_week} onChange={set("days_of_week")} /></Field>}
            {f.frequency === "monthly" && <Field label="Day of month (1-28)"><input type="number" min="1" max="28" value={f.day_of_month} onChange={set("day_of_month")} /></Field>}
            {f.frequency === "cron" && <Field label="Cron (5 fields)"><input value={f.cron_expression} onChange={set("cron_expression")} /></Field>}
            <Field label="Timezone (IANA)"><input value={f.timezone} onChange={set("timezone")} placeholder="Asia/Colombo" /></Field>
            <Field label="Config types"><select value={f.config_types} onChange={set("config_types")}><option>running,startup</option><option>running</option><option>startup</option></select></Field>
            <Field label="Target group">
              <select value={f.target_group_id} onChange={set("target_group_id")}><option value="">All enabled devices</option>{groups.data?.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select>
            </Field>
            <div><button className="btn primary" disabled={busy}>Create schedule</button></div>
          </form>
        </Card>
      )}
    </>
  );
}
