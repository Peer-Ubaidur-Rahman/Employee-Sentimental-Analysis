/* feedback_explorer.js - detail drawer for the feedback explorer (data fetched from the server on demand). */
(function () {
  "use strict";
  var drawer = document.getElementById("drawer");
  if (!drawer) return;
  var body = document.getElementById("drawerBody");
  var scrim = document.getElementById("drawerScrim");
  var colors = { Positive: "#16845B", Neutral: "#9A6B13", Negative: "#C53E4D" };

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
  function setOpen(open) {
    drawer.classList.toggle("open", open);
    scrim.classList.toggle("open", open);
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
  }
  function render(d) {
    var rating = function (v) { return v == null ? "–" : v; };
    var probs = Object.keys(d.probabilities || {}).map(function (k) {
      var v = d.probabilities[k] || 0;
      return '<div class="prob-row"><span style="width:62px">' + k + '</span><span class="track"><span class="fill d-block" style="width:' +
             (v * 100).toFixed(0) + "%;background:" + colors[k] + '"></span></span><span class="tnum">' + (v * 100).toFixed(0) + "%</span></div>";
    }).join("");
    var terms = (d.top_terms || []).map(function (t) { return '<span class="term">' + esc(t.term) + "</span>"; }).join("");
    body.className = "";
    body.innerHTML =
      '<div class="muted small mb-2">' + esc(d.submitted_at) + " · " + esc(d.department) + " · " + esc(d.submitter) + "</div>" +
      '<p style="white-space:pre-wrap">' + esc(d.text) + "</p><hr>" +
      '<div class="metric-label mb-1">Predicted sentiment</div>' +
      (d.sentiment ? '<span class="chip chip-' + d.sentiment.toLowerCase() + '">' + esc(d.sentiment) + "</span> " +
        '<span class="muted small">confidence ' + ((d.confidence || 0) * 100).toFixed(0) + "%</span>" : "<span class=muted>Not analysed</span>") +
      '<div class="mt-3">' + probs + "</div>" +
      (terms ? '<div class="metric-label mt-3 mb-1">Terms that most influenced this prediction</div>' + terms : "") +
      '<div class="metric-label mt-3 mb-1">Employee ratings (overall / management / workload / culture)</div>' +
      '<div class="tnum">' + rating(d.ratings.overall) + " / " + rating(d.ratings.management) + " / " +
      rating(d.ratings.workload) + " / " + rating(d.ratings.culture) + "</div>" +
      '<div class="notice mt-3">Automated estimate from model ' + esc(d.model_version || "n/a") +
      ". It can be wrong and must not be used on its own to make decisions about a person.</div>";
  }
  function open(url) {
    body.className = "text-muted";
    body.textContent = "Loading…";
    setOpen(true);
    fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(render)
      .catch(function () { body.textContent = "Could not load this feedback item."; });
  }
  document.querySelectorAll("tr[data-url]").forEach(function (row) {
    row.addEventListener("click", function () { open(row.dataset.url); });
  });
  document.getElementById("drawerClose").addEventListener("click", function () { setOpen(false); });
  scrim.addEventListener("click", function () { setOpen(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });

  // Dropdown and date filters apply immediately; the search box applies on Enter / the filter button.
  var form = document.getElementById("filterForm");
  ["sentiment", "department", "date_from", "date_to"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el && form) el.addEventListener("change", function () { form.submit(); });
  });
})();
