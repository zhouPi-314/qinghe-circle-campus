(() => {
  const root = document.documentElement;
  const buttons = [...document.querySelectorAll("[data-theme-toggle]")];

  function labelFor(theme) {
    return theme === "dark" ? "切换为浅色主题" : "切换为深色主题";
  }

  function sync(theme) {
    root.dataset.theme = theme;
    buttons.forEach((button) => {
      button.setAttribute("aria-label", labelFor(theme));
      button.title = labelFor(theme);
      button.setAttribute("aria-pressed", String(theme === "dark"));
    });
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      sync(next);
      try {
        localStorage.setItem("qinghe.theme", next);
      } catch (_error) {
        // Theme switching still works when storage is unavailable.
      }
    });
  });

  sync(root.dataset.theme === "dark" ? "dark" : "light");
})();
