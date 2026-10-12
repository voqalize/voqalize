/**
 * What is on the visitor's screen, for Tanvi: so "this" means what they are looking at, and she
 * says "below" on a phone where a computer would have it on the right.
 *
 * A snapshot names the device, how the page sits around her (her column beside it, her tile over
 * it, or her alone in the middle), what is open, and what is in view: every named block
 * (`data-part`, written to voice.json by `pnpm voice:parts`) and every content target
 * (`data-voice` on something that is not a button), grouped into rows from the top of the screen
 * down, left to right inside a row. Also the block they are reading (the one across the reading
 * line, 40% down), the heading above it, how far down they are, and the tab and animation step
 * showing. It works the same in a section beside her and in a page in the frame, since every
 * position is measured against what is actually visible.
 *
 * `watchViewing` measures twice a second and reports once the screen has held still for a
 * moment and differs from what was last reported, so a long scroll is one report where it ends.
 */
import type { Viewing } from './actions.gen';
import { pageAt } from './targets';

const POLL_MS = 500;
const READ_LINE = 0.4;

type Box = { top: number; bottom: number; left: number; right: number };

const narrow = () => matchMedia('(max-width: 860px)').matches;

function device(): Viewing['device'] {
  const w = innerWidth;
  if (w <= 600) return 'phone';
  if (w <= 1100 && matchMedia('(pointer: coarse)').matches) return 'tablet';
  return 'desktop';
}

const clip = (a: Box, b: Box): Box => ({ top: Math.max(a.top, b.top), bottom: Math.min(a.bottom, b.bottom), left: Math.max(a.left, b.left), right: Math.min(a.right, b.right) });

/** Every named thing in `root` that is on screen inside `box`, innermost only, with its id. */
function inView(root: ParentNode, box: Box, idOf: (el: HTMLElement) => string | null) {
  const seen: Array<{ el: HTMLElement; id: string; r: Box }> = [];
  for (const el of root.querySelectorAll<HTMLElement>('[data-part], [data-voice]')) {
    if (el.matches('button, [role="tab"], [role="tablist"] *')) continue;
    const id = idOf(el);
    if (!id) continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    const c = clip(rect, box);
    const h = c.bottom - c.top, w = c.right - c.left;
    // Enough of it shows to be read: most of a small thing, or a good slice of a big one.
    if (w <= 8 || h < Math.min(48, rect.height * 0.5)) continue;
    seen.push({ el, id, r: rect });
  }
  return seen.filter((x) => !seen.some((o) => o !== x && x.el.contains(o.el)));
}

/** Top to bottom, a row being the things whose middles share a band; left to right in a row. */
function rows(items: Array<{ id: string; r: Box }>): string[][] {
  const sorted = [...items].sort((a, b) => a.r.top - b.r.top);
  const out: Array<{ top: number; bottom: number; xs: Array<{ id: string; left: number }> }> = [];
  for (const it of sorted) {
    const mid = (it.r.top + it.r.bottom) / 2;
    const row = out.find((r) => mid > r.top && mid < r.bottom && it.r.top < r.bottom - 8);
    if (row) { row.xs.push({ id: it.id, left: it.r.left }); row.bottom = Math.max(row.bottom, it.r.bottom); }
    else out.push({ top: it.r.top, bottom: it.r.bottom, xs: [{ id: it.id, left: it.r.left }] });
  }
  return out.map((r) => r.xs.sort((a, b) => a.left - b.left).map((x) => x.id));
}

function reading(items: Array<{ id: string; r: Box }>, box: Box): string | null {
  const y = box.top + (box.bottom - box.top) * READ_LINE;
  const across = items.filter((x) => x.r.top <= y && x.r.bottom >= y);
  const pool = across.length ? across : items;
  const area = (x: { r: Box }) => { const c = clip(x.r, box); return Math.max(0, c.bottom - c.top) * Math.max(0, c.right - c.left); };
  return pool.sort((a, b) => area(b) - area(a))[0]?.id ?? null;
}

function headingAbove(root: ParentNode, box: Box): string | null {
  const y = box.top + (box.bottom - box.top) * READ_LINE;
  let last: string | null = null;
  for (const h of root.querySelectorAll<HTMLElement>('h1, h2, h3')) {
    const r = h.getBoundingClientRect();
    if (!r.height || h.closest('[hidden], .visually-hidden')) continue;
    if (r.top > y) break;
    last = h.textContent?.replace(/\s+/g, ' ').trim().slice(0, 120) || last;
  }
  return last;
}

/** Tabs selected, switches pressed and animation steps playing, among things on screen. */
function showing(root: ParentNode, box: Box): string[] {
  const out = new Set<string>();
  root.querySelectorAll<HTMLElement>('[role="tab"][aria-selected="true"][data-voice], [aria-pressed="true"][data-voice]').forEach((el) => out.add(el.dataset.voice!));
  root.querySelectorAll<HTMLElement>('[data-loop]').forEach((loop) => {
    const r = loop.getBoundingClientRect();
    if (!r.height || r.bottom < box.top || r.top > box.bottom) return;
    let n = 0;
    while (loop.classList.contains(`is-s${n + 1}`)) n++;
    const step = loop.querySelector<HTMLElement>(`[data-goto-step="${n}"][data-voice]`);
    if (step) out.add(step.dataset.voice!);
  });
  return [...out];
}

function progress(rootRect: Box, box: Box): number {
  const travel = rootRect.bottom - rootRect.top - (box.bottom - box.top);
  if (travel <= 4) return 0;
  return Math.round(Math.min(1, Math.max(0, (box.top - rootRect.top) / travel)) * 100);
}

export interface ViewSource {
  /** The open section's id, 'page' for a page in the frame, or null with Tanvi alone. */
  active: () => string | null;
  frame: HTMLIFrameElement;
}

/** What the visitor sees right now. */
export function snapshot(src: ViewSource): Viewing {
  const active = src.active();
  const base = { device: device(), layout: (!active ? 'centre' : narrow() ? 'tile' : 'beside') as Viewing['layout'] };
  if (!active) return base;
  const nav = document.querySelector('.top')?.getBoundingClientRect().bottom ?? 0;
  const screen: Box = { top: nav, bottom: innerHeight, left: 0, right: innerWidth };

  if (active === 'page') {
    const doc = src.frame.contentDocument;
    const win = src.frame.contentWindow;
    // A page still loading has no document yet (or is about:blank): nothing to report until it lands.
    if (!doc?.documentElement || !doc.body || !win || win.location.href === 'about:blank') return base;
    const fr = src.frame.getBoundingClientRect();
    // Measured inside the frame: its own viewport, cut to the part of it the visitor can see.
    const seen = clip({ top: 0, bottom: win.innerHeight, left: 0, right: win.innerWidth }, { top: screen.top - fr.top, bottom: screen.bottom - fr.top, left: -fr.left, right: screen.right - fr.left });
    const page = pageAt(win.location.pathname);
    const items = page ? inView(doc, seen, (el) => (el.dataset.part ? `${page.id}.${el.dataset.part}` : null)) : [];
    return {
      ...base,
      page: page?.id ?? null,
      path: page ? null : win.location.pathname,
      title: page ? null : doc.title.replace(/\s*[|·].*$/, '').trim() || null,
      rows: rows(items),
      focus: reading(items, seen),
      heading: headingAbove(doc, seen),
      progress: progress({ top: -win.scrollY, bottom: doc.documentElement.scrollHeight - win.scrollY, left: 0, right: 0 }, { top: 0, bottom: win.innerHeight, left: 0, right: 0 }),
      showing: showing(doc, seen),
    };
  }

  const sec = document.querySelector<HTMLElement>(`[data-section="${active}"]`);
  if (!sec) return base;
  const panel = document.getElementById('panel');
  const seen = panel ? clip(screen, panel.getBoundingClientRect()) : screen;
  const idOf = (el: HTMLElement) => el.dataset.voice ?? (el.dataset.part ? `${active}.${el.dataset.part}` : null);
  const items = inView(sec, seen, idOf);
  return {
    ...base,
    section: active,
    rows: rows(items),
    focus: reading(items, seen),
    heading: headingAbove(sec, seen),
    progress: progress(sec.getBoundingClientRect(), seen),
    showing: showing(sec, seen),
  };
}

/** Report the screen to `send` each time it settles on something new. Returns a stop function. */
export function watchViewing(src: ViewSource, send: (v: Viewing) => void): () => void {
  let last = '';
  let pending = '';
  const tick = () => {
    if (document.hidden) return;
    let v: Viewing;
    try { v = snapshot(src); } catch { return; }
    const key = JSON.stringify(v);
    // Held still for one tick, and new: report it.
    if (key === pending && key !== last) { last = key; send(v); }
    pending = key;
  };
  tick();
  const id = window.setInterval(tick, POLL_MS);
  return () => window.clearInterval(id);
}
