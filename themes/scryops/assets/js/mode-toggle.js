/* ============================================================
   scryops — dark/light mode toggle
   - Light (warm paper) is the DEFAULT (no data-theme on <html>).
   - Dark (soft dark) is applied via data-theme="dark" on <html>.
   - Stores choice in localStorage under 'scryops-mode'.
   - Re-themes Mermaid diagrams on switch (see mermaid-init.js).
   Inline the FOUC-guard snippet (see head.html) in <head> BEFORE
   CSS so the right mode paints on first frame.
   ============================================================ */
(function () {
  var KEY = 'scryops-mode';
  var root = document.documentElement;

  function apply(mode) {
    if (mode === 'dark') root.setAttribute('data-theme', 'dark');
    else root.removeAttribute('data-theme');
    document.querySelectorAll('.mode-toggle button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
    });
    if (window.scryopsRenderMermaid) window.scryopsRenderMermaid();
  }

  function current() {
    try { return localStorage.getItem(KEY) || 'light'; } catch (e) { return 'light'; }
  }

  function set(mode) {
    try { localStorage.setItem(KEY, mode); } catch (e) {}
    apply(mode);
  }

  document.addEventListener('DOMContentLoaded', function () {
    apply(current());
    document.querySelectorAll('.mode-toggle button').forEach(function (b) {
      b.addEventListener('click', function () { set(b.dataset.mode); });
    });
  });

  window.scryopsMode = { set: set, current: current };
})();
