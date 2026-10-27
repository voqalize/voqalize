/**
 * The brain's catalogue of places on www.unosalud.cl, by key:
 * `demos/unosalud/backend/knowledge/L3/anchors.json`, written and checked by
 * the brain's `knowledge/build.py` against the saved pages, and bundled into
 * the extension (`build.mjs`). The brain names a place by its key
 * (`navigate.anchor`, `cue.anchor`, `show_section.anchor`, `open_faq.faq`);
 * the page finds it by the key's selector, and by its heading words when the
 * selector matches nothing or more than one thing (the theme repeats ids:
 * `#features` five times on a page).
 *
 *   {"_meta": {…}, "<key>": {"path": "/especialidades/ortodoncia/",
 *    "selector": "…", "text": "heading words or empty",
 *    "label": {"es": "…", "en": "…"}, "faq": "<optional>"}}
 *
 * `path` "/clinicas/*\/" is any clinic's page. `faq` is a Bootstrap FAQ's
 * number (`#heading-faq-<faq>` → `#collapse-faq-<faq>`) or an Elementor
 * accordion item's `<details>` id.
 */

import raw from "virtual:unosalud-anchors";

export interface Row {
  key: string;
  path: string;
  selector: string;
  text: string;
  label: string;
  faq: string;
}

const str = (v: unknown) => (typeof v === "string" ? v : "");

/** The site's own path shape: lower case, with its trailing slash. */
export const canonical = (p: string) => {
  const path = (p || "/").toLowerCase().replace(/\/{2,}/g, "/").replace(/^\/+|\/+$/g, "");
  return path ? `/${path}/` : "/";
};

function rowsOf(data: Record<string, unknown>): Row[] {
  const out: Row[] = [];
  for (const [key, value] of Object.entries(data ?? {})) {
    if (key.startsWith("_") || !value || typeof value !== "object") continue;
    const v = value as Record<string, unknown>;
    const label = v.label && typeof v.label === "object" ? str((v.label as Record<string, unknown>).es) : str(v.label);
    out.push({
      key,
      path: v.path === "/clinicas/*/" ? "/clinicas/*/" : canonical(str(v.path)),
      selector: str(v.selector),
      text: str(v.text),
      label,
      faq: str(v.faq),
    });
  }
  return out;
}

export const ROWS: readonly Row[] = rowsOf(raw);
const BY_KEY = new Map(ROWS.map((r) => [r.key, r]));

export const row = (key: string): Row | null => BY_KEY.get((key ?? "").trim()) ?? null;

/** Whether `r` is a place of the page at `path`. */
export function onPage(r: Row, path: string): boolean {
  const here = canonical(path);
  if (r.path === "/clinicas/*/") return /^\/clinicas\/[^/]+\/$/.test(here);
  return r.path === here;
}

/** The catalogue's places for the page at `path`. */
export const rowsFor = (path: string): Row[] => ROWS.filter((r) => onPage(r, path));
