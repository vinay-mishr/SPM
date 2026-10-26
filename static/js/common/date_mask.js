/* Shared British date format (dd/mm/yyyy) helpers + input auto-mask, plus a
   clickable calendar-picker button wired onto every [data-date-mask] input.
   Backend DateFields already accept "%d/%m/%Y", so this is display-only. */
(function () {
  "use strict";

  function toDisplay(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function toIso(dmy) {
    var p = String(dmy || "").split("/");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : dmy;
  }

  function isValidDmy(value) {
    return /^\d{2}\/\d{2}\/\d{4}$/.test(value || "");
  }

  function mask(input) {
    input.addEventListener("input", function () {
      var digits = input.value.replace(/\D/g, "").slice(0, 8);
      var out = digits.slice(0, 2);
      if (digits.length > 2) out += "/" + digits.slice(2, 4);
      if (digits.length > 4) out += "/" + digits.slice(4, 8);
      input.value = out;
    });
    addPicker(input);
  }

  /* --- Calendar picker -------------------------------------------------
     The calendar icon lives INSIDE the input's own border, at its right
     edge -- not as a separate button outside it. A thin wrapper (sized to
     match the input's own original rendered width, so layout footprint
     doesn't change) holds: the input itself (with its right padding bumped
     just enough to clear the icon), a decorative icon glyph, and an
     invisible native <input type="date"> positioned only over that icon's
     small zone -- clicking there opens the browser's real date picker.
     Typing and clicking elsewhere in the field is completely unaffected. */

  var ICON_ZONE = 20; // px of extra right padding reserved for the icon

  var CALENDAR_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">'
    + '<rect x="3" y="5" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="2.6"/>'
    + '<path d="M3 9.5h18" stroke="currentColor" stroke-width="2.6"/>'
    + '<path d="M8 3v4M16 3v4" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>'
    + '</svg>';

  var stylesInjected = false;
  function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    var style = document.createElement("style");
    style.textContent =
      ".dm-field { position: relative; display: inline-block; vertical-align: middle; max-width: 100%; }\n" +
      ".dm-field > input[data-date-mask] { display: block; width: 100%; height: 100%; box-sizing: border-box; }\n" +
      ".dm-icon { position: absolute !important; top: 0 !important; right: 0 !important; width: " + ICON_ZONE + "px !important; height: 100% !important;\n" +
      "  display: flex; align-items: center; justify-content: center; color: #1d4ed8; pointer-events: none; }\n" +
      ".dm-native { position: absolute !important; top: 0 !important; right: 0 !important; width: " + ICON_ZONE + "px !important; height: 100% !important;\n" +
      "  opacity: 0; border: 0; padding: 0 !important; margin: 0 !important; cursor: pointer; }\n" +
      ".dm-field > input[data-date-mask][disabled] ~ .dm-native, .dm-field > input[data-date-mask][readonly] ~ .dm-native { pointer-events: none; cursor: default; }\n";
    document.head.appendChild(style);
  }

  function addPicker(input) {
    if (input.dataset.dmWired === "1") return;
    input.dataset.dmWired = "1";
    injectStyles();

    var rect = input.getBoundingClientRect();
    var measuredWidth = rect.width;
    var measuredHeight = rect.height;
    var basePaddingRight = parseFloat(getComputedStyle(input).paddingRight) || 0;

    var wrap = document.createElement("span");
    wrap.className = "dm-field";
    if (measuredWidth > 0) wrap.style.width = measuredWidth + "px";
    if (measuredHeight > 0) wrap.style.height = measuredHeight + "px";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    input.style.paddingRight = (basePaddingRight + ICON_ZONE) + "px";

    var icon = document.createElement("span");
    icon.className = "dm-icon";
    icon.innerHTML = CALENDAR_SVG;
    wrap.appendChild(icon);

    var native = document.createElement("input");
    native.type = "date";
    native.className = "dm-native";
    native.setAttribute("aria-label", "Choose date");
    wrap.appendChild(native);

    function syncNativeFromInput() {
      native.value = isValidDmy(input.value) ? toIso(input.value) : "";
    }

    function openPicker() {
      if (input.disabled || input.readOnly) return;
      syncNativeFromInput();
      if (typeof native.showPicker === "function") {
        try { native.showPicker(); } catch (err) { /* ignore */ }
      }
    }

    native.addEventListener("mousedown", function () {
      if (input.disabled || input.readOnly) return;
      syncNativeFromInput();
    });

    native.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        openPicker();
      }
    });

    native.addEventListener("change", function () {
      if (!native.value) return;
      input.value = toDisplay(native.value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-date-mask]").forEach(mask);
  });

  window.DateMask = { toDisplay: toDisplay, toIso: toIso, attach: mask };
})();
