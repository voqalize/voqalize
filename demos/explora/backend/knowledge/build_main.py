# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Crawl the English pages of www.explora.com into pages_main.json.

Run:  uv run --with playwright python build_main.py [--limit 150] [--out pages_main.json]

Drives real Chrome (channel="chrome") because the page content is rendered and
lazy-loaded. Pages come from the sitemap index plus the links in the header and
footer; non-English (/es/, /pt-br/, /fr/, /de/) URLs are skipped. About one page
per second, so a full run takes ~15 minutes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = "https://www.explora.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
NON_EN = re.compile(r"^/(es|pt-br|fr|de)(/|$)")
JUNK = re.compile(
    r"(prueba|test-|/password-reset/|/logout/|/account/|/register/|/members/|/user/|/login/"
    r"|/120800-2/|-old/|-subscriber/|/reporting-channel-form/|/share-with-friends/|-2/$)"
)
# Taxonomy pages that are mostly translated duplicates (…-es, …-pt-br, …-fr).
TAX_DUP = re.compile(r"/explorations-(types|difficulty|duration)/.*-(es|pt-br|fr|2)/$")

# Curated priority patterns, in order. Every page in the sitemap that matches
# a pattern is taken before any that doesn't, up to --limit.
PRIORITY = [
    r"^/$",
    r"^/destinations/$",
    r"^/(patagonia-travel-argentina-chile|atacama-desert|sacred-valley-peru|easter-island-travel)/$",
    r"^/lodge/",
    r"^/explora-expeditions/|expedition|iceland|tierra-del-fuego|sacred-mountain",
    r"^/offer/|^/program/|passport|corporate-travel",
    r"conservation-reserve",
    r"^/explorations/$|^/explorations-lodge/",
    r"^/(about-us|explora-travels|explora-hotels|explora-south-america|explora-travel-awards|explora-experts"
    r"|what-is-explorer-echo-society|benefits-categories|join-the-explorer-echo-society|explora-contact"
    r"|contact-explora-lodges|work-with-us|terms-and-conditions|payment-and-cancellation-policies"
    r"|privacy-policy|press-page|founders-vision|explorers-manifesto|blog|transfers-information)/$",
    r"(el-chalten|el-calafate|torres-del-paine|patagonia-national-park|atacama|uyuni|easter-island"
    r"|sacred-valley|machu-picchu).*(travel-tips|getting|how-to-get|frequently-asked|cuisine|dining"
    r"|gastronomy|tours|hiking|explorations|lodge|hotel)",
    r"how-to-get|travel-tips|frequently-asked|getting-there",
    r"^/20(26|25)/",
    r"^/explorations-types/",
    r"^/20(24|23)/",
    r"^/explorations/[^/]+/$",
]

LODGE_PAGE = (
    r"^/(el-chalten-lodge|el-chalten-hotel|torres-del-paine-explora-lodge|patagonia-national-park-lodge"
    r"|atacama-desert-explora-lodge|uyuni-lodge|uyuni-hotel|easter-island-reserve-hotel|machu-picchu-lodge-peru[a-z-]*"
    r"|torres-del-paine-lodge-conservation-reserve|uyuni-salt-flat-unique-lodge-jirira-lodge|el-chalten-hotel-ab)/$"
)
# Per-lodge info pages (tips, getting there, FAQ, cuisine, tours) stay "other".
LODGE_INFO = r"(travel-tips|getting|how-to-get|frequently-asked|cuisine|dining|tours|hiking)"

KIND_RULES = [
    ("home", r"^/$"),
    (
        "destination",
        r"^/(destinations|patagonia-travel-argentina-chile|atacama-desert|sacred-valley-peru|easter-island-travel)/$",
    ),
    ("expedition", r"expedition|iceland|tierra-del-fuego|sacred-mountain"),
    ("offer", r"^/offer/|^/program/|passport|corporate-travel|promotions|offers"),
    ("experience", r"^/explorations|exploration"),
    ("lodge", r"^/lodge/"),
    (
        "about",
        r"^/(about-us|explora-travels|explora-hotels|explora-south-america|explora-travel-awards|explora-experts"
        r"|expert/|expert-category/|what-is-explorer-echo-society|benefits-categories|join-the-explorer-echo-society"
        r"|explora-contact|contact-explora-lodges|work-with-us|explora-jobs|press-page|awards-page|founders-vision"
        r"|explorers-manifesto|terms-and-conditions|privacy-policy|privacy-terms|payment-and-cancellation-policies"
        r"|reporting-channel)",
    ),
]

EXTRACT_JS = r"""
() => {
  const root = document.querySelector('#content') || document.querySelector('main') || document.body;
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const esc = s => (window.CSS && CSS.escape) ? CSS.escape(s) : s;
  const uniq = arr => [...new Set(arr)];
  function selectorFor(el) {
    if (!el || el === document.body) return 'body';
    if (el.id && document.querySelectorAll('#' + esc(el.id)).length === 1) return '#' + esc(el.id);
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.body) {
      if (cur.id && document.querySelectorAll('#' + esc(cur.id)).length === 1) { parts.unshift('#' + esc(cur.id)); break; }
      let part = cur.tagName.toLowerCase();
      const cls = [...cur.classList].filter(c => /^(component-|exp_component|destination__|why-explora|tab-panels|explora-)/.test(c));
      if (cls.length) part += '.' + cls.map(esc).join('.');
      const sibs = cur.parentElement ? [...cur.parentElement.children].filter(c => c.tagName === cur.tagName) : [];
      if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(cur) + 1})`;
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }
  const HEAD_SEL = 'h1,h2,h3,.h1,.h2,.h3,.explora-page-title';
  const skip = el => el.closest('header#masthead, footer, .modal, .mobile-menu, .nav-mobile, script, style, noscript');
  const headLevel = h => { const m = (h.tagName.match(/^H([1-6])$/) || [])[1]; if (m) return +m;
    for (const c of h.classList) { const k = c.match(/^h([1-6])$/); if (k) return +k[1]; } return 2; };
  const containerOf = h => h.closest('[class*="component-"], .exp_component, .destination__our-lodges, .destination__about-destination, .why-explora, .row.mb-5, article, .container') || h.parentElement;

  // ---- sections: visible headings in document order, text up to the next heading ----
  const heads = [...root.querySelectorAll(HEAD_SEL)].filter(h => !skip(h) && visible(h) && clean(h.innerText)
      && !h.querySelector(HEAD_SEL) );
  const sections = [];
  const seenSel = new Set();
  heads.forEach((h, i) => {
    const next = heads[i + 1];
    const range = document.createRange();
    range.setStartAfter(h);
    if (next) range.setEndBefore(next); else range.setEndAfter(root.lastChild || root);
    const frag = range.cloneContents();
    frag.querySelectorAll('script,style,noscript,select,option,.d-none,.modal').forEach(n => n.remove());
    let text = clean(frag.textContent);
    const cont = containerOf(h);
    const sel = selectorFor(cont);
    const items = [];
    if (!seenSel.has(sel)) {
      seenSel.add(sel);
      cont.querySelectorAll('a[href]').forEach(a => {
        const t = clean(a.innerText); const href = a.getAttribute('href');
        if (t && href && !href.startsWith('#') && t.length < 140 && visible(a)) items.push({ text: t, href: a.href });
      });
    }
    sections.push({ heading: clean(h.innerText).slice(0, 200), level: headLevel(h), tag: h.tagName.toLowerCase(),
      selector: sel, heading_selector: selectorFor(h), text: text.slice(0, 1500),
      items: uniq(items.map(x => JSON.stringify(x))).slice(0, 30).map(x => JSON.parse(x)) });
  });

  // ---- tabs: theme .tab-panels (li[data-index] -> .panel[data-index]) and bootstrap .nav-tabs ----
  const tabs = [];
  root.querySelectorAll('.tab-panels').forEach(tp => {
    const labels = [...tp.querySelectorAll('.tab-panels-nav li')].map(li => clean(li.textContent));
    const panes = [...tp.querySelectorAll('.tab-panels-content .panel')].map(p => ({
      label: labels[+p.dataset.index] || p.dataset.index, text: clean(p.textContent).slice(0, 1500) }));
    tabs.push({ selector: selectorFor(tp), click: '.tab-panels-nav li[data-index="N"]', labels, panes });
  });
  root.querySelectorAll('.nav-tabs, [role=tablist], .nav-pills').forEach(nav => {
    if (nav.closest('.tab-panels')) return;
    const links = [...nav.querySelectorAll('a[href^="#"], [data-toggle=tab], [data-target], [role=tab]')];
    if (!links.length) return;
    const labels = links.map(a => clean(a.textContent));
    const panes = links.map((a, i) => { const id = a.getAttribute('data-target') || a.getAttribute('href') || '';
      let p = null; try { p = id.startsWith('#') && id.length > 1 ? document.querySelector(id) : null; } catch (e) {}
      return { label: labels[i], text: p ? clean(p.textContent).slice(0, 1500) : '' }; });
    tabs.push({ selector: selectorFor(nav), click: 'a / [data-toggle=tab] inside', labels, panes });
  });

  // ---- faqs: bootstrap collapse triggers + question headings ----
  const faqs = [];
  const seenQ = new Set();
  root.querySelectorAll('[data-toggle=collapse]').forEach(t => {
    const q = clean(t.textContent); const id = t.getAttribute('data-target') || t.getAttribute('href') || '';
    if (!q || /read more|read less/i.test(q) || seenQ.has(q)) return;
    let p = null; try { p = id.startsWith('#') && id.length > 1 ? document.querySelector(id) : null; } catch (e) {}
    if (!p) return;
    seenQ.add(q); faqs.push({ q: q.slice(0, 300), a: clean(p.textContent).slice(0, 1500), trigger: selectorFor(t), target: id });
  });
  root.querySelectorAll('h2,h3,h4,h5,strong,b,.h3,.h4').forEach(h => {
    const q = clean(h.textContent);
    if (!q.endsWith('?') || q.length > 200 || seenQ.has(q) || skip(h)) return;
    let a = ''; let n = (h.tagName === 'STRONG' || h.tagName === 'B') ? (h.closest('p,h3,h4') || h) : h;
    let sib = n.nextElementSibling; let guard = 0;
    while (sib && guard++ < 6 && !sib.matches('h1,h2,h3,h4,h5') && !(sib.querySelector && sib.querySelector('strong,b') && clean(sib.textContent).endsWith('?'))) {
      a += ' ' + clean(sib.textContent); sib = sib.nextElementSibling; }
    if (clean(a)) { seenQ.add(q); faqs.push({ q, a: clean(a).slice(0, 1500) }); }
  });

  // ---- CTAs: buttons and booking links (header CTA included) ----
  const ctaRe = /(book|check availability|reserve|learn more|discover|explore|see |see$|contact|join|subscribe|view|more info|request|enquir|itinerar)/i;
  const ctas = [];
  const seenC = new Set();
  document.querySelectorAll('a[href]').forEach(a => {
    if (a.closest('footer, .mobile-menu, .nav-mobile, .modal')) return;
    const t = clean(a.innerText); const href = a.href;
    if (!t || t.length > 60 || !visible(a)) return;
    const isBtn = a.matches('.btn, .explora-cta, [class*=button], [class*=cta]') || a.closest('.booking-button, .t-button, [class*=cta]');
    if (!(isBtn || /reservations\.explora\.com|mailto:/.test(href) || ctaRe.test(t))) return;
    const k = t + '|' + href; if (seenC.has(k)) return; seenC.add(k);
    ctas.push({ text: t, href, new_tab: a.target === '_blank', selector: selectorFor(a) });
  });

  const alts = uniq([...root.querySelectorAll('img[alt]')].map(i => clean(i.alt)).filter(a => a && a.length > 2));
  const meta = n => (document.querySelector(`meta[name="${n}"], meta[property="${n}"]`) || {}).content || '';
  return {
    title: document.title, description: meta('description') || meta('og:description'),
    body_class: document.body.className, lang: document.documentElement.lang,
    h1: [...root.querySelectorAll('h1')].filter(visible).map(h => clean(h.innerText)),
    sections, faqs, tabs, ctas: ctas.slice(0, 60), images_alts: alts.slice(0, 80),
    text: clean(root.innerText).slice(0, 6000),
  };
}
"""


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def sitemap_urls() -> list[str]:
    idx = fetch(BASE + "/sitemap.xml")
    subs = re.findall(r"<loc><!\[CDATA\[(.*?)\]\]></loc>", idx) or re.findall(
        r"<loc>(.*?)</loc>", idx
    )
    out: list[str] = []
    for s in subs:
        if "explora.com" not in s:
            continue
        xml = fetch(s)
        locs = re.findall(r"<loc><!\[CDATA\[(.*?)\]\]></loc>", xml) or re.findall(
            r"<loc>(.*?)</loc>", xml
        )
        out += [u for u in locs if not re.search(r"\.(jpe?g|png|webp|gif|svg)$", u, re.I)]
        time.sleep(0.3)
    return out


def norm_path(u: str) -> str | None:
    p = urlparse(u)
    if p.scheme not in ("http", "https", "") or (p.netloc and p.netloc != "www.explora.com"):
        return None
    if p.query and not p.path.endswith("/"):
        return None
    path = p.path or "/"
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    if NON_EN.match(path) or JUNK.search(path) or TAX_DUP.search(path) or path.startswith("/wp"):
        return None
    return path


def kind_of(path: str, body_class: str) -> str:
    bc = body_class or ""
    if re.match(r"^/20\d\d/", path):
        return "post"
    # Several lodge landing pages are WordPress posts or plain pages.
    if re.search(LODGE_PAGE, path):
        return "lodge"
    if "single-post" in bc and not re.search(LODGE_INFO, path):
        return "post"
    if "single-lodge" in bc or "post-type-archive-lodge" in bc:
        return "lodge"
    if "single-destination" in bc or "post-type-archive-destination" in bc:
        return "destination"
    if (
        "single-offers" in bc
        or "single-programs" in bc
        or "post-type-archive-offers" in bc
        or "post-type-archive-programs" in bc
    ):
        return "offer"
    if (
        "single-exploration" in bc
        or "post-type-archive-exploration" in bc
        or "tax-exploration" in bc
    ):
        return "experience"
    for kind, rx in KIND_RULES:
        if re.search(rx, path):
            return kind
    if re.match(r"^/20\d\d/", path):
        return "post"
    return "other"


def scroll_through(page) -> None:
    h = page.evaluate("document.scrollingElement.scrollHeight")
    y = 0
    while y < h and y < 40000:
        y += 700
        page.evaluate(f"window.scrollTo(0,{y})")
        page.wait_for_timeout(90)
        h = page.evaluate("document.scrollingElement.scrollHeight")
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0,0)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parent / "L3" / "pages_main.json")
    )
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    sm = sitemap_urls()
    print(f"sitemap urls: {len(sm)}", file=sys.stderr)
    paths = []
    for u in sm:
        p = norm_path(u)
        if p and p not in paths:
            paths.append(p)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, channel="chrome", args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US"
        )
        page = ctx.new_page()

        # Seed with every internal link in the header mega menus and the footer.
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        nav = page.evaluate(
            "[...document.querySelectorAll('header#masthead a[href], footer a[href]')].map(a=>a.href)"
        )
        nav_paths = [p for p in (norm_path(u) for u in nav) if p]
        for p in nav_paths:
            if p not in paths:
                paths.append(p)

        def rank(p: str) -> tuple[int, int]:
            if p in nav_paths:
                return (0, 0)
            for i, rx in enumerate(PRIORITY):
                if re.search(rx, p):
                    return (1 + i, 0)
            return (99, 0)

        ordered = sorted(paths, key=rank)  # stable: keeps sitemap order within a rank
        # Cap individual explorations so they don't crowd out other kinds.
        picked, n_expl = [], 0
        for p in ordered:
            if re.match(r"^/explorations/[^/]+/$", p):
                n_expl += 1
                if n_expl > 12:
                    continue
            picked.append(p)
        print(f"candidates: {len(paths)}; crawling up to {args.limit}", file=sys.stderr)

        results, seen_final = [], set()
        for p in picked:
            if len(results) >= args.limit:
                break
            url = BASE + p
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                status = resp.status if resp else 0
                page.wait_for_timeout(1200)
                final = page.url
                fpath = norm_path(final)
                if status >= 400 or not fpath or fpath in seen_final:
                    print(f"skip {p} -> {final} ({status})", file=sys.stderr)
                    time.sleep(args.delay)
                    continue
                if "challenge" in page.title().lower() or "just a moment" in page.title().lower():
                    print(f"CLOUDFLARE CHALLENGE at {p}; stopping", file=sys.stderr)
                    break
                scroll_through(page)
                data = page.evaluate(EXTRACT_JS)
                seen_final.add(fpath)
                rec: dict[str, Any] = {
                    "path": fpath,
                    "url": final,
                    "requested_path": p if p != fpath else None,
                    "status": status,
                    "title": data["title"],
                    "description": data["description"],
                    "kind": kind_of(fpath, data["body_class"]),
                    "h1": data["h1"],
                    "sections": data["sections"],
                    "faqs": data["faqs"],
                    "tabs": data["tabs"],
                    "ctas": data["ctas"],
                    "images_alts": data["images_alts"],
                    "text": data["text"],
                }
                results.append(rec)
                print(
                    f"[{len(results)}] {rec['kind']:<11} {fpath}  s={len(rec['sections'])} f={len(rec['faqs'])} t={len(rec['tabs'])}",
                    file=sys.stderr,
                )
            except Exception as e:  # keep crawling past one bad page
                print(f"error {p}: {e!s:.200}", file=sys.stderr)
            time.sleep(args.delay)
        browser.close()

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"wrote {len(results)} pages to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
