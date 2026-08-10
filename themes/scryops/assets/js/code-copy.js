/* code-copy.js — copy-to-clipboard for plain fenced code blocks.
   langswitch panels already have their own toolbar copy button
   (langswitch.js); this only targets ordinary .prose code blocks, which
   previously had no copy affordance at all. Progressive enhancement —
   the code renders and reads fine with this script absent. */
(function () {
  function wire(container) {
    var code = container.querySelector("code");
    if (!code) return;
    container.style.position = "relative";
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
    container.appendChild(btn);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".prose > .highlight, .prose > pre").forEach(wire);
  });
})();
