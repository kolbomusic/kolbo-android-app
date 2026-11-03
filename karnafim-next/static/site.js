(() => {
  "use strict";
  const toggle = document.getElementById("toggle");
  const nav = document.getElementById("nav");
  for (const control of document.querySelectorAll("[data-password-toggle]")) {
    const field = document.getElementById(control.getAttribute("aria-controls"));
    if (!field) continue;
    control.addEventListener("click", () => {
      const reveal = field.type === "password";
      field.type = reveal ? "text" : "password";
      control.setAttribute("aria-pressed", String(reveal));
      control.setAttribute("aria-label", reveal ? "הסתרת הסיסמה" : "הצגת הסיסמה");
      control.textContent = reveal ? "הסתרה" : "הצגה";
      field.focus({ preventScroll: true });
    });
  }
  // Render Free can suspend an idle web service. This client checks only
  // while a person is viewing/returning to the page; it never bypasses
  // browser safety warnings, submits forms, reads member data or runs
  // unattended keep-alive traffic.
  const connectionNotice = document.getElementById("site-connection-notice");
  const connectionText = document.getElementById("site-connection-message");
  const connectionRetry = document.getElementById("site-connection-retry");
  if (connectionNotice && connectionText && connectionRetry) {
    let checking = false, wakeAttempts = 0, retryTimer = null;
    const clearRetry = () => {
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = null;
    };
    const showConnection = text => {
      connectionText.textContent = text;
      connectionNotice.hidden = false;
    };
    const checkConnection = async () => {
      if (checking || document.hidden) return;
      if (navigator.onLine === false) {
        clearRetry();
        showConnection("אין כרגע חיבור לאינטרנט. פרטים שהזנת בדף אינם נשלחים שוב אוטומטית.");
        return;
      }
      checking = true;
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 9000);
      try {
        const response = await fetch("/health", {
          method: "GET", credentials: "same-origin", cache: "no-store",
          headers: { Accept: "application/json" }, signal: controller.signal
        });
        const contentType = String(response.headers.get("content-type") || "");
        if (!response.ok || !contentType.includes("application/json")) {
          throw new Error("Health request did not return JSON");
        }
        const body = await response.json();
        if (body.status !== "ok") throw new Error("Service not ready");
        clearRetry();
        wakeAttempts = 0;
        connectionNotice.hidden = true;
      } catch (_) {
        showConnection("ייתכן שהשרת החינמי מתעורר ממצב שינה. פרסומים וטפסים לא נשלחים שוב אוטומטית. בדוק שהחיבור חזר לפני שליחה.");
        if (wakeAttempts < 6 && retryTimer === null && !document.hidden) {
          wakeAttempts++;
          retryTimer = window.setTimeout(() => {
            retryTimer = null;
            checkConnection();
          }, 5000);
        }
      } finally {
        window.clearTimeout(timer);
        checking = false;
      }
    };
    connectionRetry.addEventListener("click", () => {
      clearRetry();
      wakeAttempts = 0;
      checkConnection();
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) clearRetry();
      else checkConnection();
    });
    window.addEventListener("online", checkConnection);
    window.addEventListener("offline", checkConnection);
    checkConnection();
  }
  if (!toggle || !nav) return;
  const close = () => {
    nav.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.textContent = "☰ תפריט";
  };
  toggle.addEventListener("click", () => {
    const open = !nav.classList.contains("open");
    nav.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "✕ סגירה" : "☰ תפריט";
  });
  nav.addEventListener("click", e => { if (e.target.closest("a")) close(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && nav.classList.contains("open")) { close(); toggle.focus(); } });
  window.addEventListener("resize", () => { if (window.innerWidth > 680) close(); });
})();