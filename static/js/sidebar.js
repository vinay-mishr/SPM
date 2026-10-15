/* Sidebar flyout menus (e.g. Master → Item / Party / Opening Balance Master).
 * The options open to the right of the sidebar; clicking elsewhere or pressing Esc closes them.
 */
(function () {
  "use strict";

  var groups = document.querySelectorAll("[data-nav-flyout]");
  if (!groups.length) return;

  function closeAll(except) {
    groups.forEach(function (group) {
      if (group !== except && !group.contains(except)) group.open = false;
    });
  }

  /* Place the options panel just to the right of the sidebar, level with the item. */
  function place(group) {
    var panel = group.querySelector(".app-nav__submenu");
    if (!panel || getComputedStyle(panel).position !== "fixed") return; // phones: shown inline
    var item = group.querySelector("summary").getBoundingClientRect();
    var parentGroup = group.parentElement.closest("[data-nav-flyout]");
    var parentPanel = parentGroup && parentGroup.querySelector(".app-nav__submenu");
    var left = parentPanel
      ? parentPanel.getBoundingClientRect().right + 8
      : group.closest(".app-sidebar").getBoundingClientRect().right + 8;
    var top = Math.max(8, Math.min(item.top - 6, window.innerHeight - panel.offsetHeight - 8));
    panel.style.top = top + "px";
    panel.style.left = left + "px";
  }

  groups.forEach(function (group) {
    group.addEventListener("toggle", function () {
      if (group.open) {
        closeAll(group);
        place(group);
      }
    });
  });

  window.addEventListener("resize", function () {
    groups.forEach(function (group) { if (group.open) place(group); });
  });
  document.querySelectorAll(".app-sidebar").forEach(function (sidebar) {
    sidebar.addEventListener("scroll", function () {
      groups.forEach(function (group) { if (group.open) place(group); });
    });
  });

  document.addEventListener("click", function (event) {
    groups.forEach(function (group) {
      if (group.open && !group.contains(event.target)) group.open = false;
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    groups.forEach(function (group) {
      if (group.open) {
        group.open = false;
        group.querySelector("summary").focus();
      }
    });
  });
})();
