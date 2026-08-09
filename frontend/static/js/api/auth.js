const AuthApi = {
  async signup(email, password) {
    return apiFetch("/api/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async login(email, password) {
    const result = await apiFetch("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    Auth.setSession(result.access_token, email);
    return result;
  },

  logout() {
    Auth.clearSession();
    window.location.href = "login.html";
  },
};
