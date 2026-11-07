/**
 * `<vql-devices>`: the device menu — a microphone picker with a larger
 * meter, and a speaker picker where the browser can route audio
 * (`setSinkId`). The silence hint repeats here, where another mic is one
 * choice away.
 *
 * Properties: `mics`, `speakers`, `micId`, `speakerId`, `canPickSpeaker`,
 * `level`, `hint`. Events: `vql-select-mic` and `vql-select-speaker`
 * (detail `{ id }`), and `vql-close` on Escape or the close button.
 *
 * Parts: `menu`, `mic-select`, `speaker-select`, `meter`, `meter-fill`, `hint`.
 */

import { LitElement, css, html, nothing } from "lit";
import { cssProps } from "./css-props.js";
import { endIcon } from "./icons.js";
import { meterLevel } from "./mic.js";
import { themeStyles } from "./theme.js";
import { type Translate, translator } from "./words.js";

type Device = Pick<MediaDeviceInfo, "deviceId" | "label">;

export class VqlDevices extends LitElement {
  static override properties = {
    mics: { attribute: false },
    speakers: { attribute: false },
    micId: { attribute: "mic-id" },
    speakerId: { attribute: "speaker-id" },
    canPickSpeaker: { type: Boolean, attribute: "can-pick-speaker" },
    level: { type: Number },
    hint: { type: Boolean },
    scheme: { reflect: true },
    t: { attribute: false },
  };

  declare mics: Device[];
  declare speakers: Device[];
  declare micId: string | undefined;
  declare speakerId: string | undefined;
  declare canPickSpeaker: boolean;
  declare level: number;
  declare hint: boolean;
  declare scheme: string | undefined;
  declare t: Translate;

  constructor() {
    super();
    this.mics = [];
    this.speakers = [];
    this.canPickSpeaker = false;
    this.level = 0;
    this.hint = false;
    this.t = translator(undefined, "en", "");
    this.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        this.close();
      }
    });
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: block;
      }
      .menu {
        display: grid;
        gap: 10px;
        padding: 14px;
        border-radius: var(--_radius);
        background: var(--_surface);
        border: 1px solid var(--_line);
        box-shadow: var(--_shadow);
        min-width: 240px;
      }
      .head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-weight: 600;
        font-size: 14px;
      }
      .head .round {
        width: 28px;
        height: 28px;
        border: 0;
      }
      .head svg {
        width: 16px;
        height: 16px;
      }
      label {
        display: grid;
        gap: 4px;
        font-size: 12px;
        color: var(--_muted);
      }
      select {
        font: inherit;
        font-size: 14px;
        color: var(--_ink);
        background: var(--_surface);
        border: 1px solid var(--_line);
        border-radius: 8px;
        padding: 6px 8px;
        max-width: 100%;
      }
      .meter {
        height: 6px;
        border-radius: 999px;
        background: var(--_raised);
        overflow: hidden;
      }
      .fill {
        height: 100%;
        background: var(--_live);
        transform-origin: left center;
        transition: transform 90ms linear;
      }
      :host(:dir(rtl)) .fill {
        transform-origin: right center;
      }
      .note {
        font-size: 12px;
        color: var(--_muted);
      }
      .hint {
        font-size: 13px;
        color: var(--_danger);
      }
    `,
  ];

  private close(): void {
    this.dispatchEvent(new CustomEvent("vql-close", { bubbles: true, composed: true }));
  }

  private pick(type: "vql-select-mic" | "vql-select-speaker", e: Event): void {
    const id = (e.target as HTMLSelectElement).value;
    this.dispatchEvent(new CustomEvent(type, { detail: { id }, bubbles: true, composed: true }));
  }

  private options(list: Device[], selected: string | undefined) {
    if (list.length === 0) return html`<option value="">${this.t("devices.default")}</option>`;
    return list.map(
      (d, i) =>
        html`<option value=${d.deviceId} ?selected=${d.deviceId === selected}>
          ${d.label || `${this.t("devices.default")} ${i + 1}`}
        </option>`,
    );
  }

  /** Focus the first control, as the menu opens. */
  override focus(): void {
    this.renderRoot.querySelector<HTMLSelectElement>("select")?.focus();
  }

  protected override render() {
    const level = meterLevel(this.level);
    return html`<div class="menu" part="menu" role="dialog" aria-label=${this.t("devices.title")}>
      <div class="head">
        <span>${this.t("devices.title")}</span>
        <button class="round" type="button" aria-label=${this.t("devices.close")} @click=${this.close}>${endIcon}</button>
      </div>
      <label
        >${this.t("devices.mic")}
        <select part="mic-select" @change=${(e: Event) => this.pick("vql-select-mic", e)}>
          ${this.options(this.mics, this.micId)}
        </select>
      </label>
      <div class="meter" part="meter" role="meter" aria-label=${this.t("devices.mic")} aria-valuemin="0" aria-valuemax="100" aria-valuenow=${Math.round(level * 100)}>
        <div class="fill" part="meter-fill" ${cssProps({ transform: `scaleX(${level})` })}></div>
      </div>
      ${this.hint
        ? html`<div class="hint" part="hint" role="status">${this.t("mic.hint")}</div>`
        : html`<div class="note">${this.t("devices.test")}</div>`}
      ${this.canPickSpeaker
        ? html`<label
            >${this.t("devices.speaker")}
            <select part="speaker-select" @change=${(e: Event) => this.pick("vql-select-speaker", e)}>
              ${this.options(this.speakers, this.speakerId)}
            </select>
          </label>`
        : nothing}
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-devices": VqlDevices;
  }
}
