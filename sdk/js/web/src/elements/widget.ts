/**
 * `<vql-widget>`: the Voqalize widget in one tag.
 *
 *   <vql-widget agent="agt_…" key="pk_…" name="Emily" anchor="bottom-left"></vql-widget>
 *
 * or with the whole configuration as a property (or as JSON in `config`):
 *
 *   widget.config = { placement: { anchor: "bottom-left" }, theme: { brand: "#0f766e" } };
 *
 * A visitor moves through these views:
 *
 * - `closed`: the launcher (`pill`, `face`, `card`, or `none`, where the
 *   page opens the widget with its own button);
 * - `open`: the call, as a `card`, a full-stage `hero`, or on a phone a
 *   bottom `sheet`;
 * - `collapsed`: a `bubble` with the live face, or a `pill`;
 * - `ended`: the end card, with the reason and "Call again".
 *
 * The face is one element for the whole call; it is resized between the
 * forms, never re-mounted.
 *
 * Methods: `open()`, `collapse()`, `close()`, `end()`, `place(anchor | {x, y})`
 * and `setMuted(muted)`.
 *
 * Events (all bubble and are composed): `vql-view` (`{ view, form }`),
 * `vql-open`, `vql-collapse`, `vql-close`, `vql-end` (`{ reason }`),
 * `vql-mic` (`{ state, hint }`), `vql-agent` (`{ state }`), `vql-place`
 * (`{ anchor, point, free }`) and, from the mic pill, `vql-pill-action`
 * (`{ kind }`), after the widget has acted on it.
 *
 * Slots: `side`, `controls-start`, `controls-end`, `launcher`, `notice`, `end`.
 *
 * Parts: `dock`, `card`, `stage`, `frame`, `face`, `status`, `grip`,
 * `expand`, `badge`, `body`, `controls`, `mic`, `devices`, `minimise`,
 * `end`, `captions`, `hint`, `notice`, `side`, `end-card`, `end-reason`,
 * `again`, `close`, `launcher`, `coach`, `mic-pill`, `sheet-handle`. The form is also a
 * part name on the card (`card sheet`, `card bubble`, …), so a page can
 * style one form only.
 */

import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import { parseWidgetConfig } from "../config/parse.js";
import { mergeInput } from "../config/site-settings.js";
import type { Anchor, Warn, WidgetConfig, WidgetConfigInput } from "../config/types.js";
import type { CaptionsController } from "../controllers/captions.js";
import { type MicPillKind, micPillOf } from "../controllers/mic-pill.js";
import type { MicSnapshot } from "../controllers/mic.js";
import { ANCHORS, PlacementController, type PlacementSnapshot, type Rect } from "../controllers/placement.js";
import type { ReadableStore } from "../controllers/store.js";
import type { SessionEvents, SessionSnapshot, SessionSource } from "../session/adapter.js";
import { type BrowserKind, detectBrowser } from "./browser.js";
import { themeColours } from "./colour.js";
import { cssProps } from "./css-props.js";
import { expandIcon, gripIcon, micOffIcon, minimiseIcon } from "./icons.js";
import { loadElement } from "./lazy.js";
import type { MicPillActionDetail } from "./mic-pill.js";
import { themeStyles } from "./theme.js";
import { type Translate, pageLanguage, translator } from "./words.js";

// ------------------------------------------------------------------- types

export type WidgetView = "closed" | "open" | "collapsed" | "ended";
export type WidgetForm = "pill" | "face" | "card" | "none" | "hero" | "sheet" | "bubble";

/** What the widget needs of a session. The package's internal `WidgetSession` is one. */
export interface WidgetSessionLike extends ReadableStore<SessionSnapshot> {
  readonly mic: ReadableStore<MicSnapshot>;
  on<K extends keyof SessionEvents>(event: K, listener: SessionEvents[K]): () => void;
  connect(source: SessionSource): Promise<void>;
  disconnect(): Promise<void>;
  setMuted(muted: boolean): void;
  /** Ask for a blocked mic again, where the browser would ask the visitor. */
  askForMic?(): void;
  selectMic(id: string): void;
  selectSpeaker(id: string): void;
  /** The client the avatar follows, where there is one. */
  readonly rawClient?: unknown;
  dispose?(): void;
}

/** Attributes that set one field of the configuration, and the field. */
export const CONFIG_ATTRIBUTES: Readonly<Record<string, string>> = {
  agent: "agent",
  key: "key",
  name: "name",
  character: "avatar.character",
  "avatar-shape": "avatar.shape",
  anchor: "placement.anchor",
  placement: "placement.mode",
  move: "placement.move",
  launcher: "launcher.style",
  label: "launcher.label",
  tagline: "launcher.tagline",
  "open-style": "open.style",
  size: "open.size",
  collapsed: "collapsed.style",
  captions: "captions.mode",
  "mic-level": "mic.level",
  "instant-start": "mic.instantStart",
  brand: "theme.brand",
  scheme: "theme.scheme",
};

function attributeValue(raw: string): unknown {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return raw;
}

/** The configuration the attributes describe, as an input to merge over the `config` property. */
export function inputFromAttributes(read: (name: string) => string | null): WidgetConfigInput {
  const out: Record<string, unknown> = {};
  for (const [attr, path] of Object.entries(CONFIG_ATTRIBUTES)) {
    const raw = read(attr);
    if (raw === null) continue;
    const keys = path.split(".");
    let node = out;
    for (const k of keys.slice(0, -1)) {
      node[k] = (node[k] as Record<string, unknown> | undefined) ?? {};
      node = node[k] as Record<string, unknown>;
    }
    node[keys.at(-1) as string] = attributeValue(raw);
  }
  // `avatar="false"`: a voice-only widget.
  if (read("avatar") === "false") out.avatar = false;
  return out as WidgetConfigInput;
}

const ROWS = ["top", "middle", "bottom"] as const;
const COLUMNS = ["left", "center", "right"] as const;

/** The anchor an arrow key moves to from `anchor`, or `anchor` itself at an edge. */
export function neighbourAnchor(anchor: Anchor, key: string): Anchor {
  const [v, h] = anchor.split("-") as [string, string];
  let row = ROWS.indexOf(v as (typeof ROWS)[number]);
  let col = COLUMNS.indexOf(h as (typeof COLUMNS)[number]);
  const step = (dr: number, dc: number): Anchor => {
    for (let i = 0; i < ROWS.length; i++) {
      row += dr;
      col += dc;
      if (row < 0 || row >= ROWS.length || col < 0 || col >= COLUMNS.length) return anchor;
      const next = `${ROWS[row]}-${COLUMNS[col]}` as Anchor;
      if (ANCHORS.includes(next)) return next;
    }
    return anchor;
  };
  if (key === "ArrowLeft") return step(0, -1);
  if (key === "ArrowRight") return step(0, 1);
  if (key === "ArrowUp") return step(-1, 0);
  if (key === "ArrowDown") return step(1, 0);
  return anchor;
}

/** The pixels an arrow key moves a freely placed widget; Shift moves further. */
const NUDGE = 16;
const NUDGE_SHIFT = 64;
/** A pointer must travel this far before a press becomes a drag. */
const DRAG_START = 5;
/** A sheet dragged down this far collapses. */
const SHEET_SWIPE = 60;
/** How long the mic prompt has to stay open before the coach mark points at it. */
const COACH_ASKING_DELAY_MS = 700;

const CARD_WIDTH = { small: 260, medium: 320, large: 380 } as const;

const objectIds = new WeakMap<object, number>();
let nextObjectId = 0;

/**
 * A key that changes when the configuration does. JSON where it can be; a
 * configuration JSON cannot write (a cycle, a BigInt) is keyed by the object
 * itself, so it is parsed again only when the page passes a new one, and the
 * parser's warnings say what is wrong with it.
 */
function configKey(value: [unknown, unknown]): string {
  try {
    return `j:${JSON.stringify(value)}`;
  } catch {
    const base = value[0];
    if (typeof base !== "object" || base === null) return `v:${String(base)}:${nextObjectId++}`;
    let id = objectIds.get(base);
    if (id === undefined) {
      id = nextObjectId++;
      objectIds.set(base, id);
    }
    let attrs: string;
    try {
      attrs = JSON.stringify(value[1]);
    } catch {
      attrs = String(nextObjectId++);
    }
    return `o:${id}:${attrs}`;
  }
}

function capitalise(s: string | undefined): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

// ------------------------------------------------------------------ element

export class VqlWidget extends LitElement {
  static override properties = {
    config: { attribute: "config" },
    session: { attribute: false },
    sessionSource: { attribute: false },
    init: { attribute: false },
    apiBase: { attribute: "api-base" },
    statusLabel: { attribute: "status-label" },
    instantStartOnIOS: { attribute: false },
    browser: { attribute: false },
    view: { reflect: true },
    form: { reflect: true },
    sessionSnap: { state: true },
    micSnap: { state: true },
    spot: { state: true },
    devicesOpen: { state: true },
    coachDismissed: { state: true },
    coachReady: { state: true },
    coachCheck: { state: true },
    hasSide: { state: true },
    narrow: { state: true },
  };

  static override get observedAttributes(): string[] {
    const own = super.observedAttributes;
    return [...own, ...Object.keys(CONFIG_ATTRIBUTES).filter((a) => !own.includes(a)), "avatar"];
  }

  /** The configuration: an object, or JSON text (the `config` attribute). Attributes override it field by field. */
  declare config: WidgetConfigInput | string | undefined;
  /** The session to show. Without one, the widget starts its own from `agent` and `key` on open. */
  declare session: WidgetSessionLike | undefined;
  /** Where a session the widget starts comes from, instead of minting one with `agent` and `key`. */
  declare sessionSource: SessionSource | undefined;
  /** Values for the session's start, such as a Site Agent's greeting. */
  declare init: Record<string, unknown> | undefined;
  declare apiBase: string | undefined;
  /** A status word set by the page or a brain's action, over the agent's state. */
  declare statusLabel: string | undefined;
  /** Library flag: allow instant start on iPhone and iPad. Off until tested on real devices. */
  declare instantStartOnIOS: boolean;
  /** The browser the coach mark writes for. Detected when unset. */
  declare browser: BrowserKind | undefined;
  /** Where the visitor is. Read it; change it with the methods. */
  declare view: WidgetView;
  /** How the current view is drawn. */
  declare form: WidgetForm;

  declare protected sessionSnap: SessionSnapshot | undefined;
  declare protected micSnap: MicSnapshot | undefined;
  declare protected spot: PlacementSnapshot | undefined;
  declare protected devicesOpen: boolean;
  declare protected coachDismissed: boolean;
  declare protected coachReady: boolean;
  /** The visitor asked "is my mic working?" where there is no device menu: the coach gives this platform's advice. */
  declare protected coachCheck: boolean;
  declare protected hasSide: boolean;
  declare protected narrow: boolean;

  /** Where configuration warnings go. Default `console.warn`. */
  warn: Warn = (m) => console.warn(`[vql-widget] ${m}`);

  /** The configuration in force, every default filled in. */
  get resolvedConfig(): WidgetConfig {
    return this.cfg;
  }

  private cfg: WidgetConfig = parseWidgetConfig({}, () => {});
  private cfgKey = "";
  private t: Translate = translator(undefined, "en", "");
  private captions: CaptionsController | null = null;
  private captionsLoading: WidgetSessionLike | undefined;
  private loadingTags = new Set<string>();
  private placement: PlacementController | null = null;
  private placementKey = "";
  private unsubs: (() => void)[] = [];
  private boundSession: WidgetSessionLike | undefined;
  /** The session the widget started itself, which it ends when it is removed. A page's own is the page's to end. */
  private ownedSession: WidgetSessionLike | undefined;
  private connectedAt: number | undefined;
  private lastMicKey = "";
  private lastAgent = "";
  private lastStatus = "";
  private drag: { id: number; x: number; y: number; started: boolean; sheet: boolean } | null = null;
  private suppressClick = false;
  private resizeObserver: ResizeObserver | null = null;
  /** Re-renders when the page adds or removes a slotted launcher. */
  private childObserver: MutationObserver | null = null;
  private cramped = false;
  private coachTimer: ReturnType<typeof setTimeout> | null = null;
  private focusAfterRender: "launcher" | "open" | "expand" | null = null;
  private layoutQueued = false;
  private readonly onWindowChange = () => this.queueLayout();

  constructor() {
    super();
    this.view = "closed";
    this.form = "pill";
    this.devicesOpen = false;
    this.coachDismissed = false;
    this.coachReady = false;
    this.coachCheck = false;
    this.hasSide = false;
    this.narrow = false;
    this.instantStartOnIOS = false;
    this.addEventListener("keydown", (e) => this.onKeydown(e));
  }

  // ------------------------------------------------------------- lifecycle

  override connectedCallback(): void {
    super.connectedCallback();
    this.narrow = this.measureNarrow();
    globalThis.addEventListener?.("resize", this.onWindowChange);
    globalThis.addEventListener?.("scroll", this.onWindowChange, { passive: true, capture: true });
    globalThis.visualViewport?.addEventListener("resize", this.onWindowChange);
    globalThis.visualViewport?.addEventListener("scroll", this.onWindowChange);
    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => this.queueLayout());
    }
    if (typeof MutationObserver !== "undefined") {
      this.childObserver = new MutationObserver(() => this.requestUpdate());
      this.childObserver.observe(this, { childList: true });
    }
    // Back in the page after a removal: follow the page's session again.
    if (this.hasUpdated && this.session && this.boundSession !== this.session) {
      this.bindSession();
      this.requestUpdate();
    }
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    globalThis.removeEventListener?.("resize", this.onWindowChange);
    globalThis.removeEventListener?.("scroll", this.onWindowChange, { capture: true });
    globalThis.visualViewport?.removeEventListener("resize", this.onWindowChange);
    globalThis.visualViewport?.removeEventListener("scroll", this.onWindowChange);
    this.stopFollowing();
    this.drag = null;
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.childObserver?.disconnect();
    this.childObserver = null;
    // Removed from the page: let go once the current task is over, so a
    // widget the page only moves (removed and inserted again) keeps its call.
    queueMicrotask(() => {
      if (!this.isConnected) this.release();
    });
    if (this.coachTimer) clearTimeout(this.coachTimer);
    this.coachTimer = null;
  }

  override attributeChangedCallback(name: string, old: string | null, value: string | null): void {
    super.attributeChangedCallback(name, old, value);
    if (name in CONFIG_ATTRIBUTES || name === "avatar") this.requestUpdate();
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    this.resolveConfig();
    if (changed.has("session")) this.bindSession();
    this.form = this.computeForm();
  }

  protected override updated(changed: PropertyValues<this>): void {
    this.applyTheme();
    if (changed.has("view") || changed.has("form")) {
      const dock = this.renderRoot.querySelector(".dock");
      this.resizeObserver?.disconnect();
      if (dock) this.resizeObserver?.observe(dock);
      this.queueLayout();
      if (changed.get("view") !== undefined || changed.get("form") !== undefined) {
        this.emit("vql-view", { view: this.view, form: this.form });
      }
    }
    if (this.focusAfterRender) {
      const target = this.focusAfterRender;
      this.focusAfterRender = null;
      void this.focusTarget(target);
    }
  }

  // ------------------------------------------------------------ public API

  /** Open the call: from the launcher, from collapsed, or again after it ended. */
  async open(): Promise<void> {
    if (this.view === "open") return;
    const from = this.view;
    this.view = "open";
    this.focusAfterRender = "open";
    this.emit("vql-open", {});
    if (from === "collapsed") return;
    await this.startCall();
  }

  /** Minimise the open call to its collapsed form. Does nothing when `collapsed.style` is `none`. */
  collapse(): void {
    if (this.view !== "open" || this.cfg.collapsed.style === "none") return;
    this.devicesOpen = false;
    this.view = "collapsed";
    this.focusAfterRender = "expand";
    this.emit("vql-collapse", {});
  }

  /** Hang up if a call is live, and go back to the launcher. */
  async close(): Promise<void> {
    const live = this.sessionSnap?.status;
    this.view = "closed";
    this.devicesOpen = false;
    this.focusAfterRender = "launcher";
    this.emit("vql-close", {});
    if (live === "connecting" || live === "connected") await this.session?.disconnect();
  }

  /** Hang up and show the end card. */
  async end(): Promise<void> {
    await this.session?.disconnect();
  }

  /** Move the widget: to an anchor, or to a point (a free place, or the nearest anchor under snap). */
  place(where: Anchor | { x: number; y: number }): void {
    const p = this.placement;
    if (!p) return;
    if (typeof where === "string") {
      if (ANCHORS.includes(where)) p.moveTo(where, true);
    } else {
      p.startDrag(p.getSnapshot().point);
      p.drag(where);
      p.endDrag();
    }
    this.emitPlace();
  }

  setMuted(muted: boolean): void {
    this.session?.setMuted(muted);
  }

  // --------------------------------------------------------- configuration

  private resolveConfig(): void {
    const attrs = inputFromAttributes((n) => this.getAttribute(n));
    let base: unknown = this.config;
    if (typeof base === "string") {
      try {
        base = JSON.parse(base);
      } catch {
        base = this.config; // the parser reports it
      }
    }
    const key = configKey([base ?? {}, attrs]);
    if (key !== this.cfgKey) {
      this.cfgKey = key;
      this.cfg = parseWidgetConfig(mergeInput(base ?? {}, attrs), this.warn);
      const c = this.cfg.captions;
      this.captions?.setMode(c.mode);
      this.captions?.configure({ lines: c.lines, lingerMs: captionLinger(c.linger), showUser: c.showUser });
      if (c.mode !== "off") this.loadCaptions();
    }
    this.t = translator(this.cfg.words, pageLanguage(this), this.displayName());
    this.syncPlacement();
  }

  private displayName(): string {
    const character = this.cfg.avatar === false ? undefined : this.cfg.avatar.character;
    return this.cfg.name || capitalise(character) || "us";
  }

  private applyTheme(): void {
    const theme = this.cfg.theme;
    const colours = themeColours(theme);
    const set = (name: string, value: string | undefined) => {
      if (value) this.style.setProperty(name, value);
      else this.style.removeProperty(name);
    };
    // Custom properties through the CSSOM: no style attribute is written as markup.
    set("--_vql-cfg-brand", colours.brand);
    set("--_vql-cfg-on-brand", colours.onBrand);
    set("--_vql-cfg-surface", colours.surface);
    set("--_vql-cfg-ink", colours.ink);
    set("--_vql-cfg-radius", theme.radius !== undefined ? `${theme.radius}px` : undefined);
    set("--_w", `${CARD_WIDTH[this.cfg.open.size]}px`);
    set("--_vql-cfg-font", theme.font && theme.font !== "inherit" ? theme.font : undefined);
    for (const [name, value] of Object.entries(theme.tokens)) set(name, value);
    const scheme = theme.scheme === "auto" ? null : theme.scheme;
    if (scheme) this.setAttribute("data-scheme", scheme);
    else this.removeAttribute("data-scheme");
  }

  private get scheme(): string | undefined {
    return this.cfg.theme.scheme === "auto" ? undefined : this.cfg.theme.scheme;
  }

  private measureNarrow(): boolean {
    const width = globalThis.innerWidth ?? 1024;
    return width < this.cfg.mobile.breakpoint;
  }

  private computeForm(): WidgetForm {
    const c = this.cfg;
    if (this.view === "closed") return this.narrow ? c.mobile.launcher : c.launcher.style;
    if (this.view === "collapsed") return c.collapsed.style === "pill" ? "pill" : "bubble";
    if (c.placement.mode === "fullscreen") return "hero";
    if (this.narrow && c.placement.mode === "corner") return c.mobile.open;
    return c.open.style;
  }

  /** Whether the dock is placed by the placement controller (a corner widget in a floating form). */
  private get floating(): boolean {
    if (this.cfg.placement.mode !== "corner") return false;
    return this.form !== "hero" && this.form !== "sheet" && this.form !== "none";
  }

  // ------------------------------------------------------------- placement

  private syncPlacement(): void {
    const p = this.cfg.placement;
    const touch = globalThis.matchMedia?.("(pointer: coarse)").matches ?? false;
    const key = JSON.stringify([p.anchor, p.move, p.remember, p.offset, p.topClear, this.cfg.agent, touch]);
    if (key === this.placementKey) return;
    this.placementKey = key;
    this.placement = new PlacementController({
      anchor: p.anchor,
      move: p.move,
      remember: p.remember,
      offset: p.offset,
      topClear: p.topClear,
      agent: this.cfg.agent,
      touch,
    });
    this.spot = undefined;
    this.placement.subscribe(() => {
      this.spot = this.placement?.getSnapshot();
    });
    this.queueLayout();
  }

  private queueLayout(): void {
    if (this.layoutQueued) return;
    this.layoutQueued = true;
    const run = () => {
      this.layoutQueued = false;
      this.layout();
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else setTimeout(run, 0);
  }

  private viewport(): { width: number; height: number } {
    const vv = globalThis.visualViewport;
    const width = globalThis.innerWidth ?? 1024;
    const height = globalThis.innerHeight ?? 768;
    // Above the on-screen keyboard: the visual viewport shrinks when it opens.
    if (vv) return { width: Math.min(width, vv.width + vv.offsetLeft), height: Math.min(height, vv.height + vv.offsetTop) };
    return { width, height };
  }

  private avoidRects(): Rect[] {
    const rects: Rect[] = [];
    const selectors = [...this.cfg.placement.avoid, "[data-vql-avoid]"];
    for (const selector of selectors) {
      let found: NodeListOf<Element>;
      try {
        found = document.querySelectorAll(selector);
      } catch {
        continue; // an invalid selector is skipped, never thrown
      }
      for (const el of found) {
        if (el === this || this.contains(el)) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) rects.push({ left: r.left, top: r.top, width: r.width, height: r.height });
      }
    }
    return rects;
  }

  private layout(): void {
    const narrow = this.measureNarrow();
    if (narrow !== this.narrow) this.narrow = narrow;
    if (!this.floating || !this.placement) return;
    const dock = this.renderRoot.querySelector<HTMLElement>(".dock");
    if (!dock) return;
    const view = this.viewport();
    const size = { width: dock.offsetWidth, height: dock.offsetHeight };
    this.placement.layout(size, view, this.avoidRects());
    this.spot = this.placement.getSnapshot();
    this.autoCollapse(size, view);
  }

  private autoCollapse(size: { width: number; height: number }, view: { width: number; height: number }): void {
    if (!this.cfg.collapsed.autoCollapse || this.cfg.collapsed.style === "none") return;
    const cramped = this.form === "card" && (size.height > view.height - 32 || size.width > view.width - 16);
    if (cramped && !this.cramped && this.view === "open") this.collapse();
    this.cramped = cramped;
  }

  private emitPlace(): void {
    const s = this.placement?.getSnapshot();
    if (s) this.emit("vql-place", { anchor: s.anchor, point: s.point, free: s.free });
  }

  // --------------------------------------------------------------- session

  private bindSession(): void {
    if (this.boundSession === this.session) return;
    const previous = this.boundSession;
    this.unbindSession();
    // A session the widget started, replaced by another: its call ends.
    if (previous && previous === this.ownedSession && previous !== this.session) {
      this.ownedSession = undefined;
      previous.dispose?.();
    }
    const s = this.session;
    this.boundSession = s;
    if (!s) {
      this.sessionSnap = undefined;
      this.micSnap = undefined;
      return;
    }
    this.loadCaptions();
    const onSession = () => this.onSession(s.getSnapshot());
    const onMic = () => this.onMic(s.mic.getSnapshot());
    this.unsubs.push(s.subscribe(onSession), s.mic.subscribe(onMic));
    onSession();
    onMic();
  }

  /**
   * Captions are their own chunk: loaded when a session binds with captions
   * on, or when they are turned on during one. The session is created before
   * it connects, so no caption is missed while the chunk loads.
   */
  private loadCaptions(): void {
    const s = this.boundSession;
    if (!s || this.captions || this.cfg.captions.mode === "off" || this.captionsLoading === s) return;
    this.captionsLoading = s;
    void import("./captions-feature.js")
      .then(({ CaptionsController, bindCaptions, VqlCaptions }) => {
        if (this.captionsLoading === s) this.captionsLoading = undefined;
        if (globalThis.customElements && !customElements.get("vql-captions")) customElements.define("vql-captions", VqlCaptions);
        if (this.boundSession !== s || this.captions) return;
        const c = this.cfg.captions;
        this.captions = new CaptionsController({
          mode: c.mode,
          lines: c.lines,
          lingerMs: captionLinger(c.linger),
          showUser: c.showUser,
        });
        this.unsubs.push(bindCaptions(s, this.captions));
        this.requestUpdate();
      })
      .catch((e: unknown) => {
        if (this.captionsLoading === s) this.captionsLoading = undefined;
        this.warn(`captions could not load: ${String(e)}`);
      });
  }

  /**
   * Whether a lazy element is ready to render. The first ask starts its
   * chunk loading and re-renders when it is defined.
   */
  private ready(tag: string): boolean {
    const registry = globalThis.customElements;
    if (!registry || registry.get(tag)) return true;
    if (!this.loadingTags.has(tag)) {
      this.loadingTags.add(tag);
      loadElement(tag, registry)
        .then(() => this.requestUpdate())
        .catch((e: unknown) => this.warn(`${tag} could not load: ${String(e)}`))
        .finally(() => this.loadingTags.delete(tag));
    }
    return false;
  }

  private unbindSession(): void {
    for (const off of this.unsubs) off();
    this.unsubs = [];
    this.captions?.reset();
    this.captions = null;
    this.boundSession = undefined;
  }

  /**
   * The widget left the page. A call it started itself is hung up, since
   * nothing could show it or end it any more; a session the page passed in
   * is only let go of.
   */
  private release(): void {
    this.unbindSession();
    const owned = this.ownedSession;
    if (!owned) return;
    this.ownedSession = undefined;
    owned.dispose?.();
    if (this.session === owned) {
      this.session = undefined;
      this.sessionSnap = undefined;
      this.micSnap = undefined;
    }
    this.view = "closed";
  }

  private onSession(snap: SessionSnapshot): void {
    this.sessionSnap = snap;
    if (snap.status === "connected" && this.connectedAt === undefined) this.connectedAt = Date.now();
    if (snap.status !== this.lastStatus) {
      this.lastStatus = snap.status;
      if (snap.status === "ended") {
        this.connectedAt = undefined;
        this.devicesOpen = false;
        this.captions?.reset();
        if (this.view !== "closed") {
          this.view = "ended";
          this.focusAfterRender = "open";
        }
        this.emit("vql-end", { reason: snap.end?.reason ?? "ended" });
      }
    }
    if (snap.agent !== this.lastAgent) {
      this.lastAgent = snap.agent;
      this.emit("vql-agent", { state: snap.agent });
    }
  }

  private onMic(snap: MicSnapshot): void {
    const before = this.micSnap?.state;
    this.micSnap = snap;
    if (snap.state !== before) {
      this.coachDismissed = false;
      this.coachReady = false;
      this.coachCheck = false;
      if (this.coachTimer) clearTimeout(this.coachTimer);
      this.coachTimer = null;
      if (snap.state === "asking") {
        this.coachTimer = setTimeout(() => {
          this.coachReady = true;
        }, COACH_ASKING_DELAY_MS);
      } else {
        this.coachReady = true;
      }
    }
    const key = `${snap.state}:${snap.hint}`;
    if (key !== this.lastMicKey) {
      this.lastMicKey = key;
      if (snap.state !== "idle") this.emit("vql-mic", { state: snap.state, hint: snap.hint });
    }
  }

  private async startCall(): Promise<void> {
    const status = this.session?.getSnapshot().status;
    if (status === "connecting" || status === "connected") return;
    const source = await this.source();
    if (!source) return; // a session shown without a call, as a preview is
    if (!this.session) {
      const { WidgetSession } = await import("../session/adapter.js");
      const own = new WidgetSession({
        instantStart: this.cfg.mic.instantStart,
        instantStartOnIOS: this.instantStartOnIOS,
        silenceHint: this.cfg.mic.silenceHint,
      });
      this.ownedSession = own;
      this.session = own;
      await this.updateComplete;
      // Removed from the page while the session module loaded.
      if (!this.isConnected) {
        this.release();
        return;
      }
    }
    await this.session?.connect(source);
  }

  private async source(): Promise<SessionSource | undefined> {
    if (this.sessionSource) return this.sessionSource;
    const { agent, key } = this.cfg;
    if (!agent || !key) return undefined;
    const { mintSession } = await import("../session/adapter.js");
    const init = this.init;
    const apiBase = this.apiBase;
    return () => mintSession({ agent, key, ...(apiBase ? { apiBase } : {}), ...(init ? { init } : {}) });
  }

  // ---------------------------------------------------------------- input

  private emit(type: string, detail: unknown): void {
    this.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
  }

  private onKeydown(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      if (this.devicesOpen) {
        this.devicesOpen = false;
        void this.focusTarget("open");
      } else if (this.view === "open") {
        this.collapse();
      }
    }
  }

  private onMoveKey(e: KeyboardEvent): void {
    const p = this.placement;
    if (!p || !this.floating || !e.key.startsWith("Arrow")) return;
    e.preventDefault();
    if (p.move === "free") {
      const d = e.shiftKey ? NUDGE_SHIFT : NUDGE;
      const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
      const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
      p.nudge(dx, dy);
    } else if (p.move === "snap") {
      p.moveTo(neighbourAnchor(p.getSnapshot().anchor, e.key));
    } else {
      return;
    }
    this.emitPlace();
  }

  private onPointerDown(e: PointerEvent): void {
    if (e.button !== 0) return;
    const path = e.composedPath();
    const sheetHandle = this.form === "sheet" && path.some((n) => (n as Element).classList?.contains("sheet-handle"));
    if (!sheetHandle) {
      if (!this.floating || !this.placement || this.placement.move === "fixed") return;
      // Presses on a control stay presses; the expand target is the exception, it is the bubble itself.
      // Only the nodes between the press and the dock count.
      const inside = path.slice(0, Math.max(0, path.indexOf(e.currentTarget as EventTarget)));
      const onControl = inside.some((n) => {
        const el = n as Element;
        if (el.classList?.contains("expand")) return false;
        const tag = el.tagName ?? "";
        return tag === "BUTTON" || tag === "SELECT" || tag === "A" || (tag.startsWith("VQL-") && tag !== "VQL-FACE");
      });
      if (onControl) return;
    }
    this.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, started: false, sheet: sheetHandle };
    // The press is followed on the window, not by capturing the pointer: a
    // capture would retarget a plain press's click away from the expand
    // button, and a fast drag leaves the dock before the dock catches up.
    window.addEventListener("pointermove", this.onWindowMove);
    window.addEventListener("pointerup", this.onWindowUp);
    window.addEventListener("pointercancel", this.onWindowUp);
  }

  private readonly onWindowMove = (e: PointerEvent): void => this.onPointerMove(e);
  private readonly onWindowUp = (e: PointerEvent): void => this.onPointerUp(e);

  private stopFollowing(): void {
    window.removeEventListener("pointermove", this.onWindowMove);
    window.removeEventListener("pointerup", this.onWindowUp);
    window.removeEventListener("pointercancel", this.onWindowUp);
  }

  private onPointerMove(e: PointerEvent): void {
    const d = this.drag;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (d.sheet) return;
    if (!d.started) {
      if (Math.hypot(dx, dy) < DRAG_START) return;
      d.started = true;
      this.placement?.startDrag({ x: d.x, y: d.y });
    }
    this.placement?.drag({ x: e.clientX, y: e.clientY });
  }

  private onPointerUp(e: PointerEvent): void {
    const d = this.drag;
    if (!d || d.id !== e.pointerId) return;
    this.drag = null;
    this.stopFollowing();
    if (d.sheet) {
      if (e.clientY - d.y > SHEET_SWIPE) this.collapse();
      return;
    }
    if (d.started) {
      this.placement?.endDrag();
      this.suppressClick = true;
      this.emitPlace();
    }
  }

  private onExpandClick(): void {
    if (this.suppressClick) {
      this.suppressClick = false;
      return;
    }
    void this.open();
  }

  private async focusTarget(target: "launcher" | "open" | "expand"): Promise<void> {
    const root = this.renderRoot;
    // A part draws its own button on its next update; wait for it before focusing.
    const inner = async (tag: string): Promise<HTMLElement | null> => {
      const el = root.querySelector(tag) as (HTMLElement & { updateComplete?: Promise<unknown> }) | null;
      if (!el) return null;
      await el.updateComplete;
      return el.shadowRoot?.querySelector<HTMLElement>("button") ?? null;
    };
    if (target === "launcher") {
      (await inner("vql-launcher"))?.focus();
    } else if (target === "expand") {
      root.querySelector<HTMLElement>(".expand")?.focus();
    } else {
      const el =
        root.querySelector<HTMLElement>(".end-card .again") ??
        (await inner("vql-mic")) ??
        root.querySelector<HTMLElement>(".dock");
      el?.focus();
    }
  }

  private onSideSlot(e: Event): void {
    this.hasSide = (e.target as HTMLSlotElement).assignedNodes({ flatten: true }).length > 0;
  }

  // --------------------------------------------------------------- render

  static override styles = [
    themeStyles,
    css`
      :host {
        display: contents;
        --_w: 320px;
      }
      .dock {
        position: fixed;
        top: 0;
        left: 0;
        z-index: var(--vql-z, 2147483000);
        max-width: calc(100vw - 16px);
        touch-action: manipulation;
      }
      .dock.unplaced {
        visibility: hidden;
      }
      .dock.inline {
        position: relative;
        top: auto;
        left: auto;
        z-index: auto;
        max-width: none;
        display: block;
      }
      .dock.draggable .stage,
      .dock.draggable .expand,
      .dock.draggable.pill .card {
        cursor: grab;
        touch-action: none;
      }
      .dock.dragging .stage,
      .dock.dragging .expand {
        cursor: grabbing;
      }

      /* -------------------------------------------------------------- card */
      .card {
        position: relative;
        width: var(--_w);
        max-width: 100%;
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        background: var(--_surface);
        color: var(--_ink);
        border: 1px solid var(--_line);
        border-radius: var(--_radius);
        box-shadow: var(--_shadow);
        overflow: hidden;
        transition: width 220ms ease, border-radius 220ms ease;
      }
      .card.with-side {
        grid-template-columns: minmax(0, 1fr) minmax(0, 0.9fr);
        width: calc(var(--_w) * 1.9);
      }
      .main-col {
        display: grid;
        min-width: 0;
      }
      .inline .card {
        width: 100%;
      }
      .stage {
        position: relative;
        display: grid;
        justify-items: center;
        padding: 0;
      }
      .frame {
        position: relative;
        width: 100%;
        aspect-ratio: 4 / 3;
        transition: width 220ms ease, height 220ms ease;
      }
      .frame vql-face {
        position: absolute;
        inset: 0;
        --vql-radius: 0px;
      }
      .card-form.circle .frame {
        width: 58%;
        aspect-ratio: 1;
        /* Clear of the status chip and the grip above it. */
        margin-top: 44px;
      }
      .card-form.circle .frame vql-face {
        --vql-radius: inherit;
      }
      .status {
        position: absolute;
        top: 10px;
        inset-inline-start: 10px;
      }
      .grip {
        position: absolute;
        top: 8px;
        inset-inline-end: 8px;
        width: 30px;
        height: 30px;
        background: var(--_surface);
        opacity: 0.85;
      }
      .grip svg {
        width: 16px;
        height: 16px;
      }
      .body {
        display: grid;
        gap: 10px;
        padding: 12px 14px 14px;
      }
      .controls {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .controls .spacer {
        flex: 1;
      }
      .pill-row {
        display: flex;
        justify-content: center;
      }
      .hint {
        font-size: 13px;
        line-height: 1.35;
        color: var(--_danger);
      }
      .devices {
        position: absolute;
        inset-inline: 8px;
        bottom: 68px;
        z-index: 2;
      }
      .side {
        display: none;
        border-inline-start: 1px solid var(--_line);
        overflow: auto;
        min-width: 0;
      }
      .card.with-side .side {
        display: block;
      }
      .captions-card {
        min-height: 2.8em;
      }
      .captions-under {
        margin-top: 8px;
        padding: 10px 14px;
        background: var(--_surface);
        border-radius: var(--_radius);
        box-shadow: var(--_shadow);
      }
      .captions-page {
        position: fixed;
        left: 50%;
        bottom: max(24px, env(safe-area-inset-bottom));
        transform: translateX(-50%);
        width: min(720px, calc(100vw - 32px));
        padding: 12px 18px;
        border-radius: var(--_radius);
        background: var(--_surface);
        box-shadow: var(--_shadow);
        z-index: var(--vql-z, 2147483000);
        --vql-caption-size: 18px;
      }

      /* ------------------------------------------------------------ bubble */
      .bubble .card {
        width: 76px;
        border-radius: 999px;
        padding: 0;
        overflow: visible;
        background: transparent;
        border: 0;
        box-shadow: none;
      }
      .bubble .frame {
        width: 76px;
        aspect-ratio: 1;
        margin: 0;
        border-radius: 999px;
        box-shadow: var(--_shadow), 0 0 0 3px var(--_surface), 0 0 0 5px var(--_line);
        transition: box-shadow 200ms ease;
      }
      .bubble .frame vql-face {
        --vql-radius: 999px;
        border-radius: 999px;
        overflow: hidden;
      }
      .bubble.agent-speaking .frame {
        box-shadow: var(--_shadow), 0 0 0 3px var(--_surface), 0 0 0 5px var(--_speaking);
      }
      .bubble.agent-thinking .frame {
        box-shadow: var(--_shadow), 0 0 0 3px var(--_surface), 0 0 0 5px var(--_thinking);
      }
      .bubble.agent-listening .frame {
        box-shadow: var(--_shadow), 0 0 0 3px var(--_surface), 0 0 0 5px var(--_listening);
      }
      .expand {
        position: absolute;
        inset: 0;
        border: 0;
        padding: 0;
        background: transparent;
        border-radius: inherit;
        cursor: pointer;
      }
      .badge {
        position: absolute;
        bottom: -2px;
        inset-inline-end: -2px;
        display: grid;
        place-items: center;
        width: 26px;
        height: 26px;
        border-radius: 999px;
        background: var(--_ink);
        color: var(--_surface);
        border: 2px solid var(--_surface);
        pointer-events: none;
      }
      .badge svg {
        width: 14px;
        height: 14px;
      }
      .badge.warn {
        background: var(--_danger);
        color: #ffffff;
      }

      /* -------------------------------------------------------------- pill */
      .pill .card {
        width: auto;
        border-radius: 999px;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 5px 6px;
      }
      .pill .main-col {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .pill .stage {
        flex: none;
      }
      .pill .grip {
        display: none;
      }
      .pill .status {
        position: static;
      }
      .pill .frame {
        width: 46px;
        aspect-ratio: 1;
        margin: 0;
        border-radius: 999px;
        overflow: hidden;
      }
      .pill .frame vql-face {
        --vql-radius: 999px;
      }
      .pill .body {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 0;
      }
      .pill .expand {
        position: static;
        width: 36px;
        height: 36px;
        border-radius: 999px;
        display: inline-grid;
        place-items: center;
      }
      .pill .expand:hover {
        background: var(--_raised);
      }

      /* -------------------------------------------------------------- hero */
      .dock.hero {
        position: fixed;
        inset: 0;
        max-width: none;
        display: grid;
        place-items: center;
        background: var(--_surface);
      }
      .dock.hero.inline {
        position: relative;
        inset: auto;
        min-height: 480px;
      }
      .hero .card {
        width: min(720px, 100%);
        border: 0;
        box-shadow: none;
        background: transparent;
        justify-items: center;
      }
      .hero .frame {
        width: min(52vh, 78vw, 520px);
        aspect-ratio: 1;
        margin: 0 auto;
      }
      .hero .frame vql-face {
        --vql-radius: var(--_radius);
      }
      .hero.circle .frame vql-face {
        --vql-radius: 999px;
      }
      .hero .body {
        justify-items: center;
        text-align: center;
        width: 100%;
      }
      .hero .captions-card {
        --vql-caption-size: 22px;
        min-height: 3em;
        width: min(640px, 100%);
      }
      .hero .controls {
        justify-content: center;
      }
      .hero .status {
        position: static;
        margin-bottom: 12px;
      }
      .hero .stage {
        display: flex;
        flex-direction: column-reverse;
        align-items: center;
      }

      /* ------------------------------------------------------------- sheet */
      .dock.sheet {
        position: fixed;
        left: 0;
        right: 0;
        top: auto;
        bottom: 0;
        max-width: none;
      }
      .sheet .card {
        width: 100%;
        border-radius: var(--_radius) var(--_radius) 0 0;
        padding-bottom: env(safe-area-inset-bottom);
        max-height: 60vh;
      }
      .sheet-handle {
        justify-self: center;
        width: 100%;
        height: 22px;
        display: grid;
        place-items: center;
        touch-action: none;
        cursor: grab;
      }
      .sheet-handle span {
        width: 40px;
        height: 4px;
        border-radius: 999px;
        background: var(--_line);
      }
      .sheet .stage {
        grid-template-columns: auto 1fr;
        justify-items: start;
        align-items: center;
        gap: 12px;
        padding: 0 14px;
      }
      .sheet .frame {
        width: 88px;
        aspect-ratio: 1;
        border-radius: var(--_radius);
        overflow: hidden;
      }
      .sheet.circle .frame {
        border-radius: 999px;
      }
      .sheet .status {
        position: static;
      }

      /* ------------------------------------------------------------- ended */
      .end-card {
        display: grid;
        gap: 10px;
        font-size: 14px;
        line-height: 1.45;
      }
      .end-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .hero .end-actions {
        justify-content: center;
      }
      .btn {
        border: 1px solid var(--_line);
        background: var(--_surface);
        border-radius: 999px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 14px;
        cursor: pointer;
      }
      .btn.primary {
        background: var(--_brand);
        color: var(--_on-brand);
        border-color: var(--_brand);
      }
      .launcher-dock.none {
        display: none;
      }
      .custom-launcher {
        display: inline-block;
        cursor: pointer;
      }
    `,
  ];

  private dockPosition(): Record<string, string | undefined> {
    if (!this.floating || !this.spot) return { transform: undefined };
    const { x, y } = this.spot.point;
    return { transform: `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)` };
  }

  private dockClass(extra: string): string {
    const c = this.cfg;
    // The card form is "card-dock" here: the dock holds an element of class
    // "card", and the card's rules (position: relative among them) must not
    // land on the fixed dock itself.
    const classes = ["dock", this.form === "card" ? "card-dock" : this.form, extra];
    if (c.placement.mode === "inline") classes.push("inline");
    if (this.floating && !this.spot) classes.push("unplaced");
    if (this.floating && this.placement && this.placement.move !== "fixed") classes.push("draggable");
    if (this.spot?.dragging) classes.push("dragging");
    if (c.avatar !== false && c.avatar.shape === "circle") classes.push("circle");
    classes.push(`agent-${this.sessionSnap?.agent ?? "idle"}`);
    return classes.filter(Boolean).join(" ");
  }

  private hasLauncherSlot(): boolean {
    return Array.from(this.children).some((el) => el.getAttribute("slot") === "launcher");
  }

  protected override render() {
    return this.view === "closed" ? this.renderClosed() : this.renderCall();
  }

  private renderClosed() {
    const c = this.cfg;
    if (this.form === "none") return html`<div class="dock launcher-dock none" part="dock"></div>`;
    const still = c.avatar === false ? undefined : c.avatar.still;
    const launcher = this.hasLauncherSlot()
      ? html`<div class="custom-launcher" part="launcher" @click=${() => void this.open()}>
          <slot name="launcher"></slot>
        </div>`
      : html`<vql-launcher
          part="launcher"
          variant=${this.form}
          name=${this.displayName()}
          label=${c.launcher.label ?? this.t("launcher.label")}
          tagline=${c.launcher.tagline ?? this.t("launcher.tagline")}
          aria-label=${this.t("launcher.aria")}
          still=${still ?? nothing}
          scheme=${this.scheme ?? nothing}
          @vql-launch=${() => void this.open()}
          @vql-preload=${() => this.preloadFace()}
        ></vql-launcher>`;
    return html`<div class=${this.dockClass("launcher-dock")} part="dock" ${cssProps(this.dockPosition())}>
      ${launcher}
    </div>`;
  }

  private preloadFace(): void {
    const c = this.cfg;
    if (c.avatar === false || !c.avatar.character) return;
    // A detached face asks the loader to start building the character; the
    // call's face takes it over when it mounts.
    const face = document.createElement("vql-face");
    face.character = c.avatar.character;
    face.preload();
  }

  private renderCall() {
    const c = this.cfg;
    const s = this.sessionSnap;
    const mic = this.micSnap;
    const micState = mic?.state ?? "idle";
    const form = this.form;
    const open = this.view === "open";
    const ended = this.view === "ended";
    const collapsed = this.view === "collapsed";
    const avatar = c.avatar;
    const scheme = this.scheme ?? nothing;
    const dir = c.dir === "auto" ? nothing : c.dir;
    const showDevices = c.controls.devices && !this.narrow && !(globalThis.matchMedia?.("(pointer: coarse)").matches ?? false);
    const micOff = micState === "asking" || micState === "blocked" || micState === "missing";
    const captionsOn = c.captions.mode !== "off" && this.captions && this.ready("vql-captions");
    const captionsAt = form === "hero" || form === "sheet" ? "card" : c.captions.position;
    const captions = (cls: string) =>
      html`<vql-captions
        class=${cls}
        part="captions"
        mode=${c.captions.mode}
        scheme=${scheme}
        .controller=${this.captions ?? undefined}
        .t=${this.t}
      ></vql-captions>`;
    const inCall = s?.status === "connecting" || s?.status === "connected";
    const pill: MicPillKind | null = inCall && !ended ? micPillOf(mic, { askingSettled: this.coachReady }) : null;
    const pillOn = c.mic.pill && pill !== null && !collapsed;
    const coachCheck = this.coachCheck && pill === "check";
    // A track the system muted reads as "missing" on the wire, but the mic
    // is there: the advice is the "is it working?" kind, not "plug one in".
    const coachState = coachCheck || (micState === "missing" && mic?.trackMuted) ? "check" : micState;
    const coachWanted =
      c.mic.coach &&
      (open || collapsed) &&
      (micOff || coachCheck) &&
      this.coachReady &&
      !this.coachDismissed &&
      !(micState === "asking" && mic?.permission === "granted") &&
      inCall;
    const coachOn = coachWanted && this.ready("vql-coach");
    const pillShown = pillOn && this.ready("vql-mic-pill");

    const face = html`<vql-face
      part="face"
      shape=${avatar === false ? "rounded" : avatar.shape}
      framing=${avatar === false ? "shoulders" : avatar.framing}
      .background=${avatar === false ? undefined : avatar.background}
      still=${avatar === false ? nothing : (avatar.still ?? nothing)}
      character=${avatar === false ? nothing : (avatar.character ?? nothing)}
      ?voice-only=${avatar === false}
      agent-state=${s?.agent ?? "idle"}
      scheme=${scheme}
      .client=${s?.status === "connected" || s?.status === "connecting" ? this.session?.rawClient : undefined}
    ></vql-face>`;

    const expand =
      collapsed
        ? html`<button
            class="expand"
            part="expand"
            type="button"
            aria-label=${this.t("widget.expand")}
            title=${this.t("widget.expand")}
            @click=${this.onExpandClick}
            @keydown=${(e: KeyboardEvent) => this.onMoveKey(e)}
          >
            ${form === "pill" ? expandIcon : nothing}
          </button>`
        : nothing;

    const badge =
      collapsed && (micState === "muted" || micOff)
        ? html`<span class=${micOff ? "badge warn" : "badge"} part="badge" aria-hidden="true">${micOffIcon}</span>`
        : nothing;

    const status = html`<vql-status
      class="status"
      part="status"
      scheme=${scheme}
      status=${s?.status ?? "idle"}
      agent=${s?.agent ?? "idle"}
      mic=${pillOn ? "idle" : micState}
      ?unheard=${pillOn}
      label=${this.statusLabel ?? nothing}
      .since=${this.connectedAt}
      .t=${this.t}
    ></vql-status>`;

    const grip =
      open && this.floating && this.placement && this.placement.move !== "fixed"
        ? html`<button
            class="round grip"
            part="grip"
            type="button"
            aria-label=${this.t("widget.move")}
            title=${this.t("widget.move")}
            @keydown=${(e: KeyboardEvent) => this.onMoveKey(e)}
          >
            ${gripIcon}
          </button>`
        : nothing;

    const micEl = html`<vql-mic
      part="mic"
      scheme=${scheme}
      state=${micState}
      .level=${mic?.level ?? 0}
      meter=${c.mic.level}
      ?hint=${mic?.hint ?? false}
      .muted=${mic?.muted ?? false}
      ?devices=${showDevices}
      .expanded=${this.devicesOpen}
      .t=${this.t}
      @vql-mute=${(e: CustomEvent<{ muted: boolean }>) => this.session?.setMuted(e.detail.muted)}
      @vql-devices=${(e: CustomEvent<{ open: boolean }>) => {
        this.devicesOpen = e.detail.open;
        if (this.devicesOpen) this.focusDevices();
      }}
    ></vql-mic>`;

    const controls = html`<div class="controls" part="controls">
      <slot name="controls-start"></slot>
      ${c.controls.mute ? micEl : nothing}
      <span class="spacer"></span>
      <slot name="controls-end"></slot>
      ${c.controls.minimise && c.collapsed.style !== "none" && form !== "hero"
        ? html`<button
            class="round"
            part="minimise"
            type="button"
            aria-label=${this.t("controls.minimise")}
            title=${this.t("controls.minimise")}
            @click=${() => this.collapse()}
          >
            ${minimiseIcon}
          </button>`
        : nothing}
      ${c.controls.end ? html`<vql-end part="end" scheme=${scheme} .t=${this.t} @vql-hangup=${() => void this.end()}></vql-end>` : nothing}
    </div>`;

    const devices =
      this.devicesOpen && showDevices && s && this.ready("vql-devices")
        ? html`<vql-devices
            class="devices"
            part="devices"
            scheme=${scheme}
            .mics=${s.devices.mics}
            .speakers=${s.devices.speakers}
            .micId=${s.devices.micId}
            .speakerId=${s.devices.speakerId}
            ?can-pick-speaker=${s.devices.canPickSpeaker}
            .level=${mic?.level ?? 0}
            ?hint=${mic?.hint ?? false}
            .t=${this.t}
            @vql-select-mic=${(e: CustomEvent<{ id: string }>) => this.session?.selectMic(e.detail.id)}
            @vql-select-speaker=${(e: CustomEvent<{ id: string }>) => this.session?.selectSpeaker(e.detail.id)}
            @vql-close=${() => {
              this.devicesOpen = false;
            }}
          ></vql-devices>`
        : nothing;

    const reason = s?.end?.reason ?? "ended";
    const endCard = html`<div class="end-card" part="end-card" role="status">
      <span part="end-reason">${this.t(`end.${reason}`)}</span>
      <slot name="end"></slot>
      <div class="end-actions">
        <button class="btn primary again" part="again" type="button" @click=${() => void this.again()}>
          ${this.t("end.again")}
        </button>
        <button class="btn" part="close" type="button" @click=${() => void this.close()}>${this.t("end.close")}</button>
      </div>
    </div>`;

    let body: unknown;
    if (collapsed && form === "bubble") body = nothing;
    else if (collapsed) {
      body = html`<div class="body" part="body">${status}${c.controls.mute ? micEl : nothing}${expand}</div>`;
    } else if (ended) {
      body = html`<div class="body" part="body">${endCard}</div>`;
    } else {
      body = html`<div class="body" part="body">
        ${captionsOn && captionsAt === "card" ? captions("captions-card") : nothing}
        <slot name="notice" part="notice"></slot>
        ${!c.mic.pill && mic?.hint && c.mic.silenceHint
          ? html`<div class="hint" part="hint" role="status">${this.t("mic.hint")}</div>`
          : nothing}
        ${pillShown
          ? html`<div class="pill-row">
              <vql-mic-pill
                part="mic-pill"
                scheme=${scheme}
                kind=${pill}
                .announce=${false}
                .t=${this.t}
                @vql-pill-action=${(e: CustomEvent<MicPillActionDetail>) => this.onPillAction(e.detail.kind, showDevices)}
              ></vql-mic-pill>
            </div>`
          : nothing}
        ${controls}
      </div>`;
    }

    const cardForm = form === "card" ? "card-form" : "";
    return html`<div
        class=${this.dockClass(cardForm)}
        part="dock"
        dir=${dir}
        role="region"
        aria-label=${this.t("widget.region")}
        tabindex="-1"
        ${cssProps(this.dockPosition())}
        @pointerdown=${(e: PointerEvent) => this.onPointerDown(e)}
      >
        ${c.mic.pill
          ? html`<span class="sr-only mic-said" role="status" aria-live="polite">${pillOn && pill ? this.t(`pill.${pill}`) : ""}</span>`
          : nothing}
        <div class=${this.hasSide && open && form === "card" ? `card ${cardForm} with-side` : `card ${cardForm}`} part="card ${form}">
          <div class="main-col">
            ${form === "sheet" ? html`<div class="sheet-handle" part="sheet-handle" aria-hidden="true"><span></span></div>` : nothing}
            <div class="stage" part="stage">
              <div class="frame" part="frame">${face}${form === "bubble" ? expand : nothing}${badge}</div>
              ${!collapsed && !ended ? status : nothing} ${grip}
            </div>
            ${body} ${devices}
          </div>
          <aside class="side" part="side"><slot name="side" @slotchange=${(e: Event) => this.onSideSlot(e)}></slot></aside>
        </div>
        ${captionsOn && captionsAt === "under" && open ? captions("captions-under") : nothing}
      </div>
      ${captionsOn && captionsAt === "page" && (open || collapsed) ? captions("captions-page") : nothing}
      ${coachOn
        ? html`<vql-coach
            part="coach"
            scheme=${scheme}
            state=${coachState}
            .browser=${this.browser ?? detectBrowser()}
            .t=${this.t}
            @vql-dismiss=${() => {
              this.coachDismissed = true;
            }}
          ></vql-coach>`
        : nothing}`;
  }

  /**
   * The mic pill was pressed. `permission` shows the coach mark again, even
   * after a dismissal; `muted` unmutes; `check` opens the device menu, or
   * where there is none, the coach mark with this platform's advice. The
   * event carries on out of the widget, so a page can add its own response.
   */
  private onPillAction(kind: MicPillKind, showDevices: boolean): void {
    if (kind === "muted") {
      this.session?.setMuted(false);
      return;
    }
    if (kind === "check" && showDevices) {
      this.devicesOpen = true;
      this.focusDevices();
      return;
    }
    if (kind === "permission") this.session?.askForMic?.();
    this.coachDismissed = false;
    this.coachReady = true;
    if (kind === "check") this.coachCheck = true;
  }

  /** Focus the device menu once its chunk is in and it has rendered. */
  private focusDevices(): void {
    void loadElement("vql-devices")
      .then(() => this.updateComplete)
      .then(() => this.renderRoot.querySelector<HTMLElement>("vql-devices")?.focus())
      .catch(() => {});
  }

  private async again(): Promise<void> {
    this.view = "open";
    this.focusAfterRender = "open";
    this.emit("vql-open", {});
    await this.startCall();
  }
}

function captionLinger(value: number | string): number {
  return typeof value === "number" ? value : parseLinger(value);
}

function parseLinger(value: string): number {
  const m = /^\s*(\d+(?:\.\d+)?)\s*(ms|s)?\s*$/.exec(value);
  if (!m) return 4000;
  const n = Number(m[1]);
  return m[2] === "ms" ? n : n * 1000;
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-widget": VqlWidget;
  }
}
