// Progressive enhancement for driftless's server-rendered pages.
//
// Deliberately tiny and self-authored — no CDN, no build step, no external
// dependency to vendor and audit. Every page works without it: forms POST and
// the server re-renders the whole page. With it, a form marked data-swap posts
// in the background and swaps just the fragment named by its data-target: the
// server still answers with the FULL re-rendered page (following the same 303
// a no-JS submit follows), and the fresh copy of the target is lifted out of
// that response — never dumped into it whole. After a swap, focus moves to the
// swapped region and a polite live region says what happened, so a keyboard or
// screen-reader user is not stranded on a Save button that no longer exists;
// a fetch that fails outright (offline, DNS) is surfaced in the same region,
// so the page can never stay silently identical to someone who just pressed
// Save. A data-swap form with no data-target, or a response that is a
// different page entirely (the designed error shell), falls back to showing
// the whole document the server sent. That is the whole contract; there is
// intentionally nothing else here.
(function () {
  "use strict";

  // The one polite live region, created on load so it exists BEFORE its first
  // message: assistive tech reliably announces changes only in a region that
  // was already in the tree.
  function statusRegion() {
    var region = document.getElementById("swap-status");
    if (!region) {
      region = document.createElement("div");
      region.id = "swap-status";
      region.setAttribute("role", "status");
      region.className = "sr-only";
      document.body.appendChild(region);
    }
    return region;
  }

  function announce(message, visible) {
    var region = statusRegion();
    region.className = visible ? "swap-error" : "sr-only";
    region.textContent = message;
  }

  function swap(form) {
    var selector = form.getAttribute("data-target");
    var target = selector ? document.querySelector(selector) : null;
    var body = new URLSearchParams(new FormData(form));
    fetch(form.action, {
      method: (form.method || "post").toUpperCase(),
      headers: { "X-Requested-With": "driftless" },
      body: body,
    })
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var fresh =
          target && new DOMParser().parseFromString(html, "text/html").querySelector(selector);
        if (target && fresh) {
          target.innerHTML = fresh.innerHTML;
          bind(target);
          target.setAttribute("tabindex", "-1"); // focusable by script, not a tab stop
          target.focus();
          announce("Saved. The section under focus has been updated.", false);
        } else {
          document.open();
          document.write(html);
          document.close();
        }
      })
      .catch(function () {
        announce(
          "That was NOT saved: the request never reached the server. " +
            "Check the connection and submit again.",
          true
        );
      });
  }

  function bind(root) {
    var forms = root.querySelectorAll("form[data-swap]");
    for (var i = 0; i < forms.length; i++) {
      forms[i].addEventListener("submit", function (event) {
        event.preventDefault();
        swap(event.currentTarget);
      });
    }
  }

  // Count-up on the home dashboard's KPI tiles (data-countup): the server-
  // rendered text is already the complete, final figure -- this only animates
  // 0 -> that same text on load, and always lands on the EXACT original string
  // (never a re-formatted approximation), so JS-off and JS-on end states are
  // identical. A tile whose text carries no digits (e.g. "n/a") is left alone.
  var COUNTUP_MS = 600;

  function countUp(el) {
    var text = el.textContent;
    var parts = /^(\D*)([\d,]*\.?\d*)(\D*)$/.exec(text);
    if (!parts || !parts[2]) {
      return;
    }
    var prefix = parts[1], digits = parts[2], suffix = parts[3];
    var target = parseFloat(digits.replace(/,/g, ""));
    if (!isFinite(target)) {
      return;
    }
    var decimals = digits.indexOf(".") === -1 ? 0 : digits.split(".")[1].length;
    var start = null;
    function frame(now) {
      if (start === null) {
        start = now;
      }
      var progress = Math.min((now - start) / COUNTUP_MS, 1);
      if (progress < 1) {
        el.textContent = prefix + (target * progress).toFixed(decimals) + suffix;
        window.requestAnimationFrame(frame);
      } else {
        el.textContent = text; // land on the exact rendered string
      }
    }
    window.requestAnimationFrame(frame);
  }

  function countUpAll(root) {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    var tiles = root.querySelectorAll("[data-countup]");
    for (var i = 0; i < tiles.length; i++) {
      countUp(tiles[i]);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    statusRegion();
    bind(document);
    countUpAll(document);
  });
})();
