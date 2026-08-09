// Thin fetch wrapper shared by every page. Handles:
//  - attaching the stored Bearer token
//  - parsing the backend's {"error": {"code": ..., "message": ...}} shape
//    into a normal JS Error with a readable .message
//  - redirecting to login on 401/403 for protected calls (never for public
//    GETs — see requireAuth flag)

const TOKEN_KEY = "asim_access_token";
const USER_KEY = "asim_user_email";

const Auth = {
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },
  setSession(token, email) {
    localStorage.setItem(TOKEN_KEY, token);
    if (email) localStorage.setItem(USER_KEY, email);
  },
  getEmail() {
    return localStorage.getItem(USER_KEY);
  },
  clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  isLoggedIn() {
    return !!Auth.getToken();
  },
  requireLogin() {
    if (!Auth.isLoggedIn()) {
      window.location.href = "login.html";
    }
  },
};

/**
 * @param {string} path - e.g. "/api/v1/citizens"
 * @param {object} options - fetch options; extra flag `auth: true` attaches
 *   the Bearer token (needed for write endpoints).
 */
async function apiFetch(path, options = {}) {
  const { auth = false, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});

  if (fetchOptions.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = Auth.getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let response;
  try {
    response = await fetch(`${window.ASIM_CONFIG.API_BASE}${path}`, {
      ...fetchOptions,
      headers,
    });
  } catch (networkErr) {
    throw new Error(
      "Can't reach the backend. Is it running at " + window.ASIM_CONFIG.API_BASE + "?"
    );
  }

  if (response.status === 204) return null;

  let body = null;
  try {
    body = await response.json();
  } catch (_) {
    // no JSON body (rare) — fall through, response.ok check below handles it
  }

  if (!response.ok) {
    if ((response.status === 401 || response.status === 403) && auth) {
      Auth.clearSession();
      window.location.href = "login.html";
      return null;
    }
    const message =
      (body && body.error && body.error.message) ||
      (body && body.detail) ||
      `Request failed (${response.status})`;
    throw new Error(message);
  }

  return body;
}
