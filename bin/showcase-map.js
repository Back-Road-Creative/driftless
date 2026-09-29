// The ONE script bin/driftless-showcase.py re-admits to the exported showcase,
// and the only one any exported page carries. Read-only means "cannot write",
// not "cannot interact": this reads the SVG the server already rendered and
// toggles classes map.css already styles.
//
// It makes NO network request (no fetch, no XMLHttpRequest, no WebSocket), uses
// NO storage (no localStorage, no sessionStorage, no indexedDB, no cookie),
// submits nothing, navigates nowhere, and evaluates no string as code. It reads
// exactly one thing off the address -- the #node- a link from another exported
// page names -- and writes none. Delete the file and the map pages degrade to
// the static reading they had before: labels on hover via map.css alone, the
// full node/tie lists below the drawing, and that same #node- landing on the
// node's own entry in those lists, which is what carries the id.
(function () {
  "use strict";

  var svg = document.querySelector("svg[aria-label]");
  if (!svg) return;
  var nodes = svg.querySelectorAll(".node");
  var edges = svg.querySelectorAll(".edge");
  var pinned = null;

  // One node and its ties lit; everything else washed back. Exactly the
  // `.map-active` / `.edge-lit` / `.node-lit` vocabulary map.css already owns.
  function highlight(id) {
    svg.classList.toggle("map-active", !!id);
    var lit = {};
    if (id) lit[id] = true;
    edges.forEach(function (edge) {
      var tie = !!id && (edge.dataset.from === id || edge.dataset.to === id);
      edge.classList.toggle("edge-lit", tie);
      if (tie) {
        lit[edge.dataset.from] = true;
        lit[edge.dataset.to] = true;
      }
    });
    nodes.forEach(function (node) {
      node.classList.toggle("node-lit", !!lit[node.dataset.node]);
    });
  }

  // The per-node summaries the exporter already ships, hidden in the markup.
  function setPanel(id) {
    document.querySelectorAll("[data-panel-for]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-panel-for") !== id;
    });
  }

  function nodeOf(target) {
    var group = target.closest && target.closest(".node");
    return group ? group.dataset.node : null;
  }

  function pin(id) {
    pinned = pinned === id ? null : id;
    highlight(pinned);
    setPanel(pinned);
  }

  // The export strips the <a> each shape carried in the live app, so the shape
  // itself becomes the focusable thing -- otherwise "on keyboard focus" is a
  // promise the exported page cannot keep.
  nodes.forEach(function (node) {
    node.setAttribute("tabindex", "0");
  });

  function hoverIn(event) {
    var id = !pinned && nodeOf(event.target);
    if (id) highlight(id);
  }
  function hoverOut(event) {
    if (!pinned && nodeOf(event.target)) highlight(null);
  }

  svg.addEventListener("mouseover", hoverIn);
  svg.addEventListener("mouseout", hoverOut);
  svg.addEventListener("focusin", hoverIn);
  svg.addEventListener("focusout", hoverOut);
  svg.addEventListener("click", function (event) {
    var id = nodeOf(event.target);
    if (id) pin(id);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" || event.key === "Esc") {
      pinned = null;
      highlight(null);
      setPanel(null);
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    var id = nodeOf(event.target);
    if (!id) return;
    event.preventDefault();
    pin(id);
  });

  // "See it on the map" from a process, technique or artifact page arrives here as
  // #node-<node id>, and the lists below the drawing carry that id on the node's own
  // entry -- so the link lands somewhere readable whether or not this file runs, and
  // where it does, the shape and its ties are lit too. An unknown id pins nothing
  // rather than washing the whole map back with nothing to show for it.
  var HASH_PREFIX = "#node-";

  function askedFor() {
    var hash = location.hash;
    if (hash.slice(0, HASH_PREFIX.length) !== HASH_PREFIX) return null;
    var wanted = decodeURIComponent(hash.slice(HASH_PREFIX.length));
    var known = null;
    nodes.forEach(function (node) {
      if (node.dataset.node === wanted) known = wanted;
    });
    return known;
  }

  function openAskedFor() {
    var id = askedFor();
    if (!id) return;
    pinned = null; // pin() toggles, so arriving at the node already pinned keeps it open
    pin(id);
  }

  openAskedFor();
  window.addEventListener("hashchange", openAskedFor);
})();
