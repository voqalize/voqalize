# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Clini's L3 knowledge: www.clini.cl and its booking and price services, as
data, read from a real browser.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON. Network is touched only by the fetching commands; each
page's extraction is cached outside the repository, so a re-run is cheap and
``search`` never fetches anything.

www.clini.cl is a Webflow site in Spanish (es-CL). Its content sits in Webflow
widgets that hide text until clicked: tabs (``.w-tab-link`` → ``.w-tab-pane``),
dropdowns (``.w-dropdown-toggle`` → ``.w-dropdown-list``, which is how the FAQs
and the branch hours are built), sliders (``.w-slider``, one slide shown) and
Finsweet CMS lists. So the crawl drives headless Chromium (Playwright, one fresh
non-persistent context, ``es-CL``, 1440x900), scrolls each page to the bottom so
lazy content loads, and reads the rendered DOM, hidden panes included. Run from
``voqalize/demos``; Playwright is not a demos dependency, so pull it in for the
run (its Chromium must be installed once with ``playwright install chromium``)::

    uv run --with playwright python clini/backend/knowledge/build.py crawl
    uv run --with playwright python clini/backend/knowledge/build.py crawl --refresh
    uv run --with playwright python clini/backend/knowledge/build.py crawl --only /laboratorio /ubicaciones
    uv run python clini/backend/knowledge/build.py crawl --offline
    uv run --with playwright python clini/backend/knowledge/build.py branches
    uv run --with playwright python clini/backend/knowledge/build.py agenda
    uv run python clini/backend/knowledge/build.py prices            # full harvest, ~3k queries
    uv run python clini/backend/knowledge/build.py prices --terms "resonancia rodilla,hemograma"
    uv run python clini/backend/knowledge/build.py maps              # L2/site-map.md, L2/blog-index.md
    uv run python clini/backend/knowledge/build.py search "ayuno hemograma"

``crawl`` seeds from ``www.clini.cl/sitemap.xml``, the header and footer
navigation and a few known aliases, follows every same-host link, and writes,
next to this file:

- ``L3/pages.json`` — the site's pages (not the blog), one JSON object a line:
  ``{path, url, type, title, description, h1, unlisted?, sections, faqs, tabs,
  sliders, forms, ctas}``. ``sections`` are the page's top-level blocks in order,
  ``{heading, level, selector, text, items, reveal, ctas}``: ``heading`` is the
  block's first visible heading as rendered (``innerText``, first line,
  whitespace collapsed), which is what the extension matches; ``selector`` is a
  CSS selector unique on that page at crawl time (Webflow designer classes such
  as ``section.section-403._2``, so match by heading first); ``text`` is the
  block's visible text followed by its hidden text (inactive tab panes, dropdown
  answers), capped; ``items`` the block's other headings. A block without a
  heading is labelled ``[block] first words`` with ``level`` 0. ``faqs`` are
  ``{q, a, section}`` (``section`` = the heading of the block holding the
  dropdown); ``tabs`` ``{section, labels, panes: [{tab, text}]}``; ``ctas`` the
  booking, price, results, telemedicine, WhatsApp and phone links on the page.
  ``unlisted`` marks a page no other page links to, or that the sitemap leaves
  out (campaign landings). 404s, redirects and ``/mantencion`` are not pages;
  they are listed in ``site.json``.
- ``L3/blog.json`` — the blog posts (``/blog/*``, ``/blog-mujer/*``), light:
  ``{path, url, title, description, date, headings, text}``.
- ``L3/site.json`` — crawl date, counts, redirects, missing pages, the header
  and footer navigation, response headers of every host, and the layout probes
  (fixed header height on desktop and mobile, fixed overlays, modals).

``branches`` reads ``/ubicaciones`` (Finsweet CMS list) into ``L3/branches.json``:
``[{name, address, comuna, region, services, hours, book_link}]``.

``agenda`` opens ``agenda-web.clini.cl/?servicio=N`` for every known service and
writes ``L3/agenda_services.json``: ``{"N": {name, url, prestaciones: [{code,
name}], regions: [{code, name, default}], sectors, linked_from}}``, where
``linked_from`` lists the site pages that link that service (from the crawl
cache; the legacy ``agenda.clini.cl`` and ``agenda-imagenes.clini.cl`` links are
mapped to the services they redirect to).

``prices`` harvests the public cotizador search
(``cotizador-web.clini.cl/Cotizar?handler=Buscar&q=``, 12 results a query) with
the words of the crawled pages plus three-letter stems, merges into
``L3/prices.json`` by id and keeps ``{id, nombre, codigo, categoria, servicio,
precioFonasa, precioParticular, requiereContraste, preparacion}``. Prices are
CLP; ``precioFonasa`` is the Fonasa Nivel 1 copago (tramos B, C, D).

``--offline`` builds from the cache only; ``--refresh`` re-renders everything.
The cache is ``$XDG_CACHE_HOME/voqalize-clini`` (``~/.cache`` by default).
Nothing here submits a form, books a slot or looks up a patient: the booking
POST is route-blocked in every agenda-web context.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
L3 = HERE / "L3"
SITE = "https://www.clini.cl"
SITEMAP = f"{SITE}/sitemap.xml"
AGENDA = "https://agenda-web.clini.cl"
COTIZADOR = "https://cotizador-web.clini.cl"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-clini"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
PARALLEL = 4
#: Aliases the site links or redirects; crawled so the redirect map is complete.
EXTRA = (
    "/cirugia-lasik/fonasa",
    "/imagenes-fonasa-nivel-1",
    "/chequeos-medicos",
    "/contacto",
    "/quienes-somos",
    "/resultados-clini",
)
#: Not a page: "Servicio en Mantenimiento" (``/chequeos-medicos`` lands here).
NOT_PAGES = ("/mantencion",)
BLOG_PREFIXES = ("/blog/", "/blog-mujer/")
#: Every agenda-web ``servicio`` code seen in the booking script and the site.
AGENDA_CODES = (55, 57, 62, 64, 65, 68, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 86)
#: Legacy booking hosts and the agenda-web service each one redirects to.
LEGACY_AGENDA = {
    "PET_CT": 71,
    "MAMOGRAFIA": 65,
    "ECOGRAFIA": 81,
    "RADIOGRAFIA": 57,
    "RESONANCIA": 64,
    "SCANNER": 70,
}
#: Links that are a way to book, pay, see results or reach a person.
CTA_HOSTS = (
    "agenda-web.clini.cl",
    "agenda.clini.cl",
    "agenda-imagenes.clini.cl",
    "reservo.cl",
    "cotizador-web.clini.cl",
    "cotizador-inteligente.clini.cl",
    "medipass",
    "dalca.cl",
    "resultados.clini.cl",
    "procloudhub.com",
    "wa.me",
    "whatsapp.com",
    "tel:",
)
TEXT_CAP = 1500
BLOG_TEXT_CAP = 1200
HEADERS_KEPT = (
    "content-security-policy",
    "x-frame-options",
    "server",
    "x-powered-by",
    "content-type",
    "cache-control",
)

# --------------------------------------------------------------------------- page JS

# Scroll to the bottom in steps so lazy images and CMS lists load, then back up.
SCROLL_JS = r"""
async () => {
  const se = document.scrollingElement;
  let y = 0, h = se.scrollHeight;
  while (y < h) {
    y += 700; window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 120));
    h = se.scrollHeight;
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 600));
  return h;
}
"""

# One pass over the rendered page: top-level blocks with their headings, text
# (visible and hidden), links and widgets; Webflow dropdown FAQs, tabs, sliders;
# forms; every link (for the crawl frontier).
PAGE_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.height > 0 && r.width > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const clean = s => (s || '').replace(/[\u00a0\u200d\u200b]/g, ' ').replace(/[ \t]+/g, ' ')
    .replace(/\n\s*\n+/g, '\n').trim();
  // Text of a hidden element (no innerText): its text nodes joined by spaces.
  const deep = el => { if (!el) return ''; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const out = [];
    for (let n = w.nextNode(); n; n = w.nextNode()) { const t = n.textContent.trim(); if (t) out.push(t); } return clean(out.join(' ')); };
  const genCls = c => /^w-node-|^w--|^wf-|[0-9a-f]{8}-/.test(c);
  const uniqSel = el => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const tag = el.tagName.toLowerCase();
    const classes = [...el.classList].filter(c => !genCls(c));
    for (let n = 1; n <= classes.length; n++) {
      const s = tag + classes.slice(0, n).map(c => '.' + CSS.escape(c)).join('');
      if (document.querySelectorAll(s).length === 1) return s;
    }
    const parent = el.parentElement;
    const idx = [...parent.children].filter(c => c.tagName === el.tagName).indexOf(el) + 1;
    const ps = parent === document.body ? 'body' : (parent.id ? '#' + CSS.escape(parent.id) : null);
    return ps ? ps + ' > ' + tag + ':nth-of-type(' + idx + ')' : null;
  };
  const CHROME = '.header-fixed-clini, .footer-nuevo, .w-nav, nav, #clinitoEmbed, .modal-feriados, .div-block-475';
  const inChrome = e => !!e.closest(CHROME);
  const skip = el => ['SCRIPT', 'STYLE', 'NOSCRIPT', 'LINK', 'IFRAME', 'TEMPLATE'].includes(el.tagName)
    || el.matches(CHROME + ', .w-embed:empty');
  const blocks = [];
  const collect = (root, depth) => {
    for (const c of root.children) {
      if (skip(c)) continue;
      if (getComputedStyle(c).position === 'fixed') continue;
      const isWrapper = c.tagName !== 'SECTION' && c.children.length > 1
        && [...c.children].filter(x => x.tagName === 'SECTION').length >= 2;
      if (isWrapper && depth < 3) { collect(c, depth + 1); continue; }
      if (c.getBoundingClientRect().height < 20 && !c.textContent.trim()) continue;
      blocks.push(c);
    }
  };
  collect(document.body, 0);
  const blockOf = e => blocks.findIndex(b => b.contains(e));
  const headingOf = el => {
    const h = [...el.querySelectorAll('h1,h2,h3,h4,h5')].find(vis) || el.querySelector('h1,h2,h3,h4');
    return h ? { text: clean(h.innerText || h.textContent), level: +h.tagName[1] } : null;
  };
  const link = a => ({ t: clean(a.innerText || a.textContent).slice(0, 100), href: a.getAttribute('href'),
    target: a.target || undefined });
  const sections = blocks.map(el => {
    const r = el.getBoundingClientRect();
    const visible = vis(el);
    const hidden = [];
    el.querySelectorAll('.w-tab-pane:not(.w--tab-active), .w-dropdown-list, .w-slide[aria-hidden="true"], [style*="display: none"], [style*="display:none"]')
      .forEach(h => { const t = deep(h); if (t) hidden.push(t.slice(0, 2000)); });
    return {
      tag: el.tagName.toLowerCase(), id: el.id || null, cls: String(el.className || ''), selector: uniqSel(el),
      heading: headingOf(el), top: Math.round(r.top + scrollY), height: Math.round(r.height), visible,
      text: (visible ? clean(el.innerText) : deep(el)).slice(0, 8000), hidden_text: hidden.slice(0, 30),
      widgets: {
        tab_links: [...el.querySelectorAll('.w-tab-link')].map(t => clean(t.innerText || t.textContent)),
        slides: el.querySelectorAll('.w-slide').length,
        dropdowns: el.querySelectorAll('.w-dropdown').length,
        forms: el.querySelectorAll('form').length,
        iframes: [...el.querySelectorAll('iframe')].map(f => f.src),
        cms_items: el.querySelectorAll('.w-dyn-item').length,
      },
      headings: [...el.querySelectorAll('h1,h2,h3,h4,h5,h6')]
        .map(h => ({ l: +h.tagName[1], t: clean(h.innerText || h.textContent).split('\n')[0].slice(0, 200), v: vis(h) }))
        .filter(h => h.t),
      links: [...el.querySelectorAll('a[href]')].map(link).filter(l => l.href && l.href !== '#').slice(0, 120),
    };
  });
  const faqs = [...document.querySelectorAll('.w-dropdown')].filter(d => !inChrome(d)).map(d => ({
    q: clean(d.querySelector('.w-dropdown-toggle')?.textContent),
    a: deep(d.querySelector('.w-dropdown-list')),
    block: blockOf(d),
  })).filter(f => f.q);
  // The newer exam pages use a custom accordion in an embed: .faq-clini .faq-item >
  // button.faq-question (with a ⌃/⌄ arrow) + .faq-answer; the item toggles .active.
  for (const d of document.querySelectorAll('.faq-item')) {
    const qb = d.querySelector('.faq-question'); const ab = d.querySelector('.faq-answer');
    if (!qb || !ab || inChrome(d)) continue;
    faqs.push({ q: deep(qb).replace(/[\u2303\u2304\u25b2\u25bc]/g, '').trim(), a: deep(ab), block: blockOf(d), kind: 'faq-item' });
  }
  const tabs = [...document.querySelectorAll('.w-tabs')].filter(t => !inChrome(t)).map(t => ({
    block: blockOf(t),
    panes: [...t.querySelectorAll('.w-tab-link')].map(l => {
      const p = t.querySelector('.w-tab-pane[data-w-tab="' + l.dataset.wTab + '"]');
      return { tab: clean(l.innerText || l.textContent), text: deep(p).slice(0, 3000) };
    }),
  }));
  const sliders = [...document.querySelectorAll('.w-slider')].filter(s => !inChrome(s)).map(s => ({
    block: blockOf(s), autoplay: s.dataset.autoplay || null,
    slides: [...s.querySelectorAll('.w-slide')].map(x => deep(x).slice(0, 400) || ('[img] ' + (x.querySelector('img')?.alt || ''))),
  }));
  const forms = [...document.querySelectorAll('form')].map(f => ({
    selector: uniqSel(f), id: f.id || null, name: f.getAttribute('name'), block: blockOf(f),
    fields: [...f.querySelectorAll('input, select, textarea')].map(i => {
      let label = i.labels && i.labels[0] ? clean(i.labels[0].innerText) : null;
      if (!label) { const prev = i.closest('div')?.querySelector('label'); if (prev) label = clean(prev.innerText); }
      return { tag: i.tagName.toLowerCase(), type: i.type, name: i.name || null, id: i.id || null,
        data_name: i.dataset.name || null, required: i.required, placeholder: i.placeholder || null, label,
        pattern: i.pattern || null,
        options: i.tagName === 'SELECT' ? [...i.options].map(o => clean(o.text)).filter(Boolean) : undefined };
    }),
    submit: [...f.querySelectorAll('[type=submit], button')].map(s => clean(s.value || s.innerText)).filter(Boolean),
    success: clean(f.closest('.w-form')?.querySelector('.w-form-done')?.textContent) || null,
  }));
  const pageLinks = [...document.querySelectorAll('a[href]')].filter(a => !inChrome(a)).map(a => ({ ...link(a), block: blockOf(a) }));
  return {
    url: location.href, title: document.title, description: document.querySelector('meta[name=description]')?.content || null,
    canonical: document.querySelector('link[rel=canonical]')?.href || null, lang: document.documentElement.lang,
    h1: [...document.querySelectorAll('h1')].map(h => clean(h.textContent)),
    scroll_height: document.scrollingElement.scrollHeight,
    sections, faqs, tabs, sliders, forms, page_links: pageLinks,
    all_links: [...new Set([...document.querySelectorAll('a[href]')].map(a => a.href))],
    jsonld: [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => s.textContent.slice(0, 3000)),
  };
}
"""

# The header and footer navigation.
CHROME_JS = r"""
() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const L = root => root ? [...root.querySelectorAll('a')].map(a => ({ text: clean(a.innerText || a.textContent), href: a.getAttribute('href'), target: a.target || undefined })).filter(l => l.href && l.href !== '#') : [];
  const hdr = document.querySelector('.header-fixed-clini');
  const menus = hdr ? [...hdr.querySelectorAll('.w-dropdown')].map(d => ({ menu: clean(d.querySelector('.w-dropdown-toggle')?.innerText), links: L(d.querySelector('.w-dropdown-list')) })) : [];
  const seen = new Set();
  const uniq = ls => ls.filter(l => { const k = l.text + '|' + l.href; if (seen.has(k)) return false; seen.add(k); return true; });
  return { menus, header: uniq(L(hdr)), footer: uniq(L(document.querySelector('.footer-nuevo'))) };
}
"""

# Layout facts the extension depends on: the fixed header, overlays, modals.
PROBE_JS = r"""
() => {
  const hdr = document.querySelector('.header-fixed-clini');
  const nav = document.querySelector('.navbar7_component-2') || document.querySelector('.w-nav');
  const r = e => e ? Math.round(e.getBoundingClientRect().bottom) : null;
  const fixed = [...document.querySelectorAll('body *')].filter(e => {
    const cs = getComputedStyle(e);
    return (cs.position === 'fixed' || cs.position === 'sticky') && e.getBoundingClientRect().height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  }).filter(e => !e.parentElement.closest('[style*="fixed"]')).slice(0, 12).map(e => {
    const b = e.getBoundingClientRect();
    return { selector: e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].join('.'),
      rect: [b.top, b.left, b.width, b.height].map(Math.round), z: getComputedStyle(e).zIndex };
  });
  const modals = [...document.querySelectorAll('.modal-feriados, .pop-up-modal, [class*=cookie]')]
    .map(e => ({ cls: String(e.className), display: getComputedStyle(e).display })).slice(0, 6);
  return {
    header_height: Math.max(r(hdr) || 0, r(nav) || 0),
    scroll_element: document.scrollingElement === document.documentElement ? 'window' : 'other',
    scroll_padding_top: getComputedStyle(document.documentElement).scrollPaddingTop,
    scroll_behavior: getComputedStyle(document.documentElement).scrollBehavior,
    fixed, modals,
  };
}
"""

BRANCHES_JS = r"""
() => {
  const clean = s => (s || '').replace(/[\u00a0\u200d]/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  const nodes = el => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const out = [];
    for (let n = w.nextNode(); n; n = w.nextNode()) { const t = clean(n.textContent); if (t) out.push(t); } return out; };
  const items = [...document.querySelectorAll('.w-dyn-item')].filter(it => it.querySelector('[fs-cmsfilter-field=Comuna], [fs-cmsfilter-field=comuna]'));
  return items.map(it => {
    const field = f => [...it.querySelectorAll('[fs-cmsfilter-field]')].filter(e => e.getAttribute('fs-cmsfilter-field').toLowerCase() === f).map(e => clean(e.textContent)).filter(Boolean);
    const list = it.querySelector('.w-dropdown-list');
    const text = clean(it.innerText || it.textContent);
    const m = text.match(/Direcci[oó]n:\s*\n?([^\n]+)/);
    return {
      name: clean(it.querySelector('h2,h3,h4,h5,.heading,[class*=title]')?.textContent),
      address: m ? clean(m[1]) : '',
      comuna: field('comuna')[0] || '', region: field('region')[0] || '', services: field('servicio'),
      hours: list ? nodes(list) : [],
      hours_text: list ? clean(list.textContent) : '',
      book_link: [...it.querySelectorAll('a')].filter(a => /reserv|agend/i.test(a.textContent)).map(a => a.getAttribute('href')),
    };
  });
}
"""

AGENDA_JS = r"""
() => {
  const opts = id => { const e = document.getElementById(id); return e && e.options ? [...e.options].filter(o => o.value).map(o => ({ v: o.value, t: o.text.trim(), sel: o.selected })) : null; };
  const reg = document.getElementById('regionSelect');
  return { service_label: document.querySelector('.service-box .service-name, .service-name')?.innerText.trim() || null,
    region: opts('regionSelect'), region_hidden: reg ? !!reg.closest('[hidden]') : null,
    sectors: opts('sector62Select'), prestacion: opts('prestacionSelect') };
}
"""

# --------------------------------------------------------------------------- cache


def cache_path(url: str, kind: str) -> Path:
    name = hashlib.sha1(url.encode()).hexdigest()[:12]
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", urllib.parse.urlsplit(url).path.strip("/") or "index")
    return CACHE / kind / f"{tail[-80:]}-{name}.json"


def cache_get(url: str, kind: str) -> dict[str, Any] | None:
    p = cache_path(url, kind)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cache_put(url: str, kind: str, data: dict[str, Any]) -> None:
    p = cache_path(url, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def cached_site() -> list[dict[str, Any]]:
    d = CACHE / "site"
    return (
        [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]
        if d.is_dir()
        else []
    )


# --------------------------------------------------------------------------- urls


def site_path(url: str) -> str | None:
    """``https://clini.cl/Laboratorio/?a#b`` → ``/laboratorio``; None off the site."""
    u = urllib.parse.urlsplit(urllib.parse.urljoin(SITE + "/", url.strip()))
    if u.scheme not in ("http", "https") or u.netloc.lower() not in ("clini.cl", "www.clini.cl"):
        return None
    path = re.sub(r"/{2,}", "/", u.path).rstrip("/").lower() or "/"
    if path.startswith("/cdn-cgi/") or re.search(
        r"\.(pdf|jpe?g|png|webp|svg|gif|docx?|xlsx?)$", path
    ):
        return None
    return path


def fold(s: str) -> str:
    d = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in d if not unicodedata.combining(c))


def collapse(s: str | None) -> str:
    return " ".join((s or "").split())


def headers_of(h: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in sorted(h.items()) if k.lower() in HEADERS_KEPT}


def page_type(path: str) -> str:
    for pre, t in (
        ("/blog-mujer/", "blog-mujer"),
        ("/blog/", "blog"),
        ("/examenes/", "exam-info"),
        ("/laboratorio/", "lab-branch"),
        ("/convenios-salud/", "agreement"),
        ("/centro-oncologico/", "oncology-cancer"),
        ("/imagenes/resonancias-magneticas/", "mri-body-part"),
        ("/cirugia-lasik", "lasik"),
        ("/imagenes", "imaging"),
        ("/cardiologia", "cardiology"),
        ("/examenes-de-cardiologia", "cardiology"),
        ("/mujer", "women"),
        ("/campanas/", "campaign"),
        ("/solicitudes/", "request-form"),
    ):
        if path.startswith(pre):
            return t
    return "core"


# --------------------------------------------------------------------------- crawl


async def new_context(browser: Any, mobile: bool = False) -> Any:
    vp = {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900}
    ctx = await browser.new_context(
        viewport=vp, locale="es-CL", user_agent=UA, is_mobile=mobile, has_touch=mobile
    )
    # Never book anything, never look up a patient.
    await ctx.route("**/*handler=AgendarCitaMedica*", lambda r: r.abort())
    await ctx.route("**/*handler=PacientePorDocumento*", lambda r: r.abort())
    return ctx


async def render(ctx: Any, url: str) -> dict[str, Any]:
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=10_000)
        out: dict[str, Any] = {
            "url": url,
            "final_url": page.url,
            "status": resp.status if resp else 0,
            "fetched": time.strftime("%Y-%m-%d"),
        }
        if out["status"] == 200:
            await page.evaluate(SCROLL_JS)
            out["data"] = await page.evaluate(PAGE_JS)
        return out
    finally:
        await page.close()


async def fetch_text(ctx: Any, url: str) -> tuple[int, str, dict[str, str]]:
    r = await ctx.request.get(url, timeout=30_000, max_redirects=0, fail_on_status_code=False)
    return r.status, await r.text(), r.headers


async def probe(browser: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mobile in (False, True):
        ctx = await new_context(browser, mobile)
        page = await ctx.new_page()
        await page.goto(SITE + "/", wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3000)
        out["mobile" if mobile else "desktop"] = await page.evaluate(PROBE_JS)
        if not mobile:
            out["nav"] = await page.evaluate(CHROME_JS)
        await ctx.close()
    return out


async def crawl_async(offline: bool, refresh: bool, only: list[str]) -> None:
    from playwright.async_api import async_playwright

    meta: dict[str, Any] = (
        json.loads((CACHE / "meta.json").read_text()) if (CACHE / "meta.json").exists() else {}
    )
    if offline:
        write_outputs(meta)
        return
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await new_context(browser)
        status, xml, _ = await fetch_text(ctx, SITEMAP)
        sitemap = sorted(
            {sp for u in re.findall(r"<loc>([^<]+)</loc>", xml) if (sp := site_path(u))}
        )
        print(f"sitemap: {status}, {len(sitemap)} urls", flush=True)
        meta["sitemap"] = sitemap or meta.get("sitemap", [])
        meta["probes"] = await probe(browser)
        nav = meta["probes"].get("nav", {})
        seeds = list(meta["sitemap"]) + list(EXTRA)
        for links in [nav.get("header", []), nav.get("footer", [])] + [
            m["links"] for m in nav.get("menus", [])
        ]:
            seeds += [sp for link in links if (sp := site_path(link["href"]))]
        meta["hosts"] = {}
        for host in (SITE, AGENDA, COTIZADOR):
            try:
                st, _, h = await fetch_text(ctx, host + "/")
                meta["hosts"][host] = {"status": st} | headers_of(h)
            except Exception as exc:
                meta["hosts"][host] = {"error": str(exc)[:200]}
        follow = not only
        queue: asyncio.Queue[str] = asyncio.Queue()
        seen: set[str] = set()
        for sp in only or seeds:
            sp = site_path(sp) or sp
            if sp not in seen:
                seen.add(sp)
                queue.put_nowait(sp)
        done = 0

        async def worker() -> None:
            nonlocal done
            while True:
                try:
                    path = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                url = SITE + ("" if path == "/" else path)
                rec = None if refresh or only else cache_get(url, "site")
                if rec is None:
                    try:
                        rec = await render(ctx, url)
                    except Exception as exc:
                        rec = {"url": url, "status": 0, "error": str(exc)[:300]}
                    if rec.get("status"):
                        cache_put(url, "site", rec)
                done += 1
                title = (rec.get("data") or {}).get("title") or rec.get("error", "")
                print(f"{done:4} {rec.get('status')} {path} {title[:60]}", flush=True)
                if follow:
                    for link in (rec.get("data") or {}).get("all_links", []):
                        sp = site_path(link)
                        if sp and sp not in seen:
                            seen.add(sp)
                            queue.put_nowait(sp)

        await asyncio.gather(*[worker() for _ in range(PARALLEL)])
        await browser.close()
    meta["crawled"] = time.strftime("%Y-%m-%d")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    write_outputs(meta)


# --------------------------------------------------------------------------- records


def _is_faq(q: str, a: str) -> bool:
    """A dropdown that asks something — not a menu ("Agendar hora") or the hours."""
    if fold(q).startswith("ver horarios"):
        return False
    return "?" in q or len(a.split()) >= 12


def _cta(link: dict[str, Any]) -> bool:
    href = link.get("href") or ""
    return any(h in href for h in CTA_HOSTS) or bool(
        re.search(r"agend|reserv|cotiz", link.get("t") or "", re.I)
    )


def _label(sec: dict[str, Any]) -> str:
    words = collapse(sec.get("text")).split()[:6]
    block = (sec.get("cls") or sec.get("tag") or "block").split(" ")[0]
    return f"[{block}] {' '.join(words)}".strip()


def page_record(rec: dict[str, Any], inbound: Counter[str], sitemap: set[str]) -> dict[str, Any]:
    d = rec["data"]
    path = site_path(rec["url"]) or "/"
    sections: list[dict[str, Any]] = []
    kept: dict[int, str] = {}
    for i, s in enumerate(d["sections"]):
        h = s.get("heading") or {}
        heading = collapse((h.get("text") or "").split("\n")[0])
        visible = collapse(s.get("text"))
        hidden = [collapse(t) for t in s.get("hidden_text", []) if t and collapse(t) not in visible]
        text = " ".join([visible, *dict.fromkeys(hidden)])
        if heading and text.startswith(heading):
            text = text[len(heading) :].strip()
        if not heading and not text:
            continue
        w = s.get("widgets", {})
        reveal: list[str] = []
        if w.get("tab_links"):
            reveal.append("tabs: " + ", ".join(w["tab_links"]))
        if w.get("dropdowns"):
            reveal.append(f"{w['dropdowns']} dropdown(s)")
        if w.get("slides"):
            reveal.append(f"slider, {w['slides']} slides")
        if w.get("cms_items"):
            reveal.append(f"{w['cms_items']} CMS items")
        if w.get("forms"):
            reveal.append("form")
        items = [x["t"] for x in s.get("headings", [])[1:] if x["t"] and x["t"] != heading]
        ctas = list(
            {
                (link["t"], link["href"]): {"text": link["t"], "href": link["href"]}
                for link in s.get("links", [])
                if _cta(link)
            }.values()
        )
        sec: dict[str, Any] = {
            "heading": heading or _label(s),
            "level": h.get("level", 0) if heading else 0,
            "selector": s.get("selector"),
            "text": text[:TEXT_CAP],
        }
        if items:
            sec["items"] = list(dict.fromkeys(items))[:25]
        if reveal:
            sec["reveal"] = reveal
        if ctas:
            sec["ctas"] = ctas[:12]
        if not s.get("visible"):
            sec["hidden"] = True
        sections.append(sec)
        kept[i] = sec["heading"]
    faqs = [
        {"q": collapse(f["q"]), "a": collapse(f.get("a"))}
        | (
            {"section": kept[f["block"]]}
            if f.get("block", -1) in kept and not kept[f["block"]].startswith("[")
            else {}
        )
        | ({"widget": f["kind"]} if f.get("kind") else {})
        for f in d.get("faqs", [])
        if _is_faq(collapse(f["q"]), collapse(f.get("a")))
    ]
    faqs = list({f["q"]: f for f in faqs}.values())
    tabs = [
        {
            "section": kept.get(t["block"]),
            "labels": [p["tab"] for p in t["panes"]],
            "panes": [
                {"tab": p["tab"], "text": collapse(p["text"])[:TEXT_CAP]} for p in t["panes"]
            ],
        }
        for t in d.get("tabs", [])
        if t["panes"]
    ]
    sliders = [
        {
            "section": kept.get(s["block"]),
            "autoplay": s.get("autoplay"),
            "slides": [collapse(x)[:300] for x in s["slides"]],
        }
        for s in d.get("sliders", [])
    ]
    forms = []
    for f in d.get("forms", []):
        if f.get("name") == "wf-form-newsletter" or f.get("id") in (
            "wf-form-newsletter",
            "email-form",
        ):
            continue
        fields = [
            {k: v for k, v in x.items() if v not in (None, "", [], False)}
            for x in f["fields"]
            if x.get("type") not in ("hidden",)
        ]
        forms.append(
            {
                k: v
                for k, v in {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "selector": f.get("selector"),
                    "section": kept.get(f.get("block", -1)),
                    "fields": fields,
                    "submit": " / ".join(f.get("submit", [])),
                    "success": f.get("success"),
                }.items()
                if v
            }
        )
    ctas = {}
    for link in d.get("page_links", []):
        if _cta(link) and not link["href"].startswith("#"):
            key = (link["t"], link["href"])
            ctas.setdefault(
                key,
                {"text": link["t"], "href": link["href"]}
                | ({"new_tab": True} if link.get("target") == "_blank" else {})
                | ({"section": kept[link["block"]]} if link.get("block", -1) in kept else {}),
            )
    out: dict[str, Any] = {
        "path": path,
        "url": rec["url"],
        "type": page_type(path),
        "title": collapse(d.get("title")),
        "description": collapse(d.get("description")),
        "h1": [collapse(x) for x in d.get("h1", []) if collapse(x)],
        "sections": sections,
        "faqs": faqs,
        "tabs": tabs,
        "sliders": sliders,
        "forms": forms,
        "ctas": list(ctas.values())[:40],
    }
    if path not in sitemap or not inbound.get(path):
        out["unlisted"] = True
    return out


def blog_record(rec: dict[str, Any]) -> dict[str, Any]:
    d = rec["data"]
    path = site_path(rec["url"]) or "/"
    date = ""
    for j in d.get("jsonld", []):
        if m := re.search(r'"datePublished"\s*:\s*"([^"]+)"', j):
            date = m.group(1)[:10]
            break
    body = d["sections"][0] if d.get("sections") else {}
    heads: list[str] = []
    for x in body.get("headings", []):
        # The post ends where the related posts and share links begin.
        if re.match(r"(explora m[aá]s|comparte en|art[ií]culos relacionados)", fold(x["t"])):
            break
        heads.append(x["t"])
    title = collapse(d.get("title")).removesuffix(" | CLINI").strip()
    text = collapse(body.get("text"))
    text = text.removeprefix("Blog |").strip()
    while text.startswith(title):
        text = text[len(title) :].strip()
    return {
        "path": path,
        "url": rec["url"],
        "type": page_type(path),
        "title": title,
        "description": collapse(d.get("description")),
        "date": date,
        "headings": list(dict.fromkeys(h for h in heads if fold(h) != fold(title)))[:20],
        "text": text[:BLOG_TEXT_CAP],
    }


def _dump_lines(path: Path, items: list[dict[str, Any]]) -> None:
    """A JSON list, one object a line: compact, and a re-crawl diffs by page."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items)
    path.write_text(f"[\n{body}\n]\n", encoding="utf-8")


def write_outputs(meta: dict[str, Any]) -> None:
    recs = cached_site()
    sitemap = set(meta.get("sitemap", []))
    inbound: Counter[str] = Counter()
    redirects: dict[str, str] = {}
    missing: list[str] = []
    good: list[dict[str, Any]] = []
    for r in recs:
        path = site_path(r["url"]) or "/"
        final = site_path(r.get("final_url") or r["url"]) or path
        if r.get("status") != 200:
            missing.append(path)
            continue
        if final != path:
            redirects[path] = final
            continue
        if path in NOT_PAGES:
            continue
        good.append(r)
        for link in set(r["data"].get("all_links", [])):
            if (sp := site_path(link)) and sp != path:
                inbound[sp] += 1
    for src, dst in list(redirects.items()):
        inbound[dst] += inbound.get(src, 0)
    pages = [
        page_record(r, inbound, sitemap)
        for r in good
        if not (site_path(r["url"]) or "").startswith(BLOG_PREFIXES)
    ]
    blog = [blog_record(r) for r in good if (site_path(r["url"]) or "").startswith(BLOG_PREFIXES)]
    pages.sort(key=lambda p: p["path"])
    blog.sort(key=lambda p: (p["date"], p["path"]), reverse=True)
    _dump_lines(L3 / "pages.json", pages)
    _dump_lines(L3 / "blog.json", blog)
    site = {
        "crawled": meta.get("crawled", time.strftime("%Y-%m-%d")),
        "site": SITE,
        "counts": {"pages": len(pages), "blog": len(blog), "sitemap": len(sitemap)},
        "redirects": dict(sorted(redirects.items())),
        "missing": sorted(missing),
        "not_pages": list(NOT_PAGES),
        "unlisted": [p["path"] for p in pages if p.get("unlisted")],
        "nav": (meta.get("probes") or {}).get("nav", {}),
        "probes": {k: v for k, v in (meta.get("probes") or {}).items() if k != "nav"},
        "hosts": meta.get("hosts", {}),
        "notes": [
            "Scroll container is the window; the fixed header covers the top: scroll to element top - 104 px.",
            "Webflow tabs (.w-tab-link), dropdowns (.w-dropdown-toggle: FAQs and branch hours) and sliders (.w-slider-dot) open with a programmatic click.",
            "The newer exam pages' FAQs are a custom accordion (.faq-clini .faq-item > button.faq-question + .faq-answer; the open item has .active): click the button.",
            "#clinitoEmbed (chat iframe) sits bottom-right at z-index 99999; on mobile .div-block-475 is a fixed bottom bar.",
        ],
    }
    (L3 / "site.json").write_text(
        json.dumps(site, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {len(pages)} pages, {len(blog)} posts; {len(redirects)} redirects, {len(missing)} missing"
    )


# --------------------------------------------------------------------------- branches


def _hours(lines: list[str], text: str) -> str:
    """The hours as lines joined by '; ' (the dropdown's own line breaks)."""
    if len(lines) > 1:
        # A bold label ("Sábado:") is its own text node: it joins what follows.
        out = ""
        for line in lines:
            out += line if not out else (" " if out.endswith(":") else "; ") + line
        return collapse(out)
    # One run-on line ("…21:00hrs Sábado: …hrsDomingos: …"): split before each day.
    t = re.sub(r"(?<=hrs)\.?\s*(?=[A-ZÁÉÍÓÚ])", "; ", text or (lines[0] if lines else ""))
    t = re.sub(
        r"(?<=[a-z\.])(?=(Toma de mu|Ex[aá]menes de larga|Centro de Salud|Todo tipo))", "; ", t
    )
    return collapse(t)


async def branches_async() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await new_context(browser)
        page = await ctx.new_page()
        await page.goto(SITE + "/ubicaciones", wait_until="load", timeout=60_000)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=10_000)
        await page.evaluate(SCROLL_JS)
        raw = await page.evaluate(BRANCHES_JS)
        await browser.close()
    out = [
        {
            "name": collapse(b["name"]),
            "address": collapse(b["address"]),
            "comuna": b["comuna"],
            "region": b["region"],
            "services": b["services"],
            "hours": _hours(b["hours"], b["hours_text"]),
            "book_link": [h for h in b["book_link"] if h and h != "#"],
        }
        for b in raw
        if b["name"]
    ]
    (L3 / "branches.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(out)} branches")


# --------------------------------------------------------------------------- agenda


def agenda_links() -> dict[int, list[str]]:
    """Site pages (from the crawl cache) that link each agenda-web service."""
    out: dict[int, set[str]] = {}
    for r in cached_site():
        if r.get("status") != 200 or not r.get("data"):
            continue
        path = site_path(r["url"]) or "/"
        if path.startswith(BLOG_PREFIXES):
            continue
        for link in r["data"].get("all_links", []):
            u = urllib.parse.urlsplit(link)
            q = dict(urllib.parse.parse_qsl(u.query))
            code: int | None = None
            if u.netloc == "agenda-web.clini.cl" and q.get("servicio", "").isdigit():
                code = int(q["servicio"])
            elif u.netloc == "agenda.clini.cl" and "Anular" not in u.path:
                code = 62
            elif u.netloc == "agenda-imagenes.clini.cl":
                code = next((c for k, c in LEGACY_AGENDA.items() if k in q), None)
            if code is not None:
                out.setdefault(code, set()).add(path)
    return {k: sorted(v) for k, v in out.items()}


async def agenda_async() -> None:
    from playwright.async_api import async_playwright

    links = agenda_links()
    out: dict[str, Any] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await new_context(browser)
        for code in AGENDA_CODES:
            page = await ctx.new_page()
            try:
                await page.goto(f"{AGENDA}/?servicio={code}", wait_until="load", timeout=60_000)
                html = await page.content()
                m = re.search(r'const\s+serviceName\s*=\s*\n?\s*("(?:[^"\\]|\\.)*")', html)
                info = await page.evaluate(AGENDA_JS)
            finally:
                await page.close()
            name = json.loads(m.group(1)) if m else info.get("service_label") or ""
            pres = [
                {"code": int(o["v"]), "name": o["t"]}
                for o in info.get("prestacion") or []
                if o["v"].isdigit()
            ]
            regions = [
                {"code": int(o["v"]), "name": o["t"], "default": o["sel"]}
                for o in info.get("region") or []
                if o["v"].isdigit()
            ]
            out[str(code)] = {
                "name": name,
                "url": f"{AGENDA}/?servicio={code}",
                "prestaciones": pres,
                "regions": regions,
                "sectors": [o["v"] for o in info.get("sectors") or []],
                "linked_from": links.get(code, []),
            }
            print(
                code,
                name,
                len(pres),
                [r["code"] for r in regions],
                len(links.get(code, [])),
                flush=True,
            )
        await browser.close()
    (L3 / "agenda_services.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(out)} agenda services")


# --------------------------------------------------------------------------- prices

PRICE_KEYS = (
    "id",
    "nombre",
    "codigo",
    "categoria",
    "servicio",
    "precioFonasa",
    "precioParticular",
    "requiereContraste",
    "preparacion",
)


def _buscar(term: str) -> list[dict[str, Any]]:
    url = f"{COTIZADOR}/Cotizar?handler=Buscar&q={urllib.parse.quote(term)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def prices(terms: list[str] | None) -> None:
    path = L3 / "prices.json"
    cat: dict[int, dict[str, Any]] = {}
    if path.exists():
        cat = {x["id"]: x for x in json.loads(path.read_text(encoding="utf-8"))}
    if not terms:
        words: Counter[str] = Counter()
        for r in cached_site():
            for s in (r.get("data") or {}).get("sections", []):
                blob = s.get("text", "") + " " + " ".join(s.get("hidden_text", []))
                words.update(fold(w) for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{4,}", blob))
        terms = [w for w, _ in words.most_common(2500)]
        terms += [a + b + c for a in "abcdefghilmnoprstuv" for b in "aeiou" for c in "lnrstcmd"]
    before = len(cat)
    with ThreadPoolExecutor(6) as ex:
        for res in ex.map(_buscar, terms):
            for it in res:
                if isinstance(it, dict) and "id" in it:
                    cat[it["id"]] = {k: it.get(k) for k in PRICE_KEYS}
    items = sorted(cat.values(), key=lambda x: (x.get("servicio") or "", x.get("nombre") or ""))
    _dump_lines(path, items)
    print(f"{len(terms)} terms: {before} → {len(items)} items")


# --------------------------------------------------------------------------- L2 maps

#: Page families that share one template: listed by path, sections once.
FAMILIES = {
    "lab-branch": "Laboratorio por sede (/laboratorio/<sede>)",
    "agreement": "Convenios (/convenios-salud/<convenio>)",
    "mri-body-part": "Resonancia por zona (/imagenes/resonancias-magneticas/<zona>)",
    "exam-info": "Exámenes de laboratorio explicados (/examenes/<examen>)",
    "oncology-cancer": "Centro Oncológico por cáncer (/centro-oncologico/<cáncer>)",
}
BLOG_GROUPS = (
    (
        "Cirugía LASIK y visión",
        r"lasik|lentes|vision|vista|ojos?\b|miopia|astigmat|presbic|oftalm|prk|glaucoma|catarata",
    ),
    (
        "Mujer, embarazo y mamas",
        r"mujer|mama|mamograf|embaraz|ginec|menstrua|ovario|utero|vph|papanicolau|lactancia|obstetr|prenatal|endometr|menopaus|fertil",
    ),
    (
        "Imagenología",
        r"resonancia|ecograf|tac\b|scanner|tomograf|radiograf|pet\b|pet-ct|rayos x|imagenolog",
    ),
    ("Cardiología", r"cardi|holter|electrocardio|corazon|presion arterial|hipertension|arritmia"),
    (
        "Laboratorio y exámenes",
        r"examen|laboratorio|sangre|hemograma|glucosa|colesterol|tiroid|orina|psa\b|vitamina|creatinina|insulina|hormona|perfil|alergia|anemia|diabetes|its\b|ets\b|vih",
    ),
    ("Fonasa, Isapre y costos", r"fonasa|isapre|bono|precio|costo|ahorr|convenio"),
)


def _short(title: str) -> str:
    for suf in (" | CLINI", " | Clini", " - CLINI", " \u2013 CLINI", " | CLINI Salud"):
        title = title.removesuffix(suf)
    return title.strip()


def maps() -> None:
    pages = json.loads((L3 / "pages.json").read_text(encoding="utf-8"))
    blog = json.loads((L3 / "blog.json").read_text(encoding="utf-8"))
    site = json.loads((L3 / "site.json").read_text(encoding="utf-8"))
    crawled = site.get("crawled", "")

    def label(t: str) -> str:
        # A menu card's title and blurb run together in textContent: keep the title.
        return re.split(r"(?<=[a-záéíóú.])(?=[A-ZÁÉÍÓÚ][a-záéíóú])", t, maxsplit=1)[0][:80]

    out = [
        "# Site map: every page of www.clini.cl, its sections and how to reach them",
        "",
        f"Sources: L3/pages.json and L3/site.json (built by knowledge/build.py from a headless-browser crawl of www.clini.cl, {crawled}).",
        "",
        "Headings are written exactly as the page renders them (first line of the heading's text, whitespace collapsed) and are the scroll targets for `{show: …}`. "
        '"tabs: A, B" means the section hides panes behind Webflow tabs (click the tab first); "FAQ xn" counts the dropdown questions on the page (`{faq: …}`); '
        '"(unlisted)" marks a page no menu or other page links to (SEO and campaign landings; reachable by path). The fixed header is 96 px tall (91 on mobile): scroll to the heading\'s top minus ~104 px.',
        "",
        "## Navigation",
    ]
    nav = site.get("nav", {})
    for m in nav.get("menus", []):
        links = ", ".join(
            f"{label(link['text'])} ({site_path(link['href']) or link['href']})"
            for link in m["links"]
            if link["text"]
        )
        out.append(f"- Header menu **{m['menu']}**: {links}")
    hdr = [
        link
        for link in nav.get("header", [])
        if link["text"] and not any(link in m["links"] for m in nav.get("menus", []))
    ]
    if hdr:
        out.append(
            "- Header links: "
            + ", ".join(
                f"{label(link['text'])} ({site_path(link['href']) or link['href']})" for link in hdr
            )
        )
    ftr = [link for link in nav.get("footer", []) if link["text"]]
    if ftr:
        out.append(
            "- Footer: "
            + ", ".join(
                f"{link['text']} ({site_path(link['href']) or link['href']})" for link in ftr
            )
        )
    if site.get("redirects"):
        out.append(
            "- Aliases that redirect: "
            + ", ".join(f"{a} → {b}" for a, b in site["redirects"].items())
        )
    if site.get("missing"):
        out.append("- Dead links (404): " + ", ".join(site["missing"]))
    out.append(
        '- /mantencion is a maintenance page ("Servicio en Mantenimiento"), not content; /chequeos-medicos lands there.'
    )
    out.append("")

    def page_lines(p: dict[str, Any], full: bool = True) -> list[str]:
        flag = " (unlisted)" if p.get("unlisted") else ""
        lines = [f"### {p['path']} — {_short(p['title'])}{flag}"]
        if full and p.get("description"):
            lines.append(f"_{p['description'][:220]}_")
        heads = []
        for sec in p["sections"]:
            if sec["heading"].startswith("["):
                continue
            extra = [r for r in sec.get("reveal", []) if r.startswith("tabs:")]
            heads.append(sec["heading"] + (f" ({extra[0]})" if extra else ""))
        if heads:
            lines.append("Sections: " + " · ".join(heads))
        bits = []
        if p.get("faqs"):
            bits.append(f"FAQ x{len(p['faqs'])}")
        for f in p.get("forms", []):
            bits.append(f"form #{f.get('id') or f.get('name')}")
        deep = sorted(
            {
                c["href"]
                for c in p.get("ctas", [])
                if "agenda-web.clini.cl" in c["href"] or "reservo.cl" in c["href"]
            }
        )
        if deep:
            bits.append("booking links: " + ", ".join(d.replace("https://", "") for d in deep[:8]))
        if bits:
            lines.append("; ".join(bits))
        return lines

    by_type: dict[str, list[dict[str, Any]]] = {}
    for p in pages:
        by_type.setdefault(p["type"], []).append(p)
    order = ["core", "lasik", "imaging", "cardiology", "campaign", "request-form", "women"]
    names = {
        "core": "Main pages",
        "lasik": "Cirugía LASIK",
        "imaging": "Imagenología",
        "cardiology": "Cardiología",
        "campaign": "Campañas",
        "request-form": "Solicitudes",
        "women": "Círculo Mujer",
    }
    for t in order:
        if t not in by_type:
            continue
        out.append(f"## {names[t]}")
        for p in by_type[t]:
            out += page_lines(p)
        out.append("")
    for t, family in FAMILIES.items():
        fam = by_type.get(t, [])
        if not fam:
            continue
        out.append(f"## {family} — {len(fam)} pages, one template")
        out += page_lines(fam[0], full=False)[1:]
        for p in fam:
            out.append(
                f"- {p['path']} — {_short(p['title'])}"
                + (" (unlisted)" if p.get("unlisted") else "")
            )
        out.append("")
    (HERE / "L2" / "site-map.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

    groups: dict[str, list[dict[str, Any]]] = {g: [] for g, _ in BLOG_GROUPS}
    groups["Blog Mujer (/blog-mujer)"] = []
    groups["Otros: prevención y bienestar"] = []
    for b in blog:
        if b["type"] == "blog-mujer":
            groups["Blog Mujer (/blog-mujer)"].append(b)
            continue
        hay = fold(f"{b['title']} {b.get('description', '')}")
        g = next(
            (g for g, rx in BLOG_GROUPS if re.search(rf"\b(?:{rx})", hay)),
            "Otros: prevención y bienestar",
        )
        groups[g].append(b)
    dates = sorted(b["date"] for b in blog if b["date"])
    out = [
        "# Blog index: every post on www.clini.cl/blog, by theme",
        "",
        f'Sources: L3/blog.json (each post\'s page: title, meta description, JSON-LD date), crawled {crawled}; https://www.clini.cl/blog (section "Blog", search box `#Blog-buscador` and category checkboxes).',
        "",
        f"{len(blog)} posts ({sum(b['type'] == 'blog' for b in blog)} under /blog, "
        f"{sum(b['type'] == 'blog-mujer' for b in blog)} under /blog-mujer)"
        + (f", {dates[0]} to {dates[-1]}" if dates else "")
        + ". All in Spanish, on the same site (open with `{page: /blog/<slug>}`). "
        'The one line under each title is the post\'s own meta description. Most posts end with an embedded LASIK lead form and "Explora más articulos"; '
        "they are information, not medical advice: for a booking, take the visitor to the service page or agenda.",
        "",
    ]
    for g, items in groups.items():
        if not items:
            continue
        out.append(f"## {g} ({len(items)})")
        for b in items:
            line = (
                f"- **{b['title']}**" + (f" ({b['date']})" if b["date"] else "") + f" — {b['path']}"
            )
            out.append(line)
            if b.get("description"):
                out.append(f"  {b['description'][:200]}")
        out.append("")
    (HERE / "L2" / "blog-index.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"wrote L2/site-map.md ({len(pages)} pages) and L2/blog-index.md ({len(blog)} posts)")


# --------------------------------------------------------------------------- search


def search(query: str, limit: int = 8) -> None:
    sys.path.insert(0, str(HERE.parent))
    import knowledge

    for h in knowledge.load().search(query, limit):
        print(
            f"{h.score:6.2f}  {h.kind:6} {h.path}  {h.section or ''}\n        {h.title}\n        {h.snippet[:200]}\n"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Clini's L3 knowledge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser(
        "crawl", help="render (or read from cache) www.clini.cl and write L3 pages/blog/site"
    )
    c.add_argument("--offline", action="store_true", help="cache only, no network")
    c.add_argument("--refresh", action="store_true", help="re-render everything")
    c.add_argument(
        "--only", nargs="+", default=[], help="re-render just these paths (no link following)"
    )
    sub.add_parser("branches", help="read /ubicaciones into L3/branches.json")
    sub.add_parser("agenda", help="read agenda-web services into L3/agenda_services.json")
    sub.add_parser("maps", help="write L2/site-map.md and L2/blog-index.md from L3")
    pr = sub.add_parser("prices", help="harvest the cotizador into L3/prices.json")
    pr.add_argument(
        "--terms", default="", help="comma-separated search terms (default: the full harvest)"
    )
    s = sub.add_parser("search", help="search the built knowledge (no network)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()
    if args.cmd == "crawl":
        asyncio.run(crawl_async(args.offline, args.refresh, args.only))
    elif args.cmd == "branches":
        asyncio.run(branches_async())
    elif args.cmd == "agenda":
        asyncio.run(agenda_async())
    elif args.cmd == "maps":
        maps()
    elif args.cmd == "prices":
        prices([t.strip() for t in args.terms.split(",") if t.strip()] or None)
    else:
        search(args.query, args.limit)


if __name__ == "__main__":
    main()
