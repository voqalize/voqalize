// A small stand-in for the site's Bootstrap 5 (tabs, pills, collapses and the
// theme's Carreras menu link) and the few layout rules the adapter reads, so
// the page test runs on saved pages with no network.
(() => {
  const css = `
    .tab-pane { display: none; } .tab-pane.active { display: block; }
    .fade { transition: opacity .12s linear; } .fade:not(.show) { opacity: 0; }
    .collapse:not(.show) { display: none; } .collapsing { height: 0; overflow: hidden; }
    .d-none { display: none !important; }
    @media (min-width: 768px) { .d-md-none { display: none !important; } .d-md-block { display: block !important; } }
    @media (min-width: 992px) { .d-lg-none { display: none !important; } .d-lg-block { display: block !important; } }
    .row { display: flex; flex-wrap: wrap; } .col-md-3 { width: 25%; } .col-md-4 { width: 33%; } .col-md-6 { width: 50%; }
    .col-md-8 { width: 66%; } .col-md-9 { width: 75%; } .col-lg-4 { width: 33%; }
    header.sticky-top { position: sticky; top: 0; height: 100px; background: #000; color: #fff; z-index: 10; }
    .btn-primary { background: rgb(242, 101, 34); color: #fff; }
    iframe { display: block; }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  const log = [];
  const target = (t) => document.querySelector(t.getAttribute("data-bs-target") || t.getAttribute("href"));
  const triggersOf = (pane) => document.querySelectorAll(`[data-bs-target="#${pane.id}"], [href="#${pane.id}"]`);

  function showTab(trigger) {
    const pane = target(trigger);
    if (!pane) return;
    const nav = trigger.closest("[role=tablist], .nav");
    for (const t of nav ? nav.querySelectorAll("[data-bs-toggle]") : []) {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    }
    trigger.classList.add("active");
    trigger.setAttribute("aria-selected", "true");
    for (const p of pane.parentElement.children) if (p.classList.contains("tab-pane")) p.classList.remove("active", "show");
    pane.classList.add("active");
    setTimeout(() => pane.classList.add("show"), 40);
    log.push(["tab", pane.id]);
  }

  function hideCollapse(pane) {
    pane.classList.remove("show");
    for (const t of triggersOf(pane)) {
      t.classList.add("collapsed");
      t.setAttribute("aria-expanded", "false");
    }
  }

  function showCollapse(pane) {
    if (pane.classList.contains("show")) return;
    const parent = pane.getAttribute("data-bs-parent");
    if (parent) for (const o of document.querySelectorAll(`${parent} .collapse.show`)) if (o !== pane) hideCollapse(o);
    pane.classList.remove("collapse");
    pane.classList.add("collapsing");
    setTimeout(() => {
      pane.classList.remove("collapsing");
      pane.classList.add("collapse", "show");
      for (const t of triggersOf(pane)) {
        t.classList.remove("collapsed");
        t.setAttribute("aria-expanded", "true");
      }
    }, 120);
    log.push(["collapse", pane.id]);
  }

  document.addEventListener("click", (e) => {
    const menu = e.target.closest("li.boton-carrera > a");
    if (menu) {
      e.preventDefault();
      const pane = document.getElementById("collapseCarreras");
      if (pane) (pane.classList.contains("show") ? hideCollapse : showCollapse)(pane);
      return;
    }
    const t = e.target.closest("[data-bs-toggle]");
    if (!t) return;
    const kind = t.getAttribute("data-bs-toggle");
    if (kind === "tab" || kind === "pill") {
      e.preventDefault();
      showTab(t);
    } else if (kind === "collapse") {
      e.preventDefault();
      const pane = target(t);
      if (pane) (pane.classList.contains("show") ? hideCollapse : showCollapse)(pane);
    }
  });

  window.bootstrap = {
    Tab: { getOrCreateInstance: (el) => ({ show: () => showTab(el) }) },
    Collapse: { getOrCreateInstance: (el) => ({ show: () => showCollapse(el) }) },
  };
  window.__shim = { log };
})();
