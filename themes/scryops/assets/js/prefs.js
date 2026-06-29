/* ============================================================
   scryops — reading preferences
   Supersedes mode-toggle.js. Manages, persists, and applies:
     • theme   : 'dark' | 'light' | 'calm'   -> html.light / html.calm
     • legible : Atkinson Hyperlegible face   -> html.pref-legible
     • spacing : looser lines & tracking      -> html.pref-spacing
     • reduce  : no transitions/animations     -> html.pref-reduce
   Stored as JSON under 'scryops-prefs'. Re-themes Mermaid on change.

   Inline the FOUC guard (see README) in <head> BEFORE the stylesheet
   so the stored prefs paint on the first frame.
   ============================================================ */
(function () {
  var KEY = 'scryops-prefs';
  var root = document.documentElement;
  var DEFAULTS = { theme: 'dark', legible: false, spacing: false, reduce: false };

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) return Object.assign({}, DEFAULTS, JSON.parse(raw));
      // migrate the old dark/light-only key if present
      var legacy = localStorage.getItem('scryops-mode');
      if (legacy) return Object.assign({}, DEFAULTS, { theme: legacy });
    } catch (e) {}
    return Object.assign({}, DEFAULTS);
  }

  var prefs = load();

  function apply() {
    root.classList.toggle('light', prefs.theme === 'light');
    root.classList.toggle('calm', prefs.theme === 'calm');
    root.classList.toggle('pref-legible', !!prefs.legible);
    root.classList.toggle('pref-spacing', !!prefs.spacing);
    root.classList.toggle('pref-reduce', !!prefs.reduce);
    syncUI();
    if (window.scryopsRenderMermaid) window.scryopsRenderMermaid();
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (e) {}
  }

  function set(patch) { Object.assign(prefs, patch); save(); apply(); }

  function syncUI() {
    document.querySelectorAll('[data-pref-theme]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.prefTheme === prefs.theme));
    });
    document.querySelectorAll('[data-pref-toggle]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(!!prefs[b.dataset.prefToggle]));
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    apply();

    var panel = document.querySelector('.pref-panel');
    var btn = document.querySelector('.pref-btn');
    if (btn && panel) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = panel.hasAttribute('hidden');
        if (open) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', String(open));
      });
      document.addEventListener('click', function (e) {
        if (!panel.hasAttribute('hidden') && !panel.contains(e.target) && e.target !== btn) {
          panel.setAttribute('hidden', ''); btn.setAttribute('aria-expanded', 'false');
        }
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !panel.hasAttribute('hidden')) {
          panel.setAttribute('hidden', ''); btn.setAttribute('aria-expanded', 'false'); btn.focus();
        }
      });
    }

    document.querySelectorAll('[data-pref-theme]').forEach(function (b) {
      b.addEventListener('click', function () { set({ theme: b.dataset.prefTheme }); });
    });
    document.querySelectorAll('[data-pref-toggle]').forEach(function (b) {
      b.addEventListener('click', function () {
        var k = b.dataset.prefToggle; var p = {}; p[k] = !prefs[k]; set(p);
      });
    });
  });

  window.scryopsPrefs = { get: function () { return Object.assign({}, prefs); }, set: set };
})();
