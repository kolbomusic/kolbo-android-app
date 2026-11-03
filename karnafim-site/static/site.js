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

  // Optional local-only voice capture. Never start capture on page load or
  // auto-submit the recording. Gracefully fall back to manual file upload.
  const recorderPanel = document.querySelector("[data-voice-recorder]");
  const upload = document.getElementById("story-uploads");
  const kind = document.querySelector('select[name="kind"]');
  if (recorderPanel && upload && kind) {
    const start = recorderPanel.querySelector("[data-record-start]");
    const stop = recorderPanel.querySelector("[data-record-stop]");
    const status = recorderPanel.querySelector("[data-record-status]");
    const preview = recorderPanel.querySelector("[data-record-preview]");
    const supported = typeof MediaRecorder !== "undefined" &&
      navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === "function" &&
      typeof DataTransfer !== "undefined";
    const mime = supported
      ? ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"]
        .find(type => MediaRecorder.isTypeSupported(type)) : null;
    let stream = null, current = null, chunks = [], previewUrl = null;
    const showPanel = () => {
      recorderPanel.hidden = kind.value !== "voice";
      if (kind.value === "voice" && !mime) {
        start.disabled = true;
        status.textContent = "הדפדפן אינו תומך בהקלטה ישירה. אפשר להעלות קובץ WebM או OGG.";
      }
    };
    kind.addEventListener("change", showPanel);
    showPanel();
    const release = () => {
      if (stream) stream.getTracks().forEach(t => t.stop());
      stream = null;
    };
    start.addEventListener("click", async () => {
      if (!mime || current?.state === "recording") return;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        current = new MediaRecorder(stream, { mimeType: mime });
        chunks = [];
        const session = current;
        session.addEventListener("dataavailable", e => { if (e.data?.size) chunks.push(e.data); });
        session.addEventListener("stop", () => {
          release();
          start.disabled = false;
          stop.disabled = true;
          if (!chunks.length) { status.textContent = "לא נקלט קול. נסו להקליט שוב."; return; }
          const type = mime.startsWith("audio/ogg") ? "audio/ogg" : "audio/webm";
          const blob = new Blob(chunks, { type });
          if (blob.size > 8 * 1024 * 1024) {
            status.textContent = "ההקלטה גדולה מ־8MB. נסו הקלטה קצרה יותר.";
            return;
          }
          const filename = type === "audio/ogg" ? "zicharon.ogg" : "zicharon.webm";
          const data = new DataTransfer();
          data.items.add(new File([blob], filename, { type }));
          upload.files = data.files;
          if (previewUrl) URL.revokeObjectURL(previewUrl);
          previewUrl = URL.createObjectURL(blob);
          preview.src = previewUrl;
          preview.hidden = false;
          status.textContent = "ההקלטה מוכנה להאזנה. היא תישלח רק בלחיצה על שליחה לביקורת.";
        });
        session.addEventListener("error", () => {
          release(); start.disabled = false; stop.disabled = true;
          status.textContent = "שגיאה בהקלטה. ניתן לצרף קובץ ידנית.";
        });
        session.start(1000);
        start.disabled = true;
        stop.disabled = false;
        status.textContent = "מקליט כעת. לעצירה לחצו על עצירת הקלטה.";
      } catch (_) {
        release();
        status.textContent = "הגישה למיקרופון לא אושרה או אינה זמינה. אפשר לבחור קובץ ידנית.";
      }
    });
    stop.addEventListener("click", () => {
      if (current?.state === "recording") current.stop();
    });
    window.addEventListener("pagehide", release);
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
    toggle.setAttribute("aria-label", "פתיחת תפריט הניווט");
    toggle.textContent = "☰ תפריט";
  };
  toggle.addEventListener("click", () => {
    const open = !nav.classList.contains("open");
    nav.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "סגירת תפריט הניווט" : "פתיחת תפריט הניווט");
    toggle.textContent = open ? "✕ סגירה" : "☰ תפריט";
    if (open) nav.querySelector("a")?.focus({ preventScroll: true });
  });
  nav.addEventListener("click", e => { if (e.target.closest("a")) close(); });
  document.addEventListener("pointerdown", e => {
    if (nav.classList.contains("open") && !nav.contains(e.target) && !toggle.contains(e.target)) close();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && nav.classList.contains("open")) { close(); toggle.focus(); }
  });
  window.addEventListener("resize", () => { if (window.innerWidth > 680) close(); });
})();