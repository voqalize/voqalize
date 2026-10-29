// The browser half of build.py: reads www.pcfactory.cl pages the way a visitor
// sees them. The site is Modyo pages with Vue widgets mounted after load, and
// several blocks (Retail Rocket rails, coupon cards, FAQ accordions) only exist
// after JS runs and the page is scrolled, so a plain HTTP fetch misses them.
//
//   node crawl.mjs pages  <out.json> <url> [url ...]   headings, sections, FAQs, links
//   node crawl.mjs stores <out.json>                    /tiendas: every store and its map card
//   node crawl.mjs facets <out.json> <url> [url ...]    a listing's filter groups as the page writes them
//
// Playwright is not a dependency of demos: build.py finds an installed copy and
// passes its entry module in PLAYWRIGHT_MODULE. Nothing here logs in, submits a
// form or touches the cart; every non-GET request from the page is aborted.

import fs from 'node:fs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

async function launch() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: UA,
    viewport: { width: 1440, height: 900 },
    locale: 'es-CL',
    timezoneId: 'America/Santiago',
  });
  // The page's own trackers POST; nothing we read needs a write.
  await ctx.route('**/*', (route) =>
    route.request().method() === 'GET' ? route.continue() : route.abort(),
  );
  return { browser, page: await ctx.newPage() };
}

async function scrollAll(page) {
  // Lazy rails render as they scroll into view: walk down the whole page.
  for (let i = 0; i < 80; i++) {
    const done = await page.evaluate(() => {
      window.scrollBy(0, 700);
      return window.scrollY + innerHeight >= document.documentElement.scrollHeight - 5;
    });
    await page.waitForTimeout(350);
    if (done) break;
  }
  await page.waitForTimeout(1200);
}

async function open(page, url) {
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);
  await scrollAll(page);
  return { status: resp ? resp.status() : 0, final: page.url() };
}

// Runs in the page. Everything a visitor can see in the main layout, by heading.
function readPage() {
  const root = document.querySelector('#main-layout') || document.body;
  // Chrome and widgets that are not the page's content.
  const SKIP = 'header, footer, nav, script, style, noscript, .modal, #accordion-compania, '
    + '#pcfAssistanceWrapper, #ocular-widget-container, #pcfChatContainer, #modyo-site-alert-wrapper';
  // Product cards: their text is names, prices and stock, which no knowledge file keeps.
  const PRODUCT = '.rr-item, .rr-swiper-slide, .products__item, .bannerHomeProd, '
    + '[class*="price"], [class*="precio"], [class*="Price"]';
  // A heading inside one of these is a card's title: an item of its block, not a section.
  const ITEM = '#accordionMenuFAQ, .cardCategories, a.card, .card a, a [class*="card"]';
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const unique = (sel, el) => {
    try {
      const all = document.querySelectorAll(sel);
      return all.length === 1 && (all[0] === el || all[0].contains(el));
    } catch { return false; }
  };
  // A selector a cue can scroll to: the heading's id, else a unique heading under
  // the nearest ancestor with an id, else that ancestor when the heading is its
  // first, else a unique class. "" when nothing stable is unique.
  const selectorOf = (h) => {
    const tag = h.tagName.toLowerCase();
    // Modyo's widget ids carry a "/" and change with every widget release.
    const stable = (id) => id && !/[/\\]|^modyo-|^(app|main-layout)$/.test(id);
    if (stable(h.id) && unique(`#${CSS.escape(h.id)}`, h)) return `#${CSS.escape(h.id)}`;
    let anc = h.parentElement;
    for (let i = 0; anc && anc !== document.body && i < 8; i++, anc = anc.parentElement) {
      if (!stable(anc.id)) continue;
      const a = `#${CSS.escape(anc.id)}`;
      if (unique(`${a} ${tag}`, h)) return `${a} ${tag}`;
      const first = anc.querySelector('h1,h2,h3,h4,h5,h6');
      if (first === h && unique(a, anc)) return a;
      break;
    }
    for (const c of h.classList) {
      if (unique(`${tag}.${CSS.escape(c)}`, h)) return `${tag}.${CSS.escape(c)}`;
    }
    // A rail's title sits just above the block that holds it (#retail-computacion):
    // scrolling there shows the title too.
    for (let a = h, i = 0; a && a !== root && i < 4; i++, a = a.parentElement) {
      const next = a.nextElementSibling;
      if (next && stable(next.id) && unique(`#${CSS.escape(next.id)}`, next)) {
        return `#${CSS.escape(next.id)}`;
      }
      if (next) break;
    }
    return '';
  };

  // FAQs first, so their questions and answers stay out of the sections.
  const faqNodes = new Set();
  const faqs = [];
  const menu = (e) => e.closest('#accordionMenuFAQ, .main-accordion, #accordion-compania');
  for (const item of root.querySelectorAll('.accordion-item')) {
    if (menu(item) || item.closest(SKIP)) continue;
    const head = item.querySelector('.accordion-header');
    const btn = item.querySelector('[data-bs-target], [data-target], [aria-controls]');
    const sel = btn && (btn.getAttribute('data-bs-target') || btn.getAttribute('data-target')
      || '#' + btn.getAttribute('aria-controls'));
    let body = null;
    try { body = sel ? item.querySelector(sel) || document.querySelector(sel) : null; } catch {}
    body = body || item.querySelector('.accordion-collapse, .collapse');
    if (!head || !body || !visible(head)) continue;
    body.classList.add('show');
    faqs.push({ q: clean(head.innerText), a: clean(body.innerText), el: head,
      selector: head.id ? `#${CSS.escape(head.id)}` : '' });
    faqNodes.add(item);
  }
  // Topic pages show their questions as anchored blocks. Términos y condiciones
  // shows one chapter at a time (its menu links switch them): the others are
  // kept too, marked hidden, read from their text.
  for (const box of root.querySelectorAll('.pregunta-container')) {
    const h = box.querySelector('h1,h2,h3,h4,h5,h6');
    if (!h) continue;
    const shown = visible(h);
    const q = clean(shown ? h.innerText : h.textContent);
    let a;
    if (shown) {
      a = clean(box.innerText).slice(q.length).trim();
    } else {
      const copy = box.cloneNode(true);
      copy.querySelector('h1,h2,h3,h4,h5,h6').remove();
      copy.querySelectorAll('p, li, br, div, h5, h6').forEach((e) => e.append(' '));
      a = clean(copy.textContent);
    }
    const topic = document.querySelector('#accordionMenuFAQ .border-active');
    faqs.push({ q, a, el: h, selector: box.id ? `#${CSS.escape(box.id)}` : '',
      topic: topic ? clean(topic.innerText) : '', ...(shown ? {} : { hidden: true }) });
    faqNodes.add(box);
  }
  const inFaq = (e) => [...faqNodes].some((n) => n.contains(e));

  const heads = [...root.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(
    (h) => clean(h.innerText).length > 1 && visible(h) && !h.closest(SKIP) && !inFaq(h)
      && !h.closest(PRODUCT),
  );
  const sections = [];
  const owner = new Map(); // heading → the section it opens or joins
  for (const h of heads) {
    const text = clean(h.innerText).slice(0, 160);
    if (h.closest(ITEM) && sections.length) {
      const s = sections[sections.length - 1];
      if (!s.items.includes(text)) s.items.push(text);
      owner.set(h, s);
      continue;
    }
    const s = { heading: text, level: +h.tagName[1], selector: selectorOf(h), text: '', items: [] };
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
    if (!el || owner.has(el) || el.closest('h1,h2,h3,h4,h5,h6')) continue;
    const t = clean(n.textContent);
    if (!t || !visible(el)) continue;
    const list = parts.get(current) || [];
    if (list.join(' ').length < 1500) list.push(t);
    parts.set(current, list);
  }
  for (const s of sections) s.text = clean((parts.get(s) || []).join(' · ')).slice(0, 1500);

  // The section an FAQ sits under: the last section heading before it.
  const order = heads.filter((h) => owner.has(h));
  for (const f of faqs) {
    let sec = '';
    for (const h of order) {
      if (h.compareDocumentPosition(f.el) & Node.DOCUMENT_POSITION_FOLLOWING) sec = owner.get(h).heading;
    }
    f.section = f.topic || sec;
    delete f.el;
    delete f.topic;
  }
  const h1 = [...root.querySelectorAll('h1')].find(visible);
  const meta = document.querySelector('meta[name="description"]');
  const links = [...new Set([...root.querySelectorAll('a[href]')].map((a) => a.href.split('#')[0]))];
  return {
    title: clean(document.title),
    description: clean(meta && meta.content),
    h1: h1 ? clean(h1.innerText) : '',
    body_class: document.body.className,
    sections,
    faqs,
    links,
  };
}

// Runs in the page: the store entries the /tiendas Vue widget renders from.
function readStoreData() {
  for (const el of document.querySelectorAll('*')) {
    const vm = el.__vue__;
    if (!vm || !Array.isArray(vm.$data && vm.$data.stores)) continue;
    const plain = (v) => { try { return JSON.parse(JSON.stringify(v)); } catch { return null; } };
    return vm.$data.stores.map((s) => ({
      meta: { name: s.meta.name, slug: s.meta.slug, tags: plain(s.meta.tags), category: s.meta.category_name },
      fields: {
        id: s.fields.id, Local: s.fields.Local, Comuna: s.fields.Comuna, Telefono: s.fields.Telefono,
        Disclaimer: s.fields.Disclaimer, Icono: s.fields.Icono, Horario: s.fields.Horario,
        Direccion: plain(s.fields.Direccion),
      },
    }));
  }
  return [];
}

async function pages(out, urls) {
  const { browser, page } = await launch();
  const result = {};
  for (const url of urls) {
    try {
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
  await open(page, 'https://www.pcfactory.cl/tiendas');
  await page.evaluate(() => window.scrollTo(0, 0));
  const data = await page.evaluate(readStoreData);
  // The hours a visitor reads are the map card's ("Ver tienda"), which can
  // differ from the entry's own Horario field: the card shows the schedule of
  // the store's tag (Mall Plaza, calle …) when it has one.
  const cards = {};
  // Clicked from the page's own JS: the open card covers the next button, and
  // a pointer click would wait on it.
  const n = await page.evaluate(() => [...document.querySelectorAll('button.btn-store')]
    .filter((b) => b.offsetParent !== null).length);
  for (let i = 0; i < n; i++) {
    await page.evaluate((k) => {
      const b = [...document.querySelectorAll('button.btn-store')].filter((x) => x.offsetParent !== null)[k];
      b.scrollIntoView({ block: 'center' });
      b.click();
    }, i);
    await page.waitForTimeout(1500);
    const text = await page.evaluate(() => {
      const iw = [...document.querySelectorAll('.gm-style-iw-d, .gm-style-iw')].pop();
      return iw ? iw.innerText : '';
    });
    const name = text.split('\n')[0].trim();
    if (name) cards[name] = text;
  }
  fs.writeFileSync(out, JSON.stringify({ stores: data, cards }, null, 1));
  console.error(`stores ${data.length}, cards ${Object.keys(cards).length}`);
  await browser.close();
}

async function facets(out, urls) {
  const { browser, page } = await launch();
  const result = {};
  for (const url of urls) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('#panel-filters h4', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(3000);
    result[url] = await page.evaluate(() =>
      [...document.querySelectorAll('#panel-filters h4')].map((h) => {
        const btn = h.querySelector('button');
        const target = btn && btn.getAttribute('data-target');
        const box = target ? document.querySelector(target) : null;
        return {
          name: h.textContent.replace(/\s+/g, ' ').trim(),
          labels: box ? [...box.querySelectorAll('label')].map((l) => l.textContent.replace(/\s+/g, ' ').trim()) : [],
        };
      }),
    );
    console.error(`ok ${url}`);
  }
  fs.writeFileSync(out, JSON.stringify(result, null, 1));
  await browser.close();
}

const [mode, out, ...rest] = process.argv.slice(2);
if (mode === 'pages') await pages(out, rest);
else if (mode === 'stores') await stores(out);
else if (mode === 'facets') await facets(out, rest);
else {
  console.error('usage: node crawl.mjs pages|stores|facets <out.json> [url ...]');
  process.exit(2);
}
