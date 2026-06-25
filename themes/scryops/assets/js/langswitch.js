/* langswitch.js — scryops multi-language code switcher (inline edition).
 *
 * One global selected language, shared by every {{< langswitch >}} block on the
 * page and persisted across reloads. Panels are the inner code blocks Hugo/Chroma
 * rendered (.highlight); their language comes from each <code data-lang>, and the
 * tab label + filename come from window.scryLangMeta (data/langmeta.yaml).
 *   - top-5 popular languages as tabs, the rest behind a "+N" overflow menu
 *   - the active language is promoted into the row if it lives in the overflow
 *   - selection resolved as: saved choice -> ?lang= -> host hook -> block default
 *   - first-load hint shows on the FIRST switcher only, until the first pick
 *
 * No dependencies. Highlighting is done server-side by Hugo/Chroma.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "scry:lang";
  // Popularity order -> which 5 are tabs vs. overflow. Keys are fence languages.
  var POPULAR = ["python", "javascript", "go", "java", "csharp", "rust", "ruby"];
  var VISIBLE_MAX = 5;
  var META = window.scryLangMeta || {};
  var ALIASES = { cs: "csharp", "c#": "csharp", js: "javascript", node: "javascript", golang: "go", py: "python", yml: "yaml", rb: "ruby" };

  var blocks = [];
  var current = null;   // globally selected fence language (or null before resolve)
  var explicit = false; // true once a user/saved choice exists

  function norm(lang) { lang = (lang || "").toLowerCase(); return ALIASES[lang] || lang; }
  function label(lang) { return (META[lang] && META[lang].label) || (lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : lang); }
  function file(lang) { return (META[lang] && META[lang].file) || ""; }

  /* ---- selection resolution ---- */
  function detect() {
    try { var saved = localStorage.getItem(STORAGE_KEY); if (saved) return { lang: norm(saved), explicit: true }; } catch (e) {}
    var qp = null;
    try { qp = new URLSearchParams(location.search).get("lang"); } catch (e) {}
    if (qp) return { lang: norm(qp), explicit: false };
    if (typeof window.scryDetectLang === "function") {
      try { var d = window.scryDetectLang(); if (d) return { lang: norm(d), explicit: false }; } catch (e) {}
    }
    return { lang: null, explicit: false };
  }
  function save(lang) { try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {} }

  function orderFor(langs) {
    var pop = POPULAR.filter(function (l) { return langs.indexOf(l) !== -1; });
    langs.forEach(function (l) { if (pop.indexOf(l) === -1) pop.push(l); });
    return pop;
  }
  function activeFor(b) {
    var ordered = orderFor(b.langs);
    if (current && b.langs.indexOf(current) !== -1) return current;
    if (b.defaultLang && b.langs.indexOf(b.defaultLang) !== -1) return b.defaultLang;
    return ordered[0];
  }
  function partition(ordered, active) {
    var visible = ordered.slice(0, VISIBLE_MAX);
    if (visible.indexOf(active) === -1 && ordered.indexOf(active) !== -1) {
      visible = ordered.slice(0, VISIBLE_MAX - 1).concat([active]);
    }
    var overflow = ordered.filter(function (l) { return visible.indexOf(l) === -1; });
    return { visible: visible, overflow: overflow };
  }

  /* ---- global state ---- */
  function choose(lang) {
    explicit = true; current = lang; save(lang);
    blocks.forEach(render);
    window.dispatchEvent(new CustomEvent("scry:langchange", { detail: { lang: lang } }));
  }

  /* ---- rendering ---- */
  function makeTab(b, lang, active) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ls-tab" + (lang === active ? " is-active" : "");
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", lang === active ? "true" : "false");
    btn.dataset.lang = lang;
    if (lang === b.defaultLang) { var dot = document.createElement("i"); dot.className = "ls-tabdot"; dot.setAttribute("aria-hidden", "true"); btn.appendChild(dot); }
    btn.appendChild(document.createTextNode(label(lang)));
    btn.addEventListener("click", function () { choose(lang); });
    return btn;
  }
  function makeOverflow(b, overflow, active) {
    var wrap = document.createElement("div"); wrap.className = "ls-overflow";
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "ls-more" + (overflow.indexOf(active) !== -1 ? " is-active" : "");
    toggle.setAttribute("aria-haspopup", "true"); toggle.setAttribute("aria-expanded", "false");
    toggle.textContent = "+" + overflow.length + " ▾";
    var menu = document.createElement("div"); menu.className = "ls-menu"; menu.hidden = true;
    overflow.forEach(function (lang) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "ls-menuitem" + (lang === active ? " is-active" : "");
      item.setAttribute("role", "tab");
      item.setAttribute("aria-selected", lang === active ? "true" : "false");
      item.dataset.lang = lang;
      if (lang === b.defaultLang) { var d = document.createElement("i"); d.className = "ls-tabdot"; d.setAttribute("aria-hidden", "true"); item.appendChild(d); }
      item.appendChild(document.createTextNode(label(lang)));
      item.addEventListener("click", function () { closeMenus(); choose(lang); });
      menu.appendChild(item);
    });
    function open(state) { menu.hidden = !state; toggle.setAttribute("aria-expanded", state ? "true" : "false"); toggle.classList.toggle("is-open", state); }
    toggle.addEventListener("click", function (e) { e.stopPropagation(); var willOpen = menu.hidden; closeMenus(); open(willOpen); });
    wrap.appendChild(toggle); wrap.appendChild(menu);
    return wrap;
  }
  function closeMenus() {
    document.querySelectorAll(".langswitch .ls-menu").forEach(function (m) { m.hidden = true; });
    document.querySelectorAll(".langswitch .ls-more").forEach(function (t) { t.setAttribute("aria-expanded", "false"); t.classList.remove("is-open"); });
  }
  function render(b) {
    var active = activeFor(b);
    var ordered = orderFor(b.langs);
    var part = partition(ordered, active);
    b.langs.forEach(function (l) { b.panels[l].hidden = (l !== active); });
    if (b.fileEl) b.fileEl.textContent = file(active);
    b.tabbar.innerHTML = "";
    part.visible.forEach(function (l) { b.tabbar.appendChild(makeTab(b, l, active)); });
    if (part.overflow.length) { b.tabbar.appendChild(makeOverflow(b, part.overflow, active)); }
    if (b.hintEl) {
      var isDefault = active === (b.defaultLang || ordered[0]);
      b.hintEl.hidden = explicit || !isDefault || b !== blocks[0]; // first switcher only
      if (b.hintLabelEl) b.hintLabelEl.textContent = label(active);
    }
  }

  /* ---- init ---- */
  function initBlock(root) {
    var panels = {};
    var host = root.querySelector("[data-ls-panels]") || root;
    host.querySelectorAll(".highlight").forEach(function (h) {
      var code = h.querySelector("code");
      var lang = norm(code && (code.dataset.lang || ""));
      if (!lang) return;
      if (!panels[lang]) panels[lang] = h; // first block per language wins
    });
    var langs = Object.keys(panels);
    if (!langs.length) return;
    var b = {
      root: root, panels: panels, langs: langs,
      tabbar: root.querySelector("[data-ls-tabs]"),
      fileEl: root.querySelector("[data-ls-file]"),
      copyEl: root.querySelector("[data-ls-copy]"),
      hintEl: root.querySelector("[data-ls-hint]"),
      hintLabelEl: root.querySelector("[data-ls-hint-label]"),
      defaultLang: norm(root.dataset.default || "") || null,
    };
    b.tabbar.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var tabs = [].slice.call(b.tabbar.querySelectorAll(".ls-tab"));
      var i = tabs.indexOf(document.activeElement);
      if (i === -1) return;
      e.preventDefault();
      var next = e.key === "ArrowRight" ? (i + 1) % tabs.length : (i - 1 + tabs.length) % tabs.length;
      tabs[next].focus(); choose(tabs[next].dataset.lang);
    });
    if (b.copyEl) {
      b.copyEl.addEventListener("click", function () {
        var active = activeFor(b);
        var pre = b.panels[active] && b.panels[active].querySelector("pre");
        var text = pre ? pre.innerText : "";
        if (navigator.clipboard) navigator.clipboard.writeText(text);
        b.copyEl.textContent = "Copied";
        clearTimeout(b._ct);
        b._ct = setTimeout(function () { b.copyEl.textContent = "Copy"; }, 1500);
      });
    }
    blocks.push(b);
  }

  function boot() {
    var roots = document.querySelectorAll("[data-langswitch]");
    if (!roots.length) return;
    roots.forEach(initBlock);
    if (!blocks.length) return;
    var res = detect();
    explicit = res.explicit; current = res.lang;
    blocks.forEach(render);
    document.addEventListener("click", closeMenus);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenus(); });
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); } else { boot(); }
})();
