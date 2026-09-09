/**
 * Central API client. Attaches the Firebase ID token (when available) as a
 * Bearer header so the FastAPI backend can identify the user.
 *
 * A token getter is injected once at app start (see main.jsx) to avoid a
 * circular dependency between this module and AuthContext.
 */
export const API_BASE =
  import.meta.env.VITE_GEN_AI_API_URL || 'http://localhost:8000';

let _tokenGetter = async () => null;

export function setTokenGetter(fn) {
  _tokenGetter = fn;
}

async function authHeaders() {
  try {
    const token = await _tokenGetter();
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

/** fetch() with base URL + auth header. Returns the raw Response. */
export async function apiFetch(path, options = {}) {
  const headers = { ...(await authHeaders()), ...(options.headers || {}) };
  return fetch(`${API_BASE}${path}`, { ...options, headers });
}

/** apiFetch + JSON parse + error normalisation. */
export async function apiJson(path, options = {}) {
  const res = await apiFetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed (${res.status}).`);
  }
  return data;
}
