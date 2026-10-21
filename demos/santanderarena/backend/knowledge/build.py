# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Santander Arena's L3 knowledge: every page of www.santanderarena.cl, as
data, read from a real browser.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON. Network is touched only by ``crawl``; each page's
extraction is cached outside the repository, so a re-run is cheap.

santanderarena.cl is a Prontus CMS site: server-rendered HTML, a full page load
per navigation, Swiper carousels whose off-screen slides are already in the DOM,
and article bodies pasted from a WYSIWYG editor, so many sections have no
``h1``-``h6`` at all. Their titles are ``span.titulos``, ``p.subtit1`` or a
paragraph that is nothing but ``<strong>``. The crawl drives headless Chromium
(Playwright) and reads the rendered DOM after scrolling each page to the bottom.
Run from ``voqalize/demos`` (Chromium must be installed once with
``playwright install chromium``)::

    uv run --no-project --with playwright python \
        santanderarena/backend/knowledge/build.py crawl
    uv run --no-project --with playwright python \
        santanderarena/backend/knowledge/build.py crawl --refresh
    uv run --no-project python santanderarena/backend/knowledge/build.py crawl --offline

``crawl`` starts at ``/`` and walks every same-host link breadth first (header,
menus, body and footer), skipping assets, PDFs, ``/cdn-cgi/``, search and any URL
with a query string, up to ``--max-pages``. It writes, next to this file:

- ``L3/pages.json`` — one record per page that answered 200, in BFS order:
  ``{path, url, title, description, kind, breadcrumbs, sections, headings,
  faqs, cards, tickets, documents, forms, iframes, text}``. ``path``, ``title``,
  ``description``, ``sections: [{heading, text, items}]``, ``headings``,
  ``faqs: [{q, a}]`` and ``text`` are the keys the shared ``knowledge.py``
  loader reads. The rest:

  - ``kind``: ``home``, ``event`` (``/nuestra-cartelera/...``), ``news``
    (``/arena-news/<slug>``), ``listing`` (the cartelera, news and fans indexes
    and Prontus ``taxport`` pages) or ``page``.
  - ``sections`` are in page order. ``heading`` is the element's
    ``innerText`` (so it is what renders, CSS ``text-transform`` included);
    ``dom_text`` is added when the DOM text differs. ``level`` is 1 for the page
    title block, else the tag's level; ``pseudo`` marks a title that is not an
    ``h`` tag; ``selector`` is a CSS path to the element. Text that comes before
    the first title belongs to a section with an empty heading.
  - ``cards``: every ``article.card`` / ``aside.card`` (hidden carousel slides
    included, Swiper duplicates dropped): ``{title, text, href, kind, section,
    date_attr, in_swiper, tickets}``.
  - ``tickets``: every link to a booking site (puntoticket.com and the like),
    ``{label, url, near, role}``; ``near`` is the card title around the link,
    else the section heading, else the page title; ``role`` is ``tickets``,
    ``parking`` or ``vip`` when the button's class says so.
  - ``faqs`` also carry ``group`` (the section heading above the question).
    Questions are numbered ``<strong>`` paragraphs (``1. ¿...?``) or accordion
    items (``details``/``.accordionItem``).

- ``L3/events.json`` — every event the cartelera lists or the crawl reached
  (past events included), sorted by date: ``{name, path, url, category,
  date_text, time_text, when_text, date, time, date_source, upcoming, summary,
  description, tickets_url, parking_url, vip_url, producer}``. ``date`` comes
  from the cartelera card's ``data-fecha`` when there is one
  (``date_source: "cartelera"``); else from a year written on the page; else the
  first date on or after the article's Prontus publication date (in its image
  paths); else the next such day-month from today. ``summary`` is hand-written
  English, kept in ``event_notes.json`` beside this file keyed by path, so a
  re-crawl keeps it; an event without a note is listed by the build.
- ``L3/site.json`` — the navigation (desktop menu with submenus, the secondary
  links above it, the mobile menu, footer columns), contact details, social
  links, the footer's legal line, redirects, broken internal links, response
  headers and every outbound host.

It also regenerates two L2 files from that data: ``L2/site-map.md`` and
``L2/events-index.md``.

``--offline`` builds from the cache only; ``--refresh`` re-renders everything.
The cache is ``$XDG_CACHE_HOME/voqalize-santanderarena`` (``~/.cache`` by
default).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
L2 = HERE / "L2"
L3 = HERE / "L3"
NOTES = HERE / "event_notes.json"
HOST = "www.santanderarena.cl"
SITE = f"https://{HOST}"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-santanderarena"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MAX_PAGES = 600
PARALLEL = 4
TEXT_CAP = 12_000
SECTION_CAP = 4_000
EVENT_TEXT_CAP = 2_000
HEADERS_KEPT = (
    "server",
    "content-type",
    "cache-control",
    "content-security-policy",
    "permissions-policy",
    "x-frame-options",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
    "referrer-policy",
)
SKIP_EXT = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|webp|ico|mp4|mp3|webm|zip|docx?|xlsx?|pptx?|css|js|json|xml)$",
    re.I,
)
SKIP_PATH = re.compile(r"^/(cdn-cgi|prontus|search|buscador)\b|/imag/|/mmedia/|/docs/", re.I)
BOOKING = re.compile(r"(^|\.)(puntoticket\.com|ticketmaster\.\w+|passline\.com|eventbrite\.\w+)$")
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )
    )
}
MONTHS["setiembre"] = 9

# ─── Browser-side scripts ─────────────────────────────────────────────────────

SCROLL_JS = r"""
async () => {
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  let y = 0;
  for (let i = 0; i < 60; i++) {
    y += Math.max(400, Math.floor(window.innerHeight * 0.8));
    window.scrollTo(0, y);
    await pause(120);
    if (y >= document.documentElement.scrollHeight) break;
  }
  window.scrollTo(0, 0);
  await pause(150);
}
"""

PAGE_JS = r"""
() => {
  const T = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return ''; } };

  // Cloudflare hides e-mail addresses behind a script; decode them in place.
  const cf = (hex) => {
    const k = parseInt(hex.slice(0, 2), 16);
    let s = '';
    for (let i = 2; i < hex.length; i += 2) s += String.fromCharCode(parseInt(hex.slice(i, i + 2), 16) ^ k);
    return s;
  };
  for (const el of document.querySelectorAll('[data-cfemail]')) el.textContent = cf(el.getAttribute('data-cfemail'));
  for (const a of document.querySelectorAll('a[href*="/cdn-cgi/l/email-protection#"]')) {
    a.setAttribute('href', 'mailto:' + cf(a.getAttribute('href').split('#')[1]));
  }

  // Count-up stats animate from 0 when scrolled into view; read their target.
  for (const el of document.querySelectorAll('[data-target]')) {
    if (/^[\d.,]+$/.test(el.getAttribute('data-target'))) el.textContent = el.getAttribute('data-target');
  }

  // The shortest selector that is unique on the page: the element's own tag and
  // classes, then nearer ancestors prepended until only it matches.
  const step = (n) => {
    let p = n.tagName.toLowerCase();
    const cls = [...n.classList].filter((c) => /^[A-Za-z][\w-]*$/.test(c)).slice(0, 2);
    if (cls.length) p += '.' + cls.join('.');
    const sib = n.parentElement ? [...n.parentElement.children].filter((c) => c.matches(p)) : [];
    if (sib.length > 1) p += `:nth-of-type(${[...n.parentElement.children].filter((c) => c.tagName === n.tagName).indexOf(n) + 1})`;
    return p;
  };
  const cssPath = (el) => {
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return '#' + el.id;
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.body; n = n.parentElement) {
      parts.unshift(n.id && /^[A-Za-z][\w-]*$/.test(n.id) ? '#' + n.id : step(n));
      const sel = parts.join(' > ');
      try { if (document.querySelectorAll(sel).length === 1 && document.querySelector(sel) === el) return sel; } catch (e) { /* keep climbing */ }
    }
    return parts.join(' > ');
  };

  const SKIP = [
    'script', 'style', 'noscript', 'template', 'svg', 'iframe', 'select', 'option', 'input',
    'textarea', 'button', 'video', 'audio', 'header#header', 'footer.footer', '.menu-responsive',
    '.lateral_bar', '.ag-translate-popper-host', '[class^="host-"]', '.swiper-pagination',
    '.swiper-button-next', '.swiper-button-prev', '.breadcrumbs', 'nav.filter', '.empty-state',
    '.swiper-slide-duplicate', '.btn__primary', '.btn__secondary', '.btn__icon', '.tooltip-text',
    'aside.card__event--sidebar', '.access1', 'ul.tools',
  ].join(',');
  const BLOCK = /^(P|DIV|LI|UL|OL|H[1-6]|ARTICLE|SECTION|ASIDE|HEADER|FIGURE|FIGCAPTION|TABLE|TR|TD|TH|BLOCKQUOTE|PRE|BR|DT|DD)$/;
  const FAQ_Q = /^(?:\d+\s*[.\-)]*\s*-?\s*)?(¿[^?]{3,}\?)\s*$/;

  // Prontus closes div.main early on some templates, so the page body (minus
  // the header, menus and footer, which SKIP drops) is the content root.
  const root = document.body;
  const inCard = (el) => {
    const c = el.closest('article.card, aside.card');
    return c && !c.classList.contains('card__horizontal') ? c : null;
  };
  const strongOnly = (el) => {
    if (el.tagName !== 'P' || !el.closest('.CUERPO')) return false;
    const t = T(el.textContent);
    if (t.length < 3 || t.length > 70 || /[.:;,]$/.test(t) || FAQ_Q.test(t)) return false;
    const strong = T([...el.querySelectorAll('strong, b')].map((s) => s.textContent).join(' '));
    return strong === t && !el.querySelector('a');
  };
  const headingLevel = (el) => {
    const cl = el.classList;
    if (cl.contains('enc-main__title') || cl.contains('block-hor__title')) return [1, false];
    if (inCard(el) || cl.contains('card__subtitle')) return [0, false];
    if (cl.contains('block-head__title')) return [2, false];
    const m = /^H([1-6])$/.exec(el.tagName);
    if (m) return [Number(m[1]), false];
    if (cl.contains('titulos') || cl.contains('subtit1') || cl.contains('subtitulo')) return [4, true];
    if (strongOnly(el) && !sections.some((x) => x.heading.toLowerCase() === T(el.textContent).toLowerCase())) return [4, true];
    return [0, false];
  };
  const shown = (el) => {
    const t = T(el.innerText);
    return t || T(el.textContent);
  };

  const sections = [];
  let cur = { heading: '', level: 0, buf: [], items: [] };
  sections.push(cur);
  const cardSection = new Map();
  const walk = (node) => {
    if (node.nodeType === 3) { cur.buf.push(node.nodeValue); return; }
    if (node.nodeType !== 1) return;
    const el = node;
    if (el.matches(SKIP)) return;
    if (el.matches('section, header.enc-main, article.block-hor') && (cur.heading || cur.buf.join('').trim())) {
      // A new page block starts a new section even before (or without) a title.
      cur = { heading: '', level: 0, buf: [], items: [], block: [...el.classList].join(' ') };
      sections.push(cur);
    }
    if (el.matches('header.enc-main') && !el.querySelector('.enc-main__title')) {
      // A banner-only page head: its title is the banner image's alt text.
      const alt = T(el.querySelector('img[alt]')?.getAttribute('alt'));
      if (alt) {
        cur = { heading: alt, level: 1, buf: [], items: [], selector: cssPath(el), tag: 'img', pseudo: true };
        sections.push(cur);
        return;
      }
    }
    const [lvl, pseudo] = headingLevel(el);
    if (lvl) {
      const text = shown(el);
      if (text) {
        cur = { heading: text, level: lvl, buf: [], items: [], selector: cssPath(el), tag: el.tagName.toLowerCase() };
        const dom = T(el.textContent);
        if (dom && dom !== text) cur.dom_text = dom;
        if (pseudo) cur.pseudo = true;
        if (el.id) cur.id = el.id;
        sections.push(cur);
        return;
      }
    }
    if (el.matches('article.card, aside.card')) cardSection.set(el, cur.heading);
    if (el.matches('.card__title') && inCard(el)) {
      const t = shown(el);
      if (t) cur.items.push(t);
    } else if (el.tagName === 'LI' && el.closest('.CUERPO')) {
      const t = T(el.textContent);
      if (t && t.length <= 160) cur.items.push(t);
    }
    const block = BLOCK.test(el.tagName);
    if (block) cur.buf.push('\n');
    for (const c of el.childNodes) walk(c);
    if (block) cur.buf.push('\n');
  };
  walk(root);
  const out = [];
  for (const s of sections) {
    const lines = s.buf.join('').split('\n').map(T).filter(Boolean);
    const text = lines.join('\n');
    delete s.buf;
    s.text = text;
    s.items = [...new Set(s.items)];
    if (!s.heading && !text) continue;
    out.push(s);
  }

  // FAQ: numbered "¿...?" paragraphs (the answer runs to the next question or
  // heading), plus any accordion markup.
  const faqs = [];
  let open = null;
  let group = '';
  const blocks = root.querySelectorAll('.CUERPO p, .CUERPO li, .CUERPO h1, .CUERPO h2, .CUERPO h3, .CUERPO h4, .CUERPO h5, .CUERPO h6, .CUERPO div:not(:has(p, div, li, h2, h3))');
  for (const el of blocks) {
    if (el.closest(SKIP)) continue;
    const t = T(el.textContent);
    if (!t) continue;
    const m = FAQ_Q.exec(t);
    if (/^H[1-6]$/.test(el.tagName)) { open = null; group = shown(el); continue; }
    if (m) { open = { q: m[1], a: '', group, selector: cssPath(el) }; faqs.push(open); continue; }
    if (open && !el.querySelector('p, li')) open.a = T(open.a + ' ' + t);
  }
  for (const d of root.querySelectorAll('details')) {
    if (d.closest(SKIP)) continue;
    const s = d.querySelector('summary');
    if (!s) continue;
    const q = T(s.textContent);
    const a = T(d.textContent.replace(s.textContent, ''));
    if (q) faqs.push({ q, a, group: '', selector: cssPath(d) });
  }
  for (const it of root.querySelectorAll('.accordionItem')) {
    if (it.closest(SKIP)) continue;
    const h = it.querySelector('.accordionItemHeading');
    const c = it.querySelector('.accordionItemContent');
    if (h && c) faqs.push({ q: T(h.textContent), a: T(c.textContent), group: '', selector: cssPath(it) });
  }

  // Cards, hidden slides included.
  const roleOf = (a) => a.classList.contains('btn-tickets') ? 'tickets'
    : a.classList.contains('btn-parking') ? 'parking'
    : a.classList.contains('btn-upgrade') ? 'vip'
    : a.classList.contains('btn-food') ? 'food' : '';
  const linkLabel = (a) => T(a.innerText) || T(a.textContent)
    || T(a.querySelector('.tooltip-text')?.textContent) || T(a.getAttribute('aria-label'))
    || T(a.getAttribute('title')) || T(a.querySelector('img')?.getAttribute('alt'))
    || (a.querySelector('img') ? '[image]' : '');
  const cards = [];
  const seen = new Set();
  for (const c of root.querySelectorAll('article.card, aside.card')) {
    if (c.closest('.swiper-slide-duplicate') || c.closest(SKIP.replace('aside.card__event--sidebar,', ''))) continue;
    const titleEl = c.querySelector('.card__title, h1, h2, h3, h4');
    const title = titleEl ? shown(titleEl) : '';
    if (!title) continue;
    const bits = ['.card__epig', '.hero__epig', '.card__subtitle', '.card__description', '.card__text', 'p']
      .flatMap((s) => [...c.querySelectorAll(s)]).filter((e) => !e.closest('.btn__primary, .btn__secondary, .btn__icon'));
    const text = [...new Set(bits.map((e) => T(e.textContent)).filter((t) => t && t !== title))].join(' · ');
    const links = [...c.querySelectorAll('a[href]')];
    const main = links.find((a) => !roleOf(a) && !/^(#|javascript:)/.test(a.getAttribute('href') || ''));
    const holder = c.closest('[data-fecha]');
    const card = {
      title,
      text,
      href: main ? abs(main.getAttribute('href')) : '',
      kind: [...c.classList].filter((x) => x !== 'card' && x.startsWith('card')).join(' '),
      section: cardSection.get(c) || '',
    };
    if (holder) { card.date_attr = holder.getAttribute('data-fecha'); card.tema = holder.getAttribute('data-tema') || ''; }
    if (c.closest('.swiper-slide')) card.in_swiper = true;
    const tk = links.filter((a) => roleOf(a)).map((a) => ({ role: roleOf(a), label: linkLabel(a), url: abs(a.getAttribute('href')) }));
    if (tk.length) card.tickets = tk;
    const key = card.title + '|' + card.href + '|' + card.section;
    if (seen.has(key)) continue;
    seen.add(key);
    cards.push(card);
  }

  // Every link: same-host ones feed the crawl; booking ones become tickets.
  const sectionOf = (el) => {
    let best = '';
    for (const s of out) {
      if (!s.selector) continue;
      let h = null;
      try { h = document.querySelector(s.selector); } catch (e) { h = null; }
      if (h && (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) best = s.heading;
    }
    return best;
  };
  const links = [];
  const tickets = [];
  const documents = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) continue;
    const url = abs(href);
    const area = a.closest('header#header, .menu-responsive') ? 'header'
      : a.closest('footer.footer') ? 'footer' : a.closest('.lateral_bar') ? 'social' : 'body';
    links.push({ url, text: linkLabel(a), area, target: a.getAttribute('target') || '' });
    if (/\.pdf($|\?)/i.test(url) && area === 'body') documents.push({ label: linkLabel(a) || shown(a.closest('article, li, p') || a), url });
    let host = '';
    try { host = new URL(url).hostname; } catch (e) { host = ''; }
    if (area === 'body' && /(^|\.)(puntoticket\.com|ticketmaster\.\w+|passline\.com|eventbrite\.\w+)$/.test(host)) {
      const card = a.closest('article.card, aside.card');
      const ct = card ? card.querySelector('.card__title, h2, h3') : null;
      const near = (ct && shown(ct)) || sectionOf(a) || T(document.title.split('|')[0]);
      tickets.push({ label: linkLabel(a), url, near, role: roleOf(a) });
    }
  }

  // Event pages: the head block and the sidebar's three buttons.
  let event = null;
  const bh = document.querySelector('.block-hor__title');
  if (bh) {
    const side = document.querySelector('aside.card__event--sidebar') || document;
    const btn = (cls) => { const a = side.querySelector('a.' + cls) || document.querySelector('.block-hor a.' + cls); return a ? { label: linkLabel(a), url: abs(a.getAttribute('href')) } : null; };
    const body = document.querySelector('.art-content .CUERPO') || document.querySelector('.art-content');
    const bodyText = body ? [...body.querySelectorAll('p, li, h2, h3, h4')].map((e) => T(e.textContent)).filter(Boolean) : [];
    const firstTicket = document.querySelector('.block-hor a[href*="puntoticket"], aside.card__event--sidebar a.btn-tickets');
    event = {
      name: shown(bh),
      when: T(document.querySelector('.block-hor__description')?.textContent),
      side_when: T(document.querySelector('aside.card__event--sidebar .card__description')?.textContent),
      tickets: btn('btn-tickets') || (firstTicket ? { label: linkLabel(firstTicket), url: abs(firstTicket.getAttribute('href')) } : null),
      parking: btn('btn-parking'),
      vip: btn('btn-upgrade'),
      body: [...new Set(bodyText)].join('\n'),
    };
  }

  const imgDates = [...document.querySelectorAll('.main img[src*="/site/artic/"], .block-hor img[src*="/site/artic/"]')]
    .map((i) => (/\/site\/artic\/(\d{8})\//.exec(i.getAttribute('src')) || [])[1]).filter(Boolean);
  const forms = [...root.querySelectorAll('form')].filter((f) => !f.closest('header#header')).map((f) => ({
    id: f.id || '', action: f.getAttribute('action') || '',
    fields: [...f.querySelectorAll('input, select, textarea')].filter((i) => i.type !== 'hidden' && i.type !== 'submit').map((i) => ({
      name: i.name || i.id || '', type: i.type || i.tagName.toLowerCase(), required: i.required,
      label: T((i.id && document.querySelector(`label[for="${i.id}"]`)?.textContent) || i.closest('label')?.textContent || i.placeholder || ''),
      options: i.tagName === 'SELECT' ? [...i.options].map((o) => T(o.textContent)).filter(Boolean) : [],
    })),
    submit: T(f.querySelector('[type=submit], button')?.textContent),
  }));
  const iframes = [...root.querySelectorAll('iframe[src]')].map((f) => abs(f.getAttribute('src')))
    .filter((s) => !/recaptcha|platform\.twitter|googletagmanager/.test(s));
  return {
    title: T(document.title),
    description: T(document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content),
    canonical: document.querySelector('link[rel="canonical"]')?.href || '',
    breadcrumbs: [...document.querySelectorAll('.breadcrumbs .breadcrumb')].map((b) => ({ text: T(b.textContent), href: b.querySelector('a') ? abs(b.querySelector('a').getAttribute('href')) : '' })),
    sections: out,
    faqs,
    cards,
    tickets,
    documents,
    links,
    event,
    img_dates: imgDates,
    forms,
    iframes,
  };
}
"""

LISTING_JS = r"""
(html) => {
  // The cartelera's month filter detaches the cards of other months from the
  // live DOM, so every event card is read from the server HTML instead.
  const T = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return ''; } };
  const role = (a) => a.classList.contains('btn-tickets') ? 'tickets' : a.classList.contains('btn-parking') ? 'parking'
    : a.classList.contains('btn-upgrade') ? 'vip' : a.classList.contains('btn-food') ? 'food' : '';
  return [...doc.querySelectorAll('[data-fecha]')].map((h) => {
    const c = h.querySelector('article.card') || h;
    const more = [...c.querySelectorAll('a[href]')].find((a) => !role(a));
    return {
      title: T(c.querySelector('.card__title')?.textContent),
      text: T(c.querySelector('.card__epig, .hero__epig')?.textContent),
      href: more ? abs(more.getAttribute('href')) : '',
      kind: 'card__event',
      section: 'Nuestra Cartelera',
      date_attr: h.getAttribute('data-fecha'),
      tema: h.getAttribute('data-tema') || '',
      tickets: [...c.querySelectorAll('a[href]')].filter(role).map((a) => ({
        role: role(a),
        label: T(a.textContent) || T(a.querySelector('.tooltip-text')?.textContent),
        url: abs(a.getAttribute('href')),
      })),
    };
  }).filter((c) => c.title);
}
"""

NAV_JS = r"""
() => {
  const T = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return ''; } };
  const cf = (hex) => { const k = parseInt(hex.slice(0, 2), 16); let s = ''; for (let i = 2; i < hex.length; i += 2) s += String.fromCharCode(parseInt(hex.slice(i, i + 2), 16) ^ k); return s; };
  const link = (a) => ({ label: T(a.innerText) || T(a.textContent) || T(a.querySelector('img')?.alt), href: abs(a.getAttribute('href')), target: a.getAttribute('target') || '' });
  const menu = [...document.querySelectorAll('header#header .desktop ul.header__links:not(.header__links--sec) > li')].map((li) => {
    const a = li.querySelector(':scope > a');
    const subs = [...li.querySelectorAll('.sub-menu a')].map(link);
    const item = link(a);
    if (subs.length) { item.href = ''; item.children = subs; }
    return item;
  });
  const secondary = [...document.querySelectorAll('header#header .header__links--sec li.sub a')].map(link);
  const mobile = [...document.querySelectorAll('.menu-responsive .menu__links > li')].map((li) => {
    const head = li.querySelector('.accordionItemHeading');
    if (head) return { label: T(head.textContent), children: [...li.querySelectorAll('.accordionItemContent a')].map(link) };
    const a = li.querySelector('a');
    return a ? link(a) : { label: T(li.textContent) };
  }).filter((x) => x.label);
  const footerCols = [...document.querySelectorAll('footer.footer .footer__col')].map((ul) => ({
    title: T(ul.querySelector('.footer__title')?.textContent),
    links: [...ul.querySelectorAll('a')].map(link),
  }));
  const contact = [...document.querySelectorAll('footer.footer .footer__contact a')].map((a) => {
    const h = a.getAttribute('href') || '';
    const href = h.includes('/cdn-cgi/l/email-protection#') ? 'mailto:' + cf(h.split('#')[1]) : abs(h);
    const span = a.querySelector('[data-cfemail]');
    return { label: span ? cf(span.getAttribute('data-cfemail')) : T(a.textContent), href, alt: T(a.querySelector('img')?.alt) };
  });
  const social = [...document.querySelectorAll('footer.footer .footer__social a')].map((a) => ({ label: T(a.querySelector('img')?.alt), href: a.href }));
  const lateral = [...document.querySelectorAll('.lateral_bar a')].map((a) => ({ label: T(a.textContent), href: a.href }));
  const access = [...document.querySelectorAll('header#header .acc-cont li, .menu-responsive .cont-access li')].map((li) => T(li.textContent)).filter(Boolean);
  return {
    menu, secondary, mobile, footer: footerCols, contact, social_footer: social, social_side: lateral,
    accessibility_widget: [...new Set(access)],
    legal: T(document.querySelector('footer.footer .footer__legal')?.textContent),
    search: { placeholder: document.querySelector('header#header #search_texto')?.placeholder || '', param: 'search_texto' },
  };
}
"""

# ─── Paths and cache ──────────────────────────────────────────────────────────


def site_path(url: str) -> str | None:
    """The canonical path of a crawlable same-host URL, else ``None``."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in (HOST, "santanderarena.cl"):
        return None
    if parts.query:
        return None
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower() or "/"
    if SKIP_EXT.search(path) or SKIP_PATH.search(path):
        return None
    return path


def page_url(path: str) -> str:
    return urlunsplit(("https", HOST, path, "", ""))


def cache_path(url: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(url).path.lower()).strip("-")[:80] or "home"
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return CACHE / f"{slug}-{digest}.json"


def cache_get(url: str) -> dict[str, Any] | None:
    p = cache_path(url)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_put(url: str, data: dict[str, Any]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path(url).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ─── Crawl ────────────────────────────────────────────────────────────────────


async def render(ctx: Any, url: str) -> dict[str, Any]:
    """One page, scrolled to the bottom, as extracted data."""
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        # A slow third-party tag never blocks extraction.
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("load", timeout=15_000)
        await page.evaluate(SCROLL_JS)
        data: dict[str, Any] = await page.evaluate(PAGE_JS)
        data["status"] = resp.status if resp else 0
        data["final_url"] = page.url
        data["headers"] = {
            k: v for k, v in (resp.headers if resp else {}).items() if k in HEADERS_KEPT
        }
        if urlsplit(url).path in ("", "/"):
            data["nav"] = await page.evaluate(NAV_JS)
        try:
            html = await resp.text() if resp else ""
        except Exception:  # a redirect response has no body
            html = ""
        if "data-fecha=" in html:
            listed = await page.evaluate(LISTING_JS, html)
            live = {(c["title"], c["href"]) for c in data["cards"]}
            data["cards"] += [c for c in listed if (c["title"], c["href"]) not in live]
            dated = {(c["title"], c["href"]): c for c in listed}
            for c in data["cards"]:
                if (src := dated.get((c["title"], c["href"]))) and "date_attr" not in c:
                    c["date_attr"], c["tema"] = src["date_attr"], src["tema"]
        return data
    finally:
        await page.close()


async def crawl_async(offline: bool, refresh: bool, max_pages: int) -> dict[str, dict[str, Any]]:
    """BFS from ``/``; returns ``{requested path: extraction}``."""
    results: dict[str, dict[str, Any]] = {}
    queue: list[str] = ["/"]
    seen: set[str] = {"/"}
    pw = browser = ctx = None
    if not offline:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]

        pw = await async_playwright().start()
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})

        async def block(route: Any) -> None:
            req = route.request
            host = urlsplit(req.url).hostname or ""
            if req.resource_type in ("image", "media", "font") or not host.endswith(
                "santanderarena.cl"
            ):
                await route.abort()
            else:
                await route.continue_()

        await ctx.route("**/*", block)
    sem = asyncio.Semaphore(PARALLEL)

    async def one(path: str) -> None:
        url = page_url(path)
        data = None if refresh else cache_get(url)
        if data is None and ctx is not None:
            async with sem:
                for attempt in range(3):
                    try:
                        data = await render(ctx, url)
                        break
                    except Exception as exc:  # retried, then reported
                        print(f"  retry {attempt + 1} {path}: {exc}", file=sys.stderr)
                        await asyncio.sleep(2 + 3 * attempt)
            if data is not None and data.get("status", 0) in (200, 404, 301, 302):
                cache_put(url, data)
        if data is not None:
            results[path] = data

    try:
        while queue and len(results) < max_pages:
            batch, queue = queue[: max_pages - len(results)], queue[max_pages - len(results) :]
            await asyncio.gather(*(one(p) for p in batch))
            for p in batch:
                data = results.get(p)
                if not data or data.get("status") != 200:
                    continue
                hrefs = [x["url"] for x in data.get("links", [])]
                hrefs += [c["href"] for c in data.get("cards", []) if c.get("href")]
                for href in hrefs:
                    q = site_path(href)
                    if q and q not in seen:
                        seen.add(q)
                        queue.append(q)
            print(f"  {len(results)} pages, {len(queue)} queued", file=sys.stderr)
    finally:
        if browser is not None:
            await browser.close()
        if pw is not None:
            await pw.stop()
    if queue:
        print(f"  page cap {max_pages} reached; {len(queue)} not crawled", file=sys.stderr)
    return results


# ─── Records ──────────────────────────────────────────────────────────────────


def kind_of(path: str) -> str:
    if path == "/":
        return "home"
    if path.startswith("/nuestra-cartelera/") or re.match(r"^/cartelera/[^/]+/[^/]+$", path):
        return "event"
    if path.startswith("/arena-news/"):
        return "news"
    if path in ("/cartelera", "/arena-news", "/arena-fans") or "/tax/port/" in path:
        return "listing"
    return "page"


def clip(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: text.rfind(" ", 0, cap)].rstrip() + " …"


def page_record(path: str, r: dict[str, Any]) -> dict[str, Any]:
    kind = kind_of(path)
    sections = []
    for s in r.get("sections", []):
        sec = {k: v for k, v in s.items() if v not in ("", None, [], False) and k != "tag"}
        sec["heading"] = s.get("heading", "")
        sec["text"] = clip(s.get("text", ""), SECTION_CAP)
        sections.append(sec)
    if kind == "event":
        sections, cards, tickets = trim_event_extras(
            sections, r.get("cards", []), r.get("tickets", [])
        )
    else:
        cards, tickets = r.get("cards", []), r.get("tickets", [])
    text = clip("\n".join(f"{s['heading']}\n{s['text']}".strip() for s in sections), TEXT_CAP)
    if kind == "event":
        text = clip(text, EVENT_TEXT_CAP)
    rec: dict[str, Any] = {
        "path": path,
        "url": page_url(path),
        "title": r.get("title", ""),
        "description": r.get("description", ""),
        "kind": kind,
        "breadcrumbs": [b["text"] for b in r.get("breadcrumbs", [])],
        "sections": sections,
        "headings": [s["heading"] for s in sections if s["heading"]],
        "faqs": r.get("faqs", []),
        "cards": cards,
        "tickets": dedupe(tickets, ("label", "url", "near")),
        "documents": dedupe(r.get("documents", []), ("url",)),
        "forms": r.get("forms", []),
        "iframes": r.get("iframes", []),
        "text": text,
    }
    if kind == "event":
        rec.pop("iframes")  # the artist's YouTube video, on every event page
    return {k: v for k, v in rec.items() if v not in ([], "") or k in ("sections", "headings")}


EXTRAS = ("Completa tu noche en Santander Arena", "Te puede interesar")


def trim_event_extras(
    sections: list[dict[str, Any]], cards: list[dict[str, Any]], tickets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Every event page ends with the same two blocks: the three "Completa tu noche"
    cards and three other events under "Te puede interesar". Keep their titles and
    links (they are scroll targets) but not their text or booking links, which
    belong to those other pages."""
    others = {i for s in sections if s["heading"] in EXTRAS[1:] for i in s.get("items", [])}
    secs = [{**s, "text": ""} if s["heading"] in EXTRAS else s for s in sections]
    slim = [
        {k: c[k] for k in ("title", "href", "kind", "section") if k in c}
        if c.get("section") in EXTRAS
        else c
        for c in cards
    ]
    keep = [t for t in tickets if t.get("near") not in others]
    # The sidebar card repeats the page head; its buttons are in ``tickets``.
    slim = [c for c in slim if "card__event--sidebar" not in c.get("kind", "")]
    return secs, slim, keep


def dedupe(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out = []
    for row in rows:
        k = tuple(row.get(x) for x in keys)
        if k not in seen:
            seen.add(k)
            out.append(row)
    return out


# ─── Events ───────────────────────────────────────────────────────────────────

DAY_MONTH = re.compile(r"(\d{1,2})\s*(?:de\s+)?([a-záéíóú]+)", re.I)
TIME = re.compile(r"(\d{1,2})[:.](\d{2})")


def fold(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )


def split_when(when: str) -> tuple[str, str]:
    """``"5 de Noviembre / 21:00 hrs"`` → ``("5 de Noviembre", "21:00 hrs")``."""
    if "/" in when:
        d, t = when.split("/", 1)
        return d.strip(), t.strip()
    m = TIME.search(when)
    if m:
        return when[: m.start()].strip(" -\u2013,"), when[m.start() :].strip()
    return when.strip(), ""


def day_month(text: str) -> tuple[int, int] | None:
    for m in DAY_MONTH.finditer(fold(text)):
        month = MONTHS.get(m.group(2))
        if month:
            return int(m.group(1)), month
    return None


def safe_date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def infer_date(
    date_text: str, body: str, img_dates: list[str], today: dt.date
) -> tuple[str | None, str]:
    """ISO date and how it was found, for an event the cartelera does not date."""
    dm = day_month(date_text)
    if not dm:
        return None, "none"
    day, month = dm
    names = [k for k, v in MONTHS.items() if v == month]
    for name in names:
        m = re.search(rf"\b{day}\s+de\s+{name}\s+(?:de\s+|del\s+)?(20\d\d)\b", fold(body))
        if m and (d := safe_date(int(m.group(1)), month, day)):
            return d.isoformat(), "page-year"
    published = sorted(img_dates)[:1]
    if published:
        p = dt.datetime.strptime(published[0], "%Y%m%d").date()
        for y in (p.year, p.year + 1):
            d = safe_date(y, month, day)
            if d and d >= p:
                return d.isoformat(), "after-publication"
    for y in (today.year, today.year + 1):
        d = safe_date(y, month, day)
        if d and d >= today:
            return d.isoformat(), "next-occurrence"
    return None, "none"


def build_events(
    pages: dict[str, dict[str, Any]], raw: dict[str, dict[str, Any]], today: dt.date
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: dict[str, Any] = {}
    if NOTES.exists():
        notes = json.loads(NOTES.read_text(encoding="utf-8"))
    listed: dict[str, dict[str, Any]] = {}
    cartelera = raw.get("/cartelera", {})
    for c in cartelera.get("cards", []):
        p = site_path(c.get("href", ""))
        if p and p.startswith("/nuestra-cartelera/") and c.get("date_attr"):
            listed.setdefault(p, c)
    paths = list(dict.fromkeys([*listed, *(p for p in pages if kind_of(p) == "event")]))
    events = []
    missing = []
    for path in paths:
        card = listed.get(path, {})
        r = raw.get(path, {})
        ev = r.get("event") or {}
        when = ev.get("when") or ev.get("side_when") or card_when(card)
        date_text, time_text = split_when(when)
        iso, source = None, "none"
        if card.get("date_attr"):
            d, m, y = (int(x) for x in card["date_attr"].split("/"))
            iso, source = dt.date(y, m, d).isoformat(), "cartelera"
            page_dm = day_month(date_text)
            if page_dm and page_dm != (d, m):
                source = f"cartelera (page says {date_text})"
        else:
            iso, source = infer_date(date_text, ev.get("body", ""), r.get("img_dates", []), today)
        tm = TIME.search(time_text or when)
        segs = path.split("/")
        category = segs[2] if len(segs) > 3 else (fold(card.get("tema", "")) or None)
        tickets = (ev.get("tickets") or {}).get("url") or first_role(card, "tickets")
        body = ev.get("body", "")
        producer = None
        if m := re.search(r"\bProduc(?:e|en|ci[oó]n)\s*:\s*([^\n]+)", body):
            # "Produce: Bizarro" / "Produce: Lotus SpA.Rut: 76.123.456-7" -> the name only.
            producer = re.split(
                r"(?i)\s*r\.?u\.?t\.?\s*:|\s*\d{1,2}\.?\d{3}\.?\d{3}-?[\dk]\b", m.group(1)
            )[0]
            producer = producer.strip() or None
        note = notes.get(path, {})
        if not note.get("summary"):
            missing.append(path)
        events.append(
            {
                "name": ev.get("name") or card.get("title") or path.rsplit("/", 1)[-1],
                "path": path,
                "url": page_url(path),
                "category": category,
                "when_text": when,
                "date_text": date_text,
                "time_text": time_text,
                "date": iso,
                "time": f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None,
                "date_source": source,
                "upcoming": bool(iso and iso >= today.isoformat()),
                "on_cartelera": path in listed,
                "has_page": path in pages,
                "summary": note.get("summary", ""),
                "description": clip(body, EVENT_TEXT_CAP),
                "tickets_url": tickets or None,
                "parking_url": (ev.get("parking") or {}).get("url") or first_role(card, "parking"),
                "vip_url": (ev.get("vip") or {}).get("url") or first_role(card, "vip"),
                "producer": producer,
            }
        )
    events.sort(key=lambda e: (e["date"] or "9999", e["time"] or "", e["name"]))
    return events, missing


def card_when(card: dict[str, Any]) -> str:
    text = card.get("text", "")
    return text.split(" · ")[0] if text else ""


def first_role(card: dict[str, Any], role: str) -> str | None:
    for t in card.get("tickets", []):
        if t.get("role") == role:
            return t.get("url")
    return None


# ─── Outputs ──────────────────────────────────────────────────────────────────


def write_outputs(raw: dict[str, dict[str, Any]], today: dt.date) -> None:
    pages: dict[str, dict[str, Any]] = {}
    redirects: dict[str, str] = {}
    broken: dict[str, list[str]] = {}
    for path, r in raw.items():
        final = site_path(r.get("final_url", "")) or path
        if r.get("status") != 200:
            broken.setdefault(path, [])
            continue
        if final != path:
            redirects[path] = final
        if final in pages:
            continue
        pages[final] = page_record(final, r)
    by_path = {p: raw[p] for p in raw}
    for p, final in redirects.items():
        by_path.setdefault(final, raw[p])
    # Who links to the broken pages.
    for path, r in raw.items():
        if r.get("status") != 200:
            continue
        for link in r.get("links", []):
            q = site_path(link["url"])
            if q in broken and path not in broken[q]:
                broken[q].append(path)
    events, missing = build_events(pages, by_path, today)
    L3.mkdir(parents=True, exist_ok=True)
    dump(L3 / "pages.json", list(pages.values()), compact=True)
    dump(L3 / "events.json", events)
    dump(L3 / "site.json", site_record(raw, pages, redirects, broken))
    write_site_map(pages, raw.get("/", {}).get("nav", {}))
    write_events_index(events, today)
    up = sum(e["upcoming"] for e in events)
    print(f"pages {len(pages)}, events {len(events)} ({up} upcoming), redirects {len(redirects)}")
    print(f"broken internal links {len(broken)}; events without a summary {len(missing)}")
    if missing:
        (CACHE / "missing_summaries.txt").write_text("\n".join(missing), encoding="utf-8")


def dump(path: Path, data: Any, compact: bool = False) -> None:
    """JSON; ``compact`` puts one record per line, to keep the file small."""
    if compact and isinstance(data, list):
        rows = ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in data)
        path.write_text(f"[\n{rows}\n]\n", encoding="utf-8")
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def site_record(
    raw: dict[str, dict[str, Any]],
    pages: dict[str, dict[str, Any]],
    redirects: dict[str, str],
    broken: dict[str, list[str]],
) -> dict[str, Any]:
    home = raw.get("/", {})
    hosts: Counter[str] = Counter()
    for r in raw.values():
        if r.get("status") != 200:
            continue
        for link in r.get("links", []):
            host = urlsplit(link["url"]).hostname
            if host and not host.endswith("santanderarena.cl"):
                hosts[host] += 1
    return {
        "site": SITE,
        "crawled": dt.date.today().isoformat(),
        "nav": home.get("nav", {}),
        "headers": home.get("headers", {}),
        "redirects": redirects,
        "broken_internal_links": dict(sorted(broken.items())),
        "page_kinds": dict(Counter(p["kind"] for p in pages.values())),
        "outbound_hosts": dict(hosts.most_common()),
    }


def write_site_map(pages: dict[str, dict[str, Any]], nav: dict[str, Any]) -> None:
    lines = [
        "# Site map: every page, its sections and cards",
        "",
        "Sources: L3/pages.json and L3/site.json (generated by build.py from a headless-browser "
        f"crawl of {SITE}).",
        "",
        "Headings are written exactly as the page renders them (innerText, so CSS uppercase is "
        "applied). `(pseudo)` marks a title that is not an h-tag (a bold paragraph, "
        "`span.titulos`). Every navigation is a full page load. Event pages are listed in "
        "events-index, not here.",
        "",
        "## Navigation",
    ]
    for item in nav.get("menu", []):
        if item.get("children"):
            kids = "; ".join(f"{c['label']} ({rel(c['href'])})" for c in item["children"])
            lines.append(f"- {item['label']} ▸ {kids}")
        else:
            lines.append(f"- {item['label']} ({rel(item['href'])})")
    if nav.get("secondary"):
        sec = "; ".join(f"{c['label']} ({rel(c['href'])})" for c in nav["secondary"])
        lines.append(f"- Top bar: {sec}")
    for col in nav.get("footer", []):
        links = "; ".join(f"{c['label']} ({rel(c['href'])})" for c in col["links"])
        lines.append(f'- Footer "{col["title"]}": {links}')
    lines.append("")
    order = {"home": 0, "page": 1, "listing": 2, "news": 3}
    fans = sorted(p["path"] for p in pages.values() if p["path"].startswith("/arena-fans/"))
    if fans:
        lines += [
            "## /arena-fans/<show> (one page per show, linked from Fotos Fans)",
            "Each has the show's name as title, a photo gallery, the modal \"Descarga tu foto en "
            'alta calidad" (form: Nombre completo, Email; then "¡Todo listo!") and "Te puede '
            'interesar". Pages: ' + ", ".join(fans),
            "",
        ]
    for p in sorted(
        (p for p in pages.values() if p["kind"] != "event" and p["path"] not in fans),
        key=lambda p: (order.get(p["kind"], 9), p["path"]),
    ):
        lines.append(f"## {p['path']} ({p['kind']})")
        lines.append(f"Title: {p['title']}")
        for s in p["sections"]:
            if not s["heading"]:
                if s.get("items"):
                    lines.append(f"  - (no heading) — {', '.join(s['items'][:12])}")
                continue
            mark = " (pseudo)" if s.get("pseudo") else ""
            items = s.get("items") or []
            extra = f" — {', '.join(items[:12])}{' …' if len(items) > 12 else ''}" if items else ""
            lines.append(
                f"{'  ' * max(0, min(s.get('level', 2), 4) - 1)}- {s['heading']}{mark}{extra}"
            )
        if p.get("faqs"):
            lines.append(f"- FAQ: {len(p['faqs'])} questions")
        if p.get("forms"):
            fields = ", ".join(
                f.get("label") or f.get("name", "") for f in p["forms"][0].get("fields", [])
            )
            lines.append(f"- Form: {fields}")
        if p.get("tickets"):
            tk = {t["url"] for t in p["tickets"]}
            lines.append(
                f"- Booking links: {len(tk)} ({', '.join(sorted(tk)[:4])}{' …' if len(tk) > 4 else ''})"
            )
        lines.append("")
    (L2 / "site-map.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_events_index(events: list[dict[str, Any]], today: dt.date) -> None:
    up = [e for e in events if e["upcoming"]]
    past = [e for e in events if not e["upcoming"]]
    lines = [
        "# Events index: every event the site lists",
        "",
        f"Sources: {SITE}/cartelera (each card's data-fecha) and every /nuestra-cartelera/... page "
        "(L3/events.json, generated by build.py).",
        "",
        f"As of {today.isoformat()}: {len(up)} upcoming, {len(past)} past. Dates in parentheses "
        "are as the site writes them. Tickets are sold only through Puntoticket. `P` = has a "
        '"Comprar estacionamiento" (parking) link, `V` = has "Compra Experiencias VIP".',
        "",
        "## Upcoming",
    ]
    for e in up:
        lines.append(event_line(e))
    lines += ["", "## Past (still on the site)"]
    for e in reversed(past):
        lines.append(event_line(e))
    (L2 / "events-index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def event_line(e: dict[str, Any]) -> str:
    flags = ("P" if e["parking_url"] else "") + ("V" if e["vip_url"] else "")
    flags = f" [{flags}]" if flags else ""
    return f"- {e['date'] or '?'} {e['time'] or ''} {e['name']} ({e['when_text']}) — {e['path']}{flags}"


def rel(href: str) -> str:
    parts = urlsplit(href)
    if parts.hostname and parts.hostname.endswith("santanderarena.cl"):
        return parts.path or "/"
    return href


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="render the site and write L3 + generated L2")
    c.add_argument("--offline", action="store_true", help="use the cache only")
    c.add_argument("--refresh", action="store_true", help="ignore the cache")
    c.add_argument("--max-pages", type=int, default=MAX_PAGES)
    c.add_argument("--today", default=None, help="ISO date that splits upcoming from past")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    raw = asyncio.run(crawl_async(args.offline, args.refresh, args.max_pages))
    write_outputs(raw, today)


if __name__ == "__main__":
    main()
