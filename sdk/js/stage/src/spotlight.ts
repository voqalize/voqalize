/**
 * The spotlight: the ring drawn around what the agent is pointing at.
 *
 * Every visible move rings its target before it acts, and the ring stays up
 * long enough to be seen. The two are separate on purpose: `ring()` holds the
 * move only for a short beat (`beatMs`), so a fast reply never leaves the
 * screen behind the voice, while the ring itself stays visible for at least
 * `dwellMs` (a `clear()` inside it waits it out), unless the next ring
 * replaces it. The ring is the page runtime's own drawing, never
 * the site's: one host element on `<html>` (outside `<body>`, whose zoom or
 * transform a site may set), a shadow root under it so no rule of the site's
 * reaches in and none of ours reaches out, and a box per ring laid in document
 * coordinates over its targets. It follows them every animation frame while
 * it is up, so a carousel that slides, an image that loads late, a scroll or a
 * resize carries the ring along. The targets' own styles are never touched.
 *
 * A group ring is one box around several elements (a row and its price);
 * `separate` draws one box per element instead (the rows a form filled). A
 * target inside a same-origin frame is ringed where the frame shows it. An
 * optional label is announced politely to screen readers. With reduced motion
 * asked for, the ring appears without its pulse or fade.
 */

export interface SpotlightTheme {
  /** The ring's colour. */
  color: string;
  /** Border width in px (2). */
  width?: number;
  /** Corner radius in px (10). */
  radius?: number;
  /** The pulse's colour (the ring's colour at 45 %), or "none". */
  glow?: string;
  /** How long `ring()` holds the move before it acts (450 ms): enough to see
   *  where it is about to act, never long enough to fall behind the voice. */
  beatMs?: number;
  /** The least a ring stays visible, unless the next ring replaces it
   *  (1500 ms). A display guarantee: nothing waits for it. */
  dwellMs?: number;
  /** How long a ring stays up when nothing replaces it (5500 ms). */
  holdMs?: number;
  /** Space between the targets and the ring, in px (6). */
  pad?: number;
}

interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Ring {
  el: HTMLElement;
  targets: Element[];
}

export interface RingOptions {
  /** Announced politely to screen readers. */
  label?: string;
  /** How long `ring()` holds the move (the theme's `beatMs` by default). */
  beatMs?: number;
  /** The least this ring stays visible (the theme's `dwellMs` by default). */
  dwellMs?: number;
  /** One box per element, rather than one around them all. */
  separate?: boolean;
}

const Z = "2147483000";

export class Spotlight {
  private host: HTMLElement | null = null;
  private layer: HTMLElement | null = null;
  private live: HTMLElement | null = null;
  private rings: Ring[] = [];
  private frame = 0;
  private holdTimer: ReturnType<typeof setTimeout> | null = null;
  private clearTimer: ReturnType<typeof setTimeout> | null = null;
  /** When the rings up now must stay until (epoch ms). */
  private until = 0;
  private readonly theme: Required<SpotlightTheme>;

  constructor(
    theme: SpotlightTheme,
    private readonly doc: Document = document,
  ) {
    this.theme = {
      width: 2,
      radius: 10,
      glow: "",
      beatMs: 450,
      dwellMs: 1500,
      holdMs: 5500,
      pad: 6,
      ...theme,
    };
  }

  /** The element the rings are drawn in (for tests and for a site that must
   *  keep its own overlays clear of it). */
  get element(): HTMLElement | null {
    return this.host;
  }

  /** The least a ring stays visible, by default. */
  get dwellMs(): number {
    return this.theme.dwellMs;
  }

  /** How long `ring()` holds a move, by default. */
  get beatMs(): number {
    return this.theme.beatMs;
  }

  /**
   * Ring `target` (one element, or several: one box round them all, or one
   * each with `separate`), replacing any ring up now. Resolves after the beat
   * (`beatMs`), so the move acts with the ring already showing; the ring
   * itself stays at least `dwellMs` (a `clear()` sooner waits it out), and
   * then until the next ring, `clear()`, or `holdMs`. Nothing to ring
   * (nothing laid out) resolves at once.
   */
  async ring(target: Element | Element[], opts: RingOptions = {}): Promise<void> {
    this.takeDown();
    const targets = (Array.isArray(target) ? target : [target]).filter(Boolean);
    const groups = opts.separate ? targets.filter((t) => this.boxOf([t])).map((t) => [t]) : [targets];
    if (!targets.length || !groups.length || !this.boxOf(targets)) return;
    this.mount();
    for (const group of groups) {
      const el = this.doc.createElement("div");
      el.className = "ring";
      el.setAttribute("part", "ring");
      this.layer!.appendChild(el);
      this.rings.push({ el, targets: group });
    }
    this.follow();
    const show = () => this.rings.forEach((r) => r.el.classList.add("on"));
    if (this.reduced()) show();
    else this.view()?.requestAnimationFrame(show);
    if (opts.label && this.live) {
      // Re-set so the same words are announced again.
      this.live.textContent = "";
      this.live.textContent = opts.label;
    }
    const dwell = opts.dwellMs ?? this.theme.dwellMs;
    this.until = Date.now() + dwell;
    this.holdTimer = setTimeout(() => this.takeDown(), Math.max(this.theme.holdMs, dwell));
    const beat = opts.beatMs ?? this.theme.beatMs;
    if (beat > 0) await new Promise<void>((r) => setTimeout(r, beat));
  }

  /** Take every ring down: now, or once the newest has been up its dwell. */
  clear(): void {
    const left = this.until - Date.now();
    if (!this.rings.length || left <= 0) return this.takeDown();
    if (this.clearTimer) return;
    this.clearTimer = setTimeout(() => this.takeDown(), left);
  }

  /** Take every ring down now, dwell or not (the call ended, the page goes). */
  private takeDown(): void {
    if (this.holdTimer) clearTimeout(this.holdTimer);
    if (this.clearTimer) clearTimeout(this.clearTimer);
    this.holdTimer = this.clearTimer = null;
    if (this.frame) this.view()?.cancelAnimationFrame(this.frame);
    this.frame = 0;
    for (const r of this.rings) r.el.remove();
    this.rings = [];
    this.until = 0;
  }

  /** Remove the overlay from the page altogether. */
  destroy(): void {
    this.takeDown();
    this.host?.remove();
    this.host = this.layer = this.live = null;
  }

  private view(): (Window & typeof globalThis) | null {
    return this.doc.defaultView as (Window & typeof globalThis) | null;
  }

  private reduced(): boolean {
    try {
      return Boolean(this.view()?.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
    } catch {
      return false;
    }
  }

  private mount(): void {
    if (this.host?.isConnected) return;
    const host = this.doc.createElement("div");
    host.setAttribute("data-voqalize", "spotlight");
    // Inline, so no rule of the page's reaches it: a zero-size box at the
    // document's origin that takes no pointer events and lets its rings
    // overflow it.
    host.style.cssText =
      `position:absolute;left:0;top:0;width:0;height:0;margin:0;padding:0;border:0;overflow:visible;` +
      `pointer-events:none;z-index:${Z};contain:style`;
    const shadow = host.attachShadow({ mode: "open" });
    const { color, width, radius } = this.theme;
    const glow = this.theme.glow || `color-mix(in srgb, ${color} 45%, transparent)`;
    const pulse = this.theme.glow === "none" ? "none" : "voqalize-ring 1.4s ease-in-out 3";
    shadow.innerHTML = `
      <style>
        :host { all: initial; }
        .ring {
          position: absolute; left: 0; top: 0; box-sizing: border-box;
          border: ${width}px solid ${color}; border-radius: ${radius}px;
          pointer-events: none; opacity: 0; transition: opacity 300ms ease;
        }
        .ring.on { opacity: 1; animation: ${pulse}; }
        .ring.gone { opacity: 0; }
        @keyframes voqalize-ring {
          0%, 100% { box-shadow: 0 0 0 0 ${glow}; }
          50% { box-shadow: 0 0 0 9px transparent; }
        }
        @media (prefers-reduced-motion: reduce) {
          .ring, .ring.on { transition: none; animation: none; }
        }
        .live { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
      </style>
      <div class="layer"></div>
      <div class="live" role="status" aria-live="polite"></div>
    `;
    this.layer = shadow.querySelector<HTMLElement>(".layer");
    this.live = shadow.querySelector<HTMLElement>(".live");
    (this.doc.documentElement ?? this.doc.body).appendChild(host);
    this.host = host;
  }

  private boxOf(targets: Element[]): Box | null {
    const rs = targets.map((el) => rectIn(el, this.view())).filter((r): r is Box => r !== null);
    if (!rs.length) return null;
    return {
      left: Math.min(...rs.map((r) => r.left)),
      top: Math.min(...rs.map((r) => r.top)),
      right: Math.max(...rs.map((r) => r.right)),
      bottom: Math.max(...rs.map((r) => r.bottom)),
    };
  }

  /** Lay each ring over its targets, in document coordinates, now and every
   *  frame while any is up. */
  private follow = (): void => {
    const view = this.view();
    const sx = view?.scrollX ?? 0;
    const sy = view?.scrollY ?? 0;
    const vw = this.doc.documentElement?.clientWidth || view?.innerWidth || 0;
    const pad = this.theme.pad;
    for (const ring of this.rings) {
      const b = this.boxOf(ring.targets);
      ring.el.classList.toggle("gone", !b);
      if (!b) continue;
      // A full-bleed block is ringed inside the screen's edges, where it shows.
      const left = vw ? Math.max(b.left - pad, 3) : b.left - pad;
      const right = vw ? Math.min(b.right + pad, vw - 3) : b.right + pad;
      ring.el.style.transform = `translate(${Math.round(left + sx)}px, ${Math.round(b.top - pad + sy)}px)`;
      ring.el.style.width = `${Math.max(right - left, 0)}px`;
      ring.el.style.height = `${b.bottom - b.top + 2 * pad}px`;
    }
    if (this.rings.length && view) this.frame = view.requestAnimationFrame(this.follow);
  };
}

/** `el`'s box in the top window's viewport, also for an element inside a
 *  same-origin frame; `null` when it is not laid out. */
function rectIn(el: Element, top: Window | null): Box | null {
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  let { left, top: t, right, bottom } = r;
  for (let win: Window | null = el.ownerDocument.defaultView; win && win !== top && win.frameElement; win = win.parent) {
    const frame = win.frameElement as HTMLElement;
    const f = frame.getBoundingClientRect();
    const dx = f.left + frame.clientLeft;
    const dy = f.top + frame.clientTop;
    left += dx;
    right += dx;
    t += dy;
    bottom += dy;
  }
  return { left, top: t, right, bottom };
}
