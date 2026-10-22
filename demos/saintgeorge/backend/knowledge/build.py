# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Saint George's College's L3 knowledge: every page of saintgeorge.cl, as
data, read from a real browser.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON. Network is touched only by ``crawl`` (and ``--pdfs``);
each page's extraction is cached outside the repository, so a re-run is cheap.

saintgeorge.cl is WordPress with a hand-built theme (``colegio-saint-george``):
server-rendered HTML, a full page load per navigation, Bootstrap 5. Custom post
types (``admision``, ``unidad``, ``colegio``, ``familia``, ``formacion-integral``,
``the-dragon``…) render from fields the REST API does not expose, so
``content.rendered`` is empty and every word has to come from the page HTML.
Accordions are Bootstrap 5 collapses (``button.accordion-button`` →
``.accordion-collapse``) whose ids (``#collapse_1_1``) repeat on every page.
Run from ``voqalize/demos`` (Chromium must be installed once with
``playwright install chromium``)::

    uv run --no-project --with playwright --with pypdf python \
        saintgeorge/backend/knowledge/build.py crawl --pdfs
    uv run --no-project --with playwright python \
        saintgeorge/backend/knowledge/build.py crawl --refresh
    uv run --no-project --with pypdf python \
        saintgeorge/backend/knowledge/build.py crawl --offline --pdfs

``crawl`` reads the Yoast sitemap (``/sitemap_index.xml`` and its sub-sitemaps)
and the public ``wp-json`` listings (for each entry's ``modified`` date), then
renders ``/``, every sitemap URL and every same-host link they lead to, breadth
first, skipping assets, PDFs, ``/wp-*``, feeds, search and any URL with a query
string, up to ``--max-pages``. Two pages at a time, with a pause between pages.
No form is ever submitted. It writes, next to this file:

- ``L3/pages.json`` — one record per page that answered 200:
  ``{path, url, title, description, kind, modified, empty, sections, headings,
  faqs, cards, documents, links, forms, iframes, anchors, text}``. ``path``,
  ``title``, ``description``, ``sections: [{heading, text, items}]``,
  ``headings``, ``faqs: [{q, a}]`` and ``text`` are the keys the shared
  ``knowledge.py`` loader reads. The rest:

  - ``kind``: ``home``, ``unit`` (``/unidad/<slug>``), ``admission``
    (``/admision/<slug>``), ``calendar``, ``family`` (``/familia/<slug>``),
    ``formation`` (``/formacion-integral/<slug>``), ``school`` (``/colegio/…``,
    ``/congregacion/…``), ``team`` (``/equipo-directivo``), ``taxonomy``
    (``/nivel``, ``/materia``, ``/tipo_de_*``), ``newsletter``
    (``/the-dragon/<slug>``) or ``page``.
  - ``empty``: the page renders WordPress's default template (a search box and
    "Recent Posts"), or has no content of its own. Never send a visitor there.
  - ``sections`` are in page order. ``heading`` is the element's ``innerText``
    (CSS ``text-transform`` applied); ``dom_text`` is added when the DOM text
    differs. ``level`` is the h-tag's level; ``pseudo`` marks a bold-only
    paragraph used as a title; ``selector`` is a CSS path to the element.
    Accordion content is not in sections: it is in ``faqs``.
  - ``faqs``: every accordion item, ``{q, a, group, label_shown, nth, nth_label,
    target, panel_id, group_id, heading_id, rows, documents}``. ``q`` is the
    button's DOM text (the page shows it in capitals), ``a`` the panel's text
    with table rows written ``cell: cell``. ``nth`` is the button's index among
    the page's ``.accordion-button``; ``nth_label`` its index among buttons with
    the same folded label. ``target`` (``#collapse_1_1``) is unique only within
    the page.
  - ``cards``: the home page's link cards (``a.card``, ``a.card-blog``).
  - ``documents``: every PDF link, ``{label, url, near, accordion, selector}``.
  - ``links``: every link in the page body that leaves the site (portals,
    ticket sales, mailto, tel), ``{label, url, near, selector}``.
  - ``iframes``: ``{src, selector, class, title}`` (Google Calendar, YouTube).
  - ``anchors``: in-page ids a visitor can be scrolled to (``#mision``).

- ``L3/sections.json`` — per path, everything a page move can target, keyed so
  it can be found again on the live page: ``{path: {url, title, kind,
  headings: [{text, level, selector, pseudo?}], anchors: [{id, heading}],
  accordions: [{label, label_shown, nth, nth_label, target, group_id,
  group_heading, find}], documents, links, iframes}}``. ``find`` is how to
  locate the button again: by folded label (and ``nth_label`` when a label
  repeats) among ``button.accordion-button`` on that page; never by id alone.
- ``L3/levels.json`` — the four units (Infant, Elementary, Junior, Senior):
  ``[{slug, name, path, url, cycle, grades, accordions: [{label, label_shown,
  target, nth}], intro, facts, documents}]``. ``grades`` are the accordion
  labels that name a grade; ``cycle`` is the page's own "desde … hasta …"
  sentence when it has one; ``facts`` are the page's sentences about courses,
  pupils, staff and hours, verbatim.
- ``L3/site.json`` — navigation (``#menu-menu-1`` with its nested dropdowns),
  footer (address, phones, e-mails, links, social), response headers,
  redirects, broken internal links, empty pages, the sitemaps, the wp-json
  type counts, every outbound link with the pages that carry it, and the
  calendar embed.
- ``L3/documents.json`` (only with ``--pdfs``) — every linked PDF with the
  pages that link it: ``[{url, labels, pages, n_pages, bytes}]``. The text
  pypdf extracts stays in the local cache: some PDFs carry third parties' bank
  details, and the L2 topics already summarise the ones worth knowing.

It also regenerates ``L2/site-map.md`` from that data.

``--offline`` builds from the cache only; ``--refresh`` re-renders everything.
The cache is ``$XDG_CACHE_HOME/voqalize-saintgeorge`` (``~/.cache`` by
default). If the site answers 403/405 or "Not allowed" three times running,
the crawl stops without writing anything (the site blocks some countries).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
L2 = HERE / "L2"
L3 = HERE / "L3"
HOST = "saintgeorge.cl"
SITE = f"https://{HOST}"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-saintgeorge"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MAX_PAGES = 300
PARALLEL = 2
PAUSE_S = 0.6
TEXT_CAP = 12_000
SECTION_CAP = 4_000
ANSWER_CAP = 3_000
PDF_TEXT_CAP = 8_000
PDF_MAX_BYTES = 12_000_000
UNITS = ("infant", "elementary", "junior", "senior")
WP_TYPES = (
    "pages",
    "admision",
    "unidad",
    "colegio",
    "familia",
    "formacion-integral",
    "the-dragon",
    "equipo-directivo",
    "congregacion",
)
HEADERS_KEPT = (
    "server",
    "content-type",
    "cache-control",
    "content-security-policy",
    "permissions-policy",
    "x-frame-options",
    "strict-transport-security",
    "referrer-policy",
)
#: Hosts the crawl lets the browser load: the site and its CSS/JS CDNs.
ALLOWED_HOSTS = ("saintgeorge.cl", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "code.jquery.com")
SKIP_EXT = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|webp|ico|mp4|mp3|webm|zip|docx?|xlsx?|pptx?|css|js|json|xml)$",
    re.I,
)
SKIP_PATH = re.compile(
    r"^/(wp-|feed|comments|author|category|tag|xmlrpc|\d{4}/)|/feed$|/embed$", re.I
)
GRADE = re.compile(
    # "PRE KINDER", "KINDER", "1º BÁSICO", "9°" (a bare ordinal: no \b after "°").
    r"\b(pre\s*-?\s*k[ií]nder\b|k[ií]nder\b|\d{1,2}\s*[º°](\s*(b[aá]sico|medio))?|"
    r"(primero|segundo|tercero|cuarto)\s+(b[aá]sico|medio)\b)",
    re.I,
)
FACT = re.compile(
    r"\b(curso|cursos|estudiantes|alumn|niñ|educador|profesor|docente|horas|nivel|"
    r"funcionari|colaborador)",
    re.I,
)

# ─── Browser-side scripts ─────────────────────────────────────────────────────

SCROLL_JS = r"""
async () => {
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  let y = 0;
  for (let i = 0; i < 40; i++) {
    y += Math.max(400, Math.floor(window.innerHeight * 0.8));
    window.scrollTo(0, y);
    await pause(100);
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
  const fold = (s) => T(s).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

  const step = (n) => {
    let p = n.tagName.toLowerCase();
    const cls = [...n.classList].filter((c) => /^[A-Za-z][\w-]*$/.test(c) && !c.startsWith('animate__')).slice(0, 2);
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
  const shown = (el) => T(el.innerText) || T(el.textContent);

  const SKIP = [
    'script', 'style', 'noscript', 'template', 'svg', 'iframe', 'select', 'option', 'input',
    'textarea', 'button', 'video', 'audio', 'img', 'form', 'nav#navbar', 'footer.footer',
    '.offcanvas', '.accordion',
  ].join(',');
  const BLOCK = /^(P|DIV|LI|UL|OL|H[1-6]|ARTICLE|SECTION|ASIDE|HEADER|FIGURE|FIGCAPTION|TABLE|TR|TD|TH|BLOCKQUOTE|PRE|BR|DT|DD|ADDRESS)$/;
  const main = document.querySelector('main') || document.body;
  const defaultTemplate = !!document.querySelector('.wp-block-search, .wp-block-latest-posts, .widget_recent_entries, .wp-block-archives');

  const strongOnly = (el) => {
    if (el.tagName !== 'P') return false;
    const t = T(el.textContent);
    if (t.length < 3 || t.length > 90 || /[.:;,]$/.test(t)) return false;
    const strong = T([...el.querySelectorAll('strong, b')].map((s) => s.textContent).join(' '));
    return strong === t && !el.querySelector('a');
  };

  const sections = [];
  let cur = { heading: '', level: 0, buf: [], items: [] };
  sections.push(cur);
  const walk = (node) => {
    if (node.nodeType === 3) { cur.buf.push(node.nodeValue); return; }
    if (node.nodeType !== 1) return;
    const el = node;
    if (el.matches(SKIP)) return;
    const m = /^H([1-6])$/.exec(el.tagName);
    const pseudo = !m && strongOnly(el);
    // A card's title (home "Nuestra comunidad", /familia) is a card, not a section.
    if ((m || pseudo) && !el.closest('.card')) {
      const text = shown(el);
      if (text && text.length <= 160) {
        cur = { heading: text, level: m ? Number(m[1]) : 4, buf: [], items: [], selector: cssPath(el) };
        const dom = T(el.textContent);
        if (dom && dom !== text) cur.dom_text = dom;
        if (pseudo) cur.pseudo = true;
        if (el.id) cur.id = el.id;
        sections.push(cur);
        return;
      }
    }
    if (el.tagName === 'LI') {
      const t = T(el.textContent);
      if (t && t.length <= 160) cur.items.push(t);
    }
    if (el.matches('section[id]') && (cur.heading || cur.buf.join('').trim())) {
      cur = { heading: '', level: 0, buf: [], items: [], anchor: el.id };
      sections.push(cur);
    }
    const block = BLOCK.test(el.tagName);
    if (block) cur.buf.push('\n');
    for (const c of el.childNodes) walk(c);
    if (block) cur.buf.push('\n');
  };
  walk(main);
  const out = [];
  for (const s of sections) {
    const lines = s.buf.join('').split('\n').map(T).filter(Boolean);
    delete s.buf;
    s.text = lines.join('\n');
    s.items = [...new Set(s.items)];
    if (!s.heading && !s.text) continue;
    out.push(s);
  }

  const headingEls = out.filter((s) => s.selector).map((s) => {
    let h = null;
    try { h = document.querySelector(s.selector); } catch (e) { h = null; }
    return [h, s.heading];
  }).filter(([h]) => h);
  const sectionOf = (el) => {
    let best = '';
    for (const [h, text] of headingEls) {
      if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = text;
    }
    return best;
  };
  const linkLabel = (a) => T(a.innerText) || T(a.textContent) || T(a.getAttribute('aria-label'))
    || T(a.getAttribute('title')) || T(a.querySelector('img')?.getAttribute('alt'))
    || decodeURIComponent((a.getAttribute('href') || '').split('/').pop() || '');

  // Accordions: one record per button, found again by its label.
  const buttons = [...main.querySelectorAll('.accordion-button')];
  const seenLabel = new Map();
  const accordions = buttons.map((b, i) => {
    const target = b.getAttribute('data-bs-target') || b.getAttribute('href') || '';
    let panel = null;
    try { panel = target ? document.querySelector(target) : null; } catch (e) { panel = null; }
    panel = panel || b.closest('.accordion-item')?.querySelector('.accordion-collapse');
    const group = b.closest('.accordion');
    const label = T(b.textContent);
    const key = fold(label);
    const nthLabel = seenLabel.get(key) || 0;
    seenLabel.set(key, nthLabel + 1);
    const rows = panel ? [...panel.querySelectorAll('tr')].map((tr) => [...tr.children].map((c) => T(c.textContent)).filter(Boolean).join(': ')).filter(Boolean) : [];
    let text = '';
    if (panel) {
      const clone = panel.cloneNode(true);
      for (const t of clone.querySelectorAll('table, script, style')) t.remove();
      const bits = [];
      const w = (n) => {
        if (n.nodeType === 3) { bits.push(n.nodeValue); return; }
        if (n.nodeType !== 1) return;
        const blk = BLOCK.test(n.tagName);
        if (blk) bits.push('\n');
        for (const c of n.childNodes) w(c);
        if (blk) bits.push('\n');
      };
      w(clone);
      text = bits.join('').split('\n').map(T).filter(Boolean).join('\n');
    }
    const docs = panel ? [...panel.querySelectorAll('a[href]')].filter((a) => /\.pdf($|\?)/i.test(a.getAttribute('href'))).map((a) => ({ label: linkLabel(a), url: abs(a.getAttribute('href')) })) : [];
    return {
      q: label,
      a: [text, rows.join('; ')].filter(Boolean).join('\n'),
      label_shown: T(b.innerText) || label,
      group: sectionOf(b),
      nth: i,
      nth_label: nthLabel,
      target,
      panel_id: panel?.id || '',
      group_id: group?.id || '',
      heading_id: b.closest('.accordion-header')?.id || '',
      open: b.getAttribute('aria-expanded') === 'true',
      rows: rows.length,
      documents: docs,
    };
  });

  const documents = [];
  const links = [];
  const pageLinks = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) continue;
    const url = abs(href);
    const area = a.closest('nav#navbar, .offcanvas') ? 'header' : a.closest('footer.footer') ? 'footer' : 'body';
    pageLinks.push({ url, text: linkLabel(a), area });
    if (area !== 'body') continue;
    const acc = a.closest('.accordion-item')?.querySelector('.accordion-button');
    if (/\.pdf($|\?)/i.test(url)) {
      const card = a.closest('.card, .card-blog');
      const label = linkLabel(a) || T(card?.textContent);
      documents.push({ label, url, near: sectionOf(a), accordion: acc ? T(acc.textContent) : '', selector: cssPath(a) });
      continue;
    }
    let host = '';
    try { host = new URL(url).hostname; } catch (e) { host = ''; }
    if (/^(mailto|tel):/i.test(url) || (host && host !== 'saintgeorge.cl' && host !== 'www.saintgeorge.cl')) {
      links.push({ label: linkLabel(a), url, near: sectionOf(a), selector: cssPath(a) });
    }
  }

  const cards = [...main.querySelectorAll('a.card, a.card-blog, .card a[href]')].map((a) => {
    const c = a.closest('.card') || a;
    const title = T(c.querySelector('.card-title, h3, h4, h5, h6')?.textContent) || T(c.textContent) || T(c.querySelector('img')?.getAttribute('alt'));
    return { title, href: abs(a.getAttribute('href')), section: sectionOf(a), kind: [...a.classList].filter((x) => x.startsWith('card')).join(' '), selector: cssPath(a) };
  }).filter((c, i, all) => all.findIndex((d) => d.href === c.href && d.title === c.title) === i);

  const iframes = [...document.querySelectorAll('main iframe[src], body iframe[src]')].map((f) => ({
    src: abs(f.getAttribute('src')), selector: cssPath(f), class: f.className || '', title: f.title || '',
  }));
  const anchors = [...main.querySelectorAll('[id]')].filter((e) => !e.closest('.accordion') && !/^(acc_|collapse_|heading_|wp-|post-)/.test(e.id) && e.id !== 'unidad' && e.id !== 'familia')
    .map((e) => ({ id: e.id, tag: e.tagName.toLowerCase(), heading: T(e.querySelector('h1, h2, h3')?.textContent) }));
  const forms = [...document.querySelectorAll('form')].filter((f) => !f.closest('nav#navbar')).map((f) => ({
    id: f.id || '', class: f.className || '', action: f.getAttribute('action') || '', method: (f.getAttribute('method') || 'get').toLowerCase(),
    fields: [...f.querySelectorAll('input, select, textarea')].filter((i) => i.type !== 'hidden' && i.type !== 'submit').map((i) => ({
      name: i.name || i.id || '', type: i.type || i.tagName.toLowerCase(), required: i.required,
      label: T((i.id && document.querySelector(`label[for="${i.id}"]`)?.textContent) || i.closest('label')?.textContent || i.placeholder || ''),
    })),
  }));
  const videos = [...main.querySelectorAll('video')].map((v) => ({ src: abs(v.currentSrc || v.getAttribute('src') || v.querySelector('source')?.getAttribute('src') || ''), selector: cssPath(v) }));
  return {
    title: T(document.title),
    description: T(document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content),
    canonical: document.querySelector('link[rel="canonical"]')?.href || '',
    body_class: document.body.className,
    default_template: defaultTemplate,
    main_text: T(main.textContent).length,
    sections: out,
    faqs: accordions,
    cards,
    documents,
    links,
    page_links: pageLinks,
    iframes,
    anchors,
    forms,
    videos,
    blocked: /not allowed/i.test(T(document.body.innerText).slice(0, 400)),
  };
}
"""

NAV_JS = r"""
() => {
  const T = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return ''; } };
  const item = (li) => {
    const a = li.querySelector(':scope > a');
    const out = { label: T(a?.textContent), href: a ? abs(a.getAttribute('href')) : '' };
    if (a?.getAttribute('data-bs-toggle') === 'dropdown') out.toggle = true;
    if (a?.getAttribute('target')) out.target = a.getAttribute('target');
    const kids = li.querySelectorAll(':scope > ul > li');
    if (kids.length) out.children = [...kids].map(item);
    return out;
  };
  const menu = [...document.querySelectorAll('#menu-menu-1 > li')].map(item);
  const f = document.querySelector('footer.footer');
  const addr = f?.querySelector('address');
  const lines = addr ? addr.innerText.split('\n').map(T).filter(Boolean) : [];
  return {
    menu,
    footer: {
      address_lines: lines,
      links: f ? [...f.querySelectorAll('a[href]')].map((a) => ({ label: T(a.textContent) || T(a.querySelector('img')?.getAttribute('src')?.split('/').pop()), href: abs(a.getAttribute('href')) })) : [],
    },
    logo: document.querySelector('nav#navbar .navbar-brand img')?.getAttribute('alt') || '',
    mobile_toggle: document.querySelector('button.navbar-toggler') ? 'button.navbar-toggler → #offcanvasNavbar' : '',
  };
}
"""

# ─── Paths and cache ──────────────────────────────────────────────────────────


def site_path(url: str) -> str | None:
    """The canonical path of a crawlable same-host URL, else ``None``."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in (HOST, f"www.{HOST}"):
        return None
    if parts.query:
        return None
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower() or "/"
    if SKIP_EXT.search(path) or SKIP_PATH.search(path):
        return None
    return path


def page_url(path: str) -> str:
    return urlunsplit(("https", HOST, path if path == "/" else path + "/", "", ""))


def cache_path(url: str, ext: str = "json") -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(url).path.lower()).strip("-")[:80] or "home"
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return CACHE / f"{slug}-{digest}.{ext}"


def cache_get(url: str) -> Any:
    try:
        return json.loads(cache_path(url).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_put(url: str, data: Any) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path(url).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class Blocked(RuntimeError):
    """The site refused us (403/405/"Not allowed"): the VPN is off."""


def fetch(url: str, timeout: float = 30.0) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CL,es"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b"", {}


# ─── Sitemap and wp-json ──────────────────────────────────────────────────────


def read_sitemaps(offline: bool, refresh: bool) -> dict[str, list[str]]:
    """``{sub-sitemap URL: [page URLs]}`` from Yoast's index."""
    key = f"{SITE}/sitemap_index.xml"
    if not refresh and (cached := cache_get(key)) is not None:
        return cached
    if offline:
        return {}
    status, body, _ = fetch(key)
    if status in (403, 405):
        raise Blocked(f"sitemap_index.xml answered {status}")
    subs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body.decode("utf-8", "replace"))
    out: dict[str, list[str]] = {}
    for sub in subs:
        time.sleep(PAUSE_S)
        st, b, _ = fetch(sub)
        if st in (403, 405):
            raise Blocked(f"{sub} answered {st}")
        out[sub] = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", b.decode("utf-8", "replace"))
        # Yoast lists images as <image:loc>; keep pages only.
        out[sub] = [u for u in out[sub] if not SKIP_EXT.search(urlsplit(u).path)]
    cache_put(key, out)
    return out


def read_wp_types(offline: bool, refresh: bool) -> dict[str, list[dict[str, Any]]]:
    """Every entry of the public post types: ``{type: [{id, slug, link, title, modified}]}``."""
    key = f"{SITE}/wp-json/wp/v2/_types"
    if not refresh and (cached := cache_get(key)) is not None:
        return cached
    if offline:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for t in WP_TYPES:
        time.sleep(PAUSE_S)
        url = f"{SITE}/wp-json/wp/v2/{t}?per_page=100&_fields=id,slug,link,title,modified"
        st, body, _ = fetch(url)
        if st in (403, 405):
            raise Blocked(f"wp-json {t} answered {st}")
        if st != 200:
            continue
        try:
            rows = json.loads(body)
        except ValueError:
            continue
        out[t] = [
            {
                "id": r.get("id"),
                "slug": r.get("slug"),
                "link": r.get("link"),
                "title": (r.get("title") or {}).get("rendered", ""),
                "modified": r.get("modified"),
            }
            for r in rows
            if isinstance(r, dict)
        ]
    cache_put(key, out)
    return out


# ─── Crawl ────────────────────────────────────────────────────────────────────


async def render(ctx: Any, url: str) -> dict[str, Any]:
    """One page, scrolled to the bottom, as extracted data."""
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("load", timeout=15_000)
        status = resp.status if resp else 0
        if status in (403, 405):
            return {"status": status, "final_url": page.url, "blocked": True}
        await page.evaluate(SCROLL_JS)
        data: dict[str, Any] = await page.evaluate(PAGE_JS)
        data["status"] = status
        data["final_url"] = page.url
        data["headers"] = {
            k: v for k, v in (resp.headers if resp else {}).items() if k in HEADERS_KEPT
        }
        if urlsplit(url).path in ("", "/"):
            data["nav"] = await page.evaluate(NAV_JS)
        return data
    finally:
        await page.close()


async def crawl_async(
    seeds: list[str], offline: bool, refresh: bool, max_pages: int
) -> dict[str, dict[str, Any]]:
    """BFS from ``/`` and the sitemap; returns ``{requested path: extraction}``."""
    results: dict[str, dict[str, Any]] = {}
    queue: list[str] = list(dict.fromkeys(["/", *seeds]))
    seen: set[str] = set(queue)
    refusals = 0
    pw = browser = ctx = None
    if not offline:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]

        pw = await async_playwright().start()
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(
            user_agent=UA, viewport={"width": 1366, "height": 900}, locale="es-CL"
        )

        async def block(route: Any) -> None:
            req = route.request
            host = urlsplit(req.url).hostname or ""
            ok = any(host == h or host.endswith(f".{h}") for h in ALLOWED_HOSTS)
            if req.resource_type in ("image", "media", "font") or not ok:
                await route.abort()
            else:
                await route.continue_()

        await ctx.route("**/*", block)
    sem = asyncio.Semaphore(PARALLEL)

    async def one(path: str) -> None:
        nonlocal refusals
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
                await asyncio.sleep(PAUSE_S)
            if data is None or data.get("blocked"):
                refusals += 1
                if refusals >= 3:
                    raise Blocked(f"{path}: refused or unreachable three times running")
                return
            refusals = 0
            if data.get("status", 0) in (200, 404, 301, 302):
                cache_put(url, data)
        if data is not None:
            results[path] = data

    try:
        while queue and len(results) < max_pages:
            batch, queue = queue[: max_pages - len(results)], queue[max_pages - len(results) :]
            for i in range(0, len(batch), PARALLEL * 4):
                await asyncio.gather(*(one(p) for p in batch[i : i + PARALLEL * 4]))
            for p in batch:
                data = results.get(p)
                if not data or data.get("status") != 200:
                    continue
                hrefs = [x["url"] for x in data.get("page_links", [])]
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
    head = path.strip("/").split("/")[0]
    deep = path.count("/") >= 2
    if head == "unidad" and deep:
        return "unit"
    if head == "admision" and deep:
        return "admission"
    if path == "/familia/calendario":
        return "calendar"
    if head == "familia" and deep:
        return "family"
    if head == "formacion-integral" and deep:
        return "formation"
    if head in ("colegio", "congregacion") and deep:
        return "school"
    if head == "equipo-directivo":
        return "team"
    if head == "the-dragon":
        return "newsletter"
    if head in ("nivel", "materia") or head.startswith("tipo_de_"):
        return "taxonomy"
    return "page"


def fold(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )


def clip(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: text.rfind(" ", 0, cap)].rstrip() + " …"


def is_empty(r: dict[str, Any], sections: list[dict[str, Any]]) -> bool:
    """WordPress's default template, or a page with nothing past its title."""
    if r.get("default_template"):
        return True
    body = sum(len(s.get("text", "")) for s in sections)
    # The calendar page is a title over two Google Calendar embeds: not empty.
    extras = ("faqs", "documents", "cards", "iframes", "links")
    return body < 40 and not any(r.get(k) for k in extras)


def page_record(path: str, r: dict[str, Any], modified: dict[str, str]) -> dict[str, Any]:
    kind = kind_of(path)
    sections = []
    for s in r.get("sections", []):
        sec = {k: v for k, v in s.items() if v not in ("", None, [], False)}
        sec["heading"] = s.get("heading", "")
        sec["text"] = clip(s.get("text", ""), SECTION_CAP)
        sections.append(sec)
    faqs = []
    for f in r.get("faqs", []):
        faq = {k: v for k, v in f.items() if v not in ("", None, [], False) or k in ("nth",)}
        faq["a"] = clip(f.get("a", ""), ANSWER_CAP)
        faqs.append(faq)
    text = clip("\n".join(f"{s['heading']}\n{s['text']}".strip() for s in sections), TEXT_CAP)
    title = r.get("title", "")
    rec: dict[str, Any] = {
        "path": path,
        "url": page_url(path),
        "title": title.split(" - Saint George")[0].split(" | Saint George")[0].strip() or title,
        "description": r.get("description", ""),
        "kind": kind,
        "modified": modified.get(path, ""),
        "empty": is_empty(r, sections),
        "sections": sections,
        "headings": [s["heading"] for s in sections if s["heading"]],
        "faqs": faqs,
        "cards": r.get("cards", []),
        "documents": dedupe(r.get("documents", []), ("url",)),
        "links": dedupe(r.get("links", []), ("url", "label")),
        "forms": r.get("forms", []),
        "iframes": r.get("iframes", []),
        "anchors": r.get("anchors", []),
        "videos": r.get("videos", []),
        "text": text,
    }
    return {
        k: v
        for k, v in rec.items()
        if v not in ([], "", False) or k in ("sections", "headings", "empty")
    }


def dedupe(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out = []
    for row in rows:
        k = tuple(row.get(x) for x in keys)
        if k not in seen:
            seen.add(k)
            out.append(row)
    return out


def sections_record(p: dict[str, Any]) -> dict[str, Any]:
    accs = []
    for f in p.get("faqs", []):
        find = {"selector": "main button.accordion-button", "label": fold(f["q"]).strip()}
        if f.get("nth_label"):
            find["nth_label"] = f["nth_label"]
        accs.append(
            {
                "label": f["q"],
                "label_shown": f.get("label_shown", f["q"]),
                "nth": f.get("nth", 0),
                "nth_label": f.get("nth_label", 0),
                "target": f.get("target", ""),
                "group_id": f.get("group_id", ""),
                "group_heading": f.get("group", ""),
                "rows": f.get("rows", 0),
                "find": find,
            }
        )
    return {
        "url": p["url"],
        "title": p["title"],
        "kind": p["kind"],
        "headings": [
            {
                k: v
                for k, v in {
                    "text": s["heading"],
                    "level": s.get("level"),
                    "selector": s.get("selector"),
                    "pseudo": s.get("pseudo"),
                    "id": s.get("id"),
                }.items()
                if v
            }
            for s in p["sections"]
            if s.get("heading")
        ],
        "anchors": p.get("anchors", []),
        "accordions": accs,
        "documents": [
            {k: d[k] for k in ("label", "url", "near", "accordion", "selector") if d.get(k)}
            for d in p.get("documents", [])
        ],
        "links": p.get("links", []),
        "iframes": p.get("iframes", []),
    }


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def level_record(slug: str, p: dict[str, Any]) -> dict[str, Any]:
    body = "\n".join(s.get("text", "") for s in p["sections"])
    cycle = next(
        (s for s in sentences(body) if re.search(r"\bdesde\b.*\bhasta\b|\babarca\b", s, re.I)),
        "",
    )
    facts = [
        s
        for s in sentences(body)
        if FACT.search(s)
        and (
            re.search(r"\d", s)
            or re.search(r"\b(dos|tres|cuatro|cinco|seis|siete|ocho)\b", s, re.I)
        )
    ]
    accs = [
        {
            "label": f["q"],
            "label_shown": f.get("label_shown", f["q"]),
            "target": f.get("target", ""),
            "nth": f.get("nth", 0),
        }
        for f in p.get("faqs", [])
    ]
    grades = [a["label"] for a in accs if GRADE.search(a["label"])]
    intro = next((s["text"] for s in p["sections"] if len(s.get("text", "")) > 80), "")
    h1 = next((s["heading"] for s in p["sections"] if s.get("level") == 1), p["title"])
    return {
        "slug": slug,
        "name": h1,
        "path": p["path"],
        "url": p["url"],
        "cycle": cycle,
        "grades": grades,
        "accordions": accs,
        "intro": clip(intro, 1_200),
        "facts": facts[:12],
        "documents": [
            {"label": d.get("label", ""), "url": d["url"]} for d in p.get("documents", [])
        ],
    }


# ─── PDFs ─────────────────────────────────────────────────────────────────────


def pdf_size(url: str) -> int:
    """The PDF's size from a HEAD request; 0 when the server does not say."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status in (403, 405):
                raise Blocked(f"{url} answered {r.status}")
            return int(r.headers.get("content-length") or 0)
    except urllib.error.HTTPError as e:
        if e.code in (403, 405):
            raise Blocked(f"{url} answered {e.code}") from e
        return 0
    except (OSError, ValueError):
        return 0


def read_pdf(url: str, reader_cls: Any) -> dict[str, Any]:
    """One PDF's size, page count and text; a large one is listed without text,
    and not downloaded."""
    size = pdf_size(url)
    if size > PDF_MAX_BYTES:
        print(f"  pdf {url}: {size} bytes, listed without text", file=sys.stderr)
        return {"status": 200, "bytes": size, "n_pages": 0, "text": "", "skipped": "too large"}
    try:
        status, body, _ = fetch(url, timeout=120)
    except Exception as exc:  # reported, not fatal
        print(f"  pdf {url}: {exc}", file=sys.stderr)
        status, body = 0, b""
    if status in (403, 405):
        raise Blocked(f"{url} answered {status}")
    meta: dict[str, Any] = {"status": status, "bytes": len(body), "n_pages": 0, "text": ""}
    if status != 200 or not body:
        return meta
    if len(body) > PDF_MAX_BYTES:
        meta["skipped"] = "too large"
        return meta
    try:
        reader = reader_cls(io.BytesIO(body))
        meta["n_pages"] = len(reader.pages)
        parts: list[str] = []
        for pg in reader.pages[:30]:
            parts.append(pg.extract_text() or "")
            if sum(map(len, parts)) > PDF_TEXT_CAP * 2:
                break
        meta["text"] = re.sub(r"[ \t]+", " ", "\n".join(parts)).strip()
    except Exception as exc:  # a broken PDF is listed without text
        meta["error"] = str(exc)[:200]
    return meta


def read_pdfs(
    pages: dict[str, dict[str, Any]], offline: bool, refresh: bool
) -> list[dict[str, Any]]:
    """Every linked PDF, with its text when it is small enough to read."""
    from pypdf import PdfReader  # type: ignore[import-not-found]

    by_url: dict[str, dict[str, Any]] = {}
    for p in pages.values():
        docs = list(p.get("documents", []))
        for f in p.get("faqs", []):
            docs += f.get("documents", [])
        for c in p.get("cards", []):
            if re.search(r"\.pdf($|\?)", c.get("href", ""), re.I):
                docs.append({"label": c.get("title", ""), "url": c["href"]})
        for d in docs:
            url = d["url"].split("#")[0]
            row = by_url.setdefault(url, {"url": url, "labels": [], "pages": []})
            if d.get("label") and d["label"] not in row["labels"]:
                row["labels"].append(d["label"])
            if p["path"] not in row["pages"]:
                row["pages"].append(p["path"])
    out = []
    for url, row in sorted(by_url.items()):
        meta = None if refresh else cache_get(url)
        if meta is None and not offline:
            time.sleep(PAUSE_S)
            meta = read_pdf(url, PdfReader)
            cache_put(url, meta)
        meta = meta or {}
        out.append(
            {
                **row,
                "status": meta.get("status"),
                "n_pages": meta.get("n_pages", 0),
                "bytes": meta.get("bytes", 0),
                "text": clip(re.sub(r"\n{2,}", "\n", meta.get("text", "")), PDF_TEXT_CAP),
            }
        )
    return out


# ─── Outputs ──────────────────────────────────────────────────────────────────


def modified_by_path(types: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rows in types.values():
        for r in rows:
            if (p := site_path(r.get("link") or "")) and r.get("modified"):
                out[p] = r["modified"]
    return out


def write_outputs(
    raw: dict[str, dict[str, Any]],
    sitemaps: dict[str, list[str]],
    types: dict[str, list[dict[str, Any]]],
    pdfs: bool,
    offline: bool,
    refresh: bool,
) -> None:
    modified = modified_by_path(types)
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
        pages[final] = page_record(final, r, modified)
    for path, r in raw.items():
        if r.get("status") != 200:
            continue
        for link in r.get("page_links", []):
            q = site_path(link["url"])
            if q in broken and path not in broken[q]:
                broken[q].append(path)
    order = list(pages)
    order.sort(key=lambda p: (p != "/", p))
    L3.mkdir(parents=True, exist_ok=True)
    dump(L3 / "pages.json", [pages[p] for p in order], compact=True)
    secs = {p: sections_record(pages[p]) for p in order if not pages[p].get("empty")}
    dump(L3 / "sections.json", secs)
    levels = [level_record(u, pages[f"/unidad/{u}"]) for u in UNITS if f"/unidad/{u}" in pages]
    dump(L3 / "levels.json", levels)
    dump(L3 / "site.json", site_record(raw, pages, redirects, broken, sitemaps, types))
    if pdfs:
        docs = read_pdfs(pages, offline, refresh)
        dump(
            L3 / "documents.json",
            [{k: v for k, v in d.items() if k != "text"} for d in docs],
            compact=True,
        )
        print(f"pdfs {len(docs)} ({sum(1 for d in docs if d['text'])} with text)")
    write_site_map(pages, order, raw.get("/", {}).get("nav", {}))
    empty = sum(1 for p in pages.values() if p.get("empty"))
    print(
        f"pages {len(pages)} ({empty} empty), levels {len(levels)}, redirects {len(redirects)}, "
        f"broken internal links {len(broken)}"
    )


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
    sitemaps: dict[str, list[str]],
    types: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    home = raw.get("/", {})
    nav = home.get("nav", {})
    hosts: Counter[str] = Counter()
    outbound: dict[str, dict[str, Any]] = {}
    for r in raw.values():
        if r.get("status") != 200:
            continue
        for link in r.get("page_links", []):
            url = link["url"]
            host = urlsplit(url).hostname or ""
            if url.startswith(("mailto:", "tel:")) or (host and host not in (HOST, f"www.{HOST}")):
                hosts[host or url.split(":")[0]] += 1
                row = outbound.setdefault(url, {"url": url, "labels": [], "areas": [], "pages": 0})
                if link.get("text") and link["text"] not in row["labels"]:
                    row["labels"].append(link["text"])
                if link.get("area") not in row["areas"]:
                    row["areas"].append(link.get("area"))
                row["pages"] += 1
    lines = nav.get("footer", {}).get("address_lines", [])
    footer_text = " ".join(lines)
    phones = re.findall(r"\+?56[\s\d]{8,13}\d", footer_text)
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", footer_text)))
    cal = pages.get("/familia/calendario", {})
    return {
        "site": SITE,
        "crawled": dt.date.today().isoformat(),
        "nav": nav.get("menu", []),
        "mobile_menu": nav.get("mobile_toggle", ""),
        "footer": {
            "address_lines": lines,
            "phones": [" ".join(p.split()) for p in phones],
            "emails": emails,
            "links": nav.get("footer", {}).get("links", []),
        },
        "headers": home.get("headers", {}),
        "redirects": redirects,
        "broken_internal_links": dict(sorted(broken.items())),
        "empty_pages": sorted(p for p, v in pages.items() if v.get("empty")),
        "page_kinds": dict(Counter(p["kind"] for p in pages.values())),
        "sitemaps": {k: len(v) for k, v in sitemaps.items()},
        "wp_types": {k: len(v) for k, v in types.items()},
        "calendar": {"path": "/familia/calendario", "iframes": cal.get("iframes", [])},
        "outbound_hosts": dict(hosts.most_common()),
        "outbound_links": sorted(outbound.values(), key=lambda r: (-r["pages"], r["url"])),
    }


def write_site_map(pages: dict[str, dict[str, Any]], order: list[str], nav: dict[str, Any]) -> None:
    lines = [
        "# Mapa del sitio: cada página, sus títulos y acordeones",
        "",
        f"Sources: L3/pages.json, L3/sections.json y L3/site.json (generados por build.py desde un "
        f"crawl con navegador headless de {SITE}).",
        "",
        "Los títulos están escritos como los muestra la página (innerText: los botones de acordeón "
        "salen en mayúsculas por CSS). `(pseudo)` marca un párrafo en negrita usado como título. "
        "`▸` es un botón de acordeón (se abre con un clic; su id `#collapse_X_Y` se repite en "
        "cada página, así que se busca por su texto). Cada navegación es una carga de página "
        "completa. Las páginas vacías (plantilla por defecto de WordPress) están al final: no "
        "llevar al visitante ahí.",
        "",
        "## Menú principal (#menu-menu-1)",
    ]

    def nav_lines(items: list[dict[str, Any]], depth: int) -> None:
        for it in items:
            href = rel(it.get("href", ""))
            mark = " (abre submenú, no navega)" if it.get("toggle") else ""
            lines.append(f"{'  ' * depth}- {it.get('label', '')} ({href}){mark}")
            nav_lines(it.get("children", []), depth + 1)

    nav_lines(nav.get("menu", []), 0)
    links = nav.get("footer", {}).get("links", [])
    if links:
        lines.append("- Footer: " + "; ".join(f"{x['label']} ({rel(x['href'])})" for x in links))
    lines.append("")
    for path in order:
        p = pages[path]
        if p.get("empty"):
            continue
        lines.append(f"## {path} ({p['kind']})")
        lines.append(f"Title: {p['title']}")
        for s in p["sections"]:
            if not s["heading"]:
                continue
            mark = " (pseudo)" if s.get("pseudo") else ""
            lines.append(f"{'  ' * max(0, min(s.get('level', 2), 4) - 1)}- {s['heading']}{mark}")
        for f in p.get("faqs", []):
            lines.append(f"  ▸ {f.get('label_shown') or f['q']}")
        for a in p.get("anchors", []):
            lines.append(f"- ancla #{a['id']}" + (f" ({a['heading']})" if a.get("heading") else ""))
        if p.get("documents"):
            docs = "; ".join(
                d.get("label") or d["url"].rsplit("/", 1)[-1] for d in p["documents"][:14]
            )
            more = " …" if len(p["documents"]) > 14 else ""
            lines.append(f"- PDFs ({len(p['documents'])}): {docs}{more}")
        if p.get("links"):
            out = "; ".join(f"{x['label']} → {x['url']}" for x in p["links"][:8])
            lines.append(f"- Enlaces externos: {out}")
        if p.get("iframes"):
            lines.append(
                "- iframes: "
                + "; ".join(
                    f"{f['selector']} ({urlsplit(f['src']).hostname})" for f in p["iframes"]
                )
            )
        lines.append("")
    empty = [p for p in order if pages[p].get("empty")]
    if empty:
        lines += ["## Páginas vacías o de plantilla (no usar)", ", ".join(empty), ""]
    (L2 / "site-map.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def rel(href: str) -> str:
    parts = urlsplit(href)
    if parts.hostname in (HOST, f"www.{HOST}"):
        return parts.path or "/"
    return href


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="render the site and write L3 + generated L2")
    c.add_argument("--offline", action="store_true", help="use the cache only")
    c.add_argument("--refresh", action="store_true", help="ignore the cache")
    c.add_argument("--pdfs", action="store_true", help="also read linked PDFs (needs pypdf)")
    c.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = ap.parse_args()
    try:
        sitemaps = read_sitemaps(args.offline, args.refresh)
        types = read_wp_types(args.offline, args.refresh)
        seeds = [p for urls in sitemaps.values() for u in urls if (p := site_path(u))]
        print(
            f"sitemaps {len(sitemaps)} ({len(seeds)} URLs), wp types {len(types)}", file=sys.stderr
        )
        raw = asyncio.run(crawl_async(seeds, args.offline, args.refresh, args.max_pages))
        write_outputs(raw, sitemaps, types, args.pdfs, args.offline, args.refresh)
    except Blocked as exc:
        sys.exit(f"stopped: the site refused the crawl ({exc}). Nothing was written.")


if __name__ == "__main__":
    main()
