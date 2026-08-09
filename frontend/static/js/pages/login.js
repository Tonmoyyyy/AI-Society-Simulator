(function () {
  if (Auth.isLoggedIn()) {
    window.location.href = "dashboard.html";
    return;
  }

  const form = document.getElementById("auth-form");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const errorBox = document.getElementById("auth-error");
  const submitBtn = document.getElementById("submit-btn");
  const loginTabBtn = document.getElementById("tab-login-btn");
  const signupTabBtn = document.getElementById("tab-signup-btn");

  let mode = "login";

  function setMode(newMode) {
    mode = newMode;
    loginTabBtn.classList.toggle("active", mode === "login");
    signupTabBtn.classList.toggle("active", mode === "signup");
    submitBtn.textContent = mode === "login" ? "Log in" : "Create account";
    passwordInput.autocomplete = mode === "login" ? "current-password" : "new-password";
    hideError();
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("d-none");
  }
  function hideError() {
    errorBox.classList.add("d-none");
  }

  loginTabBtn.addEventListener("click", () => setMode("login"));
  signupTabBtn.addEventListener("click", () => setMode("signup"));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();
    submitBtn.disabled = true;
    const email = emailInput.value.trim();
    const password = passwordInput.value;

    try {
      if (mode === "signup") {
        await AuthApi.signup(email, password);
      }
      await AuthApi.login(email, password);
      window.location.href = "dashboard.html";
    } catch (err) {
      showError(err.message);
      submitBtn.disabled = false;
    }
  });
})();
