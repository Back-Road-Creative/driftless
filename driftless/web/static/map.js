// Progressive enhancement for the method map (`/map`, method_map.html). The page
// is complete without this file: every shape is an <a>, every tie is spelled
// out in words below the SVG. This only toggles classes/`hidden` on markup
// already in the DOM, plus the filter state in the URL -- no fetch, no store.
(function () {
  "use strict";

  var svg = document.querySelector("svg[aria-label]");
  if (!svg) return;
  var nodes = svg.querySelectorAll(".node");
  var edges = svg.querySelectorAll(".edge");
  var pinned = null;
  // The slice the SERVER drew and the overview's address: the script never
  // decides what the page shows, only how to get back.
  var slice = svg.dataset.slice || "overview";
  var overviewHref = svg.dataset.overview || "";

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

  function setPanel(id) {
    document.querySelectorAll("[data-panel-for]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-panel-for") !== id;
    });
  }

  function pin(id) {
    pinned = pinned === id ? null : id;
    highlight(pinned);
    setPanel(pinned);
  }

  function nodeOf(target) {
    var group = target.closest && target.closest(".node");
    return group ? group.dataset.node : null;
  }

  // The panel follows hover/focus; a pin wins over a stray mouseover.
  function hoverIn(event) {
    var id = !pinned && nodeOf(event.target);
    if (id) {
      highlight(id);
      setPanel(id);
    }
  }
  function hoverOut(event) {
    if (!pinned && nodeOf(event.target)) {
      highlight(null);
      setPanel(null);
    }
  }

  svg.addEventListener("mouseover", hoverIn);
  svg.addEventListener("mouseout", hoverOut);
  svg.addEventListener("focusin", hoverIn);
  svg.addEventListener("focusout", hoverOut);
  // No click handler: a shape is an <a href>; cancelling it would swallow
  // Ctrl/Cmd/Shift/middle-click too.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" || event.key === "Esc") {
      pinned = null;
      highlight(null);
      setPanel(null);
      // Back out one level, to the page's own overview link.
      if (slice !== "overview" && overviewHref) window.location.assign(overviewHref);
    }
    if (event.key === " " || event.key === "Spacebar") {
      var focused = nodeOf(event.target);
      if (focused) {
        event.preventDefault();
        pin(focused);
      }
    }
  });

  // Chips and search narrow which nodes show; a hidden node's ties hide too.
  var chips = document.querySelectorAll(".map-filter");
  var flowOnly = document.getElementById("map-flow-only");
  var search = document.getElementById("map-search");
  var dims = ["kind", "group", "area", "family"];
  var countEl = document.querySelector(".map-count");
  var totalNodes = (countEl && countEl.textContent.match(/of (\d+)/)) || [];
  totalNodes = totalNodes[1] || "";

  function attrOf(node, dim) {
    if (dim === "kind") return node.dataset.kind || "";
    var shape = node.querySelector(".node-shape");
    return (shape && shape.dataset[dim]) || "";
  }

  // map.css shows labels once a filter narrows to a legible handful (~60).
  var NARROW_THRESHOLD = 60;

  // A filtered map is a shareable URL: state round-trips through the query
  // string, leaving as_of/project alone.
  function syncURL() {
    var p = new URLSearchParams(location.search);
    dims.forEach(function (d) {
      p.delete(d);
    });
    chips.forEach(function (c) {
      if (c.checked) p.append(c.dataset.dim, c.value);
    });
    var term = search ? search.value.trim() : "";
    if (term) p.set("q", term);
    else p.delete("q");
    if (flowOnly && flowOnly.checked) p.set("flow", "1");
    else p.delete("flow");
    var qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }

  function restoreFromURL() {
    var p = new URLSearchParams(location.search);
    chips.forEach(function (c) {
      if (p.getAll(c.dataset.dim).indexOf(c.value) !== -1) c.checked = true;
    });
    if (search && p.has("q")) search.value = p.get("q");
    if (flowOnly && p.get("flow") === "1") flowOnly.checked = true;
    if (flowOnly) svg.classList.toggle("map-flow-only", flowOnly.checked);
  }

  function applyFilters() {
    var byDim = {};
    chips.forEach(function (chip) {
      if (chip.checked) {
        (byDim[chip.dataset.dim] = byDim[chip.dataset.dim] || []).push(chip.value);
      }
    });
    var term = search ? search.value.trim().toLowerCase() : "";
    var hidden = {};
    var visibleCount = 0;
    nodes.forEach(function (node) {
      var visible = dims.every(function (dim) {
        var wanted = byDim[dim];
        return !wanted || wanted.indexOf(attrOf(node, dim)) !== -1;
      });
      if (visible && term) {
        visible = (node.dataset.label || "").toLowerCase().indexOf(term) !== -1;
      }
      node.classList.toggle("node-hidden", !visible);
      if (visible) {
        visibleCount += 1;
      } else {
        hidden[node.dataset.node] = true;
      }
    });
    var visibleEdges = 0;
    edges.forEach(function (edge) {
      var gone = !!(hidden[edge.dataset.from] || hidden[edge.dataset.to]);
      edge.classList.toggle("edge-hidden", gone);
      if (!gone) visibleEdges += 1;
    });
    svg.classList.toggle("map-narrow", slice !== "all" || visibleCount <= NARROW_THRESHOLD);
    if (countEl) {
      countEl.textContent =
        "Showing " + visibleCount + " of " + totalNodes + " nodes; " + visibleEdges + " relevant ties.";
    }
    syncURL();
  }

  chips.forEach(function (chip) {
    chip.addEventListener("change", applyFilters);
  });
  if (search) search.addEventListener("input", applyFilters);
  if (flowOnly) {
    flowOnly.addEventListener("change", function () {
      svg.classList.toggle("map-flow-only", flowOnly.checked);
      syncURL();
    });
  }

  var reset = document.getElementById("map-reset");
  if (reset) {
    reset.addEventListener("click", function () {
      chips.forEach(function (chip) {
        chip.checked = false;
      });
      if (search) search.value = "";
      if (flowOnly) {
        flowOnly.checked = false;
        svg.classList.remove("map-flow-only");
      }
      pinned = null;
      highlight(null);
      setPanel(null);
      applyFilters();
    });
  }

  restoreFromURL();
  applyFilters();

  // Fit / 100% / +/- (M.1): overrides the column-width default with an inline
  // pixel width; the floor is the SAME `--map-floor` method_map.html sets.
  var ZOOM_STEP = 1.25;
  var zoomButtons = document.querySelectorAll(".map-zoom [data-zoom]");

  function nativeWidth() {
    return parseFloat(svg.dataset.width) || svg.getBoundingClientRect().width;
  }

  function floorWidth() {
    return parseFloat(svg.style.getPropertyValue("--map-floor")) || 0;
  }

  function setWidth(px) {
    svg.style.width = Math.max(px, floorWidth()) + "px";
  }

  zoomButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var zoom = button.dataset.zoom;
      if (zoom === "fit") {
        svg.style.width = "";
      } else if (zoom === "100") {
        setWidth(nativeWidth());
      } else if (zoom === "in") {
        setWidth(svg.getBoundingClientRect().width * ZOOM_STEP);
      } else if (zoom === "out") {
        setWidth(svg.getBoundingClientRect().width / ZOOM_STEP);
      }
    });
  });
})();
