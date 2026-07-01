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

   Carbon uses the Sustainable Web Design v4 model — the one CO2.js
   (@tgwf/co2) implements — inlined below so the badge adds no runtime
   dependency. Method + constants are published at /colophon/#method.
   ============================================================ */
(function () {
  // --- carbon model: Sustainable Web Design v4 (as implemented by CO2.js) ---
  // Per-segment energy in kWh/GB: operational (op*) + embodied (em*). The
  // green-hosting factor offsets only the data-centre operational share; kept
  // at 0 — conservative and honest (github.io isn't a verified green host).
  var SWD = {
    opDC: 0.055, emDC: 0.012,    // data centre
    opNet: 0.059, emNet: 0.013,  // network
    opDev: 0.080, emDev: 0.081,  // user device
    grid: 494,                   // gCO₂e/kWh — global average (Ember)
    green: 0                     // green-hosting factor, 0–1
  };
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

  // SWD v4 per-byte: sum the segment energy (green offsets only the data-centre
  // operational share), then apply grid carbon intensity.
  function grams(bytes) {
    var kwhPerGB = (SWD.opDC * (1 - SWD.green) + SWD.emDC)
                 + (SWD.opNet + SWD.emNet)
                 + (SWD.opDev + SWD.emDev);
    return bytes / 1e9 * kwhPerGB * SWD.grid;
  }

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
      var set = function (sel, txt) { var el = host.querySelector(sel); if (el) el.textContent = txt; };
      var fill0 = host.querySelector('[data-fp-fill]');
      // Repeat visit: every resource came from cache, so transferSize is 0.
      // "0 B" reads like a bug — say so plainly instead.
      if (bytes === 0) {
        set('[data-fp-size]', 'cached');
        set('[data-fp-co2]', '~0 g CO₂');
        set('[data-fp-status]', '✓ served from cache');
        set('[data-fp-note]', 'no new transfer this visit');
        if (fill0) fill0.style.width = '0%';
        host.classList.remove('over');
        return;
      }
      var budget = parseInt(host.getAttribute('data-fp-budget'), 10) || DEFAULT_BUDGET;
      var pct = Math.min(100, Math.round(bytes / budget * 100));
      var under = bytes <= budget;
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
