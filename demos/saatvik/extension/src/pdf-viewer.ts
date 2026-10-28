/**
 * The PDF viewer: Saatvik's datasheets, manuals and certificates, opened on
 * their own page beside the call, at the page Sunny is reading from, with the
 * line she quotes marked.
 *
 * Their site links each PDF to open in a new tab, which would take the person
 * away from the call and land them on page one. This is pdf.js in an overlay of
 * ours, in a shadow root, to the left of the widget: the page canvas, pdf.js's
 * own text layer over it, and our marks over that. The quote is found in the
 * text layer, not in the canvas, so it is matched on what the PDF says rather
 * than on how it is drawn. A page whose text is drawn as outlines (Saatvik's
 * module datasheets) has no text layer to search: for those the brain sends
 * the quote's boxes, read off the page image at build time, and the marks are
 * drawn from them.
 *
 * pdf.js's worker is bundled with the script and started from a Blob, so the
 * viewer needs nothing from any host but the PDF itself, which is Saatvik's.
 */

import { getDocument, type PDFDocumentProxy, PDFWorker, TextLayer } from "pdfjs-dist";
import workerSource from "pdf-worker-source";

import type { Rect } from "./widget";

/** A rectangle on a page, in fractions of the page from its top left. */
export interface PageBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface OpenRequest {
  url: string;
  title: string;
  page: number;
  quote: string | null;
  /** Where the quote is on an outlined page; when given, the page is not
   *  searched and these are marked. */
  boxes?: readonly PageBox[] | null;
}

export interface Viewer {
  /** Open a document at a page, the quote marked when it is found. Rejects
   *  with the reason when the document cannot be opened. */
  open(request: OpenRequest): Promise<void>;
  /** Close it; false when nothing was open. */
  close(): boolean;
}

export interface ViewerEvents {
  opened(url: string, page: number): void;
  closed(url: string, page: number): void;
  /** Where the viewer sits while open, or nothing when it is closed. */
  covering(rects: readonly Rect[]): void;
}

const NAVY = "#13306B";
const ORANGE = "#EA7124";
const SANS = `"DM Sans", system-ui, sans-serif`;
const DISPLAY = `Syne, "DM Sans", system-ui, sans-serif`;
/** The room the widget keeps on the right: its card, and a gap either side. */
const WIDGET_ROOM = 312;
const GAP = 16;
/** Below this viewport width the viewer takes the whole screen and the widget
 *  shrinks to its bubble beside it. */
const NARROW = 880;
/** How far either side of the asked page the quote is looked for, when it is
 *  not on that page. The brain's page numbers come from the same text, so a
 *  miss is usually a neighbour. */
const SEARCH_SPAN = 6;

const STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
.panel {
  position: fixed; top: ${GAP}px; bottom: ${GAP}px; left: ${GAP}px; right: ${WIDGET_ROOM}px;
  z-index: 2147483000; display: flex; flex-direction: column;
  background: #eef0f4; border-radius: 10px; overflow: hidden;
  box-shadow: 0 24px 60px rgba(10, 20, 45, 0.35);
  font-family: ${SANS}; color: #172033;
  animation: rise 220ms ease-out;
}
.panel.narrow { right: ${GAP}px; }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.bar {
  display: flex; align-items: center; gap: 14px; padding: 12px 14px 12px 18px;
  background: ${NAVY}; color: #fff;
}
.title { flex: 1; min-width: 0; font-family: ${DISPLAY}; font-weight: 600; font-size: 16px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.where { font-size: 12px; opacity: 0.8; white-space: nowrap; }
.full { color: #fff; font-size: 12px; text-decoration: none; border: 1px solid rgba(255,255,255,0.4);
  padding: 6px 10px; border-radius: 4px; white-space: nowrap; }
.full:hover { border-color: ${ORANGE}; }
.close { width: 32px; height: 32px; display: grid; place-items: center; padding: 0; cursor: pointer;
  background: transparent; border: 0; color: #fff; border-radius: 4px; }
.close:hover { background: rgba(255,255,255,0.12); }
.pages { position: relative; flex: 1; overflow: auto; padding: 18px; display: flex; flex-direction: column; align-items: center; gap: 14px; }
.page { position: relative; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.12); flex: none; }
.page canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.state { color: #5a6475; font-size: 13px; padding: 40px 0; }
.marks { position: absolute; inset: 0; pointer-events: none; z-index: 2; }
.mark { position: absolute; background: rgba(234, 113, 36, 0.32); border-bottom: 2px solid ${ORANGE};
  mix-blend-mode: multiply; border-radius: 2px; }

/* pdf.js's text layer, from its own pdf_viewer.css: transparent text laid
   exactly over the canvas, so a quote can be found and selected. */
.textLayer { position: absolute; text-align: initial; inset: 0; overflow: clip; opacity: 1; line-height: 1;
  -webkit-text-size-adjust: none; text-size-adjust: none; forced-color-adjust: none;
  transform-origin: 0 0; caret-color: CanvasText; z-index: 1; }
.textLayer :is(span, br) { color: transparent; position: absolute; white-space: pre; cursor: text; transform-origin: 0% 0%; }
.textLayer span.markedContent { top: 0; height: 0; }
.textLayer ::selection { background: rgba(19, 48, 107, 0.25); }
`;

let worker: PDFWorker | null = null;

/** pdf.js's worker, from the source bundled with this script. One for the
 *  page's life, handed to each document explicitly: a worker pdf.js made for
 *  a document is torn down with it, and the next document opened while that
 *  teardown runs fails ("the worker is being destroyed"). */
function startWorker(): PDFWorker {
  if (worker) return worker;
  const url = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }));
  // pdf.js types `port` as null (a JSDoc default); a Worker is what it takes.
  const port = new Worker(url, { type: "module" }) as unknown as null;
  worker = new PDFWorker({ port });
  return worker;
}

/** The text a quote is matched on: lower case, one space for any run of
 *  white space, and the PDF's ligatures and typographic marks undone. */
function normChar(c: string): string {
  return c
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‐-―−]/g, "-");
}

function normText(s: string): string {
  let out = "";
  for (const ch of s) {
    const c = normChar(ch);
    if (/\s/.test(c)) {
      if (out && !out.endsWith(" ")) out += " ";
    } else out += c;
  }
  return out.trim();
}

/** Where to look for a quote, best first: the whole of it, then its opening
 *  words, then its closing words — a quote the model tidied still lands. */
function attempts(quote: string): string[] {
  const words = normText(quote).split(" ").filter(Boolean);
  const out = [words.join(" ")];
  for (const n of [10, 6, 4]) {
    if (words.length > n) {
      out.push(words.slice(0, n).join(" "));
      out.push(words.slice(-n).join(" "));
    }
  }
  return out.filter((q) => q.length >= 6);
}

/** Does this page's text hold the quote? Read from the document, no render. */
async function pageHas(doc: PDFDocumentProxy, n: number, quote: string): Promise<boolean> {
  const page = await doc.getPage(n);
  const content = await page.getTextContent();
  const text = normText(content.items.map((i) => ("str" in i ? i.str : "")).join(" "));
  return attempts(quote).some((q) => text.includes(q));
}

/** The page the quote is on: the asked page if it is there, else the nearest
 *  within reach, else the asked page. */
async function pageFor(doc: PDFDocumentProxy, asked: number, quote: string | null): Promise<number> {
  if (!quote) return asked;
  if (await pageHas(doc, asked, quote).catch(() => false)) return asked;
  for (let d = 1; d <= SEARCH_SPAN; d++) {
    for (const n of [asked + d, asked - d]) {
      if (n < 1 || n > doc.numPages) continue;
      if (await pageHas(doc, n, quote).catch(() => false)) return n;
    }
  }
  return asked;
}

/** Mark the quote in a rendered page's text layer; false when it is not
 *  there. */
function markQuote(pageEl: HTMLElement, layer: HTMLElement, marks: HTMLElement, quote: string): boolean {
  const flat: string[] = [];
  const where: ({ node: Text; offset: number } | null)[] = [];
  const spans = [...layer.querySelectorAll("span")].filter((s) => !s.classList.contains("markedContent"));
  for (const span of spans) {
    const node = span.firstChild;
    if (!(node instanceof Text)) continue;
    // Between items: one space, unless the text already ends in one.
    if (flat.length && flat[flat.length - 1] !== " ") {
      flat.push(" ");
      where.push(null);
    }
    const text = node.data;
    for (let i = 0; i < text.length; i++) {
      const c = normChar(text[i]);
      if (/\s/.test(c)) {
        if (!flat.length || flat[flat.length - 1] === " ") continue;
        flat.push(" ");
        where.push({ node, offset: i });
      } else {
        for (const part of c) {
          flat.push(part);
          where.push({ node, offset: i });
        }
      }
    }
  }
  const haystack = flat.join("");
  for (const q of attempts(quote)) {
    const at = haystack.indexOf(q);
    if (at < 0) continue;
    let s = at;
    let e = at + q.length - 1;
    while (s < e && !where[s]) s++;
    while (e > s && !where[e]) e--;
    const start = where[s];
    const end = where[e];
    if (!start || !end) continue;
    const range = document.createRange();
    range.setStart(start.node, start.offset);
    range.setEnd(end.node, Math.min(end.offset + 1, end.node.length));
    const box = pageEl.getBoundingClientRect();
    marks.replaceChildren();
    for (const r of range.getClientRects()) {
      if (r.width < 1 || r.height < 1) continue;
      const m = document.createElement("div");
      m.className = "mark";
      Object.assign(m.style, {
        left: `${r.left - box.left - 1}px`,
        top: `${r.top - box.top - 1}px`,
        width: `${r.width + 2}px`,
        height: `${r.height + 2}px`,
      });
      marks.appendChild(m);
    }
    return marks.childElementCount > 0;
  }
  return false;
}

/** Mark boxes given in fractions of the page, so they hold at any scale. */
function markBoxes(marks: HTMLElement, boxes: readonly PageBox[]): boolean {
  marks.replaceChildren();
  for (const b of boxes) {
    const m = document.createElement("div");
    m.className = "mark";
    Object.assign(m.style, {
      left: `${b.x * 100}%`,
      top: `${b.y * 100}%`,
      width: `${b.w * 100}%`,
      height: `${b.h * 100}%`,
    });
    marks.appendChild(m);
  }
  return marks.childElementCount > 0;
}

/** A URL of Saatvik's on whichever of their hosts the page is on, so the PDF
 *  is fetched same-origin. */
function onThisHost(url: string): string {
  const u = new URL(url, location.origin);
  if (u.hostname.endsWith("saatvikgroup.com")) return location.origin + u.pathname + u.search;
  return u.href;
}

export function mountViewer(events: ViewerEvents): Viewer {
  let host: HTMLElement | null = null;
  let current: { url: string; page: () => number; stop: () => void } | null = null;
  /** Each open bumps this, so a slow load overtaken by the next one stops. */
  let generation = 0;

  function close(): boolean {
    generation++;
    if (!host || !current) return false;
    const { url, page, stop } = current;
    const last = page();
    stop();
    host.remove();
    host = null;
    current = null;
    events.covering([]);
    events.closed(url, last);
    return true;
  }

  async function open(req: OpenRequest): Promise<void> {
    if (current) close();
    const mine = ++generation;
    startWorker();
    const url = onThisHost(req.url);

    host = document.createElement("div");
    host.setAttribute("data-voqalize", "pdf-viewer");
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>${STYLES}</style>
      <div class="panel" role="dialog" aria-label="Document">
        <div class="bar">
          <span class="title"></span>
          <span class="where"></span>
          <a class="full" target="_blank" rel="noopener">Open full PDF ↗</a>
          <button class="close" type="button" aria-label="Close document">
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.6"/></svg>
          </button>
        </div>
        <div class="pages"><div class="state">Opening…</div></div>
      </div>
    `;
    document.body.appendChild(host);
    const $ = <T extends Element>(sel: string) => shadow.querySelector<T>(sel)!;
    const panel = $<HTMLElement>(".panel");
    const pagesEl = $<HTMLElement>(".pages");
    const whereEl = $<HTMLElement>(".where");
    const full = $<HTMLAnchorElement>(".full");
    $<HTMLElement>(".title").textContent = req.title || url.split("/").pop() || "Document";
    full.href = `${url}#page=${req.page}`;

    const layout = () => {
      panel.classList.toggle("narrow", window.innerWidth < NARROW);
      const r = panel.getBoundingClientRect();
      events.covering(
        window.innerWidth < NARROW ? [{ left: r.left, top: r.top, right: r.right, bottom: r.bottom }] : [],
      );
    };
    layout();
    window.addEventListener("resize", layout);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    $<HTMLButtonElement>(".close").addEventListener("click", () => close());

    let seen = Math.max(1, req.page | 0);
    const observers: IntersectionObserver[] = [];
    let doc: PDFDocumentProxy | null = null;
    current = {
      url: req.url,
      page: () => seen,
      stop: () => {
        window.removeEventListener("resize", layout);
        document.removeEventListener("keydown", onKey);
        observers.forEach((o) => o.disconnect());
        void doc?.destroy();
      },
    };

    try {
      doc = await getDocument({ url, isEvalSupported: false, worker: startWorker() }).promise;
    } catch (error) {
      if (mine === generation) close();
      throw new Error(`could not open ${req.url}: ${error instanceof Error ? error.message : String(error)}`);
    }
    if (mine !== generation) return void doc.destroy();

    const total = doc.numPages;
    const asked = Math.min(Math.max(1, req.page | 0), total);
    const boxed = req.boxes?.length ? req.boxes : null;
    const target = boxed ? asked : await pageFor(doc, asked, req.quote);
    if (mine !== generation) return;
    seen = target;
    full.href = `${url}#page=${target}`;
    whereEl.textContent = `Page ${target} of ${total}`;

    // Every page gets a box of the right size at once, so the scroll position
    // is true; a page is drawn when it comes near the view.
    const first = await doc.getPage(1);
    const unscaled = first.getViewport({ scale: 1 });
    const scale = Math.min((pagesEl.clientWidth - 36) / unscaled.width, 2.2);
    pagesEl.replaceChildren();
    const boxes: HTMLElement[] = [];
    for (let n = 1; n <= total; n++) {
      const box = document.createElement("div");
      box.className = "page";
      box.dataset.n = String(n);
      box.style.width = `${Math.floor(unscaled.width * scale)}px`;
      box.style.height = `${Math.floor(unscaled.height * scale)}px`;
      pagesEl.appendChild(box);
      boxes.push(box);
    }

    const drawn = new Map<number, Promise<HTMLElement | null>>();
    const draw = (n: number): Promise<HTMLElement | null> => {
      const had = drawn.get(n);
      if (had) return had;
      const job = (async () => {
        const page = await doc!.getPage(n);
        const viewport = page.getViewport({ scale });
        const box = boxes[n - 1];
        box.style.width = `${Math.floor(viewport.width)}px`;
        box.style.height = `${Math.floor(viewport.height)}px`;
        box.style.setProperty("--scale-factor", String(viewport.scale));
        const ratio = window.devicePixelRatio || 1;
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        box.appendChild(canvas);
        await page.render({
          canvasContext: canvas.getContext("2d")!,
          viewport,
          transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
        }).promise;
        const layer = document.createElement("div");
        layer.className = "textLayer";
        box.appendChild(layer);
        await new TextLayer({ textContentSource: await page.getTextContent(), container: layer, viewport }).render();
        const marks = document.createElement("div");
        marks.className = "marks";
        box.appendChild(marks);
        return layer;
      })().catch((error) => {
        console.warn("voqalize: could not draw page", n, error);
        return null;
      });
      drawn.set(n, job);
      return job;
    };

    const near = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) void draw(Number((e.target as HTMLElement).dataset.n));
      },
      { root: pagesEl, rootMargin: "600px 0px" },
    );
    observers.push(near);
    boxes.forEach((b) => near.observe(b));

    // The page in view is the one whose top is nearest the top of the pane.
    const onScroll = () => {
      const top = pagesEl.getBoundingClientRect().top;
      let best = seen;
      let bestD = Infinity;
      for (const b of boxes) {
        const d = Math.abs(b.getBoundingClientRect().top - top - 18);
        if (d < bestD) {
          bestD = d;
          best = Number(b.dataset.n);
        }
      }
      if (best !== seen) {
        seen = best;
        whereEl.textContent = `Page ${seen} of ${total}`;
      }
    };
    pagesEl.addEventListener("scroll", onScroll, { passive: true });

    const layer = await draw(target);
    if (mine !== generation) return;
    const box = boxes[target - 1];
    let markTop: number | null = null;
    const marks = box.querySelector<HTMLElement>(".marks");
    if (marks && boxed) {
      if (markBoxes(marks, boxed)) markTop = (marks.firstElementChild as HTMLElement).offsetTop;
    } else if (marks && layer && req.quote) {
      if (markQuote(box, layer, marks, req.quote)) {
        const m = marks.firstElementChild as HTMLElement;
        markTop = m.offsetTop;
      } else {
        console.warn("voqalize: the quote is not on page", target, "of", req.url, "—", req.quote);
      }
    }
    // The quote a third of the way down the pane, or else the top of its page.
    pagesEl.scrollTop = box.offsetTop + (markTop !== null ? Math.max(markTop - pagesEl.clientHeight / 3, 0) : -18);
    onScroll();
    whereEl.textContent = `Page ${target} of ${total}`;
    events.opened(req.url, target);
  }

  return { open, close };
}
