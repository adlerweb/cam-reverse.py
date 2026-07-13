// cam-reverse web UI — shared theme toggle + toast helper.
(function () {
  const KEY = "cam-theme";

  // Cycle: auto -> light -> dark -> auto
  window.cycleTheme = function () {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "light" ? "dark" : cur === "dark" ? null : "light";
    if (next) {
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem(KEY, next);
    } else {
      document.documentElement.removeAttribute("data-theme");
      localStorage.removeItem(KEY);
    }
    updateThemeButton();
  };

  window.updateThemeButton = function () {
    const btn = document.getElementById("theme-btn");
    if (!btn) return;
    const cur = document.documentElement.getAttribute("data-theme");
    btn.textContent = cur === "light" ? "☀️ Light" : cur === "dark" ? "🌙 Dark" : "🌗 Auto";
  };

  let toastTimer;
  window.toast = function (msg, isErr) {
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.className = "toast show" + (isErr ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.className = "toast";
    }, 2600);
  };

  document.addEventListener("DOMContentLoaded", updateThemeButton);
})();
