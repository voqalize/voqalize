/**
 * `<vql-end>`: the end-call button.
 *
 * Event: `vql-hangup` when pressed. Parts: `button`.
 */

import { LitElement, css, html } from "lit";
import { endIcon } from "./icons.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

export class VqlEnd extends LitElement {
  static override properties = {
    scheme: { reflect: true },
    t: { attribute: false },
  };

  declare scheme: string | undefined;
  declare t: Translate;

  constructor() {
    super();
    this.t = translator(undefined, "en", "");
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: inline-block;
      }
      .round {
        width: 44px;
        height: 44px;
        background: var(--_danger);
        border-color: var(--_danger);
        color: #ffffff;
      }
      .round:hover {
        background: var(--_danger);
        transform: scale(1.05);
      }
    `,
  ];

  private hangup(): void {
    this.dispatchEvent(new CustomEvent("vql-hangup", { bubbles: true, composed: true }));
  }

  protected override render() {
    const label = this.t("controls.end");
    return html`<button class="round" part="button" type="button" aria-label=${label} title=${label} @click=${this.hangup}>
      ${endIcon}
    </button>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-end": VqlEnd;
  }
}
