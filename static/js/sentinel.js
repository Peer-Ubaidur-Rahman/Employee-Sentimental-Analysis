/* sentinel.js - shared UI behaviour: mobile drawer, character counter, confirm dialogs. */
(function () {
  "use strict";
  var sidebar = document.getElementById("sidebar");
  var scrim = document.getElementById("scrim");
  var toggle = document.getElementById("menuToggle");
  function setDrawer(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (scrim) scrim.classList.toggle("open", open);
  }
  if (toggle) toggle.addEventListener("click", function () { setDrawer(!sidebar.classList.contains("open")); });
  if (scrim) scrim.addEventListener("click", function () { setDrawer(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") setDrawer(false); });

  // <textarea data-counter="#target" maxlength="..."> live character counter
  document.querySelectorAll("textarea[data-counter]").forEach(function (area) {
    var target = document.querySelector(area.dataset.counter);
    var min = parseInt(area.dataset.min || "0", 10);
    function update() {
      if (!target) return;
      var n = area.value.length;
      target.textContent = n + " / " + area.maxLength + (n < min ? " (minimum " + min + ")" : "");
      target.classList.toggle("c-neg", n < min && n > 0);
    }
    area.addEventListener("input", update);
    update();
  });

  // <form data-confirm="Are you sure?"> asks before submitting
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });
})();
