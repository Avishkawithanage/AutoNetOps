import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "./api.js";
import { AuthCtx, can } from "./ui.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import { DeviceList, DeviceDetail } from "./pages/Devices.jsx";
import ConfigView from "./pages/ConfigView.jsx";
import Compare from "./pages/Compare.jsx";
import { Restores, Jobs } from "./pages/Jobs.jsx";
import Schedules from "./pages/Schedules.jsx";
import { Audit, Reports, Users, Settings } from "./pages/Admin.jsx";

const NAV = [
  ["/dashboard", "Dashboard"], ["/devices", "Devices"], ["/compare", "Compare"], ["/jobs", "Jobs"],
  ["/restores", "Restores"], ["/schedules", "Schedules"], ["/reports", "Reports"],
  ["/audit-logs", "Audit logs", "operator"], ["/users", "Users", "admin"], ["/settings", "Settings"],
];

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api.get("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);
  useEffect(() => {
    const out = () => { setUser(null); navigate("/login"); };
    window.addEventListener("anops-logout", out);
    return () => window.removeEventListener("anops-logout", out);
  }, [navigate]);

  if (!ready) return <p className="muted pad">Loading…</p>;
  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* token may already be invalid */ }
    setToken(null);
    setUser(null);
    navigate("/login");
  };
  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login onLogin={(u) => { setUser(u); navigate("/dashboard"); }} />} />
      </Routes>
    );
  }
  return (
    <AuthCtx.Provider value={{ user }}>
      <div className="shell">
        <aside className="side">
          <div className="brand">AutoNetOps</div>
          <nav>
            {NAV.filter(([, , min]) => !min || can(user, min)).map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
            ))}
          </nav>
          <div className="who">
            <div>{user.username} <span className="muted">({user.role})</span></div>
            <button className="btn ghost" onClick={logout}>Sign out</button>
          </div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/login" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/devices" element={<DeviceList />} />
            <Route path="/devices/:deviceId" element={<DeviceDetail />} />
            <Route path="/backups/:configId" element={<ConfigView />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/restores" element={<Restores />} />
            <Route path="/schedules" element={<Schedules />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/audit-logs" element={<Audit />} />
            <Route path="/users" element={<Users />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </main>
      </div>
    </AuthCtx.Provider>
  );
}
