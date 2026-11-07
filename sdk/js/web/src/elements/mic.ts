/**
 * `<vql-mic>`: the mic button, with a ring around it that moves with the
 * visitor's voice, and the caret that opens the device menu.
 *
 * It renders state and never derives it: the widget (or a page composing the
 * parts) sets `state`, `level` and `hint` from the session's mic store.
 *
 * - `state`: `idle`, `asking`, `live`, `blocked`, `missing` or `muted`.
 * - `muted`: whether the visitor muted. It can be set while the state is
 *   still `asking`, `blocked` or `missing`, before there is a track to mute,
 *   so the button reads it rather than inferring it from `state`.
 * - `level`: the local level, 0–1, from the transport's 100 ms meter.
 * - `meter`: `ring` (default), `bars` or `off` — the configuration's `mic.level`.
 * - `devices`: show the caret for the device menu.
 * - `expanded`: whether that menu is open, for `aria-expanded`.
 *
 * Events: `vql-mute` (detail `{ muted }`, the state the visitor asked for)
 * and `vql-devices` (the caret, detail `{ open }`).
 *
 * Parts: `button`, `ring`, `bars`, `caret`.
 */

import { LitElement, css, html, nothing } from "lit";
import { cssProps } from "./css-props.js";
import type { MicState } from "../controllers/mic.js";
import { caretIcon, micIcon, micOffIcon } from "./icons.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

/** How far the ring grows at full level, as a fraction of the button. */
const RING_GROWTH = 0.4;

/** The level a voice usually peaks at; the meter reads full there. */
const LEVEL_FULL = 0.35;

export function meterLevel(level: number): number {
  if (!Number.isFinite(level) || level <= 0) return 0;
  return Math.min(1, Math.sqrt(level / LEVEL_FULL));
}

export class VqlMic extends LitElement {
  static override properties = {
    state: { reflect: true },
    level: { type: Number },
    meter: { reflect: true },
    hint: { type: Boolean, reflect: true },
    muted: { type: Boolean },
    devices: { type: Boolean, reflect: true },
    expanded: { type: Boolean },
    scheme: { reflect: true },
    t: { attribute: false },
  };

  declare state: MicState;
  declare level: number;
  declare meter: "ring" | "bars" | "off";
  declare hint: boolean;
  declare muted: boolean;
  declare devices: boolean;
  declare expanded: boolean;
  declare scheme: string | undefined;
  /** The words to label with. Defaults to English. */
  declare t: Translate;

  constructor() {
    super();
    this.state = "idle";
    this.level = 0;
    this.meter = "ring";
    this.hint = false;
    this.muted = false;
    this.devices = false;
    this.expanded = false;
    this.t = translator(undefined, "en", "");
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: inline-flex;
        align-items: center;
        gap: 2px;
      }
      .wrap {
        position: relative;
        display: inline-grid;
        place-items: center;
      }
      .ring {
        position: absolute;
        inset: 0;
        border-radius: 999px;
        background: var(--_live);
        opacity: 0.28;
        transform: scale(1);
        transition: transform 90ms linear;
        pointer-events: none;
      }
      .main {
        position: relative;
        width: 44px;
        height: 44px;
      }
      :host([state="live"]) .main {
        color: var(--_live);
        border-color: var(--_live);
      }
      :host([state="muted"]) .main {
        background: var(--_ink);
        color: var(--_surface);
        border-color: var(--_ink);
      }
      :host([state="asking"]) .main,
      :host([state="blocked"]) .main,
      :host([state="missing"]) .main {
        color: var(--_danger);
        border-color: var(--_danger);
      }
      :host([hint]) .main {
        border-style: dashed;
      }
      .caret {
        width: 24px;
        height: 32px;
        border-radius: 8px;
        border: 0;
        background: transparent;
        cursor: pointer;
        display: inline-grid;
        place-items: center;
        padding: 0;
      }
      .caret svg {
        width: 16px;
        height: 16px;
      }
      .caret:hover {
        background: var(--_raised);
      }
      .bars {
        display: inline-flex;
        align-items: flex-end;
        gap: 2px;
        height: 18px;
        margin-inline-start: 4px;
      }
      .bars span {
        width: 3px;
        border-radius: 2px;
        background: var(--_live);
        transition: height 90ms linear;
      }
    `,
  ];

  /** Whether the visitor muted, from either the property or the state. */
  private get isMuted(): boolean {
    return this.muted || this.state === "muted";
  }

  private toggle(): void {
    const muted = !this.isMuted;
    this.dispatchEvent(new CustomEvent("vql-mute", { detail: { muted }, bubbles: true, composed: true }));
  }

  private openDevices(): void {
    this.dispatchEvent(
      new CustomEvent("vql-devices", { detail: { open: !this.expanded }, bubbles: true, composed: true }),
    );
  }

  protected override render() {
    const muted = this.isMuted;
    const off = muted || this.state === "blocked" || this.state === "missing";
    const level = this.state === "live" ? meterLevel(this.level) : 0;
    const ring =
      this.meter === "ring"
        ? html`<span class="ring" part="ring" ${cssProps({ transform: `scale(${1 + level * RING_GROWTH})` })}></span>`
        : nothing;
    const bars =
      this.meter === "bars"
        ? html`<span class="bars" part="bars" aria-hidden="true">
            ${[0.5, 1, 0.7].map(
              (k) => html`<span ${cssProps({ height: `${Math.round(3 + 15 * Math.min(1, level * k * 1.4))}px` })}></span>`,
            )}
          </span>`
        : nothing;
    return html`<span class="wrap">${ring}<button
          class="round main"
          part="button"
          type="button"
          aria-pressed=${muted ? "true" : "false"}
          aria-label=${muted ? this.t("mic.unmute") : this.t("mic.mute")}
          title=${muted ? this.t("mic.unmute") : this.t("mic.mute")}
          @click=${this.toggle}
        >
          ${off ? micOffIcon : micIcon}
        </button></span
      >${bars}${this.devices
        ? html`<button
            class="caret"
            part="caret"
            type="button"
            aria-haspopup="dialog"
            aria-expanded=${this.expanded ? "true" : "false"}
            aria-label=${this.t("mic.devices")}
            title=${this.t("mic.devices")}
            @click=${this.openDevices}
          >
            ${caretIcon}
          </button>`
        : nothing}`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-mic": VqlMic;
  }
}
