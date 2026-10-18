const BASE = "/api/v1";
const KEY = "anops_token";

export const getToken = () => {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
};
export const setToken = (t) => {
  try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch { /* storage blocked */ }
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : detail?.message || (detail?.errors || []).join("; ") || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body, raw = false) {
  const headers = {};
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && path !== "/auth/login") {
    setToken(null);
    window.dispatchEvent(new Event("anops-logout"));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not json */ }
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  return raw ? res : res.json();
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b = {}) => request("POST", p, b),
  put: (p, b) => request("PUT", p, b),
  del: (p) => request("DELETE", p),
  // authenticated file download (an <a href> cannot send the bearer token)
  async download(path, filename) {
    const res = await request("GET", path, undefined, true);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};

export const fmt = (iso) => (iso ? new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").toLocaleString() : "—");
export const bytes = (n) => (n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : n > 1024 ? (n / 1024).toFixed(1) + " KB" : n + " B");
