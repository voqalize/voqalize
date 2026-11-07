/**
 * `<vql-captions>`: the agent's words as they are heard.
 *
 * It draws a `CaptionsController`'s snapshot (`controller`), or a snapshot
 * set directly (`snapshot`) for a page or a preview that times its own.
 * It measures its own width and tells the controller how many characters fit
 * on a line, so lines break where the text actually wraps.
 *
 * Screen readers get each finished sentence once, from a polite live
 * region, never each word.
 *
 * Parts: `captions`, `line`, `word` (with `spoken` and `current` added as
 * the word plays), `user`, `live`.
 */

import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import type { CaptionsController, CaptionsSnapshot } from "../controllers/captions.js";
import type { ReadableStore } from "../controllers/store.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

/** An average glyph is about this fraction of the font size wide. */
const GLYPH_WIDTH = 0.52;

const EMPTY: CaptionsSnapshot = { visible: false, lines: [] };

type CaptionsSource = ReadableStore<CaptionsSnapshot> & Partial<Pick<CaptionsController, "setCharsPerLine">>;

export class VqlCaptions extends LitElement {
  static override properties = {
    controller: { attribute: false },
    snapshot: { attribute: false },
    mode: { reflect: true },
    scheme: { reflect: true },
    t: { attribute: false },
  };

  declare controller: CaptionsSource | undefined;
  declare snapshot: CaptionsSnapshot;
  declare mode: string;
  declare scheme: string | undefined;
  declare t: Translate;

  private unsubscribe: (() => void) | null = null;
  private resize: ResizeObserver | null = null;
  private announced = "";
  private lastAnnouncementId = -1;

  constructor() {
    super();
    this.snapshot = EMPTY;
    this.mode = "karaoke";
    this.t = translator(undefined, "en", "");
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: block;
        font-size: var(--_caption-size);
        line-height: 1.4;
      }
      .captions {
        min-height: 1.4em;
        transition: opacity 250ms ease;
      }
      .captions.hidden {
        opacity: 0;
      }
      .line {
        display: block;
        transition: opacity 250ms ease, transform 250ms ease;
      }
      .line.old {
        opacity: 0.55;
      }
      .word {
        color: var(--_muted);
        transition: color 120ms linear;
      }
      .word.spoken {
        color: var(--_ink);
      }
      .word.current {
        color: var(--_brand);
      }
      :host([mode="rolling"]) .word {
        color: var(--_ink);
      }
      .user {
        display: block;
        margin-top: 4px;
        font-size: 0.85em;
        color: var(--_muted);
        font-style: italic;
      }
      @keyframes vql-rise {
        from {
          opacity: 0;
          transform: translateY(6px);
        }
      }
      .line:last-child {
        animation: vql-rise 200ms ease;
      }
    `,
  ];

  override connectedCallback(): void {
    super.connectedCallback();
    this.subscribe();
    if (typeof ResizeObserver !== "undefined") {
      this.resize = new ResizeObserver(() => this.measure());
      this.resize.observe(this);
    }
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.resize?.disconnect();
    this.resize = null;
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("controller")) this.subscribe();
    const a = this.snapshot.announcement;
    if (a && a.id !== this.lastAnnouncementId) {
      this.lastAnnouncementId = a.id;
      this.announced = a.text;
    }
  }

  private subscribe(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    const c = this.controller;
    if (!c || !this.isConnected) return;
    this.snapshot = c.getSnapshot();
    this.unsubscribe = c.subscribe(() => {
      this.snapshot = c.getSnapshot();
    });
    this.measure();
  }

  private measure(): void {
    const c = this.controller;
    if (!c?.setCharsPerLine) return;
    const width = this.clientWidth;
    if (!width) return;
    const size = parseFloat(getComputedStyle(this).fontSize) || 15;
    c.setCharsPerLine(width / (size * GLYPH_WIDTH));
  }

  protected override render() {
    const s = this.snapshot;
    const lines = s.lines;
    return html`<div class=${s.visible ? "captions" : "captions hidden"} part="captions" aria-hidden="true">
        ${lines.map(
          (line, i) =>
            html`<span class=${i < lines.length - 1 ? "line old" : "line"} part="line"
              >${line.words.map((w, j) => {
                const parts = ["word", w.spoken ? "spoken" : "", w.current ? "current" : ""].filter(Boolean).join(" ");
                return html`${j > 0 ? " " : ""}<span class=${parts} part=${parts}>${w.text}</span>`;
              })}</span
            >`,
        )}
        ${s.user ? html`<span class="user" part="user">${s.user}</span>` : nothing}
      </div>
      <div class="sr-only" part="live" role="log" aria-live="polite" aria-label=${this.t("captions.label")}>
        ${this.announced}
      </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-captions": VqlCaptions;
  }
}
