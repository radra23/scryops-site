/* code-copy.js — copy-to-clipboard for plain fenced code blocks.
   langswitch panels already have their own toolbar copy button
   (langswitch.js); this only targets ordinary .prose code blocks, which
   previously had no copy affordance at all. Progressive enhancement —
   the code renders and reads fine with this script absent. */
(function () {
  // Button is appended to the actual <pre>, not the outer .highlight
  // wrapper — telemetry.css bleeds <pre> 19px past .highlight on each side
  // (the measure-relative code-well fix), and .highlight itself carries no
  // box-model styling, so anchoring position:relative there would leave
  // the button short of the well's true edge.
  function wire(pre) {
    var code = pre.querySelector("code");
    if (!code) return;
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
    pre.appendChild(btn);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".prose > .highlight, .prose > pre").forEach(function (container) {
      var pre = container.matches("pre") ? container : container.querySelector("pre");
      if (pre) wire(pre);
    });
  });
})();
