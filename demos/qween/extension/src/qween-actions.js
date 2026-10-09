// qween-actions.js — drive www.qween.com from the outside, with no help from
// Qween's developers.
//
// This is the site adapter: the brain sends a Voqalize `ui-command`
// ({command, payload}), and `run(command, payload)` performs it on Qween's own
// page. The page reports back through `start(emit)`, which calls `emit(type,
// payload)` for the brain as a `client-message`. Nothing here renders UI of our
// own except the highlight ring: Qween wants no generative UI, so every command
// lands on a page, section or dialog that Qween already has.
//
// How each command is triggered, and why, is in ../research/site-actions.md.
// Every anchor below is one of:
//   - the router Qween's framework exposes (`window.__reactRouterDataRouter`);
//   - their own stable attributes (`data-pdp-section`, `data-testid`,
//     `aria-label`);
//   - failing those, a button's visible label.
// Tailwind class names are never used as anchors except the FAQ row, which has
// no other handle (noted where it is used).

(function () {
  "use strict";

  if (window.voqalizeQween) return;

  const RING_COLOUR = "#b08d57";
  const RING_MS = 4000;
  const SETTLE_MS = 1200;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  // Qween's animated labels repeat every letter in hidden spans, so innerText
  // reads "ADD TO WISHLIST A A D D …". The first line is the real label.
  const label = (el) =>
    clean(el.getAttribute("aria-label") || (el.innerText || "").split("\n")[0]);

  function button(text, root) {
    return [...(root || document).querySelectorAll("button,[role=button],a")].find(
      (b) => visible(b) && label(b).toUpperCase() === text.toUpperCase(),
    );
  }

  function router() {
    return window.__reactRouterDataRouter || null;
  }

  function dialogOpen() {
    return [...document.querySelectorAll("[role=dialog],[aria-modal=true]")].some(visible);
  }

  // ─── Navigation ───────────────────────────────────────────────────────

  async function navigate(path) {
    const r = router();
    if (!r) {
      // Without the router, the only way to move is a reload, which drops the
      // call. Refuse rather than drop it silently.
      throw new Error("no client-side router on this page");
    }
    await r.navigate(path);
  }

  function query(params) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) {
      if (v === undefined || v === null || v === "") continue;
      for (const one of Array.isArray(v) ? v : [v]) q.append(k, String(one));
    }
    const s = q.toString();
    return s ? `?${s}` : "";
  }

  // ─── The highlight ring ───────────────────────────────────────────────
  // Drawn over the page, never on Qween's own elements, so their styles are
  // untouched. Positioned in document coordinates so it scrolls with the page.

  let ring = null;
  let ringTimer = null;

  function highlight(el) {
    clearHighlight();
    const r = el.getBoundingClientRect();
    ring = document.createElement("div");
    ring.setAttribute("data-voqalize", "highlight");
    Object.assign(ring.style, {
      position: "absolute",
      left: `${r.left + window.scrollX - 8}px`,
      top: `${r.top + window.scrollY - 8}px`,
      width: `${r.width + 16}px`,
      height: `${r.height + 16}px`,
      border: `2px solid ${RING_COLOUR}`,
      pointerEvents: "none",
      zIndex: "2147483000",
      opacity: "0",
      transition: "opacity 400ms ease",
    });
    document.body.appendChild(ring);
    requestAnimationFrame(() => {
      if (ring) ring.style.opacity = "1";
    });
    ringTimer = setTimeout(clearHighlight, RING_MS);
  }

  function clearHighlight() {
    clearTimeout(ringTimer);
    if (ring) ring.remove();
    ring = null;
  }

  async function reveal(el, { ring: withRing = true } = {}) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(700);
    if (withRing) highlight(el);
  }

  // ─── Product page ─────────────────────────────────────────────────────

  function section(name) {
    return document.querySelector(`[data-pdp-section="${name}"]`);
  }

  // Some sections mount their content only once scrolled into view (the
  // composition block is empty until then), so a section is scrolled to first
  // and searched second.
  async function inSection(name) {
    const s = section(name);
    if (!s) throw new Error(`no ${name} section on this page`);
    s.scrollIntoView({ block: "center" });
    await sleep(600);
    return s;
  }

  // The assurances under READ MORE, in the order the page shows them.
  const ASSURANCES = ["natural_stones", "igi_certified", "stone_value", "buyback_exchange"];

  const MODALS = {
    price_breakup: async () => document.querySelector("[data-testid=pdp-price-breakup-trigger]"),
    size_guide: async () => button("CHOOSE YOUR SIZE"),
    delivery: async () => button("DELIVERY/STORE PICKUP"),
    try_on: async () => button("TRY IT ON"),
    gemstone_details: async () => button("VIEW MORE", await inSection("material_specs")),
    concierge: async () => document.querySelector('button[aria-label="CONCIERGE"]'),
  };

  async function openModal({ modal, which }) {
    let el;
    if (modal === "assurance") {
      const s = await inSection("qween_difference");
      const reads = [...s.querySelectorAll("button,[role=button],a")].filter(
        (b) => visible(b) && label(b) === "READ MORE",
      );
      el = reads[ASSURANCES.indexOf(which)];
    } else if (MODALS[modal]) {
      el = await MODALS[modal]();
    } else {
      throw new Error(`unknown modal ${modal}`);
    }
    if (!el) throw new Error(`${modal} is not on this page`);
    el.click();
  }

  async function closeModal() {
    const exit3d = document.querySelector('[aria-label="Exit 3D View"]');
    if (exit3d && visible(exit3d)) exit3d.click();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  }

  // The toggle ignores a click made while the gallery is still scrolling back
  // into view, so jump, wait, then click.
  async function view3d() {
    window.scrollTo({ top: 0 });
    await sleep(600);
    const tag = [...section("gallery").querySelectorAll("span")].find(
      (s) => visible(s) && clean(s.innerText) === "3D",
    );
    const toggle = tag && tag.closest(".cursor-pointer");
    if (!toggle) throw new Error("this piece has no 3D view");
    toggle.click();
  }

  async function selectMetal({ name }) {
    const swatch = [...section("gallery").querySelectorAll("button")].find(
      (b) => label(b).toUpperCase() === name.toUpperCase(),
    );
    if (!swatch) throw new Error(`no ${name} swatch on this piece`);
    swatch.click();
  }

  async function showSection({ section: name, tab }) {
    const s = await inSection(name);
    if (tab) {
      const t = button(tab, s);
      if (t) t.click();
    }
    await reveal(s);
  }

  async function openFaq({ topic }) {
    const s = await inSection("styling_tips");
    const title = [...s.querySelectorAll("span")].find(
      (e) => e.children.length === 0 && clean(e.innerText) === topic,
    );
    // The FAQ row has no id, role or aria attribute; `.group.cursor-pointer` is
    // the only handle on the element that owns the click.
    const row = title && title.closest(".group.cursor-pointer");
    if (!row) throw new Error(`no FAQ called ${topic}`);
    row.click();
    await sleep(500);
    await reveal(row.parentElement);
  }

  // ─── Listing pages ────────────────────────────────────────────────────

  function cards() {
    return [...document.querySelectorAll("[data-testid=product-card]")].filter(visible);
  }

  function cardLink(card) {
    return card.matches("a[href]") ? card : card.querySelector('a[href*="/product/"]');
  }

  async function highlightCard({ index }) {
    const card = cards()[index - 1];
    if (!card) throw new Error(`there is no card ${index} on screen`);
    await reveal(card);
  }

  // ─── The command table ────────────────────────────────────────────────
  // Keys are the brain's Action names (snake_case of the class), payloads its
  // fields.

  const COMMANDS = {
    open_catalog: ({ params }) => navigate(`/catalog${query(params)}`),
    open_category: ({ id, params }) => navigate(`/categories/${id}${query(params)}`),
    open_collection: ({ slug, plp }) => navigate(`/collection/${plp ? "plp/" : ""}${slug}`),
    open_product: ({ slug, variant_code }) =>
      navigate(`/product/${slug}${query({ variantCode: variant_code })}`),
    open_page: ({ path }) => navigate(path),
    select_metal: selectMetal,
    show_section: showSection,
    open_modal: openModal,
    open_faq: openFaq,
    view_3d: view3d,
    close_modal: closeModal,
    highlight_card: highlightCard,
  };

  // Never throws: a failed command is reported, so the brain can say so, and
  // the call carries on.
  async function run(command, payload) {
    const fn = COMMANDS[command];
    if (!fn) return { ok: false, error: `unknown command ${command}` };
    try {
      await fn(payload || {});
      return { ok: true };
    } catch (e) {
      return { ok: false, error: String((e && e.message) || e) };
    }
  }

  // ─── What the shopper is looking at ───────────────────────────────────

  function kindOf(pathname) {
    if (pathname === "/") return "home";
    if (pathname.startsWith("/product/")) return "product";
    if (pathname === "/catalog") return "catalog";
    if (pathname.startsWith("/categories/")) return "category";
    if (pathname.startsWith("/collection/")) return "collection";
    return "page";
  }

  // The open variant's composition, from the route's own loader data: the
  // figures the page's composition block prints under its METAL, DIAMOND and
  // GEMSTONE tabs. Read from data, not the DOM, because that block is empty
  // until it is scrolled into view, and its tabs all render at once with
  // nothing to say which figures are whose. Since the 2026-10 refresh the
  // diamond count and carat are printed nowhere else: VIEW MORE opens the
  // gemstones only, and KNOW YOUR DIAMOND is the diamond guide.
  function composition(variantCode) {
    try {
      const data = router().state.loaderData["routes/product.$productSlug"];
      const variants = data.product.variants;
      const v = variants.find((x) => x.variantCode === variantCode) || variants[0];
      const parts = [];
      const c = v.variantComponents;
      const size = [
        c.weight && `gross weight ${c.weight}`,
        c.height && `height ${c.height}`,
        c.width && `width ${c.width}`,
      ].filter(Boolean);
      if (size.length) parts.push(size.join(", ") + ".");
      for (const comp of c.components || []) {
        const each = (comp.details || []).map((d) =>
          comp.type === "METAL"
            ? `${d.purity} ${d.colour}, ${d.weight}`
            : comp.type === "DIAMOND"
              ? `${d.quantity} ${d.shape}, ${d.quality}, ${d.weight} in all`
              : `${d.quantity} ${d.name} (${d.shape}), ${d.weight} in all`,
        );
        if (!each.length) continue;
        parts.push(`${comp.type}: ${each.join("; ")}.${comp.origin ? " " + clean(comp.origin) : ""}`);
      }
      return parts.join(" ") || null;
    } catch {
      // Qween's data is theirs and its shape may change; the page still reports.
      return null;
    }
  }

  function context() {
    const { pathname, search } = window.location;
    const params = {};
    for (const [k, v] of new URLSearchParams(search)) (params[k] ||= []).push(v);
    const ctx = { path: pathname + search, kind: kindOf(pathname), params, dialog_open: dialogOpen() };
    if (ctx.kind === "product") {
      ctx.slug = decodeURIComponent(pathname.split("/")[2] || "");
      ctx.variant_code = (params.variantCode || [])[0] || null;
      const h1 = document.querySelector("h1");
      ctx.name = h1 ? clean(h1.innerText) : null;
      ctx.composition = composition(ctx.variant_code);
    } else {
      ctx.cards = cards().map((c, i) => {
        const a = cardLink(c);
        const href = a ? a.getAttribute("href") : "";
        return {
          n: i + 1,
          slug: (href.match(/\/product\/([^/?#]+)/) || [])[1] || null,
          text: clean(c.innerText).slice(0, 120),
        };
      });
    }
    return ctx;
  }

  // ─── Keeping the call alive ───────────────────────────────────────────
  // The "YOU MAY ALSO LIKE" cards on a product page do a full reload, which
  // would drop the call. Route them through the router instead.

  function keepRecommendationsClientSide(e) {
    const a = e.target.closest && e.target.closest('[data-pdp-section="recommended_products"] a[href^="/"]');
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    if (!router()) return;
    e.preventDefault();
    e.stopPropagation();
    router().navigate(a.getAttribute("href"));
  }

  // A dialog's text goes to the brain whenever one opens, whoever opened it, so
  // the brain speaks the price breakup's own figures instead of recalling them.
  function watchDialogs(emit) {
    let open = null;
    const check = () => {
      const d = [...document.querySelectorAll("[role=dialog],[aria-modal=true]")].find(visible);
      if (d && d !== open) {
        open = d;
        setTimeout(() => {
          const text = (d.innerText || "").split("\n").map(clean).filter(Boolean);
          emit("dialog_opened", { title: text[0] || null, text: text.join("\n").slice(0, 4000) });
        }, 400); // the dialog fills after it mounts
      } else if (!d && open) {
        open = null;
        emit("dialog_closed", {});
      }
    };
    let queued = false;
    const mo = new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        check();
      });
    });
    mo.observe(document.body, { childList: true, subtree: true });
    return () => mo.disconnect();
  }

  let stop = null;

  function start(emit) {
    if (stop) stop();
    let last = null;
    // A report waits out SETTLE_MS; one still waiting when this session stops
    // must not emit into the next one.
    let live = true;
    const report = async () => {
      const path = window.location.pathname + window.location.search;
      if (path === last) return;
      last = path;
      clearHighlight();
      await sleep(SETTLE_MS); // listing grids fill after the route resolves
      if (live) emit("page_changed", context());
    };
    const r = router();
    const unsubscribe = r ? r.subscribe(report) : () => {};
    const unwatch = watchDialogs(emit);
    document.addEventListener("click", keepRecommendationsClientSide, true);
    report();
    stop = () => {
      live = false;
      unsubscribe();
      unwatch();
      document.removeEventListener("click", keepRecommendationsClientSide, true);
      stop = null;
    };
    return stop;
  }

  window.voqalizeQween = { run, context, start, commands: Object.keys(COMMANDS) };
})();
