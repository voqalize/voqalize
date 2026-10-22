"""Crawl explora.com lodges, expeditions/programs and their explorations into L3/lodges.json.

Drives a real Chrome (Playwright, channel="chrome") so that tab navigation, collapses,
carousels and in-page tab panels are observed the way a user (or the voice agent's
extension) sees them.

Run:
    uv run --with playwright python build_lodges.py            # full crawl incl. exploration detail pages
    uv run --with playwright python build_lodges.py --no-details  # skip per-exploration detail pages

Site model (observed 2026-10):
  * Every lodge / expedition has a sticky secondary menu
    `.explora-submenu .secondary-menu ul.list-inline a.nav-link`; every item is a separate
    WordPress URL (full page load), never a JS tab or #hash.
  * Page body = `#content > div.component-<id>` blocks (t1 hero, t2 intro, t4 text, t6/t7
    image+text with READ MORE collapse, t13 FAQ accordion, t14 exploration zones,
    t15 lightbox gallery, t17 room cards, o2 text/video, o4 bootstrap carousel,
    o6 JS tab panels, ...). Mobile duplicates live in `.d-md-none` / `.d-lg-none` twins.
  * Booking CTAs all point at https://reservations.explora.com/ibe/paso1?language=EN with no
    hotel; the page's `wpbooking.lodge_code` and the reservation form's `hotel_code` select
    give the code. `paso1?language=EN&hotel_code=<CODE>` preselects the destination.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import (  # pyright: ignore[reportMissingImports]  # uv run --with playwright
    Page,
    sync_playwright,
)

BASE = "https://www.explora.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "L3" / "lodges.json"
DELAY = 1.0
RESV = "https://reservations.explora.com/ibe/paso1?language=EN"

# Codes from the <select name="hotel_code" id="destination"> on reservations.explora.com/ibe/paso1.
HOTEL_CODES = {
    "ECFT": "El Calafate, Patagonia Argentina",
    "ERTP": "Torres del Paine - Conservation Reserve, Chile",
    "EATA": "Atacama, Chile",
    "ERAP": "Easter Island, Chile",
    "EPAT": "Torres del Paine, Patagonia Chile",
    "EPNP": "Parque Nacional Patagonia, Chile",
    "EVAL": "Machu Picchu & Sacred Valley, Peru",
    "ECHA": "El Chaltén, Patagonia Argentina",
    "PATA": "Atacama & Uyuni (Chile to Bolivia)",
    "PUYU": "Uyuni & Atacama (Bolivia to Chile)",
    "XICE": "Iceland Expedition",
    "XICW": "Iceland Winter Expedition",
    "XSCM": "Sacred Mountains Expedition",
    "XTFG": "Tierra del Fuego Expedition",
}

# (overview url, kind, fallback hotel codes, exploration archive slug)
SEEDS = [
    ("/lodge/atacama-lodge/", "lodge", ["EATA"], "atacama"),
    ("/lodge/atacama-uyuni-crossing/", "lodge", ["PATA", "PUYU"], "atacama-uyuni"),
    ("/lodge/el-calafate/", "lodge", ["ECFT"], "explorations-el-calafate"),
    ("/el-chalten-lodge/", "lodge", ["ECHA"], "el-chalten"),
    ("/lodge/easter-island-hotels/", "lodge", ["ERAP"], "easter-island"),
    ("/lodge/patagonia-national-park/", "lodge", ["EPNP"], "patagonia-national-park"),
    ("/lodge/torres-del-paine-lodge/", "lodge", ["EPAT"], "torres-del-paine"),
    (
        "/lodge/torres-del-paine-conservation-reserve/",
        "lodge",
        ["ERTP"],
        "reserva-torres-del-paine",
    ),
    (
        "/lodge/travel-machupicchu-and-the-sacred-valley-of-the-incas-peru-explora/",
        "lodge",
        ["EVAL"],
        "machu-picchu-sacred-valley",
    ),
    ("/explora-expeditions/", "expedition", [], None),
    ("/iceland-expedition-overview/", "expedition", ["XICE"], None),
    ("/explora-expeditions/iceland-winter-expedition/", "expedition", ["XICW"], None),
    ("/sacred-mountain-expedition/", "expedition", ["XSCM"], None),
    ("/travel-tierra-del-fuego/", "expedition", ["XTFG"], None),
    ("/program/photography-program-with-katsuyoshi-tanaka/", "expedition", [], None),
    ("/program/explora-connects-patagonia/", "expedition", [], None),
    ("/corporate-travel-program/", "expedition", [], None),
]

PREP_CSS = """
#content .collapse, #content .collapse.half { display:block !important; height:auto !important; max-height:none !important; }
#content .tab-panels .panel { display:block !important; }
#content .carousel-item { display:block !important; }
#content .tab-content > .tab-pane { display:block !important; opacity:1 !important; }
"""

TAB_SEL = ".explora-submenu .secondary-menu ul.list-inline a.nav-link"

JS_PAGE = r"""
() => {
  const clean = s => (s || '').replace(/<[^>]*>/g, '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const content = document.querySelector('#content');
  const out = {title: document.title, sections: [], blank: [], rooms: [], faqs: [], explorationLinks: [], archiveLinks: []};
  const sub = document.querySelector('.explora-submenu .secondary-menu');
  out.submenuLabel = sub ? clean((sub.querySelector('.row') || sub).innerText.split('\n')[0]) : null;
  const hero = document.querySelector('.component-t1');
  out.hero = hero ? clean(hero.innerText) : '';
  const kids = content ? [...content.children] : [];
  kids.forEach((blk, i) => {
    const cls = (blk.className || '').toString();
    const comp = (cls.match(/component-[\w-]+/) || [null])[0];
    if (!comp || comp === 'component-t1') return;
    if (!blk.innerText.trim() && !blk.querySelector('iframe,a[data-lightbox]')) return;
    const hs = [...blk.querySelectorAll('h1,h2,h3,h4,.h1,.h2,.h3,.card-header,strong.text-uppercase')].filter(vis).map(h => clean(h.innerText)).filter(Boolean);
    const sec = {heading: hs[0] || '', component: comp, selector: `#content > div:nth-child(${i + 1})`, text: clean(blk.innerText).slice(0, 2000), items: [], widgets: []};
    // widgets
    const W = sec.widgets;
    const rm = blk.querySelectorAll('.collapse-control[data-toggle=collapse]');
    if (rm.length) W.push({type: 'read_more', count: rm.length, selector: '.collapse-control[data-toggle=collapse]', activate: "click the span (Bootstrap collapse; adds .show to its data-target); desktop copy usually already shows full text"});
    const acc = blk.querySelectorAll('.explora-accordion button[data-toggle=collapse]');
    if (acc.length) W.push({type: 'accordion', count: acc.length, selector: '.explora-accordion button[data-toggle=collapse]', activate: "click button; target .collapse gets .show; data-parent closes siblings"});
    const owl = blk.querySelectorAll('.owl-carousel');
    if (owl.length) W.push({type: 'owl_carousel', count: owl.length, selector: '.owl-carousel', activate: "click .owl-next / .owl-prev or jQuery(el).trigger('next.owl.carousel'); ignore .owl-item.cloned"});
    const bc = blk.querySelectorAll('.carousel[id^=carousel-desktop], .carousel.slide');
    if (bc.length) W.push({type: 'bootstrap_carousel', count: bc.length, selector: '.carousel.slide', activate: "jQuery(sel).carousel('next') or click li[data-slide-to=N] in .carousel-indicators"});
    const tabs = blk.querySelectorAll('.tab-panels-nav li.nav-item[data-index]');
    if (tabs.length) W.push({type: 'inpage_tabs', count: tabs.length, selector: '.tab-panels-nav li.nav-item[data-index]', labels: [...tabs].filter(t=>vis(t)||true).map(t => clean(t.innerText)).filter((v,j,a)=>a.indexOf(v)===j), activate: "click li.nav-item[data-index=N]; pane .tab-panels-content .panel[data-index=N] gets .active"});
    const pills = blk.querySelectorAll('a.nav-link[data-toggle=pill], a.nav-link[data-toggle=tab]');
    if (pills.length) W.push({type: 'inpage_pills', count: pills.length, selector: 'a.nav-link[data-toggle=pill]', labels: [...pills].map(a => clean(a.textContent)).filter((v,j,a)=>a.indexOf(v)===j), activate: "click a.nav-link[data-toggle=pill] (Bootstrap tab; href=#v-pills-N is preventDefault'ed so the URL does not change); pane .tab-pane#v-pills-N gets .show.active"});
    const lb = blk.querySelectorAll('a[data-lightbox]');
    if (lb.length) W.push({type: 'lightbox_gallery', count: lb.length, selector: 'a[data-lightbox]', activate: "click a visible a[data-lightbox] (lightbox2); #lightbox .lb-next / .lb-prev, .lb-close"});
    const ifr = [...blk.querySelectorAll('iframe')].map(f => f.getAttribute('data-src') || f.src).filter(s => s && !s.startsWith('data:'));
    if (ifr.length) W.push({type: 'video', src: [...new Set(ifr)], activate: "lazy iframe: real URL in data-src (lazysizes swaps it when scrolled into view)"});
    if (blk.querySelector('.mapboxgl-map, [class*=mapbox]')) W.push({type: 'map', selector: '.mapboxgl-map'});
    const book = [...blk.querySelectorAll('a[href*="reservations.explora.com"]')].map(a => a.getAttribute('href'));
    if (book.length) W.push({type: 'booking_cta', hrefs: [...new Set(book)]});
    // items
    if (comp === 'component-t17') {
      blk.querySelectorAll('.card').forEach(card => {
        const name = clean((card.querySelector('.card-header') || {}).innerText);
        if (!name) return;
        const facts = [...card.querySelectorAll('.flex-grow-1 > .card-body p span')].map(s => clean(s.textContent));
        const amen = [...card.querySelectorAll('li')].map(l => clean(l.textContent));
        out.rooms.push({name, text: facts.join('; '), facts, amenities: amen});
        sec.items.push({name, facts, amenities: amen});
      });
      const counts = [...blk.querySelectorAll('.media-body span')].map(s => clean(s.textContent));
      if (counts.length) sec.room_counts = counts;
    }
    if (comp === 'component-t13') {
      const desks = blk.querySelectorAll('.d-none.d-md-block');
      let group = '';
      (desks.length ? [...desks] : [blk]).flatMap(dk => [...dk.querySelectorAll('h4, li.list-group-item')]).forEach(el => {
        if (el.tagName === 'H4') { group = clean(el.textContent); return; }
        const q = clean((el.querySelector('button') || {}).textContent);
        const a = clean((el.querySelector('.collapse') || {}).textContent);
        if (q) { out.faqs.push({q, a: a.slice(0, 3000), group}); sec.items.push({q, group}); }
      });
    }
    if (comp === 'component-t14') {
      blk.querySelectorAll('.col-md-8.d-none.d-md-block, .d-none.d-md-block > h4').forEach(z => {
        const h = z.querySelector('h4'); if (h) sec.items.push({zone: clean(h.textContent), text: clean((z.querySelector('.explora-wysiwyg') || {}).textContent).slice(0, 1200)});
      });
      blk.querySelectorAll('a[href*="/explorations-lodge/"]').forEach(a => out.archiveLinks.push(a.href));
    }
    if (tabs.length) {
      const panels = blk.querySelectorAll('.tab-panels-content .panel[data-index]');
      const seen = new Set();
      tabs.forEach(t => { const ix = t.getAttribute('data-index'); const lab = clean(t.textContent); if (seen.has(lab)) return; seen.add(lab);
        const p = [...panels].find(p => p.getAttribute('data-index') === ix); sec.items.push({tab: lab, text: clean(p ? p.textContent : '').slice(0, 1500)}); });
    }
    if (pills.length) {
      const seenP = new Set();
      pills.forEach(a => { const lab = clean(a.textContent); const id = a.getAttribute('href'); if (seenP.has(id)) return; seenP.add(id);
        const pane = id && id.startsWith('#') ? blk.querySelector(id) : null; sec.items.push({tab: lab, pane: id, text: clean(pane ? pane.textContent : '').slice(0, 3000)}); });
    }
    if (bc.length && !tabs.length) {
      const its = [...blk.querySelectorAll('.carousel-desktop .carousel-item, .d-none.d-md-block .carousel-item')].map(c => clean(c.textContent)).filter(Boolean);
      its.forEach(t => sec.items.push({slide: t.slice(0, 600)}));
    }
    if (owl.length) {
      const its = [...blk.querySelectorAll('.owl-item:not(.cloned)')].map(c => clean(c.textContent)).filter(Boolean);
      [...new Set(its)].forEach(t => sec.items.push({card: t.slice(0, 600)}));
    }
    if (comp === 'component-multi_columns' || comp === 'component-t9' || comp === 'component-two_columns') {
      [...blk.querySelectorAll('h3,h4,.h3,.h4')].filter(vis).forEach(h => {
        const box = h.closest('[class*=col]') || h.parentElement; sec.items.push({heading: clean(h.textContent), text: clean(box.innerText).slice(0, 800)});
      });
    }
    out.sections.push(sec);
  });
  if (!out.sections.length) {
    const m = document.querySelector('#primary #main, #main, #primary');
    if (m) {
      const hs = [...m.querySelectorAll('h1,h2,h3,.h1,.h2')].filter(vis).map(h => clean(h.innerText)).filter(Boolean);
      out.sections.push({heading: hs[0] || '', component: 'legacy-main', selector: '#primary #main', text: clean(m.innerText).slice(0, 2000), items: hs.slice(1, 30).map(h => ({heading: h})), widgets: []});
    }
  }
  out.blank = [...new Set([...document.querySelectorAll('a[target=_blank]')].map(a => a.href))];
  out.booking = [...new Set([...document.querySelectorAll('a[href*="reservations.explora.com"]')].map(a => a.getAttribute('href')))];
  out.bookingCtas = [...document.querySelectorAll('a[href*="reservations.explora.com"]')].map(a => ({text: clean(a.innerText), href: a.getAttribute('href'), target: a.target || '', visible: vis(a)})).filter(x => x.text);
  out.explorationLinks = [...new Set([...document.querySelectorAll('#content a[href*="/exploration/"], #content a[href*="/explorations/"]')].map(a => a.href))];
  out.archiveLinks = [...new Set(out.archiveLinks.concat([...document.querySelectorAll('#content a[href*="/explorations-lodge/"]')].map(a => a.href)))];
  out.inpageAnchors = [...new Set([...document.querySelectorAll('#content a[href^="#"]')].map(a => a.getAttribute('href')).filter(h => h.length > 1))];
  return out;
}
"""

JS_ARCHIVE = r"""
() => {
  const clean = s => (s || '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
  const cards = [...document.querySelectorAll('.t-taxonomy-exploration .card')].map(c => {
    const dts = [...c.querySelectorAll('dl.exploration-terms dt')].map(d => clean(d.textContent));
    const a = c.querySelector('a[href]');
    return {name: clean((c.querySelector('.card-header strong') || {}).textContent), area: clean((c.querySelectorAll('.card-header')[1] || {}).textContent),
            activity: dts[0] || '', difficulty: dts[1] || '', duration: dts[2] || '', text: clean((c.querySelector('.exploration-content p') || {}).textContent),
            url: a ? a.href : null, id: c.id};
  });
  const next = document.querySelector('a.next.page-numbers');
  const filters = {};
  document.querySelectorAll('.explorations-filters-filter input.checkbox-term').forEach(i => {
    const g = (i.closest('.explorations-filters-filter').className.match(/exploration-(\w+)-filter/) || [])[1] || 'other';
    (filters[g] = filters[g] || []).push({term: i.dataset.term, name: i.dataset.name});
  });
  return {cards, next: next ? next.href : null, filters, total: clean((document.querySelector('.alert') || {}).textContent)};
}
"""

JS_DETAIL = r"""
() => {
  const clean = s => (s || '').replace(/<[^>]*>/g, '').replace(/\u00a0/g,' ').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  const c = document.querySelector('.explora-content') || document.querySelector('#content');
  const txt = clean(c ? c.innerText : '');
  return {title: document.title, text: txt, h: [...document.querySelectorAll('.explora-content h1,.explora-content h2,.explora-content h3')].map(h => clean(h.innerText)).filter(Boolean).slice(0, 6),
          map: !!document.querySelector('.mapboxgl-map'), lodge: clean((document.querySelector('.explora-static-title h2') || {}).innerText)};
}
"""


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def goto(page: Page, url: str) -> int:
    time.sleep(DELAY)
    r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=15000)
    return r.status if r else 0


def scroll_through(page: Page):
    """Scroll the page like a reader so lazysizes swaps images/iframes in."""
    h = page.evaluate("document.body.scrollHeight")
    y = 0
    while y < h:
        y += 900
        page.evaluate(f"window.scrollTo(0,{y})")
        time.sleep(0.12)
        h = page.evaluate("document.body.scrollHeight")
    page.evaluate("window.scrollTo(0,0)")


def prep(page: Page):
    page.evaluate("document.querySelectorAll('.owl-item.cloned').forEach(e=>e.remove())")
    page.add_style_tag(content=PREP_CSS)


def lodge_code_from_html(html: str) -> str | None:
    m = re.search(r'var wpbooking = \{[^}]*"lodge_code":"([A-Z]{4})"', html)
    return m.group(1) if m else None


def probe_widgets(page: Page) -> dict:
    """Actually click one instance of each widget type and record whether it reacted."""
    res = {}
    try:
        loc = page.locator("#content .collapse-control[data-toggle=collapse]:visible").first
        if loc.count():
            tgt = loc.get_attribute("data-target")
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.6)
            res["read_more"] = {
                "selector": "#content .collapse-control[data-toggle=collapse]",
                "target": tgt,
                "expanded_after_click": page.evaluate(
                    "(t)=>document.querySelector(t)?.classList.contains('show')", tgt
                ),
            }
    except Exception as e:
        res["read_more"] = {"error": str(e)[:120]}
    try:
        loc = page.locator("#content .explora-accordion button[data-toggle=collapse]:visible").first
        if loc.count():
            tgt = loc.get_attribute("data-target")
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.6)
            res["accordion"] = {
                "selector": "#content .explora-accordion button[data-toggle=collapse]",
                "expanded_after_click": page.evaluate(
                    "(t)=>document.querySelector(t)?.classList.contains('show')", tgt
                ),
            }
    except Exception as e:
        res["accordion"] = {"error": str(e)[:120]}
    try:
        loc = page.locator("#content .tab-panels-nav li.nav-item[data-index='1']:visible").first
        if loc.count():
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.6)
            res["inpage_tabs"] = {
                "selector": "#content .tab-panels-nav li.nav-item[data-index]",
                "pane_active_after_click": page.evaluate(
                    "()=>!!document.querySelector('#content .tab-panels-content .panel.active[data-index=\"1\"]')"
                ),
                "url_changed": False,
            }
    except Exception as e:
        res["inpage_tabs"] = {"error": str(e)[:120]}
    try:
        loc = page.locator("#content a.nav-link[data-toggle=pill]:visible").nth(1)
        if loc.count():
            tgt = loc.get_attribute("href")
            before = page.url
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.6)
            res["inpage_pills"] = {
                "selector": "#content a.nav-link[data-toggle=pill]",
                "pane_active_after_click": page.evaluate(
                    "(t)=>document.querySelector(t)?.classList.contains('active')", tgt
                ),
                "url_changed": page.url != before,
            }
    except Exception as e:
        res["inpage_pills"] = {"error": str(e)[:120]}
    try:
        loc = page.locator("#content .owl-carousel .owl-next:visible").first
        if loc.count():
            before = page.evaluate(
                "()=>document.querySelector('#content .owl-carousel .owl-stage')?.style.transform"
            )
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.8)
            after = page.evaluate(
                "()=>document.querySelector('#content .owl-carousel .owl-stage')?.style.transform"
            )
            res["owl_carousel"] = {
                "selector": "#content .owl-carousel .owl-next",
                "moved": before != after,
            }
    except Exception as e:
        res["owl_carousel"] = {"error": str(e)[:120]}
    try:
        loc = page.locator("#content a[data-lightbox]:visible").first
        if loc.count():
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.8)
            opened = page.evaluate(
                "()=>getComputedStyle(document.querySelector('#lightbox')).display!=='none'"
            )
            res["lightbox"] = {
                "selector": "#content a[data-lightbox]",
                "opened": opened,
                "close": "#lightbox .lb-close",
            }
            page.keyboard.press("Escape")
            time.sleep(0.3)
            page.evaluate(
                "()=>{const c=document.querySelector('#lightbox .lb-close'); if(c&&getComputedStyle(document.querySelector('#lightbox')).display!=='none') c.click();}"
            )
    except Exception as e:
        res["lightbox"] = {"error": str(e)[:120]}
    return res


FACT_PATTERNS = {
    "altitude": r"[^.\n]{0,80}\b\d[\d.,]*\s?(?:m\.?a\.?s\.?l\.?|meters above sea level|masl|ft above sea level)[^.\n]{0,60}",
    "min_nights": r"[^.\n]{0,80}\b(?:minimum (?:stay )?of \w+ nights?|\w+ nights? minimum|\w+[- ]night minimum|two nights or longer|at least \w+ nights)[^.\n]{0,80}",
    "airport": r"[^.\n]{0,100}\bairport\b[^.\n]{0,120}",
    "transfer": r"[^.\n]{0,100}\b(?:\d+(?:[.,]\d+)?|one|two|three|four|five)[- ](?:and a half )?(?:hours?|hrs?|minutes?)\b[^.\n]{0,100}",
    "rooms_count": r"[^.\n]{0,40}\b\d+[- ](?:rooms?|suites?|guest rooms)\b[^.\n]{0,60}",
    "season": r"[^.\n]{0,80}\b(?:best time|high season|low season|open (?:from|year-round|all year)|year-round|closed (?:from|during))\b[^.\n]{0,120}",
    "all_inclusive": r"[^.\n]{0,80}\b(?:all[- ]inclusive|rates include|included in (?:our|the) rates?)\b[^.\n]{0,160}",
}


def extract_facts(text: str) -> dict:
    facts = {}
    for k, pat in FACT_PATTERNS.items():
        hits = []
        for m in re.finditer(pat, text, flags=re.I):
            s = re.sub(r"\s+", " ", m.group(0)).strip(" ,;:")
            if s and s not in hits:
                hits.append(s)
            if len(hits) >= 6:
                break
        if hits:
            facts[k] = hits
    return facts


def parse_itinerary(text: str) -> list[dict]:
    days = []
    for m in re.finditer(
        r"(?im)^\s*(day\s*\d+(?:\s*[-\u2013&]\s*\d+)?)\s*[:\-\u2013|]?\s*(.*)$", text
    ):
        days.append({"day": m.group(1).strip(), "title": m.group(2).strip()[:200]})
    return days


def crawl_archive(page: Page, url: str) -> tuple[list[dict], dict]:
    cards: list[dict] = []
    filters: dict = {}
    seen = set()
    nxt = url
    pages = 0
    while nxt and nxt not in seen and pages < 12:
        seen.add(nxt)
        goto(page, nxt)
        d = page.evaluate(JS_ARCHIVE)
        if not filters:
            filters = {"filters": d["filters"], "total": d["total"], "url": url}
        cards.extend(d["cards"])
        nxt = d["next"]
        pages += 1
    uniq, ids = [], set()
    for c in cards:
        if c["url"] in ids:
            continue
        ids.add(c["url"])
        uniq.append(c)
    filters["pages"] = pages
    return uniq, filters


def crawl_entry(
    page: Page, ctx, seed, details: bool, shots: Path | None
) -> tuple[dict, list[dict]]:
    path, kind, codes, arch_slug = seed
    url = urljoin(BASE, path)
    status = goto(page, url)
    log("ENTRY", url, status)
    html = page.content()
    code = lodge_code_from_html(html)
    tabs_meta = page.evaluate(
        f"""()=>[...document.querySelectorAll('{TAB_SEL}')].map((a,i)=>({{label:a.innerText.trim(), href:a.getAttribute('href'),
             current: a.closest('li').classList.contains('current-menu-item'), idx:i}}))"""
    )
    header_cta = page.evaluate(
        """()=>{const a=[...document.querySelectorAll('.booking-button a')].find(a=>a.offsetParent); return a?{text:a.innerText.trim(),href:a.getAttribute('href'),target:a.target}:null}"""
    )
    entry: dict = {
        "path": urlparse(url).path,
        "url": url,
        "name": "",
        "destination": "",
        "kind": kind,
        "tabs": [],
        "rooms": [],
        "explorations": [],
        "faqs": [],
        "booking": {},
        "facts": {},
        "text": "",
    }
    hero = page.evaluate(
        "()=>[...document.querySelectorAll('.component-t1 .explora-slider-title *')].map(e=>e.innerText.trim()).filter(Boolean)"
    )
    # hero is like ["OVERVIEW", "Atacama", "The Atacama Desert, Chile"] (tab label, name, destination)
    hero_lines = [h for h in hero if "\n" not in h]
    if len(hero_lines) >= 3:
        entry["name"], entry["destination"] = hero_lines[1], hero_lines[2]
    elif len(hero_lines) == 2:
        # e.g. ["INTRODUCING", "Explora Expeditions"]: an upper-case kicker, then the name
        if hero_lines[0].isupper():
            entry["name"] = hero_lines[1]
        else:
            entry["name"], entry["destination"] = hero_lines[0], hero_lines[1]
    entry["submenu_label"] = page.evaluate(
        "()=>{const s=document.querySelector('.explora-submenu .secondary-menu'); return s? s.innerText.trim().split('\\n')[0]:null}"
    )
    entry["page_title"] = page.title()

    tab_list = tabs_meta or [{"label": "OVERVIEW", "href": url, "current": True, "idx": 0}]
    all_text: list[str] = []
    all_booking: set[str] = set()
    all_blank: set[str] = set()
    archive_links: set[str] = set()
    widget_probe_done = set()
    exploration_links: set[str] = set()

    for i, t in enumerate(tab_list):
        href = str(t["href"] or url)
        label = str(t["label"])
        tab_url = urljoin(url, href)
        tab: dict = {
            "label": t["label"],
            "selector": f'{TAB_SEL}[href="{href}"]',
            "url": tab_url,
            "mechanism": None,
            "sections": [],
        }
        if i == 0 and (
            t["current"] or tab_url.rstrip("/") == url.rstrip("/") or "preview=true" in href
        ):
            # Overview: already loaded; it is its own URL.
            tab["mechanism"] = "url"
            if "preview=true" in href:
                tab["quirk"] = (
                    "submenu OVERVIEW href is a WordPress preview link (?post_type=lodge&p=...&preview=true); real URL used instead"
                )
                tab["url"] = url
        else:
            # verify mechanism by clicking the real tab link from the current page
            page.evaluate("window.__mark=1")
            before = page.url
            loc = page.locator(f'{TAB_SEL}[href="{href}"]:visible').first
            try:
                if not loc.count():
                    raise RuntimeError("tab link not present on current page")
                time.sleep(DELAY)
                loc.scroll_into_view_if_needed()
                loc.click()
                with contextlib.suppress(Exception):
                    page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(0.5)
                mark = page.evaluate("window.__mark")
                if mark is None:
                    tab["mechanism"] = "url"
                elif page.url != before and "#" in page.url:
                    tab["mechanism"] = "anchor"
                else:
                    tab["mechanism"] = "inpage"
                tab["url"] = page.url
            except Exception as e:
                log("  click failed, goto", tab_url, e)
                goto(page, tab_url)
                tab["mechanism"] = "url"
                tab["note"] = "click failed; loaded via goto"
        log("  TAB", t["label"], tab["mechanism"], page.url)
        scroll_through(page)
        if shots:
            slug = re.sub(r"[^a-z0-9]+", "-", entry["path"].strip("/").split("/")[-1].lower())[:40]
            page.screenshot(
                path=str(shots / f"{slug}__{i}_{t['label'].lower().replace(' ', '-')}.png")
            )
        # interaction probe once per entry on pages that have the widget
        wp = probe_widgets(page) if len(widget_probe_done) < 7 else {}
        for k, v in wp.items():
            widget_probe_done.add(k)
            tab.setdefault("widget_probe", {})[k] = v
        if wp and page.url.rstrip("/") != tab["url"].rstrip("/"):
            goto(page, tab["url"])  # undo any navigation caused by probing
        tab_html = page.content()
        code = code or lodge_code_from_html(tab_html)
        prep(page)
        d = page.evaluate(JS_PAGE)
        tab["page_title"] = d["title"]
        tab["sections"] = d["sections"]
        if d["inpageAnchors"]:
            tab["inpage_anchors"] = d["inpageAnchors"]
        entry["rooms"].extend(d["rooms"])
        entry["faqs"].extend(d["faqs"])
        all_booking.update(d["booking"])
        all_blank.update(d["blank"])
        archive_links.update(d["archiveLinks"])
        exploration_links.update(d["explorationLinks"])
        tab_text = "\n".join(
            s["text"]
            for s in d["sections"]
            if s["component"] not in ("component-t11", "component-t11b", "component-t12")
        )
        all_text.append(f"## {t['label']}\n{tab_text}")
        if re.search(r"itinerar", label, re.I):
            entry.setdefault("itinerary", []).extend(
                parse_itinerary("\n".join(s["text"] for s in d["sections"]))
            )
        entry["tabs"].append(tab)
        # go back to overview for consistent nth() indexing of the menu
        if i < len(tab_list) - 1 and not tabs_meta:
            break

    if not entry["name"]:
        first = next(
            (sec["heading"] for t in entry["tabs"] for sec in t["sections"] if sec["heading"]), ""
        )
        entry["name"] = first.title() if first.isupper() else first
    # booking
    codes_found = [code] if code else []
    exp_req = sorted(
        {m for h in all_booking for m in re.findall(r"expedition_request=([A-Z]{4})", h)}
    )
    hotel_codes = codes_found or (exp_req if codes else []) or codes
    entry["booking"] = {
        "href": sorted(all_booking),
        "header_cta": header_cta,
        "hotel_param": {"hotel_code": hotel_codes[0]} if hotel_codes else None,
        "hotel_codes": hotel_codes,
        "hotel_code_source": "wpbooking.lodge_code on page"
        if codes_found
        else (
            "expedition_request in CTA href"
            if exp_req
            else "reservations paso1 <select name=hotel_code> (mapped)"
        ),
        "reservation_names": {c: HOTEL_CODES.get(c) for c in hotel_codes},
        "prefill_url": f"{RESV}&hotel_code={hotel_codes[0]}" if hotel_codes else RESV,
        "deep_link_pattern": "https://reservations.explora.com/ibe/paso2?hotel_code={CODE}&check_in_date=YYYY-MM-DD&nights={N}&language=EN",
        "expedition_request_urls": [h for h in all_booking if "expedition_request" in h],
        "page_ctas_carry_hotel": any("hotel_code" in h for h in all_booking),
    }
    entry["opens_new_tab"] = sorted(all_blank)
    full = "\n\n".join(all_text)
    entry["text"] = full[:8000]
    entry["facts"] = extract_facts(full)
    if entry["rooms"]:
        seen = set()
        entry["rooms"] = [
            r for r in entry["rooms"] if not (r["name"] in seen or seen.add(r["name"]))
        ]
    if entry["faqs"]:
        seen = set()
        entry["faqs"] = [f for f in entry["faqs"] if not (f["q"] in seen or seen.add(f["q"]))]

    # explorations archive
    expl_entries: list[dict] = []
    arch = None
    for a in archive_links:
        p = urlparse(a)
        if p.path.startswith("/explorations-lodge/"):
            arch = f"{BASE}{'/'.join(p.path.split('/')[:3])}/"
            break
    if not arch and arch_slug:
        arch = f"{BASE}/explorations-lodge/{arch_slug}/"
    if arch:
        cards, finfo = crawl_archive(page, arch)
        entry["facts"]["explorations_archive"] = finfo
        log("  ARCHIVE", arch, len(cards))
        for c in cards:
            ex = {
                "name": c["name"],
                "area": c["area"],
                "activity": c["activity"],
                "difficulty": c["difficulty"],
                "duration": c["duration"],
                "text": c["text"],
                "url": c["url"],
            }
            entry["explorations"].append(ex)
        if details:
            for c in cards:
                if not c["url"]:
                    continue
                try:
                    goto(page, c["url"])
                    dd = page.evaluate(JS_DETAIL)
                except Exception as e:
                    log("   detail fail", c["url"], e)
                    continue
                txt = dd["text"]
                dist = re.search(r"(\d+[.,]?\d*\s?km\s*/\s*\d+[.,]?\d*\s?mi)", txt)
                hours = re.search(r"\b(\d+\s?h(?:\s?\d+\s?m)?)\b", txt)
                elev = {}
                for lab in ["Elevation Gain", "Elevation Loss", "Max. Altitude", "Min. Altitude"]:
                    m = re.search(
                        re.escape(lab) + r"\s*\n?\s*(-?[\d.,]+ m)\s*\n?\s*(-?[\d.,]+ ft)?", txt
                    )
                    if m:
                        elev[lab] = " / ".join(x for x in m.groups() if x)
                body = txt.split("Select your preferred explorations")[0]
                path_txt = (
                    body.split("EXPLORATION PATH", 1)[-1]
                    .split("Perspective")[0]
                    .split("ELEVATION PROFILE")[0]
                    .strip()
                )
                expl_entries.append(
                    {
                        "path": urlparse(c["url"]).path,
                        "url": c["url"],
                        "name": c["name"],
                        "destination": entry["name"],
                        "kind": "exploration",
                        "lodge_url": url,
                        "tabs": [],
                        "rooms": [],
                        "explorations": [],
                        "faqs": [],
                        "booking": {"href": [], "hotel_param": entry["booking"]["hotel_param"]},
                        "facts": {
                            "area": c["area"],
                            "activity": c["activity"],
                            "difficulty": c["difficulty"],
                            "duration": c["duration"],
                            "distance": dist.group(1) if dist else None,
                            "time": hours.group(1) if hours else None,
                            "elevation": elev or None,
                            "has_map": dd["map"],
                            "page_title": dd["title"],
                        },
                        "text": path_txt[:8000],
                    }
                )
                for ex in entry["explorations"]:
                    if ex["url"] == c["url"]:
                        ex["distance"] = dist.group(1) if dist else None
                        ex["time"] = hours.group(1) if hours else None
                        ex["elevation"] = elev or None
    else:
        entry["facts"]["exploration_links_on_pages"] = sorted(exploration_links)[:80]
    return entry, expl_entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-details", action="store_true")
    ap.add_argument("--only", help="substring filter on seed path")
    ap.add_argument("--shots", help="directory for per-tab screenshots")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument(
        "--merge",
        action="store_true",
        help="replace matching entries in the existing --out file instead of overwriting it",
    )
    args = ap.parse_args()
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(
            headless=True, channel="chrome", args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        page = ctx.new_page()
        explorations: list[dict] = []
        for seed in SEEDS:
            if args.only and args.only not in seed[0]:
                continue
            try:
                e, ex = crawl_entry(page, ctx, seed, not args.no_details, shots)
            except Exception as err:
                log("FAILED", seed[0], err)
                continue
            results.append(e)
            explorations.extend(ex)
        b.close()
    seen = set()
    for ex in explorations:
        if ex["url"] in seen:
            continue
        seen.add(ex["url"])
        results.append(ex)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.merge and out.exists():
        new_urls = {r["url"] for r in results}
        old = [r for r in json.loads(out.read_text()) if r["url"] not in new_urls]
        results = (
            [r for r in old if r["kind"] != "exploration"]
            + [r for r in results if r["kind"] != "exploration"]
            + [r for r in old if r["kind"] == "exploration"]
            + [r for r in results if r["kind"] == "exploration"]
        )
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    log("wrote", out, len(results))


if __name__ == "__main__":
    main()
