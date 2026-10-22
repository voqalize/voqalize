# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Javier's knowledge of Universidad Alberto Hurtado's sites.

The university spreads over three WordPress hosts, and a prospective student
moves between them:

- ``admision.uahurtado.cl``: undergraduate admissions. 50 careers
  (``/carreras/<slug>/``), the vías de admisión, becas, gratuidad, visits.
- ``postgrados.uahurtado.cl``: 82 postgraduate programmes
  (``/programa/<slug>/``), listed by especialidad, área and facultad.
- ``www.uahurtado.cl``: the institution: la universidad, campus, estudiantes.

Two steps, so the knowledge can be rebuilt without the network:

``crawl`` reads the public ``/wp-json`` endpoints (httpx) and renders the pages
Javier can open in headless Chromium (Playwright), and caches both in
``$XDG_CACHE_HOME/voqalize-uahurtado`` (``~/.cache`` by default). Then it runs
``render``. ``render`` (or ``crawl --offline``) writes, next to this file:

- ``L3/carreras.json``: the 50 careers: ``{slug, name, url, faculty,
  menu_group, area, title_awarded, grado, duration, campus, jornada, modalidad,
  summary, tabs, has_audiomalla, admision_directa, pedagogia, malla_pdf,
  aliases}``. Static facts only.
- ``L3/programas.json``: the 82 postgraduate programmes: ``{slug, name, url,
  type, especialidad, area, areas, faculty, modalidad, duration, summary,
  aliases}``. Static facts only.
- ``L3/pages.json``: every page Javier may open, one record per line, in the
  shape the shared ``knowledge.py`` loader reads (``path, title,
  description, sections: [{heading, text, items}], headings, faqs: [{q, a}],
  text``) plus ``key`` (``<host>:<path>``, unique: the three hosts each have a
  ``/``), ``host``, ``url``, ``kind``, ``breadcrumbs``, section
  ``level/selector/id/pane/collapse/hidden``, ``tabs``, ``accordions``,
  ``anchors``, ``cards``, ``documents``, ``forms``, ``iframes``. Career and
  programme pages share one template each: the template record (``kind:
  "template"``, path ``/carreras/*`` or ``/programa/*``) carries their
  sections, tab ids and form once; each career and programme then has a light
  record (``kind: "carrera"`` / ``"programa"``, ``template``, ``title``,
  ``tabs``, ``headings``) with no text.
- ``L3/site.json``: hosts, navigation per host (the admisión menu with its
  dropdowns, the career mega-menu by faculty, the postgrados and www menus),
  contact details, WhatsApp links, the lead form's fields, response headers,
  redirects and outbound hosts.
- ``L2/facultad-*.md`` (one per faculty, its careers with a short static
  summary), ``L2/postgrado-catalogo.md`` (every programme by type) and
  ``L2/site-map.md`` (every page with its headings). The other L2 files and
  ``L1.md`` are hand-written and never touched here.

What is deliberately **not** stored, because it changes and Javier reads it
live on the page: fees (matrícula, arancel, titulación in UF), postgraduate
prices and discounts, PAES ponderaciones and minimum scores, application
windows, start dates, admission calendars and open calls for visits or events.
The REST reads never ask for those fields, and page text on the pages that
carry them is not kept (``VOLATILE``); any other line with a peso amount, a UF
value or a day-and-month date is dropped from page text.

Run from ``voqalize/demos`` (Chromium once: ``uv run --no-project --with
playwright playwright install chromium``)::

    uv run --no-project --with playwright --with httpx python uahurtado/backend/knowledge/build.py crawl
    uv run --no-project --with playwright --with httpx python uahurtado/backend/knowledge/build.py crawl --refresh
    uv run --no-project python uahurtado/backend/knowledge/build.py render

The site blocks some countries: a 403, 405, "Not allowed" or a timeout stops
the crawl with a message instead of writing partial data. It is polite: one
REST request at a time with a pause, two pages rendering at once, images,
media, fonts and third-party hosts blocked.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
L2 = HERE / "L2"
L3 = HERE / "L3"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-uahurtado"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HOSTS = {
    "admision": "admision.uahurtado.cl",
    "postgrados": "postgrados.uahurtado.cl",
    "www": "www.uahurtado.cl",
}
HOST_KEY = {v: k for k, v in HOSTS.items()}
REST_PAUSE_S = 0.4
PARALLEL = 2
TEXT_CAP = 8_000
SECTION_CAP = 2_500
SUMMARY_CAP = 300
HEADERS_KEPT = (
    "server",
    "content-type",
    "cache-control",
    "content-security-policy",
    "content-security-policy-report-only",
    "permissions-policy",
    "x-frame-options",
    "access-control-allow-origin",
    "referrer-policy",
)

# ─── The pages Javier can open ────────────────────────────────────────────────
# (host, path, kind). Career and programme pages are added from the REST lists.

PAGES: list[tuple[str, str, str]] = [
    ("admision", "/", "home"),
    ("admision", "/que-quiero-estudiar/", "listing"),
    ("admision", "/estudia-en-la-uah/", "page"),
    ("admision", "/vias-de-admision/", "page"),
    ("admision", "/admision-via-paes/", "page"),
    ("admision", "/requisitos-de-admision/", "page"),
    ("admision", "/admision-directa/", "page"),
    ("admision", "/ranking-1000/", "page"),
    ("admision", "/admision-pace/", "page"),
    ("admision", "/programa-de-atraccion-de-talento-pedagogico/", "page"),
    ("admision", "/aranceles/", "page"),
    ("admision", "/becas-y-beneficios/", "page"),
    ("admision", "/gratuidad-universitaria/", "page"),
    ("admision", "/deportista-destacado/", "page"),
    ("admision", "/pedagogias/", "listing"),
    ("admision", "/ingenierias/", "listing"),
    ("admision", "/continuidad-de-estudios/", "listing"),
    ("admision", "/continuidad/", "listing"),
    ("admision", "/ven-y-conocenos/", "page"),
    ("admision", "/visitas-guiadas-uah/", "page"),
    ("admision", "/admision-visita-la-uah/", "page"),
    ("admision", "/red-internacional/", "page"),
    ("admision", "/audiomallas/", "listing"),
    ("admision", "/tu-vocacion/", "page"),
    ("admision", "/en-cada-paso-te-acompanamos/", "page"),
    ("admision", "/a-toda-prueba/", "page"),
    ("admision", "/indicadores-de-calidad/", "page"),
    ("admision", "/resultados-ensayo-paes/", "page"),
    ("admision", "/campusb/", "page"),
    ("www", "/", "home"),
    ("www", "/la-universidad/", "page"),
    ("www", "/la-universidad/campus/", "page"),
    ("www", "/la-universidad/campus/campus-patrimonial/", "page"),
    ("www", "/la-universidad/campus/campusb/", "page"),
    ("www", "/la-universidad/calidad-uah/", "page"),
    ("www", "/estudiantes/", "page"),
    ("www", "/programas-uah/", "listing"),
    ("www", "/events/", "listing"),
    ("postgrados", "/", "home"),
    ("postgrados", "/financiamiento/", "page"),
    ("postgrados", "/descuentos/", "page"),
    ("postgrados", "/formas-de-pago/", "page"),
    ("postgrados", "/doctorados/", "listing"),
    ("postgrados", "/magister-online/", "listing"),
    ("postgrados", "/especialidad/magister/", "listing"),
    ("postgrados", "/especialidad/diplomado/", "listing"),
    ("postgrados", "/especialidad/doctorado/", "listing"),
    ("postgrados", "/especialidad/cursos/", "listing"),
]
#: Postgraduate programme pages rendered to read the shared template (one per type).
PROGRAMME_SAMPLES = (
    "magister-intervencion-psicosocial",
    "doctorado-en-filosofia",
    "diplomado-psicologia-educacional",
    "postitulo-en-neuropsicologia-clinica",
    "curso-supervision-tesis",
    "magister-gestion-direccion-educacional-online",
)
#: Pages whose text is about money, scores, dates or open calls: only their
#: structure (headings, tabs, anchors) is kept; the brain reads them live.
VOLATILE = {
    ("admision", "/aranceles"),
    ("admision", "/requisitos-de-admision"),
    ("admision", "/admision-visita-la-uah"),
    ("admision", "/admision-via-paes"),
    ("admision", "/ven-y-conocenos"),
    ("admision", "/visitas-guiadas-uah"),
    ("admision", "/resultados-ensayo-paes"),
    ("admision", "/ranking-1000"),
    ("www", "/events"),
    ("postgrados", "/descuentos"),
    ("postgrados", "/formas-de-pago"),
}

# ─── Scrubbing changing facts out of page text ────────────────────────────────

MONTHS = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
CHANGING = re.compile(
    r"\$\s?\d"  # peso amounts
    r"|\b\d+(?:[.,]\d+)?\s*U\.?F\.?\b|\bUF\s*\d"  # UF values
    rf"|\b\d{{1,2}}\s*(?:de\s+|al\s+\d{{1,2}}\s+(?:de\s+)?)?(?:{MONTHS})\b"  # 5 de enero, 5 al 8 de enero
    rf"|\b(?:{MONTHS})\s+(?:de\s+|del\s+)?20\d\d\b"  # enero de 2026
    r"|\b\d{1,2}[/-]\d{1,2}[/-](?:20)?\d\d\b"  # 30/10/2026
    r"|\b(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*\.?\s+\d{1,2}\b(?!\s*(?:%|horas|semestres|años|cr[eé]ditos))"  # Octubre 22
    r"|\b\d{1,2}:\d{2}\s*(?:am|pm|hrs?)\b"  # 4:00 pm
    r"|\bREALIZADO\b|\binscripciones? (?:abiertas|cerradas)\b",
    re.I,
)


#: Score thresholds and bands ("mayor o igual a 800", "680 a 779", "800 y más",
#: "550 puntos", "percentil 37") change every admission year.
SCORE = re.compile(
    r"\b\d{3,4}(?:[.,]\d+)?\s*(?:a|y)\s*(?:\d{3,4}|más)\b"
    r"|\b(?:puntaje|puntos|ranking|percentil|PAES|NEM)\b[^.;]*?\b\d{2,4}(?:[.,]\d+)?\b"
    r"|\b\d{3,4}(?:[.,]\d+)?\s*(?:o más\s*)?puntos\b",
    re.I,
)
#: A percentage in the same sentence as a year is a discount for that year.
YEAR_PERCENT = re.compile(r"(?=.*\d\s*%)(?=.*\b20\d\d\b)|.*\d\s*%\s+\d+\s*%")


def scrub_sentences(line: str) -> str:
    """A line without the sentences that carry score thresholds or a
    year-bound percentage."""
    parts = re.split(r"(?<=[.;:])\s+", line)
    return " ".join(x for x in parts if not SCORE.search(x) and not YEAR_PERCENT.match(x))


def scrub(text: str) -> str:
    """Page text without the lines that carry money, UF values or dates, and
    without the sentences that carry score thresholds or year-bound percentages."""
    out = []
    for line in text.splitlines():
        if not line.strip() or CHANGING.search(line):
            continue
        if kept := scrub_sentences(line).strip():
            out.append(kept)
    return "\n".join(out)


#: A month and day split over two lines ("Oct" / "22") survive the line test;
#: once the text is joined they are cut out as tokens.
DATE_TOKEN = re.compile(
    rf"\b(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|{MONTHS})[a-z]*\.?\s+\d{{1,2}}\b(?!\s*(?:%|horas|semestres|años))",
    re.I,
)


def joined(text: str, cap: int) -> str:
    # Table cells are lines of their own, so a score band ("25%" / "50%" /
    # "680 a 779") only shows as one once the text is joined: scrub again.
    return clip(scrub_sentences(" ".join(DATE_TOKEN.sub("", text).split())), cap)


def changing(text: str) -> bool:
    return bool(CHANGING.search(text))


# ─── Network ──────────────────────────────────────────────────────────────────


class Blocked(SystemExit):
    """The site refused us: almost always the VPN dropped (the site blocks India)."""


def blocked(why: str) -> Blocked:
    return Blocked(
        f"STOP: the site refused the request ({why}). The VPN has probably dropped; "
        "reconnect to a US exit and run again. Nothing was written."
    )


class Rest:
    """One polite JSON client: a request at a time, a pause between them."""

    def __init__(self) -> None:
        import httpx

        self._httpx = httpx
        self.client = httpx.Client(
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
        )
        self._last = 0.0

    def get(self, url: str) -> Any:
        wait = REST_PAUSE_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.client.get(url)
        except self._httpx.TimeoutException as exc:
            raise blocked(f"timeout on {url}") from exc
        finally:
            self._last = time.monotonic()
        if r.status_code in (403, 405) or "not allowed" in r.text[:500].lower():
            raise blocked(f"HTTP {r.status_code} on {url}")
        r.raise_for_status()
        return r.json()


CARRERA_FIELDS = ",".join(
    ["id", "slug", "link", "title", "areas", "facultades", "modified"]
    + [
        f"acf.{f}"
        for f in (
            "bajada_carrera",
            "grado_academico_carrera",
            "titulo_profesional_carrera",
            "mencion_carrera",
            "sede_carrera",
            "regimen_carrera",
            "modalidad_carrera",
            "duracion_carrera",
            "descripcion_carrera",
            "perfil_de_egreso",
            "malla_curricular_carrera",
            "audiomalla",
            "disp-admision_especial",
            "disp-pedagogia",
        )
    ]
)
PROGRAMA_FIELDS = ",".join(
    ["slug"]
    + [
        f"acf.{f}"
        for f in (
            "duracion",
            "modalidad",
            "card_keyword",
            "descripcion_principal",
            "abstract_program",
            "objetivos_program",
            "texto_grado",
        )
    ]
)


def crawl_rest(refresh: bool) -> None:
    out = CACHE / "rest"
    out.mkdir(parents=True, exist_ok=True)
    rest: Rest | None = None

    def fetch(name: str, url: str) -> Any:
        nonlocal rest
        path = out / f"{name}.json"
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        rest = rest or Rest()
        print(f"  rest {name}", file=sys.stderr)
        data = rest.get(url)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    adm = f"https://{HOSTS['admision']}/wp-json/wp/v2"
    pos = f"https://{HOSTS['postgrados']}/wp-json/wp/v2"
    fetch("carreras", f"{adm}/carreras?per_page=100&_fields={CARRERA_FIELDS}")
    fetch("adm_areas", f"{adm}/areas?per_page=100&_fields=id,name,slug,count")
    fetch("adm_facultades", f"{adm}/facultades?per_page=100&_fields=id,name,slug,count")
    # The full programme list with ACF takes over two minutes; without ACF it is
    # instant, and each programme's static fields come by slug.
    programas = fetch(
        "programas",
        f"{pos}/programa?per_page=100&_fields=id,slug,link,title,especialidad,areas_estudio,facultades,modified",
    )
    fetch("pos_especialidad", f"{pos}/especialidad?per_page=100&_fields=id,name,slug,count")
    fetch("pos_areas", f"{pos}/areas_estudio?per_page=100&_fields=id,name,slug,count")
    fetch("pos_facultades", f"{pos}/facultades?per_page=100&_fields=id,name,slug,count")
    for p in programas:
        fetch(f"programa_{p['slug']}", f"{pos}/programa?slug={p['slug']}&_fields={PROGRAMA_FIELDS}")
    if rest is not None:
        rest.client.close()


# ─── Rendering pages ──────────────────────────────────────────────────────────

PAGE_JS = r"""
() => {
  const T = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t\r\f\v]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
  const T1 = (s) => T(s).replace(/\s+/g, ' ');
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return ''; } };
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
      try { if (document.querySelectorAll(sel).length === 1 && document.querySelector(sel) === el) return sel; } catch (e) { /* climb */ }
    }
    return parts.join(' > ');
  };
  const CHROME = 'header#header, #header, nav, footer, #collapseCarreras, #MenuCarreras, #sideMenu, #overlay, .modal, '
    + '#userwayAccessibilityIcon, .uwy, #wpadminbar, .offcanvas, #menu-top, .skip-link, #toggleSideMenu';
  const SKIP = CHROME + ', script, style, noscript, template, svg, iframe, select, option, input, textarea, form, audio, video, link';
  const chrome = (el) => !!el.closest(CHROME);
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const shown = (el) => T1(el.innerText) || T1(el.textContent);
  const where = (el) => {
    const out = {};
    const pane = el.closest('.tab-pane');
    if (pane && pane.id) out.pane = pane.id;
    const col = el.closest('.collapse, .accordion-collapse');
    if (col && col.id) out.collapse = col.id;
    if (!visible(el)) out.hidden = true;
    return out;
  };

  const sections = [];
  let cur = { heading: '', level: 0, buf: [], items: [] };
  sections.push(cur);
  const BLOCK = /^(P|DIV|LI|UL|OL|H[1-6]|ARTICLE|SECTION|ASIDE|HEADER|FIGURE|FIGCAPTION|TABLE|TR|TD|TH|BLOCKQUOTE|PRE|BR|DT|DD)$/;
  const walk = (node) => {
    if (node.nodeType === 3) { cur.buf.push(node.nodeValue); return; }
    if (node.nodeType !== 1) return;
    const el = node;
    if (el.matches(SKIP)) return;
    const m = /^H([1-6])$/.exec(el.tagName);
    if (m) {
      const text = shown(el);
      if (text) {
        cur = { heading: text, level: Number(m[1]), buf: [], items: [], selector: cssPath(el), ...where(el) };
        const dom = T1(el.textContent);
        if (dom && dom !== text) cur.dom_text = dom;
        if (el.id) cur.id = el.id;
        if (el.closest('.card')) cur.card = true;
        sections.push(cur);
        return;
      }
    }
    if (el.tagName === 'LI') { const t = T1(el.textContent); if (t && t.length <= 160) cur.items.push(t); }
    const block = BLOCK.test(el.tagName);
    if (block) cur.buf.push('\n');
    if (el.tagName === 'TD' || el.tagName === 'TH') cur.buf.push(' ');
    for (const c of el.childNodes) walk(c);
    if (block) cur.buf.push('\n');
  };
  walk(document.body);
  const out = [];
  for (const s of sections) {
    s.text = s.buf.join('').split('\n').map(T1).filter(Boolean).join('\n');
    delete s.buf;
    s.items = [...new Set(s.items)].slice(0, 60);
    if (!s.heading && !s.text) continue;
    out.push(s);
  }

  const tabs = [...document.querySelectorAll('[data-bs-toggle="tab"], [data-bs-toggle="pill"], [data-toggle="tab"], [role="tab"]')]
    .filter((el) => !chrome(el))
    .map((el) => ({
      id: el.id || '',
      label: shown(el),
      target: el.getAttribute('data-bs-target') || el.getAttribute('href') || '',
      kind: el.getAttribute('data-bs-toggle') || 'tab',
      active: el.classList.contains('active'),
      selector: cssPath(el),
    }));
  const accordions = [...document.querySelectorAll('[data-bs-toggle="collapse"]')]
    .filter((el) => !chrome(el))
    .map((el) => {
      const target = el.getAttribute('data-bs-target') || el.getAttribute('href') || '';
      let body = null;
      try { body = target.startsWith('#') ? document.querySelector(target) : null; } catch (e) { body = null; }
      return {
        label: shown(el),
        target,
        selector: cssPath(el),
        expanded: el.getAttribute('aria-expanded') === 'true',
        parent: el.closest('.accordion')?.id || '',
        text: body ? T(body.innerText || body.textContent) : '',
      };
    });
  const cards = [];
  const seen = new Set();
  for (const c of document.querySelectorAll('.card')) {
    if (chrome(c)) continue;
    const tEl = c.querySelector('.card-title, h2, h3, h4, h5');
    const title = tEl ? shown(tEl) : '';
    if (!title) continue;
    const text = [...c.querySelectorAll('.card-text, p')].map((e) => T1(e.textContent)).filter((t) => t && t !== title);
    const a = [...c.querySelectorAll('a[href]')].find((x) => !/^(#|javascript:)/.test(x.getAttribute('href') || ''))
      || (c.closest('a[href]'));
    const link = [...c.querySelectorAll('a')].map((x) => T1(x.textContent)).filter(Boolean).pop() || '';
    const card = { title, text: [...new Set(text)].join(' · '), href: a ? abs(a.getAttribute('href')) : '', button: link, selector: cssPath(c), ...where(c) };
    const key = card.title + '|' + card.href;
    if (seen.has(key)) continue;
    seen.add(key);
    cards.push(card);
  }
  const anchors = [...document.querySelectorAll('[id]')]
    .filter((el) => !chrome(el) && !el.matches(SKIP) && /^[A-Za-z][\w-]*$/.test(el.id)
      && /^(SECTION|DIV|ARTICLE|TABLE|UL|H[1-6]|ASIDE|MAIN|BUTTON|A)$/.test(el.tagName)
      && !/^(menu-item|wp-|attachment|userway|hs-|cookie|uw)/.test(el.id))
    .map((el) => ({ id: el.id, tag: el.tagName.toLowerCase(), ...where(el) }))
    .slice(0, 250);
  const links = [];
  const documents = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) continue;
    const url = abs(href);
    const area = chrome(a) ? (a.closest('footer') ? 'footer' : 'header') : 'body';
    const label = T1(a.innerText) || T1(a.textContent) || T1(a.getAttribute('aria-label')) || T1(a.getAttribute('title')) || '';
    links.push({ url, text: label, area, target: a.getAttribute('target') || '' });
    if (/\.pdf($|\?)/i.test(url) && area === 'body') documents.push({ label, url });
  }
  const forms = [...document.querySelectorAll('form')].filter((f) => !f.closest('header#header, #header')).map((f) => ({
    id: f.id || '',
    action: f.getAttribute('action') || '',
    method: (f.getAttribute('method') || 'get').toLowerCase(),
    fields: [...f.querySelectorAll('input, select, textarea')].filter((i) => i.type !== 'submit').map((i) => ({
      name: i.name || i.id || '',
      type: i.type || i.tagName.toLowerCase(),
      required: i.required,
      label: T1((i.id && document.querySelector(`label[for="${i.id}"]`)?.textContent) || i.placeholder || i.getAttribute('aria-label') || ''),
      options: i.tagName === 'SELECT' ? [...i.options].map((o) => T1(o.textContent)).filter(Boolean).slice(0, 80) : [],
    })),
    submit: T1(f.querySelector('[type=submit], button')?.textContent),
  }));
  const iframes = [...document.querySelectorAll('iframe[src]')].map((f) => abs(f.getAttribute('src')))
    .filter((s) => !/recaptcha|googletagmanager|doubleclick|facebook|hotjar|clarity/.test(s));
  const datos = {};
  for (const tr of document.querySelectorAll('#malla table tr')) {
    const th = tr.querySelector('th');
    const td = tr.querySelector('td');
    if (th && td) datos[T1(th.textContent)] = T1(td.textContent);
  }
  const audios = [...document.querySelectorAll('audio source[src], audio[src]')].map((a) => ({ src: abs(a.getAttribute('src')), pane: a.closest('.tab-pane')?.id || '' }));
  const h1 = [...document.querySelectorAll('h1')].filter((h) => !chrome(h)).map((h) => shown(h)).filter(Boolean);
  return {
    title: T1(document.title),
    description: T1(document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content),
    canonical: document.querySelector('link[rel="canonical"]')?.href || '',
    h1,
    breadcrumbs: [...document.querySelectorAll('nav[aria-label="breadcrumb"] li, #breadcrumbs a, #breadcrumbs span.breadcrumb_last')].map((b) => T1(b.textContent)).filter(Boolean),
    body_class: document.body.className,
    sections: out, tabs, accordions, cards, anchors, links, documents, forms, iframes, datos, audios,
  };
}
"""

NAV_JS = r"""
() => {
  const T1 = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return ''; } };
  const link = (a) => ({ label: T1(a.innerText) || T1(a.textContent), href: abs(a.getAttribute('data-href') || a.getAttribute('href') || ''), target: a.getAttribute('target') || '' });
  const menus = {};
  for (const ul of document.querySelectorAll('ul.navbar-nav[id], ul.menu[id]')) {
    if (ul.closest('footer')) continue;
    menus[ul.id] = [...ul.querySelectorAll(':scope > li')].map((li) => {
      const a = li.querySelector(':scope > a, :scope > button');
      const item = a ? link(a) : { label: T1(li.textContent), href: '' };
      const kids = [...li.querySelectorAll('.dropdown-menu a, .sub-menu a')].map(link);
      if (kids.length) item.children = kids;
      if (li.classList.contains('boton-carrera')) item.opens = '#collapseCarreras';
      return item;
    }).filter((x) => x.label);
  }
  const mega = [];
  const mc = document.querySelector('#MenuCarreras');
  if (mc) {
    let group = null;
    for (const el of mc.querySelectorAll('p, a')) {
      if (el.tagName === 'P' && T1(el.textContent)) { group = { group: T1(el.textContent), careers: [] }; mega.push(group); }
      else if (el.tagName === 'A' && group) group.careers.push(link(el));
    }
  }
  const foot = document.querySelector('footer') || document.querySelector('#footer, .footer');
  const footer = foot ? {
    text: T1(foot.innerText),
    links: [...foot.querySelectorAll('a[href]')].map(link).filter((l) => l.label || l.href),
  } : null;
  const whatsapp = [...new Set([...document.querySelectorAll('a[href*="wa.me"], a[href*="whatsapp"]')].map((a) => a.href))];
  return { menus, mega, footer, whatsapp, search: [...document.querySelectorAll('form[role=search], form.search-form, form[action*="?s"], input[name=s]')].length > 0 };
}
"""

BLOCK_HOSTS = re.compile(r"(^|\.)uahurtado\.cl$|^cdn\.jsdelivr\.net$")


def cache_file(url: str) -> Path:
    return CACHE / "pages" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")


async def render_pages(urls: list[str], refresh: bool) -> None:
    from playwright.async_api import async_playwright

    (CACHE / "pages").mkdir(parents=True, exist_ok=True)
    todo = [u for u in urls if refresh or not cache_file(u).exists()]
    if not todo:
        return
    print(f"  rendering {len(todo)} pages", file=sys.stderr)
    stop: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA, locale="es-CL", viewport={"width": 1366, "height": 900}
        )

        async def route(r: Any) -> None:
            req = r.request
            host = urlsplit(req.url).hostname or ""
            if req.resource_type in ("image", "media", "font") or not BLOCK_HOSTS.search(host):
                await r.abort()
            else:
                await r.continue_()

        await ctx.route("**/*", route)
        queue: asyncio.Queue[str] = asyncio.Queue()
        for u in todo:
            queue.put_nowait(u)

        async def worker() -> None:
            page = await ctx.new_page()
            while not queue.empty() and not stop:
                url = queue.get_nowait()
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                except Exception as exc:  # timeouts mean the VPN dropped
                    stop.append(f"{type(exc).__name__} on {url}")
                    break
                status = resp.status if resp else 0
                body_start = (await page.content())[:3000].lower()
                if status in (403, 405) or "not allowed" in body_start:
                    stop.append(f"HTTP {status} on {url}")
                    break
                await page.wait_for_timeout(900)
                data = await page.evaluate(PAGE_JS)
                is_home = urlsplit(page.url).path in ("", "/")
                if is_home:
                    data["nav"] = await page.evaluate(NAV_JS)
                headers = await resp.all_headers() if resp else {}
                data.update(
                    url=url,
                    final_url=page.url,
                    status=status,
                    headers={k: v for k, v in headers.items() if k in HEADERS_KEPT},
                    redirected=[r.url for r in (await _chain(resp))] if resp else [],
                )
                cache_file(url).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"    {status} {url}", file=sys.stderr)
                await page.wait_for_timeout(300)
            await page.close()

        await asyncio.gather(*(worker() for _ in range(PARALLEL)))
        await browser.close()
    if stop:
        raise blocked(stop[0])


async def _chain(resp: Any) -> list[Any]:
    out = []
    req = resp.request.redirected_from
    while req is not None:
        out.append(req)
        req = req.redirected_from
    return out


def all_urls() -> list[str]:
    urls = [f"https://{HOSTS[h]}{p}" for h, p, _ in PAGES]
    carreras = read_rest("carreras")
    urls += [c["link"] for c in carreras]
    urls += [f"https://{HOSTS['postgrados']}/programa/{s}/" for s in PROGRAMME_SAMPLES]
    for t in read_rest("pos_areas"):
        if t.get("count"):
            urls.append(f"https://{HOSTS['postgrados']}/areas_estudio/{t['slug']}/")
    for t in read_rest("pos_facultades"):
        if t.get("count") and str(t.get("name", "")).startswith("Facultad"):
            urls.append(f"https://{HOSTS['postgrados']}/facultades/{t['slug']}/")
    return urls


# ─── Render: cache → layers ───────────────────────────────────────────────────


def read_rest(name: str) -> Any:
    path = CACHE / "rest" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run `build.py crawl` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def read_page(url: str) -> dict[str, Any] | None:
    path = cache_file(url)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def plain(raw: Any) -> str:
    """HTML (or ACF text) as one line of plain text."""
    if not isinstance(raw, str):
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\u00a0", " ")
    return " ".join(text.split())


def clip(text: str, cap: int) -> str:
    """At most ``cap`` characters, cut at a sentence end (else a word)."""
    text = " ".join(text.split())
    if len(text) <= cap:
        return text
    cut = text[:cap]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end >= cap * 0.5:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


def summary_of(*candidates: Any) -> str:
    for raw in candidates:
        text = plain(raw).lstrip("/ ").strip()
        # Drop sentences that carry changing facts.
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s and not changing(s)]
        text = " ".join(sentences)
        if len(text) >= 40:
            return clip(text, SUMMARY_CAP)
    return ""


def fold(s: str) -> str:
    d = unicodedata.normalize("NFKD", s.lower())
    return " ".join("".join(c for c in d if not unicodedata.combining(c)).split())


def path_of(url: str) -> str:
    p = urlsplit(url).path
    p = re.sub(r"/{2,}", "/", p).rstrip("/").lower()
    return p or "/"


def key_of(url: str) -> str:
    return f"{HOST_KEY.get(urlsplit(url).hostname or '', urlsplit(url).hostname)}:{path_of(url)}"


# ── Careers ──

FACULTY_NAMES = {
    "ciencias sociales": "Facultad de Ciencias Sociales",
    "derecho": "Facultad de Derecho",
    "economia y negocios": "Facultad de Economía y Negocios",
    "educacion": "Facultad de Educación",
    "filosofia y humanidades": "Facultad de Filosofía y Humanidades",
    "ingenieria": "Facultad de Ingeniería",
    "psicologia": "Facultad de Psicología",
}
FACULTY_FILES = {
    "Facultad de Ciencias Sociales": "facultad-ciencias-sociales",
    "Facultad de Derecho": "facultad-derecho",
    "Facultad de Economía y Negocios": "facultad-economia-y-negocios",
    "Facultad de Educación": "facultad-educacion",
    "Facultad de Filosofía y Humanidades": "facultad-filosofia-y-humanidades",
    "Facultad de Ingeniería": "facultad-ingenieria",
    "Facultad de Psicología": "facultad-psicologia",
}


def faculty_of(raw: str, group: str, area: str = "") -> str:
    """The career's faculty, from its Datos Académicos row, else its menu group,
    else its área."""
    for text in (raw, group, area):
        f = fold(text).replace("facultad de ", "").replace(" uah", "").strip()
        for k, v in FACULTY_NAMES.items():
            if f == k or f.startswith(k):
                return v
        for k, v in FACULTY_NAMES.items():
            if k in f:
                return v
    return raw or group


#: Spoken variants the generic rules below would not produce.
ALIAS_EXTRA: dict[str, list[str]] = {
    "psicologia": ["psico", "psicóloga", "psicólogo"],
    "derecho": ["leyes", "abogacía", "abogado", "abogada"],
    "ingenieria-comercial": ["comercial", "ingeniería comercial diurna", "ing comercial"],
    "ingenieria-comercial-cev-campb": [
        "ingeniería comercial vespertina",
        "ingeniería comercial continuidad",
        "comercial vespertino",
    ],
    "ingenieria-civil-en-informatica": [
        "informática",
        "ingeniería informática",
        "ingeniería en computación",
        "computación",
    ],
    "ingenieria-civil-informatica-tns-continuidad": [
        "informática para técnicos",
        "informática tns",
        "informática continuidad",
    ],
    "ingenieria-civil-industrial": ["industrial", "ingeniería industrial"],
    "ingenieria-civil-industrial-tns-continuidad": [
        "industrial para técnicos",
        "industrial tns",
        "industrial continuidad",
    ],
    "ingenieria-civil-industrial-100-online": ["industrial online", "ingeniería industrial online"],
    "ingenieria-civil-plan-comun-conducente-a-ingenieria-civil-en-informatica-e-ingenieria-civil-industrial": [
        "plan común",
        "ingeniería civil plan común",
        "ingeniería civil",
    ],
    "educacion-basica": ["pedagogía básica", "educación básica", "profesor de básica", "básica"],
    "educacion-parvularia": ["parvularia", "educadora de párvulos", "párvulos"],
    "pedagogia-en-educacion-diferencial": ["diferencial", "educación diferencial"],
    "pedagogia-en-ingles": ["inglés", "profesor de inglés"],
    "pedagogia-en-matematica": ["pedagogía en matemáticas", "profesor de matemática", "matemática"],
    "pedagogia-en-historia-y-ciencias-sociales": ["pedagogía en historia", "profesor de historia"],
    "pedagogia-en-lengua-castellana-y-comunicacion": [
        "pedagogía en lenguaje",
        "pedagogía en castellano",
        "profesor de lenguaje",
    ],
    "pedagogia-en-biologia-y-ciencias-naturales": [
        "pedagogía en biología",
        "pedagogía en ciencias",
        "profesor de biología",
    ],
    "pedagogia-en-artes-visuales": ["pedagogía en arte", "profesor de artes"],
    "pedagogia-en-musica": ["profesor de música"],
    "pedagogia-en-filosofia": ["profesor de filosofía"],
    "pedagogia-para-profesionales-continuidad-de-estudios": [
        "pedagogía para profesionales",
        "ser profesor siendo profesional",
    ],
    "trabajo-social": ["asistente social", "trabajadora social", "trabajador social"],
    "ciencia-politica": [
        "ciencia política",
        "relaciones internacionales",
        "ciencias políticas",
        "politología",
    ],
    "periodismo": ["periodista", "comunicaciones"],
    "sociologia": ["sociólogo", "socióloga"],
    "antropologia": ["antropólogo", "antropóloga"],
    "arqueologia": ["arqueólogo", "arqueóloga"],
    "geografia": ["geógrafo", "geógrafa"],
    "contador-publico-auditor-diurno": [
        "contador auditor",
        "contabilidad",
        "auditoría",
        "contador público",
    ],
    "contador-publico-auditor-cev-campb": [
        "contador auditor vespertino",
        "contador auditor continuidad",
    ],
    "gestion-de-informacion-bibliotecologia-y-archivistica": [
        "bibliotecología",
        "archivística",
        "bibliotecario",
    ],
    "licenciatura-en-historia": ["historia"],
    "licenciatura-en-filosofia": ["filosofía"],
    "licenciatura-en-lengua-y-literatura": ["literatura", "lengua y literatura", "letras"],
    "licenciatura-en-teoria-e-historia-del-arte": ["historia del arte", "teoría del arte"],
    "bachillerato-en-filosofia-y-humanidades": ["bachillerato en filosofía"],
    "bachillerato-en-humanidades": ["bachillerato"],
    "interpretacion-superior-mencion-canto": ["canto", "canto lírico"],
    "interpretacion-superior-en-direccion-coral": ["dirección coral", "director de coro"],
    "interpretacion-superior-en-musica-antigua": ["música antigua"],
    "administracion-publica": ["administración pública diurna"],
    "administracion-publica-100-online": [
        "administración pública online",
        "administración pública vespertina",
    ],
    "ingenieria-en-gestion-y-analitica-de-datos": [
        "analítica de datos",
        "ciencia de datos",
        "data",
    ],
    "ingenieria-en-gestion-de-personas": ["recursos humanos", "gestión de personas"],
    "ingenieria-en-gestion-logistica": ["logística"],
    "ingenieria-en-gestion-financiera-continuidad-de-estudios": ["gestión financiera", "finanzas"],
    "ingenieria-en-gestion-comercial-y-marketing-continuidad-de-estudios": [
        "marketing",
        "gestión comercial",
    ],
    "ingenieria-en-gestion-de-empresas": ["gestión de empresas"],
    "ingenieria-en-gestion-de-la-innovacion-y-emprendimiento": [
        "innovación y emprendimiento",
        "emprendimiento",
    ],
}

_QUALIFIERS = re.compile(
    r"\s*(\(.*?\)|100% online|,? continuidad de estudios|,? para tns|- continuidad.*)$", re.I
)


def aliases_for(slug: str, name: str, extra: dict[str, list[str]]) -> list[str]:
    out: list[str] = []

    def add(s: str) -> None:
        s = " ".join(s.split()).strip(" ,.-")
        if s and fold(s) != fold(name) and fold(s) not in {fold(x) for x in out}:
            out.append(s)

    base = _QUALIFIERS.sub("", name).strip()
    if ":" in base:  # "Diplomado en Psicología Educacional: desarrollo humano…"
        base = base.split(":")[0].strip()
    add(base)
    low = base[0].lower() + base[1:] if base else base
    add(low)
    # Licenciaturas are said by their discipline ("historia"); a magíster or
    # doctorado is not (the bare discipline is a career), so it gets the
    # spoken "de" and "máster" forms instead.
    if base.startswith("Licenciatura en "):
        add(base[len("Licenciatura en ") :])
    for written, spoken in (
        ("Magíster en ", ("magíster de ", "máster en ")),
        ("Magíster ", ("máster en ",)),
        ("Doctorado en ", ("doctorado de ",)),
        ("Diplomado en ", ("diplomado de ",)),
        ("Postítulo en ", ("postítulo de ",)),
    ):
        if base.startswith(written):
            for form in spoken:
                add(form + base[len(written) :])
            break
    for a in extra.get(slug, []):
        add(a)
    return out[:10]


def short_duration(text: str) -> str:
    """The duration alone: the field sometimes runs on into class days and
    hours ("7 trimestresEn algunos niveles…")."""
    head = re.split(r"(?<=[a-záéíóú])(?=[A-ZÁÉÍÓÚ])", text.strip())[0]
    return clip(head, 90)


def build_carreras() -> list[dict[str, Any]]:
    rest = read_rest("carreras")
    areas = {a["id"]: html.unescape(a["name"]) for a in read_rest("adm_areas")}
    home = read_page(f"https://{HOSTS['admision']}/") or {}
    groups: dict[str, str] = {}
    for g in (home.get("nav") or {}).get("mega", []):
        for c in g["careers"]:
            groups[path_of(c["href"])] = g["group"]
    out = []
    for c in sorted(rest, key=lambda x: x["slug"]):
        acf = c.get("acf") or {}
        page = read_page(c["link"]) or {}
        datos = page.get("datos") or {}
        name = html.unescape(c["title"]["rendered"]).strip()
        group = groups.get(path_of(c["link"]), "")
        area_names = [areas[a] for a in c.get("areas") or [] if a in areas]
        audio = acf.get("audiomalla") or {}
        has_audio = bool(isinstance(audio, dict) and audio.get("archivo_de_audio_carrera")) or any(
            a.get("pane") == "malla" for a in page.get("audios") or []
        )
        modalidad = datos.get("Modalidad") or plain(acf.get("modalidad_carrera"))
        tabs = [t["id"].removesuffix("-tab") for t in page.get("tabs") or [] if t.get("id")]
        rec = {
            "slug": c["slug"],
            "name": name,
            "url": c["link"],
            "faculty": faculty_of(
                datos.get("Facultad", ""), group, datos.get("Área") or " ".join(area_names)
            ),
            "menu_group": group,
            "area": datos.get("Área") or ", ".join(area_names),
            "title_awarded": " ".join(
                (
                    datos.get("Título profesional") or plain(acf.get("titulo_profesional_carrera"))
                ).split()
            ),
            "grado": " ".join(
                (datos.get("Grado académico") or plain(acf.get("grado_academico_carrera"))).split()
            ),
            "duration": short_duration(datos.get("Duración") or plain(acf.get("duracion_carrera"))),
            "campus": datos.get("Sede")
            or plain(acf.get("sede_carrera"))
            or ("100% Online" if "online" in fold(modalidad) else ""),
            "jornada": datos.get("Régimen") or plain(acf.get("regimen_carrera")),
            "modalidad": "100% online (clases asincrónicas, con instancias sincrónicas voluntarias)"
            if len(modalidad) > 60 and "asincr" in modalidad
            else clip(modalidad, 160),
            "summary": summary_of(
                acf.get("descripcion_carrera"),
                acf.get("bajada_carrera"),
                acf.get("perfil_de_egreso"),
            ),
            "tabs": tabs,
            "has_audiomalla": has_audio,
            "admision_directa": str(acf.get("disp-admision_especial")).lower() == "true",
            "pedagogia": str(acf.get("disp-pedagogia")).lower() == "true",
            "malla_pdf": acf.get("malla_curricular_carrera")
            if isinstance(acf.get("malla_curricular_carrera"), str)
            else "",
            "aliases": aliases_for(c["slug"], name, ALIAS_EXTRA),
        }
        if not page:
            rec["unrendered"] = True
        out.append(rec)
    dedupe_aliases(out)
    return out


def dedupe_aliases(items: list[dict[str, Any]]) -> None:
    """An alias that is another item's name, or that two items share, is
    ambiguous: drop it (the qualified variants keep their own)."""
    names = {fold(i["name"]) for i in items}
    counts = Counter(fold(a) for i in items for a in i["aliases"])
    for i in items:
        i["aliases"] = [a for a in i["aliases"] if fold(a) not in names and counts[fold(a)] == 1]


# ── Programmes ──

MODALIDAD = {
    "online-sincronico": "Online sincrónico",
    "online": "Online",
    "hibrida": "Semipresencial sincrónica (híbrida)",
    "presencial": "Presencial",
    "semipresencial": "Semipresencial",
}


def programme_type(slug: str, especialidades: list[str]) -> str:
    if slug.startswith("postitulo"):
        return "postitulo"
    if "doctorado" in especialidades or slug.startswith("doctorado"):
        return "doctorado"
    if (
        "magister" in especialidades
        or "magister-online" in especialidades
        or slug.startswith(("magister", "mba"))
    ):
        return "magister"
    if "diplomado" in especialidades or slug.startswith("diplomado"):
        return "diplomado"
    return "otro"


PROGRAMME_ALIAS_EXTRA: dict[str, list[str]] = {
    "mba-magister-en-administracion-de-empresas": ["MBA", "eme be a", "magíster en administración"],
    "magister-derecho-penal": ["derecho penal online"],
    "magister-derecho-penal_sinc": ["magíster en derecho penal", "derecho penal"],
}


def build_programas(carreras: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rest = read_rest("programas")
    esp = {t["id"]: t for t in read_rest("pos_especialidad")}
    areas = {t["id"]: html.unescape(t["name"]) for t in read_rest("pos_areas")}
    facs = {t["id"]: html.unescape(t["name"]) for t in read_rest("pos_facultades")}
    out = []
    for p in sorted(rest, key=lambda x: x["slug"]):
        detail = read_rest(f"programa_{p['slug']}")
        acf = (detail[0].get("acf") if detail else {}) or {}
        especialidades = [esp[e]["slug"] for e in p.get("especialidad") or [] if e in esp]
        name = html.unescape(p["title"]["rendered"]).strip()
        area_names = [areas[a] for a in p.get("areas_estudio") or [] if a in areas]
        fac_names = [
            facs[f]
            for f in p.get("facultades") or []
            if f in facs and facs[f].startswith("Facultad")
        ]
        mod_raw = acf.get("modalidad") or ""
        duration = plain(acf.get("duracion"))
        rec = {
            "slug": p["slug"],
            "name": name,
            "url": p["link"],
            "type": programme_type(p["slug"], especialidades),
            "especialidad": [esp[e]["name"] for e in p.get("especialidad") or [] if e in esp],
            "area": area_names[0] if area_names else "",
            "areas": area_names,
            "faculty": fac_names[0] if fac_names else "",
            "modalidad": MODALIDAD.get(mod_raw, mod_raw),
            "duration": "" if changing(duration) else duration,
            "summary": summary_of(
                acf.get("card_keyword"),
                acf.get("descripcion_principal"),
                acf.get("abstract_program"),
                acf.get("objetivos_program"),
            ),
            "aliases": aliases_for(p["slug"], name, PROGRAMME_ALIAS_EXTRA),
        }
        out.append(rec)
    dedupe_aliases(out)
    # A programme never takes a career's name or alias: "psicología" is the career.
    taken = {fold(c["name"]) for c in carreras or []} | {
        fold(a) for c in carreras or [] for a in c["aliases"]
    }
    for p in out:
        p["aliases"] = [a for a in p["aliases"] if fold(a) not in taken]
    return out


# ── Pages ──


def section_record(s: dict[str, Any], keep_text: bool) -> dict[str, Any] | None:
    if changing(s.get("heading", "")):
        return None
    rec: dict[str, Any] = {"heading": s.get("heading", "")}
    for k in ("level", "selector", "id", "pane", "collapse", "hidden", "dom_text", "card"):
        if s.get(k):
            rec[k] = s[k]
    text = scrub(s.get("text", "")) if keep_text else ""
    rec["text"] = joined(text, SECTION_CAP) if text else ""
    items = [i for i in s.get("items") or [] if not changing(i)] if keep_text else []
    if items:
        rec["items"] = items[:40]
    return rec


def faqs_of(
    r: dict[str, Any], sections: list[dict[str, Any]], keep_text: bool
) -> list[dict[str, Any]]:
    faqs: list[dict[str, Any]] = []
    group = ""
    for s in sections:
        h = s["heading"]
        if s.get("level", 9) <= 2 and "?" not in h:
            group = h
        if (
            h.startswith("¿")
            and h.rstrip().endswith("?")
            and not s.get("card")
            and not h.lower().startswith("¿quieres saber más")
        ):
            faqs.append(
                {
                    "q": h,
                    "a": clip(s["text"], 900) if keep_text else "",
                    "group": group,
                    "selector": s.get("selector", ""),
                }
            )
    for a in r.get("accordions") or []:
        q = a["label"]
        if "?" in q and not changing(q):
            faqs.append(
                {
                    "q": q,
                    "a": joined(scrub(a.get("text", "")), 900) if keep_text else "",
                    "group": "",
                    "selector": a["selector"],
                    "target": a["target"],
                }
            )
    return faqs


def page_record(
    url: str, kind: str, r: dict[str, Any], keep_text: bool, light: bool = False
) -> dict[str, Any]:
    host = HOST_KEY.get(urlsplit(url).hostname or "", "")
    sections = [x for s in r.get("sections") or [] if (x := section_record(s, keep_text))]
    headings = [s["heading"] for s in sections if s["heading"]]
    rec: dict[str, Any] = {
        "key": key_of(url),
        "host": host,
        "path": path_of(url),
        "url": url,
        "title": r.get("title", ""),
        "h1": (r.get("h1") or [""])[0],
        "description": "" if changing(r.get("description", "")) else r.get("description", ""),
        "kind": kind,
    }
    if light:
        rec["headings"] = headings
        return rec
    if not keep_text:
        rec["volatile"] = True
    rec["breadcrumbs"] = r.get("breadcrumbs") or []
    rec["sections"] = sections
    rec["headings"] = headings
    rec["faqs"] = faqs_of(r, sections, keep_text)
    rec["tabs"] = [
        {k: t[k] for k in ("id", "label", "target", "kind", "active", "selector") if k in t}
        for t in r.get("tabs") or []
    ]
    rec["accordions"] = [
        {k: a[k] for k in ("label", "target", "selector", "expanded", "parent") if k in a}
        for a in r.get("accordions") or []
    ]
    rec["anchors"] = (r.get("anchors") or []) + [
        {"id": f["id"], "tag": "form"} for f in r.get("forms") or [] if f.get("id")
    ]
    rec["cards"] = [
        {
            **{
                k: c[k]
                for k in ("title", "href", "button", "selector", "pane", "collapse", "hidden")
                if c.get(k)
            },
            "text": ""
            if not keep_text or changing(c.get("text", ""))
            else clip(c.get("text", ""), 400),
        }
        for c in r.get("cards") or []
        if not changing(c.get("title", ""))
    ]
    rec["documents"] = [
        d for d in r.get("documents") or [] if keep_text or not changing(d.get("label", ""))
    ]
    rec["forms"] = [
        {
            "id": f["id"],
            "action": f["action"],
            "method": f["method"],
            "submit": f["submit"],
            "fields": [x for x in f["fields"] if x["type"] != "hidden"],
        }
        for f in r.get("forms") or []
        if f.get("fields")
    ]
    rec["iframes"] = r.get("iframes") or []
    rec["text"] = (
        clip("\n".join(s["text"] for s in sections if s["text"]), TEXT_CAP) if keep_text else ""
    )
    return rec


def template_record(
    name: str, path: str, host: str, samples: list[dict[str, Any]], note: str
) -> dict[str, Any]:
    """One record for a page template: the sections, tabs, accordions and form
    the pages built from it share, read from rendered samples."""
    base = samples[0]
    url = base["url"]
    rec = page_record(url, "template", base, keep_text=False)
    # Headings that are the item's own name are not shared; keep the ones that
    # appear on at least half the samples, with the first sample's selector.
    counts = Counter(
        fold(s["heading"])
        for r in samples
        for s in {fold(x["heading"]): x for x in r.get("sections") or []}.values()
    )
    shared = []
    names = {fold(h) for r in samples for h in r.get("h1") or []}
    seen = set()
    for r in samples:
        for s in r.get("sections") or []:
            f = fold(s["heading"])
            if f in names or f in seen or counts[f] < max(2, len(samples) // 2):
                continue
            seen.add(f)
            if (x := section_record(s, keep_text=False)) is not None:
                shared.append(x)
    tab_ids: dict[str, dict[str, Any]] = {}
    for r in samples:
        for t in r.get("tabs") or []:
            if t.get("id") and t["id"] not in tab_ids:
                tab_ids[t["id"]] = {k: t[k] for k in ("id", "label", "target", "kind") if k in t}
    rec.update(
        key=f"{host}:{path}",
        path=path,
        url=f"https://{HOSTS[host]}{path}",
        title=name,
        h1="",
        description=note,
        template=name,
        sections=shared,
        headings=[s["heading"] for s in shared],
        tabs=list(tab_ids.values()),
        faqs=[],
        cards=[],
        documents=[],
        iframes=[],
        samples=[r["url"] for r in samples],
    )
    rec.pop("volatile", None)
    anchor_ids = Counter(
        a["id"] for r in samples for a in {x["id"]: x for x in r.get("anchors") or []}.values()
    )
    rec["anchors"] = [
        a for a in base.get("anchors") or [] if anchor_ids[a["id"]] >= max(2, len(samples) // 2)
    ]
    return rec


CARRERA_TEMPLATE_NOTE = (
    "Every career page (/carreras/<slug>/) is built from this template. Hero #cabeza-carrera: h1 with the "
    "career name, the .bajada line, and the lead form #admisionForm (career preset in a hidden field). Body "
    "#cuerpo-carrera: a vertical Bootstrap tab list; open a tab with document.querySelector('#<id>-tab').click(). "
    "#malla (active by default) holds the Datos Académicos table (Carrera, Modalidad, Área, Grado académico, "
    "Título profesional, Facultad, Sede, Régimen, Duración), the malla PDF link and, on some careers, the "
    "audiomalla <audio>. #requisitos_carrera holds the PAES ponderaciones and minimums (left .col-md-6) and "
    "Aranceles (right .col-md-6): read both live, never from here. Which tabs a career has is in carreras.json."
)
PROGRAMA_TEMPLATE_NOTE = (
    "Every postgraduate programme page (postgrados.uahurtado.cl/programa/<slug>/) is built from this template. "
    "Hero #cabeza-carrera with the h1 and the lead form #admisionForm. Main column: accordion #programaAccordion "
    'with buttons [data-bs-target="#collapseDGeneral|#collapsePlanEstudios|#collapseMalla|#collapseRequisitos|'
    '#collapsePerfilGraduado|#collapseDocentes"]. #collapseRequisitos (Requisitos y Valores) holds fees and '
    "discounts: read live. The sidebar's h3 blocks (Postulaciones, Inicio, Director/a, Contacto e Información, "
    "Admisión) hold dates and contacts: read live."
)


def build_pages(
    carreras: list[dict[str, Any]], programas: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    raw_by_url: dict[str, dict[str, Any]] = {}
    seen_keys: set[str] = set()
    for host, path, kind in PAGES:
        url = f"https://{HOSTS[host]}{path}"
        r = read_page(url)
        if not r or r.get("status") != 200:
            print(f"  not rendered or not 200: {url}", file=sys.stderr)
            continue
        raw_by_url[url] = r
        final = r.get("final_url") or url
        if key_of(final) != key_of(url):
            # A redirect: the page is recorded once, under where it lands
            # (site.json lists the redirect).
            if urlsplit(final).hostname not in HOST_KEY:
                continue  # it left the three hosts (a faculty site)
            url = final
            host = HOST_KEY[urlsplit(url).hostname or ""]
        if key_of(url) in seen_keys:
            continue
        seen_keys.add(key_of(url))
        keep = (host, path_of(url)) not in VOLATILE
        pages.append(page_record(url, kind, r, keep))
    for t in read_rest("pos_areas"):
        url = f"https://{HOSTS['postgrados']}/areas_estudio/{t['slug']}/"
        if (r := read_page(url)) is not None:
            pages.append(page_record(url, "listing", r, keep_text=True))
    for t in read_rest("pos_facultades"):
        url = f"https://{HOSTS['postgrados']}/facultades/{t['slug']}/"
        if (r := read_page(url)) is not None:
            pages.append(page_record(url, "listing", r, keep_text=True))
    # Templates, then one light record per career and programme.
    career_raw = [r for c in carreras if (r := read_page(c["url"]))]
    if career_raw:
        pages.append(
            template_record("carrera", "/carreras/*", "admision", career_raw, CARRERA_TEMPLATE_NOTE)
        )
    for c in carreras:
        r = read_page(c["url"]) or {"title": c["name"], "h1": [c["name"]], "sections": []}
        rec = page_record(c["url"], "carrera", r, keep_text=False, light=True)
        rec.update(
            template="carrera", slug=c["slug"], tabs=c["tabs"], has_audiomalla=c["has_audiomalla"]
        )
        pages.append(rec)
    prog_raw = [
        r
        for s in PROGRAMME_SAMPLES
        if (r := read_page(f"https://{HOSTS['postgrados']}/programa/{s}/"))
    ]
    if prog_raw:
        pages.append(
            template_record(
                "programa", "/programa/*", "postgrados", prog_raw, PROGRAMA_TEMPLATE_NOTE
            )
        )
    for p in programas:
        pages.append(
            {
                "key": key_of(p["url"]),
                "host": "postgrados",
                "path": path_of(p["url"]),
                "url": p["url"],
                "title": p["name"],
                "h1": p["name"],
                "description": "",
                "kind": "programa",
                "template": "programa",
                "slug": p["slug"],
            }
        )
    return pages, raw_by_url


def build_site(
    pages: list[dict[str, Any]],
    raw_by_url: dict[str, dict[str, Any]],
    carreras: list[dict[str, Any]],
) -> dict[str, Any]:
    nav: dict[str, Any] = {}
    headers: dict[str, Any] = {}
    whatsapp: set[str] = set()
    for host, h in HOSTS.items():
        r = read_page(f"https://{h}/") or {}
        n = r.get("nav") or {}
        foot = n.get("footer") or {}
        nav[host] = {
            "menus": n.get("menus") or {},
            "footer_links": [x for x in foot.get("links") or [] if x.get("label")],
        }
        if n.get("mega"):
            nav[host]["career_menu"] = {
                "opens": "#collapseCarreras",
                "button": "#menu-menu-principal-1 > li.boton-carrera > a",
                "groups": n["mega"],
            }
        nav[host]["footer_text"] = scrub(foot.get("text", "")) if foot else ""
        headers[host] = r.get("headers") or {}
        whatsapp |= set(n.get("whatsapp") or [])
    redirects = []
    outbound: Counter[str] = Counter()
    all_raw = list(raw_by_url.values()) + [r for c in carreras if (r := read_page(c["url"]))]
    for r in all_raw:
        if (r.get("final_url") and path_of(r["final_url"]) != path_of(r["url"])) or (
            r.get("final_url") and urlsplit(r["final_url"]).hostname != urlsplit(r["url"]).hostname
        ):
            redirects.append({"from": r["url"], "to": r["final_url"]})
        for link in r.get("links") or []:
            host = urlsplit(link["url"]).hostname or ""
            if host and not host.endswith("uahurtado.cl"):
                outbound[host] += 1
    uah_hosts: Counter[str] = Counter(
        urlsplit(link["url"]).hostname or ""
        for r in all_raw
        for link in r.get("links") or []
        if (urlsplit(link["url"]).hostname or "").endswith("uahurtado.cl")
    )
    # The lead form as the career page carries it (never submitted by Javier).
    lead = None
    for c in carreras:
        r = read_page(c["url"]) or {}
        for f in r.get("forms") or []:
            if f.get("id") == "admisionForm":
                lead = {
                    "id": "admisionForm",
                    "action": f["action"],
                    "method": f["method"],
                    "submit": f["submit"],
                    "fields": [
                        {k: x[k] for k in ("name", "type", "required", "label") if k in x}
                        | ({"options": len(x["options"])} if x.get("options") else {})
                        for x in f["fields"]
                    ],
                    "note": "A real lead in UAH's admissions pipeline. Fill fields with input/change events; never submit, requestSubmit or click Enviar.",
                }
                break
        if lead:
            break
    return {
        "crawled": dt.date.today().isoformat(),
        "hosts": {
            "admision": {
                "url": f"https://{HOSTS['admision']}",
                "role": "Undergraduate admissions: careers, vías de admisión, becas, gratuidad, visits, lead form",
            },
            "postgrados": {
                "url": f"https://{HOSTS['postgrados']}",
                "role": "Postgraduate programmes: magíster, doctorado, diplomados, postítulos, cursos",
            },
            "www": {
                "url": f"https://{HOSTS['www']}",
                "role": "Institution: la universidad, campus, estudiantes, news, events",
            },
            "simula": {
                "url": "https://simula.uahurtado.cl",
                "role": "Simulador de Puntaje PAES (needs a full lead form with reCAPTCHA; offer it, never fill it)",
            },
        },
        "contact": {
            "address": "Av. Bernardo O'Higgins 1825, Metro Los Héroes, Santiago",
            "phone": "+56 2 2692 0200",
            "admision_email": "futuroestudiante@uahurtado.cl",
            "admision_phone": "+56 9 9793 7820",
            "postgrados_email": "postgrados@uahurtado.cl",
            "whatsapp": sorted(whatsapp),
            "note": "The site has no contact page: contact details are in each host's footer and the admisión home carousel; the lead form #admisionForm is the 'solicita información' route.",
        },
        "nav": nav,
        "lead_form": lead,
        "headers": headers,
        "redirects": redirects,
        "uah_hosts_linked": dict(uah_hosts.most_common()),
        "outbound_hosts": dict(outbound.most_common(40)),
        "page_kinds": dict(Counter(p["kind"] for p in pages)),
        "path_collisions": sorted(
            path for path, n in Counter(p["path"] for p in pages).items() if n > 1
        ),
    }


# ── Generated L2 ──


def write_faculty_files(carreras: list[dict[str, Any]]) -> None:
    by_fac: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in carreras:
        by_fac[c["faculty"]].append(c)
    for fac, stem in FACULTY_FILES.items():
        items = sorted(by_fac.get(fac, []), key=lambda c: fold(c["name"]))
        lines = [
            f"# {fac}: carreras de pregrado",
            "",
            f"Sources: admision.uahurtado.cl/carreras/<slug>/ (Datos Académicos and Descripción de la Carrera), "
            f"generated by build.py on {dt.date.today().isoformat()}.",
            "",
            f"{len(items)} careers. Fees, PAES ponderaciones and minimum scores are not here: they are on each "
            "career's Requisitos y Aranceles tab, read live.",
            "",
        ]
        for c in items:
            bits = [
                b
                for b in (
                    c["title_awarded"] and f"Título: {c['title_awarded']}",
                    c["grado"] and f"Grado: {c['grado']}",
                )
                if b
            ]
            facts = ", ".join(
                b
                for b in (
                    c["duration"],
                    c["jornada"],
                    c["campus"],
                    c["modalidad"] if len(c["modalidad"]) < 40 else "",
                )
                if b
            )
            lines += [
                f"## {c['name']}",
                f"`{path_of(c['url'])}` · {facts}"
                + (
                    f" · menú: {c['menu_group']}"
                    if c["menu_group"] and not c["menu_group"].startswith("Facultad")
                    else ""
                ),
            ]
            if bits:
                lines.append(". ".join(bits) + ".")
            if c["summary"]:
                lines.append(c["summary"])
            extras = [
                x
                for x in (
                    "Audiomalla en la pestaña Malla Curricular" if c["has_audiomalla"] else "",
                    "Disponible en Admisión Directa" if c["admision_directa"] else "",
                )
                if x
            ]
            if extras:
                lines.append(" · ".join(extras) + ".")
            lines.append("")
        (L2 / f"{stem}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


TYPE_TITLES = {
    "doctorado": "Doctorados",
    "magister": "Magíster",
    "diplomado": "Diplomados",
    "postitulo": "Postítulos",
    "otro": "Cursos y talleres",
}


def write_programme_catalogue(programas: list[dict[str, Any]]) -> None:
    lines = [
        "# Postgrado: catálogo de programas",
        "",
        f"Sources: postgrados.uahurtado.cl/wp-json/wp/v2/programa, generated by build.py on {dt.date.today().isoformat()}.",
        "",
        f"{len(programas)} programmes on postgrados.uahurtado.cl, each at `/programa/<slug>/`. Application windows, "
        "start dates, fees and discounts are not here: they are on the programme page (sidebar Postulaciones / Inicio, "
        "accordion Requisitos y Valores), read live.",
        "",
    ]
    for t, title in TYPE_TITLES.items():
        items = sorted((p for p in programas if p["type"] == t), key=lambda p: fold(p["name"]))
        if not items:
            continue
        lines += [f"## {title} ({len(items)})", ""]
        for p in items:
            facts = " · ".join(x for x in (p["faculty"], p["modalidad"], p["duration"]) if x)
            lines.append(
                f"- **{p['name']}** (`{p['slug']}`){': ' + facts if facts else ''}. {p['summary']}".rstrip()
            )
        lines.append("")
    (L2 / "postgrado-catalogo.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_site_map(pages: list[dict[str, Any]], site: dict[str, Any]) -> None:
    lines = [
        "# Mapa del sitio",
        "",
        f"Sources: the rendered pages, generated by build.py on {dt.date.today().isoformat()}.",
        "",
        "Every page Javier can open, by host, with its section headings as the page shows them (tab and "
        "accordion labels in brackets). Career and programme pages share a template; their own list is in "
        "the faculty topics and postgrado-catalogo.",
        "",
    ]
    for host in ("admision", "www", "postgrados"):
        lines += [f"## {HOSTS[host]}", ""]
        for p in pages:
            if p["host"] != host or p["kind"] in ("carrera", "programa"):
                continue
            heads = [h for h in p.get("headings", []) if not p.get("sections") or True]
            heads = list(dict.fromkeys(heads))[:18]
            tabs = [t["label"] for t in p.get("tabs") or [] if t.get("label")]
            acc = [
                a["label"]
                for a in p.get("accordions") or []
                if a.get("label") and "?" not in a["label"]
            ][:12]
            label = p.get("h1") or p["title"]
            line = f"- `{p['path']}` {label}"
            if p["kind"] == "template":
                line += f" (template, {p['template']})"
            if heads:
                line += ": " + " · ".join(heads)
            if tabs:
                line += " [tabs: " + " · ".join(dict.fromkeys(tabs)) + "]"
            if acc:
                line += " [accordion: " + " · ".join(dict.fromkeys(acc)) + "]"
            lines.append(line)
        lines.append("")
    (L2 / "site-map.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def dump(path: Path, data: Any, per_line: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if per_line and isinstance(data, list):
        body = (
            "[\n"
            + ",\n".join(json.dumps(d, ensure_ascii=False, separators=(",", ":")) for d in data)
            + "\n]\n"
        )
    else:
        body = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    path.write_text(body, encoding="utf-8")


def render() -> None:
    carreras = build_carreras()
    programas = build_programas(carreras)
    pages, raw_by_url = build_pages(carreras, programas)
    site = build_site(pages, raw_by_url, carreras)
    dump(L3 / "carreras.json", carreras)
    dump(L3 / "programas.json", programas)
    dump(L3 / "pages.json", pages, per_line=True)
    dump(L3 / "site.json", site)
    L2.mkdir(parents=True, exist_ok=True)
    write_faculty_files(carreras)
    write_programme_catalogue(programas)
    write_site_map(pages, site)
    print(
        f"carreras {len(carreras)} · programas {len(programas)} · pages {len(pages)} "
        f"({dict(Counter(p['kind'] for p in pages))}) · path collisions {site['path_collisions']}",
        file=sys.stderr,
    )
    unrendered = [c["slug"] for c in carreras if c.get("unrendered")]
    if unrendered:
        print(f"  careers not rendered: {unrendered}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser(
        "crawl", help="read the REST endpoints and render the pages, then render the layers"
    )
    c.add_argument(
        "--refresh", action="store_true", help="ignore the cache and fetch everything again"
    )
    c.add_argument("--offline", action="store_true", help="build from the cache only")
    sub.add_parser("render", help="build the layers from the cache")
    args = ap.parse_args()
    if args.cmd == "crawl" and not args.offline:
        crawl_rest(args.refresh)
        asyncio.run(render_pages(all_urls(), args.refresh))
    render()


if __name__ == "__main__":
    main()
