// The browser half of build.py: reads www.agroplanet.cl pages the way a visitor
// sees them. The site is an Angular SPA: every page is drawn by JS after the
// first load, the home's blocks fill in from CMS slots as they scroll into view,
// and the policy pages are mat-accordions. A plain HTTP fetch sees an empty
// <app-root>, so each page is opened in Chromium and read once its content is
// on screen (not on `load`, which fires before the router has drawn anything).
//
//   node crawl.mjs pages  <out.json> <url> [url ...]   headings, sections, accordion panels, links
//   node crawl.mjs stores <out.json>                    /nuestras-tiendas: every store card, all pages
//
// Playwright is not a dependency of demos: build.py finds an installed copy and
// passes its entry module in PLAYWRIGHT_MODULE. Nothing here logs in, submits a
// form or touches the cart; every non-GET request from the page is aborted.

import fs from 'node:fs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

async function launch({ allowCartAdd = false } = {}) {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: UA,
    viewport: { width: 1366, height: 900 },
    locale: 'es-CL',
    timezoneId: 'America/Santiago',
  });
  // The page's own trackers POST; nothing we read needs a write.
  // The one exception, for the quote form only: /cotizacion shows "Tu carro está
  // vacío" until the cart holds something, so the crawler adds one product to
  // its own throwaway anonymous session (never a visitor's) to read the form's
  // labels. The form itself is never filled or submitted.
  await ctx.route('**/*', (route) => {
    const req = route.request();
    if (req.method() === 'GET') return route.continue();
    if (allowCartAdd && /api\.agroplanet\.cl\/webapi\/cart\/add/.test(req.url())) return route.continue();
    return route.abort();
  });
  return { browser, page: await ctx.newPage() };
}

// What each route draws once its content is in: the router outlet's component.
const READY = {
  '/': 'app-category-home',
  '/nuestras-tiendas': '.listStoreFinder mat-card',
  '/carro': 'app-cart',
  '/cotizacion': 'app-quote, app-cart',
};
const READY_DEFAULT = 'mat-expansion-panel, router-outlet + * h1, router-outlet + * h2, router-outlet + * h3';

async function closeSplash(page) {
  // A full load of / opens an empty dialog that blocks scrolling.
  await page.evaluate(() => {
    const x = document.querySelector('app-generic-dialog .close');
    if (x) x.click();
  });
  await page.waitForTimeout(500);
}

async function scrollAll(page) {
  for (let i = 0; i < 40; i++) {
    const done = await page.evaluate(() => {
      window.scrollBy(0, 600);
      return window.scrollY + innerHeight >= document.documentElement.scrollHeight - 5;
    });
    await page.waitForTimeout(350);
    if (done) break;
  }
  await page.waitForTimeout(1200);
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function open(page, url) {
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const path = new URL(url).pathname;
  const sel = READY[path] || READY_DEFAULT;
  await page.waitForSelector(sel, { state: 'attached', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(3000);
  await closeSplash(page);
  await scrollAll(page);
  // Some accordions render a panel's body only once it is opened (lazy
  // matExpansionPanelContent): open every closed panel of the page's content.
  const opened = await page.evaluate(() => {
    const heads = [...document.querySelectorAll('mat-expansion-panel-header[aria-expanded="false"]')]
      .filter((h) => !h.closest('app-footer, app-plp-filter, .cdk-overlay-container'));
    heads.forEach((h) => h.click());
    return heads.length;
  });
  if (opened) await page.waitForTimeout(1500);
  return { status: resp ? resp.status() : 0, final: page.url() };
}

// Runs in the page. The router outlet's content, by heading and accordion panel.
function readPage() {
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const outlet = document.querySelector('router-outlet');
  const root = (outlet && outlet.parentElement) || document.body;
  // Chrome and widgets that are not the page's content.
  const SKIP = 'app-header-desktop, app-sticky-header-desktop, app-top-bar, app-menu-desktop, '
    + 'app-footer, app-breadcrumb, .cookies-wrapper, .cdk-overlay-container, script, style, '
    + 'mat-icon, app-plp-filter';
  // Product cards: their text is names and prices, which no knowledge file keeps.
  const PRODUCT = 'app-product-card, app-products-carousel, app-cart-product, app-resumen, '
    + '[class*="price"], [class*="precio"]';
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const unique = (sel, el) => {
    try {
      const all = document.querySelectorAll(sel);
      return all.length === 1 && all[0] === el;
    } catch { return false; }
  };
  // A CSS path a cue can scroll to: from the nearest component tag (app-*) or id,
  // tag:nth-of-type steps down to the element. Angular's _ngcontent attributes
  // and ids like mat-input-7 change between builds, so neither is used.
  const stableId = (id) => id && !/^(mat-|cdk-|ng-)/.test(id) && !/\d{2,}/.test(id);
  const selectorOf = (el) => {
    if (!el) return '';
    if (stableId(el.id) && unique(`#${CSS.escape(el.id)}`, el)) return `#${CSS.escape(el.id)}`;
    const tag0 = el.tagName.toLowerCase();
    for (const c of el.classList) {
      if (!/^(ng-|mat-focus|cdk-)/.test(c) && unique(`${tag0}.${CSS.escape(c)}`, el)) return `${tag0}.${CSS.escape(c)}`;
    }
    const steps = [];
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const tag = e.tagName.toLowerCase();
      if (e !== el && stableId(e.id)) {
        const s = [`#${CSS.escape(e.id)}`, ...steps].join(' > ');
        if (unique(s, el)) return s;
      }
      const sibs = e.parentElement ? [...e.parentElement.children].filter((c) => c.tagName === e.tagName) : [e];
      steps.unshift(sibs.length > 1 ? `${tag}:nth-of-type(${sibs.indexOf(e) + 1})` : tag);
      if (tag.startsWith('app-')) {
        const s = steps.join(' > ');
        if (unique(s, el)) return s;
      }
      if (steps.length > 16) break;
    }
    return '';
  };
  // Block-level text of a subtree, hidden or not (a collapsed panel's body is in
  // the DOM but not rendered, so innerText would be empty).
  const blockText = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll('script, style, mat-icon').forEach((e) => e.remove());
    copy.querySelectorAll('p, li, br, div, h1, h2, h3, h4, h5, h6, tr, td').forEach((e) => e.append(' \n'));
    return copy.textContent.split('\n').map(clean).filter(Boolean).join(' ');
  };

  // Accordion panels first, so their titles and bodies stay out of the sections.
  const faqNodes = new Set();
  const faqs = [];
  for (const panel of root.querySelectorAll('mat-expansion-panel')) {
    if (panel.closest(SKIP)) continue;
    const head = panel.querySelector('mat-expansion-panel-header');
    const title = panel.querySelector('mat-panel-title') || head;
    const body = panel.querySelector('.mat-expansion-panel-content');
    if (!head || !visible(head)) continue;
    faqs.push({ q: clean(title.innerText), a: body ? blockText(body) : '', el: head,
      selector: selectorOf(head) });
    faqNodes.add(panel);
  }
  const inFaq = (e) => [...faqNodes].some((n) => n.contains(e));

  // Headings: h1–h6, plus the home's block titles (div.fw-700.fs18), which the
  // site draws as bold divs rather than heading tags.
  const HEADS = 'h1,h2,h3,h4,h5,h6,app-category-home div.fw-700.fs18, mat-card span.fs18.fw-700';
  const heads = [...root.querySelectorAll(HEADS)].filter(
    (h) => clean(h.innerText).length > 1 && visible(h) && !h.closest(SKIP) && !inFaq(h)
      && !h.closest(PRODUCT),
  );
  const sections = [];
  const owner = new Map();
  for (const h of heads) {
    const s = { heading: clean(h.innerText).slice(0, 160), level: /^H\d$/.test(h.tagName) ? +h.tagName[1] : 2,
      selector: selectorOf(h), text: '', items: [] };
    sections.push(s);
    owner.set(h, s);
  }
  // Each visible text goes to the section of the heading before it.
  let current = null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      if (n.nodeType === 1) {
        if (n.matches(SKIP) || n.matches(PRODUCT) || faqNodes.has(n)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const parts = new Map();
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.nodeType === 1) {
      if (owner.has(n)) current = owner.get(n);
      continue;
    }
    if (!current) continue;
    const el = n.parentElement;
    if (!el || owner.has(el) || [...owner.keys()].some((h) => h.contains(el))) continue;
    const t = clean(n.textContent);
    if (!t || !visible(el)) continue;
    const list = parts.get(current) || [];
    if (list.join(' ').length < 1500) list.push(t);
    parts.set(current, list);
  }
  for (const s of sections) s.text = clean((parts.get(s) || []).join(' · ')).slice(0, 1500);

  // The section a panel sits under: the last section heading before it.
  const order = heads.filter((h) => owner.has(h));
  for (const f of faqs) {
    let sec = '';
    for (const h of order) {
      if (h.compareDocumentPosition(f.el) & Node.DOCUMENT_POSITION_FOLLOWING) sec = owner.get(h).heading;
    }
    f.section = sec;
    delete f.el;
  }

  // The home's blocks, in order, whether or not they carry a title: the hero,
  // the brand strip and each app-category-home (tiles are images with their
  // text baked in, so their alt text and "Ver productos" links are what is kept).
  const blocks = [];
  if (location.pathname === '/' || location.pathname === '/inicio') {
    const add = (label, el) => {
      if (!el) return;
      const r = el.getBoundingClientRect();
      const title = el.querySelector('div.fw-700.fs18');
      const tiles = [...el.querySelectorAll('div.title')].map((t) => clean(t.innerText)).filter(Boolean);
      const alts = [...el.querySelectorAll('img[alt]')]
        .filter((i) => !i.closest('app-product-card, app-products-carousel')).map((i) => clean(i.alt))
        .filter((a) => a && !/^(img|image|banner|fondo)$/i.test(a));
      const links = [...new Set([...el.querySelectorAll('a[href]')]
        .filter((a) => !a.closest('app-product-card'))
        .map((a) => a.getAttribute('href')).filter((h) => h && h.startsWith('/')))];
      blocks.push({ label, heading: title ? clean(title.innerText) : '', selector: selectorOf(el),
        top: Math.round(r.top + scrollY), height: Math.round(r.height), tiles,
        alts: [...new Set(alts)].slice(0, 20), links,
        products: el.querySelectorAll('app-product-card').length });
    };
    add('hero', document.querySelector('app-main-carousel'));
    add('brands', document.querySelector('app-brands-carousel-home'));
    document.querySelectorAll('app-category-home').forEach((el, i) => add(`category-home-${i + 1}`, el));
  }

  // Form labels (the quote form) and the cart's empty state.
  const labels = [...root.querySelectorAll('mat-label, button, mat-card span.fs18')]
    .filter((e) => visible(e) && !e.closest(SKIP))
    .map((e) => {
      const copy = e.cloneNode(true);
      copy.querySelectorAll('mat-icon').forEach((i) => i.remove());
      return clean(copy.textContent);
    }).filter((t) => t && t.length < 80);
  // The chrome around every page, read once from home: top bar, header and footer links.
  let chrome = null;
  if (location.pathname === '/' || location.pathname === '/inicio') {
    const linksOf = (sel) => [...document.querySelectorAll(sel)].filter(visible).map((a) => ({
      text: clean(a.innerText) || clean(a.getAttribute('title')) || clean((a.querySelector('img') || {}).alt),
      href: a.getAttribute('href') || '',
      new_tab: a.target === '_blank',
    }));
    const footer = document.querySelector('app-footer');
    chrome = {
      top_bar: linksOf('app-top-bar a'),
      shortcuts: [...document.querySelectorAll('app-menu-desktop .menu_desktop a')].filter(visible)
        .map((a) => clean(a.innerText.replace(/^menu/, ''))).filter(Boolean),
      footer_links: linksOf('app-footer a'),
      footer_text: footer ? footer.innerText.split('\n').map(clean).filter(Boolean) : [],
      whatsapp: (document.querySelector('a.whatsapp-float') || {}).href || '',
    };
  }
  const h1 = [...root.querySelectorAll('h1')].find(visible);
  const meta = document.querySelector('meta[name="description"]');
  const links = [...new Set([...root.querySelectorAll('a[href]')].map((a) => a.href.split('#')[0]))];
  return {
    title: clean(document.title),
    description: clean(meta && meta.content),
    h1: h1 ? clean(h1.innerText) : '',
    sections,
    faqs,
    blocks,
    labels: [...new Set(labels)],
    chrome,
    links,
  };
}

// Runs in the page: the store cards /nuestras-tiendas shows on its current page.
function readStoreCards() {
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim();
  return [...document.querySelectorAll('.listStoreFinder mat-card')].map((card) => {
    const field = (label) => {
      const f = [...card.querySelectorAll('span.field-mobile')].find((s) => clean(s.innerText).startsWith(label));
      return f && f.nextElementSibling ? clean(f.nextElementSibling.innerText) : '';
    };
    const head = card.querySelector('.fs20');
    const lines = card.innerText.split('\n').map(clean).filter(Boolean);
    const at = lines.findIndex((l) => l.startsWith('Horarios de Atención'));
    const hours = at >= 0 ? lines.slice(at + 1).filter((l) => !/^(ABIERTO|CERRADO)$/.test(l)) : [];
    const maps = card.querySelector('a[href*="google.com/maps"]');
    return {
      name: head ? clean(head.innerText).replace(/^Tienda\s*/, '') : '',
      address: field('Dirección'),
      phone: field('Télefono') || field('Teléfono'),
      hours,
      maps: maps ? maps.href : '',
    };
  });
}

// Puts one product in the crawler's own cart: the first product of a listing,
// through its page's "Cotizar" button (adds one unit and opens /cotizacion).
async function fillCart(page) {
  await open(page, 'https://www.agroplanet.cl/categoria/lubricantes/AG100');
  const href = await page.evaluate(() => {
    const a = document.querySelector('app-plp-grid a[href^="/producto/"]');
    return a ? a.href : '';
  });
  if (!href) throw new Error('no product link on the listing');
  await page.goto(href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('app-product-info', { state: 'attached', timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.locator('app-product-info button:has-text("Cotizar"):visible').first().click();
  await page.waitForURL(/\/cotizacion/, { timeout: 30000 });
}

async function pages(out, urls) {
  const quote = urls.some((u) => new URL(u).pathname === '/cotizacion');
  const { browser, page } = await launch({ allowCartAdd: quote });
  const result = {};
  // The empty cart first: /carro is read before anything is added.
  const ordered = [...urls].sort((a, b) =>
    (new URL(a).pathname === '/cotizacion') - (new URL(b).pathname === '/cotizacion'));
  for (const url of ordered) {
    try {
      if (new URL(url).pathname === '/cotizacion') await fillCart(page);
      const nav = await open(page, url);
      result[url] = { url, ...nav, ...(await page.evaluate(readPage)) };
      console.error(`ok ${nav.status} ${url} -> ${nav.final}`);
    } catch (err) {
      result[url] = { url, error: String(err) };
      console.error(`ERR ${url}: ${err}`);
    }
  }
  fs.writeFileSync(out, JSON.stringify(result, null, 1));
  await browser.close();
}

async function stores(out) {
  const { browser, page } = await launch();
  await open(page, 'https://www.agroplanet.cl/nuestras-tiendas');
  const cards = [];
  const seen = new Set();
  // ngx-pagination: "Continuar" moves one page on; stop when a page adds nothing new.
  for (let i = 0; i < 10; i++) {
    const got = await page.evaluate(readStoreCards);
    const fresh = got.filter((c) => c.name && !seen.has(c.name));
    fresh.forEach((c) => { seen.add(c.name); cards.push(c); });
    if (!fresh.length) break;
    const more = await page.evaluate(() => {
      const next = document.querySelector('pagination-controls li.pagination-next:not(.disabled) a');
      if (!next) return false;
      next.click();
      return true;
    });
    if (!more) break;
    await page.waitForTimeout(1500);
  }
  fs.writeFileSync(out, JSON.stringify({ cards }, null, 1));
  console.error(`store cards ${cards.length}`);
  await browser.close();
}

const [mode, out, ...rest] = process.argv.slice(2);
if (mode === 'pages') await pages(out, rest);
else if (mode === 'stores') await stores(out);
else {
  console.error('usage: node crawl.mjs pages|stores <out.json> [url ...]');
  process.exit(2);
}
