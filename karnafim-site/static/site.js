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