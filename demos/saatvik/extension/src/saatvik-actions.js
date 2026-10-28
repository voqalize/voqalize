// saatvik-actions.js — drive www.saatvikgroup.com from the outside, with no
// help from Saatvik's developers.
//
// This is the site adapter: the brain sends a Voqalize `ui-command`
// ({command, payload}), and `run(command, payload)` performs it on Saatvik's
// own page. The page reports back through `start(emit)`, which calls
// `emit(event, payload)` for the brain. The PDF viewer and the lead brief are
// ours and live beside the widget (`pdf-viewer.ts`, `widget.ts`); everything
// here lands on a page, section, accordion or form Saatvik already has.
//
// Every anchor below is one of:
//   - the router their framework exposes (`window.next.router`);
//   - their own stable ids (`#calc-units`, `#calc-state`, `#calc-tariff`);
//   - a form field's placeholder, a select's first option, a button's visible
//     label or `aria-*` attribute.
// Their utility class names are never used as anchors except where noted.

(function () {
  "use strict";

  if (window.voqalizeSaatvik) return;

  // The demo must not send real enquiries to Saatvik's sales inbox. While this
  // is true, SUBMIT on any enquiry form is reported to the brain and then
  // stopped, with a note beside the button. Set it to false when Saatvik wants
  // the agent's enquiries to reach them.
  const DEMO_BLOCK_SUBMIT = true;

  // Saatvik's own orange, read off their buttons.
  const RING_COLOUR = "#EA7124";
  const RING_MS = 5000;
  const SETTLE_MS = 600;
  const WAIT_MS = 8000;
  /** Caps on what goes to the brain, so one page cannot flood its context. */
  const MAX_HEADINGS = 60;
  const MAX_FAQS = 40;
  const MAX_DEALERS = 12;
  const MAX_RESULT_CHARS = 1500;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  /** For matching what the brain said against what the page shows: case,
   *  spacing, `&`/`and`, curly quotes and dashes do not count. */
  const norm = (s) =>
    clean(String(s || ""))
      .toLowerCase()
      .replace(/[‘’]/g, "'")
      .replace(/[“”]/g, '"')
      .replace(/[‐-―]/g, "-")
      .replace(/\s*&\s*/g, " and ")
      .replace(/[.:?!]+$/, "")
      .trim();
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  async function waitFor(fn, ms = WAIT_MS) {
    const until = Date.now() + ms;
    for (;;) {
      const v = fn();
      if (v) return v;
      if (Date.now() > until) return null;
      await sleep(100);
    }
  }

  function main() {
    return document.querySelector("main") || document.body;
  }

  // ─── Their page, less their chat ──────────────────────────────────────
  // Sunny replaces Saatvik's chat launcher, so it is hidden for as long as the
  // extension runs. Their WhatsApp button sits in the corner the widget takes;
  // it moves to the other corner rather than going away.

  function styleThePage() {
    if (document.querySelector("style[data-voqalize=saatvik]")) return;
    const style = document.createElement("style");
    style.setAttribute("data-voqalize", "saatvik");
    style.textContent = `
      #club21-chat-button, #club21-chat-widget, #club21-chat-iframe { display: none !important; }
      div.fixed:has(> button[aria-label="Chat on WhatsApp"]),
      div.fixed:has(> * > button[aria-label="Chat on WhatsApp"]) {
        right: auto !important; left: 24px !important; align-items: flex-start !important;
      }
      @keyframes voqalize-ring {
        0%, 100% { box-shadow: 0 0 0 0 rgba(234, 113, 36, 0.45); }
        50% { box-shadow: 0 0 0 8px rgba(234, 113, 36, 0); }
      }
      @keyframes voqalize-toast { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    `;
    document.head.appendChild(style);
  }

  // ─── The highlight ring ───────────────────────────────────────────────
  // Drawn over the page, never on Saatvik's own elements, so their styles are
  // untouched. Positioned in document coordinates so it scrolls with the page.

  let rings = [];
  let ringTimer = null;

  function rectOf(els) {
    const rs = els.filter(visible).map((el) => el.getBoundingClientRect());
    if (!rs.length) return null;
    return {
      left: Math.min(...rs.map((r) => r.left)),
      top: Math.min(...rs.map((r) => r.top)),
      right: Math.max(...rs.map((r) => r.right)),
      bottom: Math.max(...rs.map((r) => r.bottom)),
    };
  }

  /** Ring each group: a group is one element, or several ringed as one box. */
  function highlight(...groups) {
    clearHighlight();
    for (const group of groups) {
      const r = rectOf(Array.isArray(group) ? group : [group]);
      if (!r) continue;
      const ring = document.createElement("div");
      ring.setAttribute("data-voqalize", "highlight");
      Object.assign(ring.style, {
        position: "absolute",
        left: `${r.left + window.scrollX - 6}px`,
        top: `${r.top + window.scrollY - 6}px`,
        width: `${r.right - r.left + 12}px`,
        height: `${r.bottom - r.top + 12}px`,
        border: `2px solid ${RING_COLOUR}`,
        borderRadius: "6px",
        pointerEvents: "none",
        zIndex: "2147483000",
        opacity: "0",
        transition: "opacity 300ms ease",
        animation: "voqalize-ring 1.4s ease-in-out 3",
      });
      document.body.appendChild(ring);
      rings.push(ring);
    }
    requestAnimationFrame(() => rings.forEach((ring) => (ring.style.opacity = "1")));
    ringTimer = setTimeout(clearHighlight, RING_MS);
  }

  function clearHighlight() {
    clearTimeout(ringTimer);
    rings.forEach((ring) => ring.remove());
    rings = [];
  }

  /** The height of their fixed header, which a scroll to the top of anything
   *  has to clear. */
  function headerHeight() {
    const h = document.querySelector("header");
    if (!h) return 0;
    const pos = getComputedStyle(h).position;
    return pos === "fixed" || pos === "sticky" ? h.getBoundingClientRect().height : 0;
  }

  async function scrollToTop(el) {
    const top = el.getBoundingClientRect().top + window.scrollY - headerHeight() - 24;
    window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
    await sleep(SETTLE_MS + 200);
  }

  async function scrollToCentre(el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(SETTLE_MS + 200);
  }

  // ─── Navigation ───────────────────────────────────────────────────────

  function samePath(a, b) {
    const strip = (p) => (p || "/").replace(/\/+$/, "") || "/";
    return strip(a) === strip(b);
  }

  // Paths the site answers with a permanent redirect, by their targets. The
  // router follows a redirect softly but with an extra round trip, so a move
  // goes straight to the target. The brain's `knowledge.REDIRECTS` is the same
  // table.
  const REDIRECTS = {
    "/contact-us": "/contact",
    "/saatvik-solar-gti-inverter": "/inverters",
    "/epc-solutions/carport-solar-solutions": "/epc-solutions/carport",
    "/epc-solutions/roof-top": "/epc-solutions/rooftop/commercial",
  };

  function redirected(url) {
    const to = REDIRECTS[url.pathname.replace(/\/+$/, "").toLowerCase()];
    if (to) url.pathname = to;
    return url;
  }

  // The router moves softly only while it can fetch the next page's payload.
  // When that fetch fails it loads the page in full instead (checked in Chrome
  // 2026-10-14: offline, `router.push` replaced the document), and a full load
  // drops the call until it rejoins on the new page. That is the reload on the
  // owner's hotspot call 1c91dcfc, whose uplink stalled every 10 to 20 s. So a
  // move first checks the site answers, and on a dead network it fails where
  // it stands — the call stays up and the brain says so — rather than letting
  // the router fall back to a load. The check is a HEAD of their favicon, about
  // 300 ms from the CDN; a page's own payload is rendered on demand and took
  // 1.4 to 4 s, which would make every move that much slower.
  const PROBE_TRIES = 3;
  const PROBE_MS = 1500;
  async function reachable() {
    for (let i = 0; i < PROBE_TRIES; i++) {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), PROBE_MS);
      try {
        const r = await fetch(`/favicon.ico?probe=${Date.now()}`, { method: "HEAD", signal: ctl.signal, cache: "no-store" });
        if (r.ok) return true;
      } catch {
        // A dropped or timed-out fetch: try again.
      } finally {
        clearTimeout(timer);
      }
    }
    return false;
  }

  async function navigate(path, { top = true } = {}) {
    if (typeof path !== "string" || !path.startsWith("/")) throw new Error(`not a path on this site: ${path}`);
    const target = redirected(new URL(path, location.origin));
    if (samePath(location.pathname, target.pathname) && location.search === target.search) {
      if (top) window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const from = location.pathname;
    const router = window.next && window.next.router;
    if (router && typeof router.push === "function") {
      if (!(await reachable())) throw new Error("the network dropped, so the page did not move");
      await router.push(target.pathname + target.search + target.hash);
    } else {
      // Without the router the move is a page load. The call rejoins on the
      // next page, so this is slower, not broken.
      location.assign(target.href);
      return;
    }
    // The site redirects some paths (/about-us lands on /about), so arriving
    // anywhere new counts; `page_changed` tells the brain where that was.
    const arrived = await waitFor(() => samePath(location.pathname, target.pathname) || !samePath(location.pathname, from));
    if (!arrived) throw new Error(`the page did not move to ${path}`);
    await settled();
  }

  /** The new page has rendered: its heading is up and the DOM has stopped
   *  changing for a moment. */
  async function settled() {
    await waitFor(() => main().querySelector("h1, h2"), 4000);
    await new Promise((resolve) => {
      let timer = setTimeout(done, 400);
      const obs = new MutationObserver(() => {
        clearTimeout(timer);
        timer = setTimeout(done, 400);
      });
      obs.observe(document.body, { childList: true, subtree: true });
      const cap = setTimeout(done, 3000);
      function done() {
        obs.disconnect();
        clearTimeout(timer);
        clearTimeout(cap);
        resolve();
      }
    });
  }

  /** A page, and where on it to land once it is up: a heading or words, a
   *  spec tab, or an FAQ. A cue spoken with the page names the page's own
   *  headings as the crawl knew them; one the live page has since lost leaves
   *  the visitor at the top of the page, not on a failed move. */
  async function navigateTo({ path, heading, text, tab, faq }) {
    const landing = Boolean(heading || text || tab || faq);
    await navigate(path, { top: !landing });
    if (!landing) return;
    try {
      if (faq) await openFaq({ question: faq });
      else if (tab) await openTab({ label: tab });
      else await showSection({ heading, text });
    } catch (error) {
      console.info("voqalize: landed at the top of", location.pathname, "-", error && error.message);
    }
  }

  async function goTo(path) {
    if (!samePath(location.pathname, path)) await navigate(path);
  }

  // Not every link on their site is the router's: a plain anchor in the header,
  // footer or a blog post loads the next page in full, which drops the call
  // until it rejoins on the new page. While a call is live, a same-origin link
  // the router left alone is pushed through it instead. This listens on the
  // window in the bubble phase, after React's own handler at the root, so a
  // link the router already took arrives with its default prevented.
  const FILE = /\.(pdf|jpe?g|png|webp|gif|svg|zip|docx?|xlsx?|pptx?|mp4)$/i;
  function watchLinks() {
    window.addEventListener("click", (e) => {
      if (!emitter || e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target && e.target.closest && e.target.closest("a[href]");
      if (!a || a.closest("[data-voqalize]") || a.hasAttribute("download")) return;
      if (a.target && a.target !== "_self") return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || FILE.test(url.pathname)) return;
      // A jump within this page is the browser's own and keeps the document.
      if (samePath(url.pathname, location.pathname) && url.search === location.search) return;
      const router = window.next && window.next.router;
      if (!router || typeof router.push !== "function") return;
      e.preventDefault();
      const to = redirected(url);
      reachable().then((ok) => {
        if (ok) router.push(to.pathname + to.search + to.hash);
        else toast(a, "The network dropped. Try that link again in a moment.");
      });
    });
  }

  // ─── What the page shows ──────────────────────────────────────────────

  function headings() {
    return [...main().querySelectorAll("h1, h2, h3")].filter(visible);
  }

  /** Their FAQ accordions: a button with `aria-expanded` whose first span is
   *  the question (the trailing span is the +/− sign). */
  function faqButtons() {
    return [...main().querySelectorAll("button[aria-expanded]")].filter(
      (b) => visible(b) && clean(faqQuestion(b)).length > 8,
    );
  }

  function faqQuestion(b) {
    const span = b.querySelector("span");
    return clean(span ? span.textContent : b.textContent);
  }

  function context() {
    const seen = new Set();
    const hs = [];
    for (const h of headings()) {
      const t = clean(h.textContent);
      if (!t || seen.has(t)) continue;
      seen.add(t);
      hs.push(t);
      if (hs.length >= MAX_HEADINGS) break;
    }
    return {
      path: location.pathname,
      title: document.title,
      headings: hs,
      faqs: faqButtons().map(faqQuestion).slice(0, MAX_FAQS),
      tabs: tabButtons().map((b) => clean(b.textContent)),
    };
  }

  // ─── open_tab ─────────────────────────────────────────────────────────
  // Spec tabs — ELECTRICAL / MECHANICAL / WARRANTY on a module, eight on the
  // battery, three on a pump or BESS — are plain buttons with no role, and
  // only the open tab's rows are on the page until another is clicked.
  const TAB_SELECTOR = "#specifications button, main button[role=tab], button.text-xs.font-medium.tracking-widest";
  function tabButtons() {
    const seen = new Set();
    return [...document.querySelectorAll(TAB_SELECTOR)].filter((b) => {
      const t = clean(b.textContent);
      if (!t || t.length > 40 || !visible(b) || b.hasAttribute("aria-expanded") || seen.has(norm(t))) return false;
      seen.add(norm(t));
      return true;
    });
  }

  async function openTab({ label }) {
    const want = norm(label);
    const tabs = tabButtons();
    const tab = tabs.find((b) => norm(b.textContent) === want) || tabs.find((b) => norm(b.textContent).includes(want) || want.includes(norm(b.textContent)));
    if (!tab) throw new Error(`no tab "${label}" on ${location.pathname}; it has: ${tabs.map((b) => clean(b.textContent)).join(" | ") || "none"}`);
    tab.click();
    await sleep(400);
    await scrollToTop(tab);
    const panel = tab.closest("section") || tab.parentElement;
    const r = panel.getBoundingClientRect();
    highlight(r.height > window.innerHeight * 1.5 ? tab : panel);
  }

  // ─── show_section ─────────────────────────────────────────────────────

  function findHeading(heading) {
    const want = norm(heading);
    if (!want) return null;
    const all = headings();
    return (
      all.find((h) => norm(h.textContent) === want) ||
      all.find((h) => norm(h.textContent).startsWith(want)) ||
      all.find((h) => want.startsWith(norm(h.textContent)) && norm(h.textContent).length > 3) ||
      all.find((h) => norm(h.textContent).includes(want)) ||
      null
    );
  }

  /** The section a heading heads: its `<section>`, or else the nearest
   *  ancestor that holds more than the heading itself. */
  function sectionOf(h) {
    const s = h.closest("section");
    if (s && s !== main()) return s;
    let el = h.parentElement;
    while (el && el !== main() && clean(el.textContent).length <= clean(h.textContent).length + 20) {
      el = el.parentElement;
    }
    return el || h;
  }

  /** The smallest visible element in `root` whose text contains `text`. */
  function smallestContaining(root, text) {
    const want = norm(text);
    if (!want) return null;
    let best = null;
    let bestLen = Infinity;
    for (const el of root.querySelectorAll("*")) {
      if (!visible(el)) continue;
      const t = norm(el.textContent);
      if (!t.includes(want)) continue;
      if (t.length < bestLen) {
        best = el;
        bestLen = t.length;
      }
    }
    // A table cell or a spec row reads better as its whole row.
    const row = best && best.closest("tr");
    if (row && root.contains(row)) return row;
    return best;
  }

  async function showSection({ heading, text }) {
    if (!heading && text) {
      // Words with no heading: a model, a spec row, a card, wherever it is.
      const el = smallestContaining(main(), text);
      if (!el) throw new Error(`"${text}" is not on ${location.pathname}`);
      await scrollToCentre(el);
      highlight(el);
      return;
    }
    const h = findHeading(heading);
    if (!h) {
      const known = context().headings.slice(0, 20).join(" | ");
      throw new Error(`no heading "${heading}" on ${location.pathname}; it has: ${known}`);
    }
    const section = sectionOf(h);
    if (text) {
      const el = smallestContaining(section, text) || smallestContaining(main(), text);
      if (!el) throw new Error(`"${text}" is not in the section "${clean(h.textContent)}"`);
      await scrollToCentre(el);
      highlight(el);
      return;
    }
    await scrollToTop(h);
    const r = section.getBoundingClientRect();
    // A section taller than the screen is ringed by its heading alone.
    highlight(r.height > window.innerHeight * 1.5 ? h : section);
  }

  // ─── open_faq ─────────────────────────────────────────────────────────

  function faqAnswer(b) {
    const id = b.getAttribute("aria-controls");
    const byId = id && document.getElementById(id);
    if (byId) return byId;
    return b.nextElementSibling || (b.parentElement && b.parentElement.nextElementSibling) || null;
  }

  async function openFaq({ question }) {
    const want = norm(question);
    const all = faqButtons();
    const b =
      all.find((x) => norm(faqQuestion(x)) === want) ||
      all.find((x) => norm(faqQuestion(x)).startsWith(want)) ||
      all.find((x) => want.startsWith(norm(faqQuestion(x)))) ||
      all.find((x) => norm(faqQuestion(x)).includes(want));
    if (!b) {
      const known = all.map(faqQuestion).slice(0, 15).join(" | ");
      throw new Error(`no FAQ "${question}" on ${location.pathname}${known ? `; it has: ${known}` : ""}`);
    }
    if (b.getAttribute("aria-expanded") !== "true") {
      b.click();
      await waitFor(() => b.getAttribute("aria-expanded") === "true", 2000);
      await sleep(350);
    }
    await scrollToCentre(b);
    const answer = faqAnswer(b);
    highlight(answer && visible(answer) ? [b, answer] : b);
  }

  // ─── The contact page's enquiry forms ─────────────────────────────────

  const TABS = { domestic: "DOMESTIC ENQUIRY", export: "EXPORT ENQUIRY", dealer: "DEALER ENQUIRY" };

  /** Each field the brain may fill, by how the form labels it: the input's
   *  placeholder, or the select's first option. */
  const FIELDS = {
    name: { placeholder: "enter full name" },
    company: { placeholder: "enter company" },
    email: { placeholder: "enter email" },
    mobile: { placeholder: "enter mobile" },
    city: { placeholder: "enter city" },
    district: { placeholder: "enter district" },
    state: { placeholder: "enter state", select: "select state" },
    category: { select: "select category" },
    investment: { select: "select investment" },
    message: { textarea: true },
  };

  function tabButton(kind) {
    const text = TABS[kind];
    return [...main().querySelectorAll("button")].find((b) => visible(b) && clean(b.textContent).toUpperCase() === text);
  }

  function enquiryForm() {
    return [...main().querySelectorAll("form")].find((f) => visible(f) && fieldIn(f, "name"));
  }

  function fieldIn(form, key) {
    const spec = FIELDS[key];
    if (spec.textarea) return form.querySelector("textarea");
    if (spec.placeholder) {
      const input = [...form.querySelectorAll("input")].find((i) =>
        norm(i.placeholder).startsWith(spec.placeholder),
      );
      if (input) return input;
    }
    if (spec.select) {
      return (
        [...form.querySelectorAll("select")].find((s) => s.options[0] && norm(s.options[0].text).startsWith(spec.select)) ||
        null
      );
    }
    return null;
  }

  /** Which of the forms is showing, told by its fields. */
  function formKind(form) {
    if (!form) return null;
    if (fieldIn(form, "district")) return "dealer";
    const state = fieldIn(form, "state");
    if (state && state.tagName === "SELECT") return "domestic";
    if (fieldIn(form, "message")) return "export";
    return null;
  }

  function required(el) {
    if (el.tagName === "SELECT") return /\*\s*$/.test(el.options[0] ? el.options[0].text : "");
    return /\*\s*$/.test(el.placeholder || "");
  }

  function isEmpty(el) {
    if (el.tagName === "SELECT") return el.selectedIndex <= 0;
    return !clean(el.value);
  }

  /** Set a value the way a person typing would, so React's state takes it. */
  function setNative(el, value) {
    const proto =
      el.tagName === "SELECT"
        ? HTMLSelectElement.prototype
        : el.tagName === "TEXTAREA"
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** The option of a select that best matches what the brain said: exact,
   *  then prefix, then the one sharing the most words. */
  function pickOption(select, said) {
    const want = norm(said);
    const opts = [...select.options].slice(1);
    const exact = opts.find((o) => norm(o.text) === want || norm(o.value) === want);
    if (exact) return exact;
    const prefix = opts.find((o) => norm(o.text).startsWith(want) || want.startsWith(norm(o.text)));
    if (prefix) return prefix;
    const words = new Set(want.split(/[^a-z0-9]+/).filter((w) => w.length > 2));
    let best = null;
    let bestScore = 0;
    for (const o of opts) {
      const score = norm(o.text)
        .split(/[^a-z0-9]+/)
        .filter((w) => words.has(w)).length;
      if (score > bestScore) {
        best = o;
        bestScore = score;
      }
    }
    return best;
  }

  function fieldName(form, el) {
    for (const key of Object.keys(FIELDS)) if (fieldIn(form, key) === el) return key;
    return clean(el.placeholder || (el.options && el.options[0] && el.options[0].text) || el.name).replace(/\*$/, "");
  }

  function missingIn(form) {
    const fields = [...form.querySelectorAll("input:not([type=checkbox]):not([type=hidden]), select, textarea")];
    return fields.filter((el) => visible(el) && required(el) && isEmpty(el));
  }

  function submitButton(form) {
    return form.querySelector("button[type=submit]") || [...form.querySelectorAll("button")].find((b) => /submit/i.test(b.textContent));
  }

  async function openEnquiry({ kind, prefill }) {
    if (!TABS[kind]) throw new Error(`no enquiry form called ${kind}; there are: ${Object.keys(TABS).join(", ")}`);
    await goTo("/contact");
    const tab = await waitFor(() => tabButton(kind));
    if (!tab) throw new Error(`no ${TABS[kind]} tab on /contact`);
    tab.click();
    const form = await waitFor(() => {
      const f = enquiryForm();
      return f && formKind(f) === kind ? f : null;
    }, 4000);
    if (!form) throw new Error(`the ${TABS[kind]} form did not open`);

    const skipped = [];
    for (const [key, value] of Object.entries(prefill || {})) {
      if (value === null || value === undefined || value === "") continue;
      const el = FIELDS[key] && fieldIn(form, key);
      if (!el) {
        skipped.push(key);
        continue;
      }
      if (el.tagName === "SELECT") {
        const opt = pickOption(el, String(value));
        if (!opt) {
          skipped.push(key);
          continue;
        }
        setNative(el, opt.value);
      } else {
        setNative(el, String(value));
      }
      await sleep(30);
    }
    if (skipped.length) console.info("voqalize: the", kind, "form has no place for", skipped);

    await scrollToTop(form);
    const missing = missingIn(form);
    const submit = submitButton(form);
    highlight(...missing, ...(submit ? [submit] : []));
    emit("enquiry_opened", { kind, missing: missing.map((el) => fieldName(form, el)) });
  }

  // ─── Booking a product (/book) ────────────────────────────────────────
  // Two client-side steps with no <form>: step 1 is a Residential / Commercial
  // choice and CONTINUE, step 2 the details, CONSENT and CONFIRM BOOKING. The
  // choice shows as chosen only by its orange border, and the page ignores
  // clicks until it has hydrated, so a choice is clicked until it shows.
  // Every product with a BOOK NOW books through the same page; an unknown
  // slug silently shows the TEJ PLUS G12R module, so only these are sent.
  const BOOKABLE = new Set([
    "surya-connect-kit", "tej-plus-g12r", "tej-m10r", "n-topcon", "bifacial-g2tb",
    "mono-perc", "vega-g2wb", "uday-single-phase", "uday-three-phase", "uday-plus-hybrid",
  ]);
  const BOOK_FIELDS = ["name", "mobile", "email", "address", "state", "city", "pincode"];
  const buttonNamed = (re) => [...main().querySelectorAll("button")].find((b) => visible(b) && re.test(clean(b.textContent)));
  const bookingField = (key) => document.querySelector(`#${key}`);
  const confirmBooking = () => buttonNamed(/confirm booking/i);

  const bookingProduct = () => new URLSearchParams(location.search).get("product") || "";

  async function bookProduct({ product, installation, details }) {
    if (!BOOKABLE.has(product)) throw new Error(`${product} has no booking page; bookable: ${[...BOOKABLE].join(", ")}`);
    const kind = installation === "commercial" ? "commercial" : "residential";
    if (location.pathname !== "/book" || bookingProduct() !== product) await navigate(`/book?product=${product}`);
    if (!(await waitFor(() => bookingField("name") || buttonNamed(/^continue\b/i), 8000))) {
      throw new Error("the booking page did not load");
    }
    if (!bookingField("name")) {
      const choice = new RegExp(`^${kind}\\b`, "i");
      const chosen = () => /saatvik-orange/.test((buttonNamed(choice) || {}).className || "");
      const picked = await waitFor(() => {
        if (!chosen()) {
          const b = buttonNamed(choice);
          if (b) b.click();
        }
        return chosen();
      }, 8000);
      if (!picked) throw new Error(`could not choose ${kind} on the booking page`);
      const next = buttonNamed(/^continue\b/i);
      if (next) next.click();
      if (!(await waitFor(() => bookingField("name"), 6000))) throw new Error("the booking page did not move to its details step");
    }
    for (const key of BOOK_FIELDS) {
      const value = details && details[key];
      if (value === null || value === undefined || value === "") continue;
      const el = bookingField(key);
      if (!el) continue;
      const text = key === "mobile" ? String(value).replace(/\D/g, "").slice(-10) : key === "pincode" ? String(value).replace(/\D/g, "").slice(0, 6) : String(value);
      setNative(el, text);
      await sleep(30);
    }
    const missing = BOOK_FIELDS.filter((k) => bookingField(k) && !clean(bookingField(k).value));
    await scrollToTop(bookingField("name"));
    highlight(...missing.map(bookingField), ...[bookingField("consent"), confirmBooking()].filter(Boolean));
    emit("booking_opened", { product, installation: kind, missing });
  }

  function readBooking() {
    const out = {};
    for (const key of BOOK_FIELDS) out[key] = bookingField(key) ? clean(bookingField(key).value) : "";
    return out;
  }

  function bookingKind() {
    const sub = clean((main().innerText.match(/Booking [^\n·]+·\s*(\w+)/i) || [])[1]);
    return /commercial/i.test(sub) ? "commercial" : "residential";
  }

  /** Every field the form has, by our names, as the person left them. */
  /** The fields `enquiry_submitted` carries; the dealer tab's city, district
   *  and investment have no place in it. */
  const REPORTED = ["name", "company", "email", "mobile", "category", "state", "message"];

  function readFields(form) {
    const out = {};
    for (const key of REPORTED) {
      const el = fieldIn(form, key);
      if (!el) continue;
      out[key] = el.tagName === "SELECT" ? (el.selectedIndex > 0 ? clean(el.options[el.selectedIndex].text) : "") : clean(el.value);
    }
    return out;
  }

  // SUBMIT on an enquiry form: reported to the brain first, then — while
  // DEMO_BLOCK_SUBMIT holds — stopped before the page sends it. Both listeners
  // are on `window` in the capture phase, so they run before React's, which
  // sits on the page's root. Pressing Enter in a field submits through a click
  // on the same button, so one report per press.
  let lastReport = 0;

  function onSubmitIntent(e, form) {
    const kind = formKind(form);
    if (!kind) return;
    if (Date.now() - lastReport > 500) {
      lastReport = Date.now();
      emit("enquiry_submitted", { kind, fields: readFields(form) });
    }
    if (!DEMO_BLOCK_SUBMIT) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    toast(submitButton(form) || form, "Demo: this enquiry was not sent to Saatvik.");
  }

  // CONFIRM BOOKING: reported, then — while DEMO_BLOCK_SUBMIT holds — stopped.
  function onBookingIntent(e, button) {
    if (Date.now() - lastReport > 500) {
      lastReport = Date.now();
      emit("booking_submitted", { product: bookingProduct(), installation: bookingKind(), fields: readBooking() });
    }
    if (!DEMO_BLOCK_SUBMIT) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    toast(button, "Demo: this booking was not sent to Saatvik.");
  }

  function watchSubmits() {
    const onClick = (e) => {
      const b = e.target && e.target.closest && e.target.closest("button");
      if (b && location.pathname === "/book" && /confirm booking/i.test(clean(b.textContent))) {
        onBookingIntent(e, b);
        return;
      }
      if (!b || !b.form || (b.type || "submit") !== "submit") return;
      onSubmitIntent(e, b.form);
    };
    const onSubmit = (e) => {
      if (e.target instanceof HTMLFormElement) onSubmitIntent(e, e.target);
    };
    window.addEventListener("click", onClick, true);
    window.addEventListener("submit", onSubmit, true);
  }

  let toastEl = null;
  function toast(near, text) {
    if (toastEl) toastEl.remove();
    const r = near.getBoundingClientRect();
    toastEl = document.createElement("div");
    toastEl.setAttribute("data-voqalize", "toast");
    toastEl.setAttribute("role", "status");
    toastEl.textContent = text;
    Object.assign(toastEl.style, {
      position: "absolute",
      left: `${r.left + window.scrollX}px`,
      top: `${r.bottom + window.scrollY + 10}px`,
      maxWidth: "320px",
      padding: "10px 14px",
      background: "#13306B",
      color: "#fff",
      font: '500 13px/1.4 "DM Sans", system-ui, sans-serif',
      borderLeft: `3px solid ${RING_COLOUR}`,
      borderRadius: "4px",
      boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
      zIndex: "2147483000",
      animation: "voqalize-toast 200ms ease-out",
    });
    document.body.appendChild(toastEl);
    const mine = toastEl;
    setTimeout(() => {
      if (toastEl === mine) {
        mine.remove();
        toastEl = null;
      }
    }, 5000);
  }

  // ─── The solar calculator ─────────────────────────────────────────────

  function calcButton() {
    return [...main().querySelectorAll("button")].find((b) => /calculate/i.test(b.textContent));
  }

  /** The result block: the smallest element holding both the system size and
   *  the call to unlock the full report. */
  function calcResult() {
    let best = null;
    for (const el of main().querySelectorAll("div, section")) {
      const t = el.textContent || "";
      if (!/recommended system size/i.test(t)) continue;
      if (!best || t.length < (best.textContent || "").length) best = el;
    }
    if (!best) return null;
    // Widen to the block that also holds the savings, if the size sits alone.
    let el = best;
    while (el.parentElement && el.parentElement !== main() && !/savings|payback|₹/i.test(el.textContent)) {
      el = el.parentElement;
    }
    return el;
  }

  function resultText(el) {
    const t = (el.innerText || el.textContent || "").replace(/\n{2,}/g, "\n").trim();
    const cut = t.search(/unlock your full report/i);
    return (cut > 0 ? t.slice(0, cut) : t).trim().slice(0, MAX_RESULT_CHARS);
  }

  async function runCalculator({ units, state, rate }) {
    await goTo("/solar-calculator");
    // After a result the page swaps its fields for the report; its own
    // "Edit my inputs" brings them back.
    if (!document.getElementById("calc-units")) {
      const edit = [...main().querySelectorAll("button")].find((b) => /edit my inputs/i.test(b.textContent || ""));
      if (edit) edit.click();
    }
    const unitsEl = await waitFor(() => document.getElementById("calc-units"));
    const stateEl = document.getElementById("calc-state");
    const rateEl = document.getElementById("calc-tariff");
    if (!unitsEl || !stateEl || !rateEl) throw new Error("the calculator's fields are not on the page");
    const opt = pickOption(stateEl, state);
    if (!opt) throw new Error(`the calculator has no state "${state}"`);
    const before = calcResult();
    const beforeText = before ? resultText(before) : "";
    setNative(unitsEl, String(units));
    setNative(stateEl, opt.value);
    setNative(rateEl, String(rate));
    await sleep(150);
    const go = calcButton();
    if (!go) throw new Error("no calculate button on the page");
    go.click();
    const result = await waitFor(() => {
      const el = calcResult();
      return el && resultText(el) !== beforeText ? el : null;
    });
    if (!result) throw new Error("the calculator showed no result");
    await sleep(300);
    await scrollToTop(result);
    highlight(result);
    emit("calculator_result", {
      inputs: { units: Number(units), state: clean(opt.text), rate: Number(rate) },
      text: resultText(result),
    });
  }

  // ─── The dealer locator ───────────────────────────────────────────────

  /** Each dealer card is a pressable button: its name, its type, then
   *  "City, State". The phone is a `tel:` link beside it. */
  function dealerCards() {
    return [...main().querySelectorAll("button[aria-pressed]")].filter(visible);
  }

  function readDealer(card) {
    const ps = [...card.querySelectorAll("p")].map((p) => clean(p.textContent));
    const type = clean((card.querySelector("span") || {}).textContent || "");
    // The card's own block holds the call link; climb until one is found.
    let block = card.parentElement;
    let tel = null;
    for (let i = 0; block && i < 3 && !tel; i++, block = block.parentElement) {
      tel = block.querySelector('a[href^="tel:"]');
    }
    return {
      name: ps[0] || clean(card.textContent).slice(0, 80),
      type,
      city: ps[1] || "",
      phone: tel ? clean(tel.textContent) || tel.getAttribute("href").slice(4) : "",
    };
  }

  async function findDealer({ state, query }) {
    await goTo("/dealer-locator");
    const select = await waitFor(() => main().querySelector("select"));
    const search = main().querySelector('input[type="search"]');
    if (!select) throw new Error("the dealer locator's state list is not on the page");
    let shown = "All States";
    if (state) {
      const opt = pickOption(select, state);
      if (!opt || /all states/i.test(opt.text)) {
        const listed = [...select.options].slice(1).map((o) => clean(o.text)).join(", ");
        throw new Error(`the dealer locator lists no dealers in ${state}; it lists: ${listed}`);
      }
      setNative(select, opt.value);
      shown = clean(opt.text);
    } else {
      const all = [...select.options].find((o) => /all states/i.test(o.text));
      if (all) setNative(select, all.value);
    }
    if (search) setNative(search, query || "");
    await sleep(700);
    const cards = dealerCards();
    const dealers = cards.slice(0, MAX_DEALERS).map(readDealer);
    const list = cards[0] && (cards[0].closest(".overflow-y-auto") || cards[0].parentElement);
    if (list) {
      await scrollToTop(select);
      highlight(cards.length ? cards.slice(0, 3) : list);
    }
    // Strings, empty for "not filtered": the brain's model has no null here.
    emit("dealers_shown", { state: state ? shown : "", query: query || "", dealers });
  }

  // ─── Reporting ────────────────────────────────────────────────────────

  let emitter = null;
  function emit(event, payload) {
    if (emitter) emitter(event, payload);
  }

  let lastPath = null;
  let reportTimer = null;
  function routeChanged() {
    clearTimeout(reportTimer);
    reportTimer = setTimeout(async () => {
      if (location.pathname === lastPath) return;
      lastPath = location.pathname;
      clearHighlight();
      await settled();
      emit("page_changed", context());
    }, 50);
  }

  let patched = false;
  function watchRoutes() {
    if (patched) return;
    patched = true;
    for (const name of ["pushState", "replaceState"]) {
      const real = history[name];
      history[name] = function (...args) {
        const out = real.apply(this, args);
        routeChanged();
        return out;
      };
    }
    window.addEventListener("popstate", routeChanged);
  }

  /** Report every route change, and the enquiry forms' SUBMITs, through
   *  `emit` until the returned stop. The page as it stands is reported first. */
  function start(next) {
    emitter = next;
    lastPath = location.pathname;
    emit("page_changed", context());
    return () => {
      if (emitter === next) emitter = null;
    };
  }

  const COMMANDS = {
    navigate: navigateTo,
    show_section: showSection,
    open_faq: openFaq,
    open_tab: openTab,
    open_enquiry: openEnquiry,
    book_product: bookProduct,
    run_calculator: runCalculator,
    find_dealer: findDealer,
  };

  /** Perform one of the brain's Actions. Never throws. */
  async function run(command, payload) {
    const fn = COMMANDS[command];
    if (!fn) return { ok: false, error: `the page cannot ${command}` };
    try {
      await fn(payload || {});
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error && error.message ? error.message : String(error) };
    }
  }

  styleThePage();
  watchRoutes();
  watchSubmits();
  watchLinks();

  window.voqalizeSaatvik = {
    run,
    context,
    start,
    commands: Object.keys(COMMANDS),
    demoBlocksSubmit: DEMO_BLOCK_SUBMIT,
  };
})();
