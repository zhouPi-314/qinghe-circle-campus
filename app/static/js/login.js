(() => {
  const form = document.getElementById("login-form");
  const password = document.getElementById("password");
  const toggle = document.getElementById("password-toggle");
  const identifier = document.getElementById("identifier");
  const remember = document.getElementById("remember-account");
  const submit = form?.querySelector('button[type="submit"]');
  const identitySwitcher = document.querySelector(".identity-switcher");
  const identityPicker = document.getElementById("identity-picker");
  const selectedRole = document.getElementById("selected-role");
  const roleChip = document.getElementById("role-chip");
  const roleNotice = document.getElementById("role-required-notice");
  const roleConfigNode = document.getElementById("identity-config");
  const loginIntro = document.getElementById("login-intro");
  const contextLabel = document.getElementById("context-label");
  const contextValue = document.getElementById("context-value");
  const contextAction = document.getElementById("context-action");
  const registrationNotice = document.getElementById("registration-guard-notice");
  const accountLabel = document.getElementById("account-label");
  const footnoteText = document.getElementById("footnote-text");
  const footnoteLink = document.getElementById("footnote-link");
  const securityVerification = document.getElementById("security-verification");
  const securityError = document.getElementById("security-verification-error");
  const captchaImage = document.getElementById("login-captcha-image");
  const captchaRefresh = document.getElementById("captcha-refresh");

  if (
    !form ||
    !password ||
    !toggle ||
    !identifier ||
    !remember ||
    !submit ||
    !selectedRole ||
    !roleConfigNode ||
    !registrationNotice
  ) {
    return;
  }

  let identityConfig = {};
  try {
    identityConfig = JSON.parse(roleConfigNode.textContent);
  } catch (_error) {
    // The fallback identity page remains available when configuration is invalid.
  }

  let currentRole = form.dataset.role || "";
  let roleSync = Promise.resolve(true);

  function storageKey(role) {
    return `qinghe.login.identifier.${role || "default"}`;
  }

  function restoreIdentifier(role) {
    try {
      const stored = localStorage.getItem(storageKey(role));
      if (stored) {
        identifier.value = stored;
        remember.checked = true;
      }
    } catch (_error) {
      // Local storage may be unavailable in hardened browser profiles.
    }
  }

  function setControlledState(enabled) {
    identifier.disabled = !enabled;
    password.disabled = !enabled;
    toggle.disabled = !enabled;
    remember.disabled = !enabled;
    submit.disabled = !enabled;
  }

  function syncRole(role) {
    const syncUrl = identityPicker?.dataset.roleSyncUrl;
    if (!syncUrl) return roleSync;
    const csrf = identityPicker.querySelector('input[name="csrf_token"]')?.value || "";
    roleSync = roleSync.then(async () => {
      try {
        const response = await fetch(syncUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ csrf_token: csrf, role }),
        });
        if (response.ok) return true;
      } catch (_error) {
        // The visible error below explains that navigation must be retried.
      }
      roleNotice.textContent = "身份同步失败，请重新选择后再继续。";
      roleNotice.hidden = false;
      return false;
    });
    return roleSync;
  }

  function applyRole(role) {
    const config = identityConfig[role];
    if (!config) return false;

    const roleChanged = currentRole && currentRole !== role;
    if (roleChanged) {
      identifier.value = "";
      password.value = "";
      remember.checked = false;
      document.querySelectorAll(".form-field.has-error").forEach((field) => {
        field.classList.remove("has-error");
      });
      document.querySelectorAll(".field-error").forEach((error) => {
        error.hidden = true;
      });
    }

    currentRole = role;
    form.dataset.role = role;
    selectedRole.value = role;
    roleChip.textContent = config.label;
    loginIntro.textContent = config.intro;
    roleNotice.hidden = true;
    contextLabel.textContent = config.context_label;
    contextValue.textContent = config.context_text;
    accountLabel.textContent = config.account_label;
    identifier.placeholder = config.account_placeholder;
    setControlledState(true);

    if (config.context_action_url) {
      contextAction.href = config.context_action_url;
      contextAction.textContent = config.context_action_label;
      contextAction.hidden = false;
    } else {
      contextAction.hidden = true;
    }

    footnoteText.textContent = config.footnote;
    registrationNotice.hidden = true;
    footnoteLink.dataset.registrationReady = config.registration_ready ? "1" : "0";
    if (config.footnote_url) {
      footnoteLink.href = config.footnote_url;
      footnoteLink.textContent = config.footnote_link_label;
      footnoteLink.hidden = false;
    } else {
      footnoteLink.hidden = true;
    }

    document.title = `${config.label}登录 - 青禾流转`;
    if (!roleChanged) restoreIdentifier(role);
    syncRole(role);
    return true;
  }

  identityPicker?.addEventListener("change", (event) => {
    const role = event.target instanceof HTMLInputElement ? event.target.value : "";
    if (!applyRole(role)) return;
    window.setTimeout(() => {
      if (identitySwitcher) identitySwitcher.open = false;
    }, 120);
  });

  identityPicker?.addEventListener("submit", (event) => {
    event.preventDefault();
    const checked = identityPicker.querySelector('input[name="role"]:checked');
    if (checked) applyRole(checked.value);
    if (identitySwitcher) identitySwitcher.open = false;
  });

  document.addEventListener("click", (event) => {
    if (identitySwitcher?.open && !identitySwitcher.contains(event.target)) {
      identitySwitcher.open = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && identitySwitcher?.open) {
      identitySwitcher.open = false;
      identitySwitcher.querySelector("summary")?.focus();
    }
  });

  contextAction.addEventListener("click", async (event) => {
    event.preventDefault();
    const target = contextAction.href;
    if (await roleSync) window.location.assign(target);
  });

  footnoteLink.addEventListener("click", async (event) => {
    event.preventDefault();
    if (currentRole === "student" && footnoteLink.dataset.registrationReady !== "1") {
      registrationNotice.hidden = false;
      contextAction.focus();
      return;
    }
    const target = footnoteLink.href;
    if (await roleSync) window.location.assign(target);
  });

  if (!currentRole) {
    setControlledState(false);
  } else {
    const currentConfig = identityConfig[currentRole];
    if (currentConfig) {
      footnoteLink.dataset.registrationReady = currentConfig.registration_ready ? "1" : "0";
    }
    restoreIdentifier(currentRole);
  }

  toggle.addEventListener("click", () => {
    const show = password.type === "password";
    password.type = show ? "text" : "password";
    toggle.setAttribute("aria-pressed", String(show));
    toggle.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
    password.focus({ preventScroll: true });
  });

  form.addEventListener("submit", (event) => {
    if (securityVerification?.dataset.mode === "turnstile") {
      const turnstileToken = document.querySelector(
        '.cf-turnstile [name="cf-turnstile-response"]',
      )?.value;
      if (!turnstileToken) {
        if (securityError) {
          securityError.textContent = "请先完成安全验证。";
          securityError.hidden = false;
        }
        event.preventDefault();
        return;
      }
      if (securityError) securityError.hidden = true;
    }
    try {
      if (remember.checked) localStorage.setItem(storageKey(currentRole), identifier.value.trim());
      else localStorage.removeItem(storageKey(currentRole));
    } catch (_error) {
      // Account remembering is optional; login submission must continue.
    }
    submit.setAttribute("aria-busy", "true");
    submit.querySelector("span").textContent = "正在登录…";
  });

  captchaRefresh?.addEventListener("click", () => {
    if (!captchaImage) return;
    const baseUrl = captchaImage.dataset.captchaSrc;
    if (!baseUrl) return;
    captchaRefresh.disabled = true;
    captchaImage.src = `${baseUrl}?refresh=${Date.now()}`;
  });

  captchaImage?.addEventListener("load", () => {
    if (captchaRefresh) captchaRefresh.disabled = false;
  });

  captchaImage?.addEventListener("error", () => {
    if (securityError) {
      securityError.textContent = "验证码加载失败，请换一张后重试。";
      securityError.hidden = false;
    }
    if (captchaRefresh) captchaRefresh.disabled = false;
  });

})();
