/* ============================================================
   scryops — Mermaid theming (warm palette)
   Re-themes Mermaid for the current mode and re-renders on
   toggle. Loaded after mermaid.min.js (see baseof.html).
   Dark: soft dark — amber node borders, blue-gray edges.
   Light: warm paper — earthy green nodes, muted blue-gray edges.
   ============================================================ */
(function () {
  if (typeof mermaid === 'undefined') return;

  function isDark() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  }

  function vars() {
    return isDark()
      ? {
          background:        '#1B1A17',
          primaryColor:      '#26241F',
          primaryBorderColor:'#8DA06B',
          primaryTextColor:  '#DAD4C8',
          lineColor:         '#7A93A0',
          secondaryColor:    '#26241F',
          tertiaryColor:     '#1B1A17',
          edgeLabelBackground:'#1B1A17',
          clusterBkg:        '#26241F',
          clusterBorder:     '#322F28',
          titleColor:        '#C99A4E',
          fontFamily:        "'IBM Plex Mono', monospace",
          fontSize:          '13.5px',
          nodeBorder:        '#322F28',
          mainBkg:           '#26241F',
          nodeTextColor:     '#E4DDD0'
        }
      : {
          background:        '#F3EFE6',
          primaryColor:      '#E7E0D2',
          primaryBorderColor:'#5E6B3F',
          primaryTextColor:  '#2B2723',
          lineColor:         '#4D6470',
          secondaryColor:    '#E7E0D2',
          tertiaryColor:     '#F3EFE6',
          edgeLabelBackground:'#F3EFE6',
          clusterBkg:        '#E7E0D2',
          clusterBorder:     '#D8CFBA',
          titleColor:        '#A65A3C',
          fontFamily:        "'IBM Plex Mono', monospace",
          fontSize:          '13.5px',
          nodeBorder:        '#D8CFBA',
          mainBkg:           '#E7E0D2',
          nodeTextColor:     '#2B2723'
        };
  }

  function cacheSource() {
    document.querySelectorAll('.mermaid').forEach(function (el) {
      if (!el.dataset.src) el.dataset.src = el.textContent.trim();
    });
  }

  function render() {
    cacheSource();
    mermaid.initialize({ startOnLoad: false, theme: 'base', themeVariables: vars() });
    document.querySelectorAll('.mermaid').forEach(function (el) {
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
