/* ============================================================
   scryops — Mermaid theming (Telemetry)
   Re-themes Mermaid for the current mode and re-renders on
   toggle. Loaded after mermaid.min.js (see partials/head.html).
   Diagrams read green node strokes, cyan edges, bright labels —
   matching the obs-* figure frame.
   ============================================================ */
(function () {
  if (typeof mermaid === 'undefined') return;

  function vars() {
    var light = document.documentElement.classList.contains('light');
    return light
      ? {
          background:        '#FFFFFF',
          primaryColor:      '#EAF1ED',
          primaryBorderColor:'#1E8F52',
          primaryTextColor:  '#18201E',
          lineColor:         '#0E7E91',
          secondaryColor:    '#E7F2EB',
          tertiaryColor:     '#F4F6F5',
          fontFamily:        "'IBM Plex Mono', monospace",
          fontSize:          '14px'
        }
      : {
          background:        '#0B1011',
          primaryColor:      '#10191A',
          primaryBorderColor:'#2BAE76',
          primaryTextColor:  '#EAF0EE',
          lineColor:         '#5BD8E8',
          secondaryColor:    '#0C1A14',
          tertiaryColor:     '#0C1213',
          fontFamily:        "'IBM Plex Mono', monospace",
          fontSize:          '14px'
        };
  }

  // Stash original source so we can re-render on theme change.
  function cacheSource() {
    document.querySelectorAll('.mermaid').forEach(function (el) {
      if (!el.dataset.src) el.dataset.src = el.textContent.trim();
    });
  }

  function render() {
    cacheSource();
    mermaid.initialize({ startOnLoad: false, theme: 'base', themeVariables: vars() });
    document.querySelectorAll('.mermaid').forEach(function (el, i) {
      el.removeAttribute('data-processed');
      el.innerHTML = el.dataset.src;
    });
    if (mermaid.run) {
      mermaid.run({ querySelector: '.mermaid' });
    } else {
      mermaid.init(undefined, document.querySelectorAll('.mermaid'));
    }
  }

  window.scryopsRenderMermaid = render;
  document.addEventListener('DOMContentLoaded', render);
})();
