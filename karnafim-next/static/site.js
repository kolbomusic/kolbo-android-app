(() => {
  "use strict";
  const toggle = document.getElementById("toggle");
  const nav = document.getElementById("nav");
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
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  window.addEventListener("resize", () => { if (window.innerWidth > 680) close(); });
})();