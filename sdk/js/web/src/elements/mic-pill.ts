/**
 * `<vql-mic-pill>`: a pill that says what the mic needs from the visitor,
 * and does it when pressed.
 *
 * - `permission`, "Grant mic permission": pressing it asks for the coach mark;
 * - `muted`, "You are muted": pressing it asks to unmute;
 * - `check`, "Is your mic working?": pressing it asks for the device menu.
 *
 * The pill does not act itself: it fires `vql-pill-action` with
 * `detail.kind`, and the widget (or the page) does the rest. Which kind shows
 * is `micPillOf()` in `controllers/mic-pill.ts`; with no `kind` the pill
 * renders nothing.
 *
 * It is a separate element from `<vql-status>` because it is a control, not
 * a label: the status chip says where the call is, the pill asks the visitor
 * to do something. The widget loads it only when a mic needs attention.
 *
 * Properties: `kind`, `t` (the words), `scheme`, `announce` (default true:
 * the pill carries its own polite live region; the widget turns it off and
 * announces from a region that is there before the pill loads).
 *
 * Tokens: `--vql-danger` (permission), `--vql-ink` (muted), `--vql-warn`
 * (check), with the rest of the theme.
 *
 * Parts: `pill`, `icon`, `text`.
 */

import { LitElement, css, html, nothing } from "lit";
import type { MicPillKind } from "../controllers/mic-pill.js";
import { micIcon, micOffIcon } from "./icons.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

export interface MicPillActionDetail {
  kind: MicPillKind;
}

export class VqlMicPill extends LitElement {
  static override properties = {
    kind: { reflect: true },
    announce: { type: Boolean },
    scheme: { reflect: true },
    t: { attribute: false },
  };

  declare kind: MicPillKind | null | undefined;
  declare announce: boolean;
  declare scheme: string | undefined;
  declare t: Translate;

  constructor() {
    super();
    this.announce = true;
    this.t = translator(undefined, "en", "");
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: inline-block;
        --_warn: var(--vql-warn, #b45309);
        --_tone: var(--_warn);
      }
      :host([kind="permission"]) {
        --_tone: var(--_danger);
      }
      :host([kind="muted"]) {
        --_tone: var(--_ink);
      }
      .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 5px 12px 5px 9px;
        border-radius: 999px;
        border: 1px solid color-mix(in srgb, var(--_tone) 45%, transparent);
        background: color-mix(in srgb, var(--_tone) 12%, var(--_surface));
        color: var(--_ink);
        font-size: 13px;
        font-weight: 600;
        line-height: 1.2;
        white-space: nowrap;
        cursor: pointer;
        animation: vql-pill-in 180ms ease;
        transition: background-color 120ms ease;
      }
      .pill:hover {
        background: color-mix(in srgb, var(--_tone) 22%, var(--_surface));
      }
      .pill svg {
        width: 16px;
        height: 16px;
        color: var(--_tone);
      }
      @keyframes vql-pill-in {
        from {
          opacity: 0;
          transform: translateY(4px);
        }
      }
    `,
  ];

  private press(): void {
    const kind = this.kind;
    if (!kind) return;
    this.dispatchEvent(
      new CustomEvent<MicPillActionDetail>("vql-pill-action", { detail: { kind }, bubbles: true, composed: true }),
    );
  }

  protected override render() {
    const kind = this.kind;
    const text = kind ? this.t(`pill.${kind}`) : "";
    const live = this.announce ? html`<span class="sr-only" role="status" aria-live="polite">${text}</span>` : nothing;
    if (!kind) return live;
    return html`<button class="pill" part="pill" type="button" @click=${this.press}>
        <span part="icon">${kind === "check" ? micIcon : micOffIcon}</span>
        <span part="text">${text}</span>
      </button>
      ${live}`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-mic-pill": VqlMicPill;
  }
  interface HTMLElementEventMap {
    "vql-pill-action": CustomEvent<MicPillActionDetail>;
  }
}
