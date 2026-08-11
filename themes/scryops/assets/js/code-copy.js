/* code-copy.js — copy-to-clipboard for plain fenced code blocks.
   langswitch panels already have their own toolbar copy button
   (langswitch.js); this only targets ordinary .prose code blocks, which
   previously had no copy affordance at all. Progressive enhancement —
   the code renders and reads fine (just without the button, and without
   the measure-flush bleed telemetry.css applies via .code-well) with
   this script absent.

   Wraps <pre> in a new <div class="code-well"> rather than appending the
   button straight to <pre>: <pre> is the element carrying
   overflow-x:auto, so a button living inside it scrolls away with the
   code — unreachable on exactly the long lines worth copying — and
   without ITS OWN non-scrolling anchor there's no correct place to pin
   it in the first place. .code-well never scrolls, so the button stays
   put and reachable at any scroll position. */
(function () {
  function wire(pre) {
    var code = pre.querySelector("code");
    if (!code) return;
    var well = document.createElement("div");
    well.className = "code-well";
    pre.parentNode.insertBefore(well, pre);
    well.appendChild(pre);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "code-copy-btn";
    btn.textContent = "Copy";
    btn.setAttribute("aria-live", "polite");
    btn.addEventListener("click", function () {
      var text = code.innerText;
      if (navigator.clipboard) navigator.clipboard.writeText(text);
      btn.textContent = "Copied";
      clearTimeout(btn._ct);
      btn._ct = setTimeout(function () {
        btn.textContent = "Copy";
      }, 1500);
    });
    well.appendChild(btn);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".prose > .highlight, .prose > pre").forEach(function (container) {
      var pre = container.matches("pre") ? container : container.querySelector("pre");
      if (pre) wire(pre);
    });
  });
})();
