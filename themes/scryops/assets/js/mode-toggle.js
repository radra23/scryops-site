/* ============================================================
   scryops — dark/light mode toggle
   - Dark is the default (no class on <html>).
   - Stores choice in localStorage under 'scryops-mode'.
   - Re-themes Mermaid diagrams on switch (see mermaid-init.js).
   Inline the FOUC-guard snippet (see README) in <head> BEFORE
   CSS so the right mode paints on first frame.
   ============================================================ */
(function () {
  var KEY = 'scryops-mode';
  var root = document.documentElement;

  function apply(mode) {
    if (mode === 'light') root.classList.add('light');
    else root.classList.remove('light');
    document.querySelectorAll('.mode-toggle button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
    });
    if (window.scryopsRenderMermaid) window.scryopsRenderMermaid();
  }

  function current() {
    try { return localStorage.getItem(KEY) || 'dark'; } catch (e) { return 'dark'; }
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
