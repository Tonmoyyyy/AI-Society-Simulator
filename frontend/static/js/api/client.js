// Thin fetch wrapper shared by every page. Handles:
//  - attaching the stored Bearer token
//  - parsing the backend's {"error": {"code": ..., "message": ...}} shape
//  - handling 401/403 errors gracefully without immediate logout loops

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
 * @param {object} options - fetch options
 */
async function apiFetch(path, options = {}) {
  const { auth = true, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});

  if (fetchOptions.body && !headers.has("Content-Type") && !(fetchOptions.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (auth) {
    const token = Auth.getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let response;
  try {
    const baseUrl = window.ASIM_CONFIG ? window.ASIM_CONFIG.API_BASE : "http://127.0.0.1:8000";
    response = await fetch(`${baseUrl}${path}`, {
      ...fetchOptions,
      headers,
    });
  } catch (networkErr) {
    console.error(`[API Fetch Network Error] Path: ${path}`, networkErr);
    throw new Error(
      "Can't reach the backend. Is it running at " + (window.ASIM_CONFIG ? window.ASIM_CONFIG.API_BASE : "http://127.0.0.1:8000") + "?"
    );
  }

  if (response.status === 204) return null;

  let body = null;
  try {
    body = await response.json();
  } catch (_) {
    // Non-JSON response
  }

  if (!response.ok) {
    // 401/403 এরর আসলে সরাসরি রিডাইরেক্ট না করে এরর থ্রো করা হচ্ছে
    if ((response.status === 401 || response.status === 403) && auth) {
      const msg = (body && body.detail) || "Admin permissions required or token expired.";
      throw new Error(`[${response.status}] ${msg}`);
    }

    const message =
      (body && body.error && body.error.message) ||
      (body && body.detail) ||
      `Request failed (${response.status})`;
    throw new Error(message);
  }

  return body;
}