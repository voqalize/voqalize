# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build SendPotion's L3 knowledge: every page of sendpotion.com and every post on
blog.sendpotion.com, as data, read from a real browser.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON. Network is touched only by ``crawl``; each page's
extraction is cached outside the repository, so a re-run is cheap and ``search``
never fetches anything.

Neither site can be read from its server HTML alone. sendpotion.com is a custom
static site (S3 + CloudFront, *not* Webflow) whose headings are split into
GSAP-animated lines and whose page scrolls inside a Smooth Scrollbar container;
blog.sendpotion.com is a Medium publication on a custom domain that answers a
plain ``curl`` with a Cloudflare 403. So the crawl drives headless Chromium
(Playwright, fresh non-persistent contexts) and reads the rendered DOM: the main
site with JavaScript on, scrolled to the bottom with wheel events so every reveal
fires; the blog with JavaScript off and every subresource blocked, one post at a
time, because Medium's server HTML already holds the whole article and a hydrated
page's burst of ``/_/graphql`` calls gets the next post a 403. Run from
``voqalize/demos``; Playwright is not a demos dependency, so pull it in for the
run (its Chromium must be installed once with ``playwright install chromium``)::

    uv run --with playwright python sendpotion/backend/knowledge/build.py crawl
    uv run --with playwright python sendpotion/backend/knowledge/build.py crawl --refresh
    uv run python sendpotion/backend/knowledge/build.py crawl --offline
    uv run python sendpotion/backend/knowledge/build.py search "lip sync"

``crawl`` starts from both sitemaps (``sendpotion.com/sitemap.xml``, Medium's
``blog.sendpotion.com/sitemap/sitemap.xml``) and the blog's ``/feed``, follows
every same-host link a main-site page carries, and writes, next to this file:

- ``L3/pages.json`` — the English main-site pages, ``[{path, url, title,
  description, canonical, alternates: {lang: url}, headings, sections, faqs,
  stats, tables, pricing, tabs, forms, iframes, ctas, widgets, text}]``.
  ``headings``, ``faqs: [{q, a}]``, ``stats: [{label, value}]``, ``tables`` and
  ``text`` keep the Saatvik loader's shape. The rest:

  - ``sections``: the page in order, ``[{heading, level, id, block, selector,
    text, items, images, reveal}]``. ``heading`` is the heading's DOM text with
    whitespace collapsed, exactly as rendered (no CSS text-transform is in use
    on this site; ``transform`` is recorded when one is). A run of text before a
    block's first heading becomes a section whose ``heading`` is a synthetic
    ``[block] snippet`` label and ``level`` 0. ``block`` is the page block's
    class (``pt-hero``, ``pt-pricing`` ...), ``selector`` a CSS selector for the
    heading or block, ``items`` the card titles, plan names and list items in
    the section, ``images`` the alt text of its images (logo strips), and
    ``reveal`` notes a GSAP line reveal that starts at ``opacity: 0``.
  - ``faqs`` also carry ``selector`` (the accordion item); how an answer is
    hidden and opened is probed once and written to ``site.json``.
  - ``pricing``: ``[{plan, price, price_note, brief, cta: {text, href},
    features}]``.
  - ``forms``: ``[{selector, id, name, action, method, fields: [{tag, type,
    name, id, label, placeholder, required, options}], submit}]``;
    ``iframes``: ``[{src, host, cross_origin, title, selector}]`` — a Calendly
    or YouTube frame is cross-origin and cannot be filled from the page.
  - ``ctas``: every button-styled link and every link off the site,
    ``[{text, href, target, selector}]``; ``outbound``: every link on the page
    (nav, footer or body) to ``blog.sendpotion.com`` or ``app.sendpotion.com``,
    with ``area`` and ``new_tab`` (``target=_blank``).
  - The ``/es/`` and ``/pt-br/`` translations are not crawled (English only).
  - ``widgets``: what the page has that moves (sliders, typed text, videos,
    marquees), found by class.

- ``L3/blog.json`` — every post, ``[{url, path, title, subtitle, author,
  date, date_iso, reading_time, tags, member_only, headings: [{level, id,
  text}], text, summary, use_cases}]``. ``text`` is the post body, a paragraph a
  line. ``summary`` and ``use_cases`` are hand-written and kept in
  ``blog_notes.json`` beside this file, keyed by path, so a re-crawl keeps them;
  a post without a note gets an empty summary and is listed by the build.
- ``L3/site.json`` — the navigation (top nav, language switch, footer), both
  hosts' response headers, the probes (does a nav click reload the page; how a
  FAQ opens; how the page scrolls), every external host linked, and the blog's
  tag pages.

``--offline`` builds from the cache only; ``--refresh`` re-renders everything.
The cache is ``$XDG_CACHE_HOME/voqalize-sendpotion`` (``~/.cache`` by default).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
L3 = HERE / "L3"
NOTES = HERE / "blog_notes.json"
SITE = "https://sendpotion.com"
BLOG = "https://blog.sendpotion.com"
SITEMAP = f"{SITE}/sitemap.xml"
BLOG_SITEMAP = f"{BLOG}/sitemap/sitemap.xml"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-sendpotion"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
I18N = ("/es/", "/pt-br/")
HEADERS_KEPT = (
    "content-security-policy",
    "content-security-policy-report-only",
    "permissions-policy",
    "feature-policy",
    "x-frame-options",
    "cross-origin-opener-policy",
    "cross-origin-embedder-policy",
    "referrer-policy",
    "strict-transport-security",
    "server",
    "x-powered-by",
    "content-type",
    "cache-control",
    "via",
)
POST_RE = re.compile(r"^/[a-z0-9-]+-[0-9a-f]{10,12}$")
PARALLEL = 4
# Cloudflare in front of Medium answers 403 once a client opens a few posts at a
# time: the blog is read one post at a time, with a pause, backing off on a 403.
BLOG_PAUSE = 2.0
BLOG_BACKOFF = 90.0

# --------------------------------------------------------------------------- page JS

# Scroll the Smooth Scrollbar container to the bottom with wheel events, the way a
# visitor would, so every GSAP reveal fires; window.scrollTo does nothing here.
SCROLL_JS = r"""
async () => {
  const lay = document.querySelector('.pt-layout[data-scrollbar]');
  const sc = document.querySelector('.scroll-content');
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  if (!lay || !sc) {
    for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await sleep(80); }
    window.scrollTo(0, 0); return {smooth: false};
  }
  const total = sc.scrollHeight;
  for (let i = 0; i < 200; i++) {
    lay.dispatchEvent(new WheelEvent('wheel', {deltaY: 700, bubbles: true, cancelable: true}));
    await sleep(110);
    const m = /translate3d\(0px, (-?[\d.]+)px/.exec(sc.style.transform || '');
    if (m && -parseFloat(m[1]) + innerHeight >= total - 2) break;
  }
  await sleep(600);
  lay.dispatchEvent(new WheelEvent('wheel', {deltaY: -total * 2, bubbles: true, cancelable: true}));
  await sleep(600);
  return {smooth: true, total};
}
"""

# Which headings start hidden (GSAP split lines at opacity 0) before any scroll.
HIDDEN_JS = r"""
() => [...document.querySelectorAll('.scroll-content h1, .scroll-content h2, .scroll-content h3, .scroll-content h4')].filter(h => !h.closest('.pt-faq-item, details')).map(h => {
  const lines = [...h.querySelectorAll(':scope > div, :scope > p > div')];
  const hid = (lines.length ? lines : [h]).some(e => getComputedStyle(e).opacity === '0');
  return hid;
})
"""

PAGE_JS = r"""
() => {
  const norm = (s) => (s || '').replace(/[\u200e\u200b\u00a0]/g, ' ').replace(/\s+/g, ' ').trim();
  const root = document.querySelector('.scroll-content') || document.querySelector('main') || document.body;
  const dispCache = new Map();
  // Inactive tab panes and reviews behind "Load more" are display:none but are
  // the page's content: they are read, and marked with what reveals them.
  const REVEALABLE = '.pt-program-item, .pt-review-item';
  const hidden = (el) => {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      if (dispCache.has(e)) { if (dispCache.get(e)) return true; continue; }
      const cs = getComputedStyle(e);
      const h = (cs.display === 'none' && !e.matches(REVEALABLE)) || e.tagName === 'SCRIPT' || e.tagName === 'STYLE' || e.tagName === 'NOSCRIPT'
        || e.matches('.pt-fallbox, .plyr__controls, .plyr__menu__container, .plyr__sr-only, .plyr__tooltip, .plyr__captions, button.plyr__control--overlaid, #typed, #typed-strings, .typed-cursor');
      dispCache.set(e, h);
      if (h) return true;
    }
    return false;
  };
  const blockOf = (node, stop) => {
    for (let e = node.parentElement; e && e !== stop; e = e.parentElement) {
      const d = getComputedStyle(e).display;
      if (d !== 'inline' && d !== 'contents') return e;
    }
    return stop;
  };
  // Visible text of an element, a line per block box.
  const textOf = (el) => {
    const out = []; let last = null; let line = '';
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (!n.nodeValue.trim() || hidden(n.parentElement)) continue;
      const b = blockOf(n, el);
      if (b !== last && line.trim()) { out.push(norm(line)); line = ''; }
      last = b; line += n.nodeValue;
    }
    if (line.trim()) out.push(norm(line));
    return out.filter(Boolean);
  };
  const headText = (h) => norm(textOf(h).join(' ')) + (h.querySelector('#typed') ? ' …' : '');
  const cls = (e) => (e.className && e.className.toString ? e.className.toString() : '');
  const blockClass = (e) => (cls(e).split(/\s+/).find(c => c.startsWith('pt-')) || e.tagName.toLowerCase());
  const sel = (e) => {
    if (e.id) return '#' + CSS.escape(e.id);
    const parts = [];
    for (let x = e; x && x !== document.body && parts.length < 4; x = x.parentElement) {
      let p = x.tagName.toLowerCase();
      const c = cls(x).split(/\s+/).filter(c => c.startsWith('pt-') && !c.startsWith('pt-btn_')).slice(0, 1);
      if (c.length) p += '.' + c.join('.');
      const sib = x.parentElement ? [...x.parentElement.children].filter(s => s.tagName === x.tagName && cls(s) === cls(x)) : [];
      if (sib.length > 1) p += `:nth-of-type(${[...x.parentElement.children].filter(s => s.tagName === x.tagName).indexOf(x) + 1})`;
      parts.unshift(p);
      if (c.length && /^(section|header|footer)$/.test(x.tagName.toLowerCase())) break;
    }
    return parts.join(' > ');
  };
  const isItem = (e) => {
    if (e.tagName === 'LI') return true;
    if (/^H[1-6]$/.test(e.tagName) || e.querySelector('h1,h2,h3,h4')) return false;
    return cls(e).split(/\s+/).some(c => /^pt-[a-z0-9-]+-(title|name|plan|label|caption|heading|tag)$/.test(c));
  };
  const inFaq = (e) => !!e.closest('.pt-faq-item, details');

  // ---- sections
  const blocks = [...root.children].filter(e => !cls(e).includes('pt-scroller') && !cls(e).includes('scrollbar-track'));
  const sections = [];
  for (const blk of blocks) {
    const bc = blockClass(blk);
    let cur = null;
    const start = (heading, level, el) => {
      cur = {heading, level, id: el ? (el.id || (el.closest('[id]') && el.closest('[id]') !== root && blk.contains(el.closest('[id]')) ? el.closest('[id]').id : '')) : (blk.id || ''),
             block: bc, selector: el ? sel(el) : sel(blk), text: [], items: [], images: [], transform: ''};
      if (el) { const tt = getComputedStyle(el).textTransform; if (tt && tt !== 'none') cur.transform = tt; }
      const pane = el && el.closest('.pt-program-item');
      if (pane) {
        const btn = pane.closest('.pt-program')?.querySelector(`.pt-program-nav[data-program="${CSS.escape(pane.dataset.program)}"]`);
        cur.tab = {label: btn ? norm(btn.textContent) : pane.dataset.program, button: btn ? sel(btn) : '', active_on_load: pane.classList.contains('-active')};
      }
      const rv = el && el.closest('.pt-review-item');
      if (rv && getComputedStyle(rv).display === 'none') cur.needs = 'click "Load more" (.pt-review-more)';
      sections.push(cur);
    };
    const w = document.createTreeWalker(blk, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let lastBlock = null, line = '';
    const flush = () => { if (cur && line.trim()) cur.text.push(norm(line)); line = ''; };
    const skipUntil = { el: null };
    for (let n = w.currentNode; n; n = w.nextNode()) {
      if (skipUntil.el && !skipUntil.el.contains(n)) skipUntil.el = null;
      if (skipUntil.el) continue;
      if (n.nodeType === 1) {
        if (hidden(n)) { skipUntil.el = n; continue; }
        if (/^H[1-4]$/.test(n.tagName) && !inFaq(n)) {
          flush();
          start(headText(n), +n.tagName[1], n);
          skipUntil.el = n; lastBlock = null; continue;
        }
        if (n.tagName === 'IMG' && n.alt && cur) cur.images.push(norm(n.alt));
        if (n.tagName === 'IMG' && n.alt && !cur) { start('', 0, null); cur.images.push(norm(n.alt)); }
        if (isItem(n)) { const t = norm(textOf(n).join(' ')); if (t && t.length < 200) { if (!cur) start('', 0, null); cur.items.push(t); } }
        continue;
      }
      if (!n.nodeValue.trim() || hidden(n.parentElement)) continue;
      if (!cur) start('', 0, null);
      const b = blockOf(n, blk);
      if (b !== lastBlock) flush();
      lastBlock = b; line += n.nodeValue;
    }
    flush();
  }
  for (const s of sections) {
    s.text = [...new Set(s.text)].join('\n');
    s.items = [...new Set(s.items)];
    s.images = [...new Set(s.images)];
    if (!s.heading) s.heading = `[${s.block}] ` + (s.text.split('\n')[0] || s.images.slice(0, 4).join(', ')).slice(0, 60);
  }

  // ---- FAQs
  const faqs = [...document.querySelectorAll('.pt-faq-item')].map(it => ({
    q: norm(textOf(it.querySelector('.pt-faq-title') || it).join(' ')),
    a: norm((it.querySelector('.pt-faq-text') || it.querySelector('.pt-faq-info') || {textContent: ''}).textContent),
    selector: sel(it),
  })).filter(f => f.q);
  for (const d of document.querySelectorAll('details')) {
    const s = d.querySelector('summary');
    if (s) faqs.push({q: norm(s.textContent), a: norm(d.textContent.replace(s.textContent, '')), selector: sel(d)});
  }

  // ---- pricing
  const pricing = [...document.querySelectorAll('.pt-pricing-item')].filter(it => norm(it.querySelector('.pt-pricing-price')?.textContent)).map(it => {
    const price = it.querySelector('.pt-pricing-price');
    const a = it.querySelector('.pt-pricing-action a');
    return {
      plan: norm(it.querySelector('.pt-pricing-plan')?.textContent),
      price: norm(price?.querySelector('span')?.textContent),
      price_note: norm(textOf(price?.querySelector('sup') || document.createElement('i')).join(' · ')),
      brief: norm(textOf(it.querySelector('.pt-pricing-brief') || document.createElement('i')).join(' · ')),
      cta: a ? {text: norm(textOf(a).join(' ')), href: a.getAttribute('href')} : null,
      features: [...it.querySelectorAll('.pt-pricing-list li')].map(l => norm(l.textContent)),
      selector: sel(it),
    };
  });

  // ---- reviews / testimonials (.pt-review-item; some hidden behind "Load more")
  const reviews = [...document.querySelectorAll('.pt-review-item')].map(it => ({
    name: norm(it.querySelector('.pt-review-name')?.textContent),
    position: norm(it.querySelector('.pt-review-position')?.textContent),
    text: norm(it.querySelector('.pt-review-text')?.textContent),
    logo: it.querySelector('.pt-review-logo img')?.alt || '',
    hidden_until_load_more: getComputedStyle(it).display === 'none',
    selector: sel(it),
  })).filter(r => r.text || r.name);

  const cards = [...document.querySelectorAll('.pt-pricing-item')].filter(it => !norm(it.querySelector('.pt-pricing-price')?.textContent)).map(it => ({
    title: norm(it.querySelector('.pt-pricing-plan')?.textContent), text: norm(textOf(it.querySelector('.pt-pricing-brief') || it).join(' ')), selector: sel(it)}));

  // ---- tables
  const tables = [...root.querySelectorAll('table')].map(t => {
    const rows = [...t.querySelectorAll('tr')].map(r => [...r.children].map(c => norm(c.textContent)));
    return {caption: norm(t.querySelector('caption')?.textContent), header: rows[0] || [], rows: rows.slice(1)};
  });

  // ---- tabs (generic: ARIA tabs, Webflow tabs, pt-*tab* classes)
  const tabs = [];
  for (const prog of document.querySelectorAll('.pt-program')) {
    const navs = [...prog.querySelectorAll('.pt-program-nav')];
    if (!navs.length) continue;
    tabs.push({
      kind: 'pt-program', heading: norm(textOf(prog.querySelector('h2') || prog).join(' ')), container: sel(prog),
      how: 'click .pt-program-nav[data-program=KEY]; panes are .pt-program-item[data-program=KEY], the active ones carry -active, the rest are display:none',
      tabs: navs.map(b => ({label: norm(b.textContent), key: b.dataset.program, button: sel(b), active_on_load: b.classList.contains('-active'),
        panes: [...prog.querySelectorAll(`.pt-program-item[data-program="${CSS.escape(b.dataset.program)}"]`)].map(p => ({
          title: norm(p.querySelector('.pt-program-title')?.textContent), text: norm(p.querySelector('.pt-program-text')?.textContent)}))})),
    });
  }
  const tabSets = new Set([...document.querySelectorAll('[role=tablist], .w-tab-menu, [class*="-tabs"], [class*="pt-tab"]')]);
  for (const ts of tabSets) {
    if (ts.closest('.pt-program')) continue;
    const labels = [...ts.querySelectorAll('[role=tab], .w-tab-link, [class*="-tab "], [class*="-tab"]')].filter(e => e.children.length < 6).map(e => ({text: norm(e.textContent), selector: sel(e), active: /active|current|selected/.test(cls(e)) || e.getAttribute('aria-selected') === 'true'}));
    if (labels.length) tabs.push({container: sel(ts), labels});
  }

  // ---- forms and frames
  const labelFor = (f) => {
    if (f.id) { const l = document.querySelector(`label[for="${CSS.escape(f.id)}"]`); if (l) return norm(l.textContent); }
    const l = f.closest('label'); if (l) return norm(l.textContent);
    return norm(f.getAttribute('aria-label') || '');
  };
  const fieldOf = (f) => ({
    tag: f.tagName.toLowerCase(), type: f.type || '', name: f.name || '', id: f.id || '',
    label: labelFor(f), placeholder: f.placeholder || '', required: !!f.required,
    options: f.tagName === 'SELECT' ? [...f.options].map(o => ({value: o.value, text: norm(o.textContent)})) : [],
    selector: sel(f),
  });
  const forms = [...document.querySelectorAll('form')].map(fm => ({
    selector: sel(fm), id: fm.id, name: fm.getAttribute('name') || fm.dataset.name || '', classes: cls(fm),
    action: fm.getAttribute('action') || '', method: (fm.getAttribute('method') || 'get').toLowerCase(),
    fields: [...fm.querySelectorAll('input, select, textarea')].filter(f => f.type !== 'hidden').map(fieldOf),
    hidden_fields: [...fm.querySelectorAll('input[type=hidden]')].map(f => f.name),
    submit: norm([...fm.querySelectorAll('button, input[type=submit]')].map(b => b.value || b.textContent).join(' | ')),
    messages: [...fm.parentElement.querySelectorAll('[class*=success], [class*=error], [class*=fail], [class*=-done], [class*=message]')].map(e => norm(e.textContent)).filter(Boolean),
  }));
  const loose = [...document.querySelectorAll('input, select, textarea')].filter(f => !f.closest('form') && !f.closest('.plyr') && f.type !== 'hidden').map(fieldOf);
  const iframes = [...document.querySelectorAll('iframe')].filter(f => !f.id.startsWith('intercom')).map(f => {
    let host = ''; try { host = new URL(f.src, location.href).host; } catch (e) {}
    return {src: f.src, host, cross_origin: host !== location.host, title: f.title || '', selector: sel(f)};
  });

  // ---- links and CTAs
  const links = [...document.querySelectorAll('a[href]')].map(a => a.href);
  const outbound = [...document.querySelectorAll('a[href]')].filter(a => /^(blog|app)\.sendpotion\.com$/.test(a.host)).map(a => ({
    host: a.host, href: a.href, text: norm(textOf(a).join(' ')) || norm(a.getAttribute('aria-label')),
    area: a.closest('nav.pt-navbar') ? 'nav' : a.closest('footer.pt-footer') ? 'footer' : 'body',
    target: a.getAttribute('target') || '', new_tab: a.getAttribute('target') === '_blank'}));
  const ctas = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href], button')) {
    if (a.closest('nav.pt-navbar, footer.pt-footer, .plyr, .pt-program-navs')) continue;
    const href = a.getAttribute('href') || '';
    let ext = false; try { ext = !!href && new URL(href, location.href).host !== location.host; } catch (e) {}
    const btn = /pt-btn|btn/.test(cls(a)) || a.tagName === 'BUTTON';
    if (!btn && !ext) continue;
    const text = norm(textOf(a).join(' ')) || norm(a.getAttribute('aria-label'));
    const key = text + '|' + href;
    if (seen.has(key)) continue; seen.add(key);
    ctas.push({text, href, target: a.getAttribute('target') || '', selector: sel(a)});
  }

  // ---- stats: short number-like leaves with their label
  const stats = [];
  for (const e of root.querySelectorAll('*')) {
    if (e.children.length || hidden(e)) continue;
    const t = norm(e.textContent);
    if (!/^[$€£]?\d[\d,.]*\s*(%|\+|x|k|K|M|B|hrs?|mins?|sec)?\+?$/.test(t) || /^\d+\.$/.test(t)) continue;
    const box = e.parentElement?.parentElement || e.parentElement;
    const label = norm(textOf(box).join(' ').replace(t, ''));
    if (label && label.length < 160 && !e.closest('.pt-pricing-item, .pt-advantage')) stats.push({value: t, label});
  }

  // ---- widgets
  const widgets = [];
  const add = (kind, e, note) => widgets.push({kind, selector: sel(e), note: note || ''});
  document.querySelectorAll('[class*=slider], [class*=swiper], [class*=carousel], [class*=marquee], [class*=ticker]').forEach(e => { if (!e.closest('[class*=slider] [class*=slider]')) add('slider/marquee', e, cls(e)); });
  if (document.querySelector('#typed')) add('typed-text', document.querySelector('#typed'), 'typed.js types into the h1 (span#typed), cycling: ' + [...document.querySelectorAll('#typed-strings > *')].map(e => norm(e.textContent)).join(' / ') + '; the h1 is recorded with " …" in place of the moving word');
  document.querySelectorAll('.pt-fallbox').forEach(e => add('falling-words', e, 'decorative physics words: ' + [...e.querySelectorAll('.pt-fallbox-item')].map(i => norm(i.textContent)).join(' / ')));
  const vids = document.querySelectorAll('.scroll-content video'); if (vids.length) widgets.push({kind: 'video', selector: '', note: vids.length + ' <video> elements (autoplay loops and players)'});
  document.querySelectorAll('[class*=modal], [class*=popup], [class*=lightbox]').forEach(e => add('modal', e, cls(e)));
  document.querySelectorAll('[class*=dropdown], .w-dropdown').forEach(e => add('dropdown', e, cls(e)));
  document.querySelectorAll('[class*=player], .plyr').forEach(e => { if (!e.parentElement.closest('[class*=player], .plyr')) add('video-player', e, cls(e)); });

  const classes = [...new Set([...root.querySelectorAll('[class]')].flatMap(e => cls(e).split(/\s+/)).filter(c => /^pt-[a-z0-9]+(-[a-z0-9]+)?$/.test(c)))].sort();

  return {
    title: document.title,
    description: document.querySelector('meta[name=description]')?.content || '',
    canonical: document.querySelector('link[rel=canonical]')?.href || '',
    alternates: Object.fromEntries([...document.querySelectorAll('link[rel=alternate][hreflang]')].map(l => [l.hreflang, l.href])),
    lang: document.documentElement.lang,
    headings: [...root.querySelectorAll('h1,h2,h3,h4')].filter(h => !inFaq(h)).map(headText).filter(Boolean),
    sections, faqs, pricing, cards, reviews, tables, tabs, forms, loose_fields: loose, iframes, ctas, outbound, stats, widgets, links, classes,
    text: textOf(root).filter((l, i, a) => a.indexOf(l) === i).join('\n'),
  };
}
"""

CHROME_JS = r"""
() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const nav = document.querySelector('nav.pt-navbar');
  const foot = document.querySelector('footer.pt-footer');
  const link = (a) => ({text: norm(a.textContent) || a.getAttribute('aria-label') || '', href: a.getAttribute('href'), target: a.getAttribute('target') || '', classes: a.className});
  const fixed = [...document.querySelectorAll('body *')].filter(e => {
    const cs = getComputedStyle(e); return (cs.position === 'fixed' || cs.position === 'sticky') && e.getBoundingClientRect().width > 0;
  }).map(e => ({tag: e.tagName.toLowerCase(), id: e.id, classes: e.className.toString(), rect: e.getBoundingClientRect().toJSON(), z: getComputedStyle(e).zIndex}));
  return {
    top_nav: nav ? [...nav.querySelectorAll('.pt-navbar-navs a')].map(link) : [],
    language_switch: nav ? [...nav.querySelectorAll('.pt-navbar-lang a')].map(link) : [],
    nav_actions: nav ? [...nav.querySelectorAll('.pt-navbar-actions a, .pt-navbar-toggle button')].map(link) : [],
    footer_nav: foot ? [...foot.querySelectorAll('.pt-footer-navs a')].map(link) : [],
    footer_cta: foot ? [...foot.querySelectorAll('.pt-footer-text a')].map(link) : [],
    footer_social: foot ? [...foot.querySelectorAll('.pt-footer-socials a')].map(link) : [],
    footer_links: foot ? [...foot.querySelectorAll('.pt-footer-links a')].map(link) : [],
    footer_text: foot ? norm(foot.querySelector('.pt-footer-text')?.innerText) : '',
    fixed_elements: fixed,
    html_class: document.documentElement.className,
    globals: Object.keys(window).filter(k => /intercom|hubspot|hbspt|gtag|dataLayer|Webflow|jQuery|gsap|ScrollTrigger|Plyr|Typed|rewardful|_hs|posthog|clarity|hotjar|fbq|lintrk|Calendly|grecaptcha/i.test(k)),
    scripts: [...document.querySelectorAll('script[src]')].map(s => s.src),
    intercom: (() => { const s = window.intercomSettings; return s ? {app_id: s.app_id, settings_keys: Object.keys(s)} : null; })(),
  };
}
"""

# Does a click on an in-site link reload the document, and how does a FAQ open?
PROBE_FAQ_JS = r"""
async () => {
  const it = document.querySelector('.pt-faq-item');
  if (!it) return null;
  const info = it.querySelector('.pt-faq-info');
  const snap = () => { const cs = getComputedStyle(info); return {item_class: it.className, height: cs.height, display: cs.display, overflow: cs.overflow, opacity: cs.opacity, inline_style: info.getAttribute('style') || ''}; };
  const before = snap();
  it.querySelector('.pt-faq-toggle').click();
  await new Promise(r => setTimeout(r, 900));
  const after = snap();
  it.querySelector('.pt-faq-toggle').click();
  await new Promise(r => setTimeout(r, 900));
  const others = [...document.querySelectorAll('.pt-faq-item')].map(e => e.className);
  return {toggle: '.pt-faq-item .pt-faq-toggle', answer: '.pt-faq-item .pt-faq-info > .pt-faq-text', before, after, closed_again: snap(), siblings_after: others.slice(0, 3)};
}
"""

BLOG_JS = r"""
() => {
  const norm = (s) => (s || '').replace(/[\u200e\u200b\u00a0]/g, ' ').replace(/\s+/g, ' ').trim();
  const art = document.querySelector('article') || document.body;
  const q = (s) => art.querySelector(s);
  let ld = null;
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); if (j && (j['@type'] === 'NewsArticle' || j['@type'] === 'Article' || j.headline)) ld = j; } catch (e) {}
  }
  const titleEl = q('[data-testid=storyTitle]') || q('h1');
  const subEl = q('.pw-subtitle-paragraph');
  // Hydrated, Medium marks body blocks [data-selectable-paragraph]; its server HTML
  // (what a JS-less render sees) has the same blocks with the same 4-hex ids.
  let paras = [...art.querySelectorAll('[data-selectable-paragraph]')];
  if (!paras.length) paras = [...art.querySelectorAll(':is(h1,h2,h3,h4,h5,h6,p,li,pre,blockquote,figcaption)[id]')];
  paras = paras.filter(e => e !== titleEl && e !== subEl && !e.closest('[data-testid=storyTitle]'));
  const headings = [];
  const lines = [];
  for (const p of paras) {
    const t = norm(p.innerText || p.textContent);
    if (!t) continue;
    const tag = p.tagName;
    if (/^H[1-6]$/.test(tag)) { headings.push({level: +tag[1], tag: tag.toLowerCase(), id: p.id || '', text: t}); lines.push('## ' + t); }
    else if (tag === 'LI') lines.push('- ' + t);
    else if (tag === 'FIGCAPTION') lines.push('[caption] ' + t);
    else if (tag === 'PRE') lines.push('```' + t + '```');
    else if (tag === 'BLOCKQUOTE') lines.push('> ' + t);
    else lines.push(t);
  }
  const tags = [...new Set([...document.querySelectorAll('a[href*="/tag/"]')].map(a => norm(a.textContent)).filter(Boolean))];
  const links = [...new Set([...art.querySelectorAll('a[href]')].map(a => a.href))];
  return {
    title: norm(titleEl?.textContent) || ld?.headline || document.title,
    subtitle: norm(subEl?.textContent),
    author: norm(document.querySelector('[data-testid=authorName]')?.textContent) || (ld?.author?.name || ''),
    date: norm(document.querySelector('[data-testid=storyPublishDate]')?.textContent),
    date_iso: ld?.datePublished || '',
    modified_iso: ld?.dateModified || '',
    reading_time: norm(document.querySelector('[data-testid=storyReadTime]')?.textContent),
    description: document.querySelector('meta[name=description]')?.content || '',
    canonical: document.querySelector('link[rel=canonical]')?.href || '',
    member_only: /Member-only story/.test(document.body.innerText.slice(0, 4000)),
    tags, headings, text: lines.join('\n'), links,
    paragraph_selector: '[data-selectable-paragraph] (after hydration); article :is(h2,h3,p,li)[id] in the server HTML',
    heading_ids: headings.filter(h => h.id).length,
  };
}
"""

BLOG_LIST_JS = r"""
() => ({title: document.title, text: (document.querySelector('main') || document.body).innerText.slice(0, 6000),
        links: [...new Set([...document.querySelectorAll('a[href]')].map(a => a.href.split('?')[0]))]})
"""

# --------------------------------------------------------------------------- cache


def cache_path(url: str, kind: str) -> Path:
    name = hashlib.sha1(url.encode()).hexdigest()[:16]
    tail = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        urllib.parse.urlsplit(url).path.strip("/").rsplit("/", 1)[-1] or "index",
    )[-60:]
    return CACHE / kind / f"{name}-{tail}.json"


def cache_get(url: str, kind: str) -> dict[str, Any] | None:
    p = cache_path(url, kind)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def cache_put(url: str, kind: str, data: dict[str, Any]) -> None:
    p = cache_path(url, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- urls


def site_path(url: str) -> str | None:
    """The canonical path of a main-site URL (trailing slash, no query), or None."""
    u = urllib.parse.urlsplit(urllib.parse.urljoin(SITE + "/", url))
    if u.scheme not in ("http", "https") or u.netloc.removeprefix("www.") != "sendpotion.com":
        return None
    path = u.path or "/"
    if path.startswith(("/assets/", "/cdn-cgi/", *I18N)) or re.search(r"\.[a-z0-9]{2,5}$", path):
        return None
    return path if path.endswith("/") else path + "/"


def blog_path(url: str) -> str | None:
    u = urllib.parse.urlsplit(url)
    if u.netloc != "blog.sendpotion.com":
        return None
    path = u.path.rstrip("/")
    return path if POST_RE.match(path) else None


def headers_of(h: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in sorted(h.items()) if k.lower() in HEADERS_KEPT}


# --------------------------------------------------------------------------- crawl


async def render(ctx: Any, url: str, *, site: bool) -> dict[str, Any]:
    page = await ctx.new_page()
    try:
        resp = await page.goto(
            url, wait_until="load" if site else "domcontentloaded", timeout=90_000
        )
        if site:
            await page.wait_for_timeout(2500)
        out: dict[str, Any] = {
            "url": url,
            "final_url": page.url,
            "status": resp.status if resp else 0,
            "headers": headers_of(await resp.all_headers()) if resp else {},
            "fetched": time.strftime("%Y-%m-%d"),
        }
        if site:
            hidden0 = await page.evaluate(HIDDEN_JS)
            out["scroll"] = await page.evaluate(SCROLL_JS)
            data = await page.evaluate(PAGE_JS)
            heads = [s for s in data["sections"] if s["level"] > 0]
            for s, hid in zip(heads, hidden0, strict=False):
                if hid:
                    s["reveal"] = "GSAP line reveal: opacity 0 until scrolled into view"
            out["chrome"] = await page.evaluate(CHROME_JS)
            if "pt-faq" in " ".join(data.get("classes", [])):
                out["faq_probe"] = await page.evaluate(PROBE_FAQ_JS)
        else:
            data = await page.evaluate(BLOG_JS if blog_path(url) else BLOG_LIST_JS)
        out["data"] = data
        return out
    finally:
        await page.close()


async def probe_navigation(ctx: Any) -> dict[str, Any]:
    """Click a top-nav link and a footer link; report whether the document reloaded."""
    page = await ctx.new_page()
    res: dict[str, Any] = {}
    try:
        await page.goto(SITE + "/", wait_until="load", timeout=90_000)
        await page.wait_for_timeout(2500)
        for name, sel_ in (
            ("top_nav_pricing", 'nav a[href="/pricing/"]'),
            ("footer_faq", 'footer a[href="/faq/"]'),
        ):
            await page.evaluate("window.__marker = 42")
            await page.evaluate(f"document.querySelector('{sel_}').click()")
            await page.wait_for_timeout(3500)
            res[name] = {
                "url_after": page.url,
                "document_kept": await page.evaluate("window.__marker === 42"),
                "title_after": await page.title(),
            }
            await page.go_back()
            await page.wait_for_timeout(2500)
            res[name]["back_url"] = page.url
            res[name]["back_document_kept"] = await page.evaluate("window.__marker === 42")
        # How scrolling works: scrollIntoView vs a wheel event on the container.
        res["scroll"] = await page.evaluate(
            r"""async () => {
              const sleep = (ms) => new Promise(r => setTimeout(r, ms));
              const h = [...document.querySelectorAll('h2')].find(e => /Pricing/.test(e.textContent));
              const sc = document.querySelector('.scroll-content'); const lay = document.querySelector('.pt-layout');
              const t0 = h.getBoundingClientRect().top; h.scrollIntoView(); await sleep(700);
              const t1 = h.getBoundingClientRect().top;
              lay.dispatchEvent(new WheelEvent('wheel', {deltaY: t1 - 120, bubbles: true, cancelable: true})); await sleep(1500);
              return {window_scrollY: scrollY, document_scroll_height: document.scrollingElement.scrollHeight,
                      content_height: sc.scrollHeight, heading_top_before: t0, after_scrollIntoView: t1,
                      after_wheel_to_120: h.getBoundingClientRect().top, content_transform: sc.style.transform};
            }"""
        )
    except Exception as e:  # a probe must not stop the crawl
        res["error"] = repr(e)
    finally:
        await page.close()
    return res


async def probe_blog_spa(ctx: Any, post_url: str) -> dict[str, Any]:
    page = await ctx.new_page()
    res: dict[str, Any] = {}
    try:
        await page.goto(BLOG + "/", wait_until="load", timeout=90_000)
        await page.wait_for_timeout(3000)
        await page.evaluate("window.__marker = 42")
        path = urllib.parse.urlsplit(post_url).path
        clicked = await page.evaluate(
            f"""() => {{ const a = [...document.querySelectorAll('a[href*="{path}"]')][0]; if (a) {{ a.click(); return a.href; }} return null; }}"""
        )
        await page.wait_for_timeout(4000)
        res = {
            "clicked": clicked,
            "url_after": page.url,
            "document_kept": await page.evaluate("window.__marker === 42"),
        }
    except Exception as e:
        res["error"] = repr(e)
    finally:
        await page.close()
    return res


async def fetch_text(ctx: Any, url: str) -> str:
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, wait_until="load", timeout=90_000)
        body = await resp.text() if resp else ""
        if "<loc>" not in body and "<item>" not in body:
            body = await page.content()
        return body
    finally:
        await page.close()


async def crawl_async(offline: bool, refresh: bool) -> None:
    results_site: dict[str, dict[str, Any]] = {}
    results_blog: dict[str, dict[str, Any]] = {}
    misses: list[str] = []
    meta: dict[str, Any] = {}

    async def get(ctx: Any, url: str, *, site: bool) -> dict[str, Any] | None:
        kind = "site" if site else "blog"
        if not refresh and (c := cache_get(url, kind)):
            return c
        if offline or ctx is None:
            misses.append(url)
            return None
        for attempt in range(4 if not site else 3):
            try:
                r = await render(ctx, url, site=site)
                if not site:
                    await asyncio.sleep(BLOG_PAUSE)
                if r["status"] >= 400:
                    raise RuntimeError(f"HTTP {r['status']}")
                cache_put(url, kind, r)
                print(f"  {r['status']} {url}", file=sys.stderr)
                return r
            except Exception as e:
                if attempt == (3 if not site else 2):
                    print(f"  ! {url}: {e}", file=sys.stderr)
                    misses.append(url)
                    return None
                print(f"  retry {url}: {e}", file=sys.stderr)
                await asyncio.sleep(BLOG_BACKOFF * (attempt + 1) if not site else 3 * (attempt + 1))
        return None

    async def run(ctx: Any, bctx: Any) -> None:
        sem = asyncio.Semaphore(PARALLEL)
        blog_sem = asyncio.Semaphore(1)

        async def one(url: str, site: bool) -> tuple[str, dict[str, Any] | None]:
            async with sem if site else blog_sem:
                return url, await get(ctx if site else bctx, url, site=site)

        # ---- main site: sitemap, then every same-host link, breadth first
        seeds = ["/"]
        sm = cache_get(SITEMAP, "meta")
        if (sm is None or refresh) and ctx is not None and not offline:
            sm = {"body": await fetch_text(ctx, SITEMAP)}
            cache_put(SITEMAP, "meta", sm)
        if sm:
            seeds += [
                p
                for u in re.findall(r"<loc>([^<]+)", sm["body"])
                if (p := site_path(u.replace("&amp;", "&")))
            ]
        meta["sitemap_paths"] = sorted(set(seeds))
        todo = list(dict.fromkeys(seeds))
        seen = set(todo)
        while todo:
            batch, todo = todo, []
            for url_path, r in await asyncio.gather(*(one(SITE + p, True) for p in batch)):
                if not r:
                    continue
                results_site[site_path(url_path) or url_path] = r
                for link in r["data"]["links"]:
                    if (p := site_path(link)) and p not in seen:
                        seen.add(p)
                        todo.append(p)

        # ---- blog: Medium sitemap + RSS, then links between posts
        bs = cache_get(BLOG_SITEMAP, "meta")
        if (bs is None or refresh) and ctx is not None and not offline:
            bs = {
                "body": await fetch_text(ctx, BLOG_SITEMAP),
                "feed": await fetch_text(ctx, BLOG + "/feed"),
            }
            cache_put(BLOG_SITEMAP, "meta", bs)
        bs = bs or {"body": "", "feed": ""}
        locs = re.findall(r"<loc>([^<]+)", bs["body"])
        feed_links = re.findall(r"<link>([^<]+)</link>", bs.get("feed", ""))
        meta["blog_sitemap_all"] = locs
        meta["blog_tags"] = sorted(u for u in locs if "/tagged/" in u)
        meta["blog_feed_posts"] = [p for u in feed_links if (p := blog_path(u.split("?")[0]))]
        posts = list(
            dict.fromkeys(p for u in locs + feed_links if (p := blog_path(u.split("?")[0])))
        )
        seen_b = set(posts)
        todo_b = posts
        while todo_b:
            batch, todo_b = todo_b, []
            for url, r in await asyncio.gather(*(one(BLOG + p, False) for p in batch)):
                if not r:
                    continue
                results_blog[urllib.parse.urlsplit(url).path] = r
                for link in r["data"].get("links", []):
                    if (p := blog_path(link.split("?")[0])) and p not in seen_b:
                        seen_b.add(p)
                        todo_b.append(p)
        for extra in ("/", "/about"):
            if r := await get(bctx, BLOG + extra, site=False):
                meta["blog_" + ("home" if extra == "/" else "about")] = r

        # ---- probes (cached as one record)
        pr = cache_get(SITE + "#probes", "meta")
        if (pr is None or refresh) and ctx is not None and not offline:
            first_post = BLOG + (meta["blog_feed_posts"] or posts or ["/"])[0]
            pr = {
                "site": await probe_navigation(ctx),
                "blog": await probe_blog_spa(ctx, first_post),
            }
            cache_put(SITE + "#probes", "meta", pr)
        meta["probes"] = pr or {}

    if offline:
        await run(None, None)
    else:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US"
            )
            # The blog is read from Medium's server HTML with JavaScript off: a hydrated
            # Medium page fires a burst of /_/graphql calls through the custom domain,
            # and Cloudflare answers the next post with a 403.
            bctx = await browser.new_context(
                user_agent=UA, java_script_enabled=False, locale="en-US"
            )

            async def lean(route: Any) -> None:
                if route.request.resource_type == "document":
                    await route.continue_()
                else:
                    await route.abort()

            await bctx.route("**/*", lean)
            try:
                await run(ctx, bctx)
            finally:
                await browser.close()

    write_outputs(results_site, results_blog, meta)
    if misses:
        print(f"{len(misses)} not fetched: {misses[:10]}", file=sys.stderr)


def page_record(r: dict[str, Any]) -> dict[str, Any]:
    d = r["data"]
    path = site_path(r["final_url"]) or site_path(r["url"]) or "/"
    for key in ("links", "classes"):
        d.pop(key, None)
    rec = {"path": path, "url": SITE + path, "status": r["status"], **d}
    rec["sections"] = [
        {k: v for k, v in s.items() if v not in ("", [], None)}
        | {"heading": s["heading"], "level": s["level"]}
        for s in d["sections"]
    ]
    if "faq_probe" in r:
        rec["faq_probe"] = r["faq_probe"]
    return rec


def write_outputs(
    site: dict[str, dict[str, Any]], blog: dict[str, dict[str, Any]], meta: dict[str, Any]
) -> None:
    L3.mkdir(exist_ok=True)
    by_path: dict[str, dict[str, Any]] = {}
    for path in sorted(site):
        rec = page_record(site[path])
        rec.pop("faq_probe", None)
        if rec["path"] != path:  # a redirect: keep the target once, note the alias
            rec = by_path.get(rec["path"], rec)
            rec.setdefault("aliases", []).append(path)
        by_path.setdefault(rec["path"], rec)
    pages = list(by_path.values())

    notes: dict[str, dict[str, Any]] = (
        json.loads(NOTES.read_text(encoding="utf-8")) if NOTES.exists() else {}
    )
    posts, missing = [], []
    for path, r in blog.items():
        d = r["data"]
        if "headings" not in d:
            continue
        note = notes.get(path, {})
        if not note:
            missing.append(path)
        posts.append(
            {
                "url": BLOG + path,
                "path": path,
                "title": d["title"],
                "subtitle": d["subtitle"],
                "author": d["author"],
                "date": d["date"],
                "date_iso": d["date_iso"],
                "reading_time": d["reading_time"],
                "tags": d["tags"],
                "member_only": d["member_only"],
                "description": d["description"],
                "summary": note.get("summary", ""),
                "use_cases": note.get("use_cases", []),
                "group": note.get("group", ""),
                "headings": d["headings"],
                "text": d["text"],
            }
        )
    posts.sort(key=lambda p: p["date_iso"], reverse=True)

    home = site.get("/")
    chrome = (home or {}).get("chrome", {})
    hosts = Counter()
    for r in site.values():
        for c in r["data"].get("ctas", []):
            h = urllib.parse.urlsplit(urllib.parse.urljoin(SITE, c["href"] or "")).netloc
            if h and h != "sendpotion.com":
                hosts[h] += 1
    for k in (
        "top_nav",
        "footer_nav",
        "footer_social",
        "footer_links",
        "nav_actions",
        "footer_cta",
    ):
        for a in chrome.get(k, []):
            h = urllib.parse.urlsplit(urllib.parse.urljoin(SITE, a.get("href") or "")).netloc
            if h and h != "sendpotion.com":
                hosts[h] += 1
    faq_probe = next((r["faq_probe"] for r in site.values() if r.get("faq_probe")), None)
    blog_any = next(iter(blog.values()), None)
    site_json = {
        "crawled": time.strftime("%Y-%m-%d"),
        "site": {
            "host": "sendpotion.com",
            "headers": (home or {}).get("headers", {}),
            "stack": "Custom static site on Amazon S3 behind CloudFront (not Webflow). GSAP + ScrollTrigger animations, "
            "Smooth Scrollbar on .pt-layout[data-scrollbar], an AJAX router that swaps #view-main and pushes history, typed.js, "
            "Plyr video players, Intercom, Rewardful, Google gtag.",
            "chrome": chrome,
            "faq_probe": faq_probe,
            "sitemap_paths": meta.get("sitemap_paths", []),
            "external_hosts": dict(hosts.most_common()),
        },
        "blog": {
            "host": "blog.sendpotion.com",
            "headers": (blog_any or {}).get("headers", {}),
            "home_headers": (meta.get("blog_home") or {}).get("headers", {}),
            "stack": "Medium publication on a custom domain (Cloudflare in front; x-powered-by: Medium / Express).",
            "tags": meta.get("blog_tags", []),
            "feed_posts": meta.get("blog_feed_posts", []),
            "about": ((meta.get("blog_about") or {}).get("data") or {}).get("text", "")[:3000],
            "home": ((meta.get("blog_home") or {}).get("data") or {}).get("text", "")[:3000],
        },
        "probes": meta.get("probes", {}),
    }
    for name, data in (("pages.json", pages), ("blog.json", posts), ("site.json", site_json)):
        (L3 / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    print(f"pages {len(pages)}, posts {len(posts)} -> {L3}")
    if missing:
        print(
            f"{len(missing)} posts have no blog_notes.json entry: {missing[:5]}...", file=sys.stderr
        )


# --------------------------------------------------------------------------- search

TOKEN = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*")
STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "do",
        "does",
        "can",
    ]
)


def tokens(s: str) -> list[str]:
    return [t for t in TOKEN.findall(s.lower()) if t not in STOP]


def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """BM25 over page sections, FAQs and blog posts (standard library only)."""
    passages: list[tuple[dict[str, Any], str]] = []
    for p in json.loads((L3 / "pages.json").read_text(encoding="utf-8")):
        for s in p["sections"]:
            passages.append(
                (
                    {"kind": "section", "path": p["path"], "title": s["heading"]},
                    f"{s['heading']}\n{s.get('text', '')}\n{' '.join(s.get('items', []))}",
                )
            )
        for f in p["faqs"]:
            passages.append(
                ({"kind": "faq", "path": p["path"], "title": f["q"]}, f"{f['q']}\n{f['a']}")
            )
    for b in json.loads((L3 / "blog.json").read_text(encoding="utf-8")):
        passages.append(
            (
                {"kind": "post", "path": b["url"], "title": b["title"]},
                f"{b['title']}\n{b['summary']}\n{' '.join(b['use_cases'])}\n{b['text']}",
            )
        )
    q = tokens(query)
    toks = [Counter(tokens(t)) for _, t in passages]
    n = len(passages)
    df: Counter[str] = Counter()
    for tf in toks:
        df.update(tf.keys())
    avg = sum(sum(tf.values()) for tf in toks) / max(n, 1)
    out = []
    for (hit, text), tf in zip(passages, toks, strict=True):
        length = sum(tf.values())
        s = 0.0
        for w in q:
            if f := tf.get(w, 0):
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * f * 2.4 / (f + 1.4 * (0.25 + 0.75 * length / avg))
        if s > 0:
            low = text.lower()
            at = max(0, low.find(q[0]) - 60) if q else 0
            out.append(
                hit | {"score": round(s, 2), "snippet": " ".join(text[at : at + 240].split())}
            )
    return sorted(out, key=lambda h: -h["score"])[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[2])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="render (or read from cache) and write L3/*.json")
    c.add_argument("--offline", action="store_true", help="cache only, no network")
    c.add_argument("--refresh", action="store_true", help="re-render everything")
    s = sub.add_parser("search", help="search L3 (no network)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()
    if args.cmd == "crawl":
        asyncio.run(crawl_async(args.offline, args.refresh))
    else:
        for r in search(args.query, args.limit):
            print(
                f"{r['score']:6.2f}  {r['kind']:8} {r['path']}\n        {r['title']}\n        {r['snippet']}\n"
            )


if __name__ == "__main__":
    main()
