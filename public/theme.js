/* Light/dark toggle. The saved choice ("light" | "dark") is applied by an inline script in <head> to avoid a flash;
   with no saved choice the page follows the system setting. */
(function () {
  var root = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function current() { return root.dataset.theme || (mq && mq.matches ? "dark" : "light"); }
  function sync() { btn.setAttribute("aria-pressed", String(current() === "dark")); }
  btn.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("kr.theme", next); } catch (e) { /* storage blocked: the choice lasts for this visit */ }
    sync();
  });
  if (mq && mq.addEventListener) mq.addEventListener("change", sync);
  sync();
})();
