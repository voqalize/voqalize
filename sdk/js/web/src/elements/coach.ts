/**
 * `<vql-coach>`: the coach mark that tells a visitor where to allow the mic.
 *
 * A page cannot point at the browser's own permission prompt, so this sits
 * at the top of the window and says where the prompt (or the setting that
 * undoes a block) is in this visitor's browser. It shows for `asking`,
 * `blocked` and `missing`, and hides itself for any other state.
 *
 * Properties: `state`, `browser` (detected when not set), `t` (the words).
 * Event: `vql-dismiss` from its close button; the widget then keeps it
 * hidden until the mic state changes.
 *
 * Parts: `coach`, `text`, `dismiss`.
 */

import { LitElement, css, html, nothing } from "lit";
import type { MicState } from "../controllers/mic.js";
import { type BrowserKind, coachKey, detectBrowser } from "./browser.js";
import { endIcon, micOffIcon } from "./icons.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

export class VqlCoach extends LitElement {
  static override properties = {
    state: { reflect: true },
    browser: {},
    placement: { reflect: true },
    scheme: { reflect: true },
    t: { attribute: false },
  };

  declare state: MicState | undefined;
  declare browser: BrowserKind | undefined;
  /** `top` (default): fixed at the top of the window. `inline`: in the flow, for a composed layout. */
  declare placement: "top" | "inline";
  declare scheme: string | undefined;
  declare t: Translate;

  constructor() {
    super();
    this.placement = "top";
    this.t = translator(undefined, "en", "");
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: block;
      }
      :host([placement="top"]) {
        position: fixed;
        top: max(12px, env(safe-area-inset-top));
        left: 50%;
        transform: translateX(-50%);
        z-index: var(--vql-z, 2147483000);
        width: min(560px, calc(100vw - 32px));
      }
      .coach {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 12px 12px 12px 14px;
        border-radius: var(--_radius);
        background: var(--_ink);
        color: var(--_surface);
        box-shadow: var(--_shadow);
        font-size: 14px;
        line-height: 1.4;
        animation: vql-drop 220ms ease;
      }
      .coach > svg {
        flex: none;
        margin-top: 1px;
        color: var(--_brand);
      }
      .text {
        flex: 1;
      }
      .dismiss {
        flex: none;
        width: 28px;
        height: 28px;
        border: 0;
        background: transparent;
        color: inherit;
      }
      .dismiss svg {
        width: 16px;
        height: 16px;
      }
      @keyframes vql-drop {
        from {
          opacity: 0;
          transform: translateY(-8px);
        }
      }
    `,
  ];

  private dismiss(): void {
    this.dispatchEvent(new CustomEvent("vql-dismiss", { bubbles: true, composed: true }));
  }

  protected override render() {
    const state = this.state;
    if (state !== "asking" && state !== "blocked" && state !== "missing") return nothing;
    const text = this.t(coachKey(state, this.browser ?? detectBrowser()));
    return html`<div class="coach" part="coach" role="status">
      ${micOffIcon}
      <span class="text" part="text">${text}</span>
      <button class="round dismiss" part="dismiss" type="button" aria-label=${this.t("coach.dismiss")} @click=${this.dismiss}>
        ${endIcon}
      </button>
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-coach": VqlCoach;
  }
}
