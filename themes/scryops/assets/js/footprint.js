/* ============================================================
   scryops — footprint.js  (permacomputing, Phase 2)
   Measures THIS page's real transfer size from the Performance API
   and estimates CO₂, then fills any [data-footprint] badge on the
   page. No build step, no third-party calls — observability applied
   to the publication itself.

   transferSize reflects the NETWORK, so cached resources count as
   ~0 on repeat visits (a return visitor sees a lighter footprint —
   that's correct). Caveat: cross-origin resources without a
   Timing-Allow-Origin header report transferSize 0, so a CDN font
   is invisible here until you self-host it (that's Phase 4, and a
   reason to do it).

   Carbon is a Sustainable Web Design approximation. For rigor, swap
   the two constants below for the @tgwf/co2 (CO2.js) library.
   ============================================================ */
(function () {
  // --- carbon model (edit these, or replace with CO2.js) ---
  var KWH_PER_GB = 0.81;   // Sustainable Web Design: total energy per GB
  var GRID_G_PER_KWH = 442; // global average grid intensity, gCO₂e/kWh
  var DEFAULT_BUDGET = 120 * 1024; // bytes; per-page override via data-fp-budget

  function totalBytes() {
    if (!('performance' in window) || !performance.getEntriesByType) return null;
    var bytes = 0;
    var res = performance.getEntriesByType('resource');
    for (var i = 0; i < res.length; i++) bytes += (res[i].transferSize || 0);
    var nav = performance.getEntriesByType('navigation')[0];
    if (nav) bytes += (nav.transferSize || 0);
    return bytes;
  }

  function grams(bytes) { return bytes / 1e9 * KWH_PER_GB * GRID_G_PER_KWH; }

  function fmtBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(2) + ' MB';
  }
  function fmtG(g) {
    if (g < 0.01) return '<0.01 g CO\u2082';
    return '~' + (g < 1 ? g.toFixed(2) : g.toFixed(1)) + ' g CO\u2082';
  }

  function render() {
    var hosts = document.querySelectorAll('[data-footprint]');
    if (!hosts.length) return;
    var bytes = totalBytes();
    hosts.forEach(function (host) {
      if (bytes === null) { host.setAttribute('hidden', ''); return; }
      var budget = parseInt(host.getAttribute('data-fp-budget'), 10) || DEFAULT_BUDGET;
      var pct = Math.min(100, Math.round(bytes / budget * 100));
      var under = bytes <= budget;
      var set = function (sel, txt) { var el = host.querySelector(sel); if (el) el.textContent = txt; };
      set('[data-fp-size]', fmtBytes(bytes));
      set('[data-fp-co2]', fmtG(grams(bytes)));
      set('[data-fp-status]', under ? '\u2713 under budget' : '\u26A0 over budget');
      set('[data-fp-note]', pct + '% of the ' + fmtBytes(budget) + ' page budget');
      var fill = host.querySelector('[data-fp-fill]');
      if (fill) fill.style.width = pct + '%';
      host.classList.toggle('over', !under);
    });
  }

  // Run after load so late/async resources are included.
  if (document.readyState === 'complete') setTimeout(render, 0);
  else window.addEventListener('load', function () { setTimeout(render, 200); });

  window.scryopsFootprint = render; // re-run manually if you inject content
})();
