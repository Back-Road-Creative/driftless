// Progressive enhancement for the glossary (`/glossary`, glossary.html). The
// page is complete and correct without this file: every term is already
// rendered, grouped and cross-linked in the DOM. This only toggles the
// `hidden` attribute on the `.glossary-entry` markup the template emits, off
// its own `data-glossary-term` attribute -- no fetch, no store, no second
// source of truth for the term list.
(function () {
  "use strict";

  var input = document.querySelector("[data-glossary-filter]");
  var groups = document.querySelector("[data-glossary-groups]");
  var count = document.querySelector("[data-glossary-count]");
  if (!input || !groups) return;

  var entries = groups.querySelectorAll(".glossary-entry");

  function apply() {
    var needle = input.value.trim().toLowerCase();
    var shown = 0;
    entries.forEach(function (entry) {
      var term = entry.getAttribute("data-glossary-term") || "";
      var match = !needle || term.indexOf(needle) !== -1;
      entry.hidden = !match;
      if (match) shown += 1;
    });
    if (count) {
      count.hidden = !needle;
      count.textContent = needle
        ? shown + " of " + entries.length + " terms match “" + input.value + "”"
        : "";
    }
  }

  input.addEventListener("input", apply);
})();
