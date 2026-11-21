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
  const accountLabel = document.getElementById("account-label");
  const footnoteText = document.getElementById("footnote-text");
  const footnoteLink = document.getElementById("footnote-link");

  if (
    !form ||
    !password ||
    !toggle ||
    !identifier ||
    !remember ||
    !submit ||
    !selectedRole ||
    !roleConfigNode
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
    if (config.footnote_url) {
      footnoteLink.href = config.footnote_url;
      footnoteLink.textContent = config.footnote_link_label;
      footnoteLink.hidden = false;
    } else {
      footnoteLink.hidden = true;
    }

    document.title = `${config.label}登录 - 青禾流转`;
    if (!roleChanged) restoreIdentifier(role);
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

  if (!currentRole) {
    setControlledState(false);
  } else {
    restoreIdentifier(currentRole);
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
      if (remember.checked) localStorage.setItem(storageKey(currentRole), identifier.value.trim());
      else localStorage.removeItem(storageKey(currentRole));
    } catch (_error) {
      // Account remembering is optional; login submission must continue.
    }
    submit.setAttribute("aria-busy", "true");
    submit.querySelector("span").textContent = "正在登录…";
  });
})();
