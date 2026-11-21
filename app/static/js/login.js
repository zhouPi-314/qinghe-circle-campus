(() => {
  const form = document.getElementById("login-form");
  const password = document.getElementById("password");
  const toggle = document.getElementById("password-toggle");
  const identifier = document.getElementById("identifier");
  const remember = document.getElementById("remember-account");
  const submit = form?.querySelector('button[type="submit"]');

  if (!form || !password || !toggle || !identifier || !remember || !submit) return;

  const storageKey = `qinghe.login.identifier.${form.dataset.role || "default"}`;
  try {
    const stored = localStorage.getItem(storageKey);
    if (stored && !identifier.value) {
      identifier.value = stored;
      remember.checked = true;
    }
  } catch (_error) {
    // Local storage may be unavailable in hardened browser profiles.
  }

  toggle.addEventListener("click", () => {
    const show = password.type === "password";
    password.type = show ? "text" : "password";
    toggle.setAttribute("aria-pressed", String(show));
    toggle.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
    password.focus({ preventScroll: true });
  });

  form.addEventListener("submit", () => {
    try {
      if (remember.checked) localStorage.setItem(storageKey, identifier.value.trim());
      else localStorage.removeItem(storageKey);
    } catch (_error) {
      // Account remembering is optional; login submission must continue.
    }
    submit.setAttribute("aria-busy", "true");
    submit.querySelector("span").textContent = "正在登录…";
  });
})();
