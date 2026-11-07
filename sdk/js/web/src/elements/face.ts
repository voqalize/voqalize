/**
 * `<vql-face>`: the frame the agent's face lives in.
 *
 * - **The avatar**, loaded lazily. `@voqalize/avatar` is an optional peer and
 *   never a hard dependency: the face asks the avatar loader for it only
 *   when it has a character and a live client, and if the module cannot be
 *   loaded the still image stays. A page that bundles the avatar hands it
 *   over once with `setAvatarLoader(() => import("@voqalize/avatar"))`.
 * - **Your own face**: anything in the default slot replaces the avatar.
 * - **A still image**, shown until the avatar has drawn.
 * - **A background** under the transparent face: a colour, a CSS gradient,
 *   or the URL of an image, GIF or muted looping video.
 * - **Voice only** (`avatar: false`): a waveform in place of the face.
 *
 * The element fills the box it is given and never re-mounts the avatar when
 * that box changes size, so the widget can scale it between its states.
 *
 * Parts: `frame`, `background`, `still`, `avatar`, `wave`.
 */

import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import { cssProps } from "./css-props.js";
import type { AvatarBackground, AvatarFraming, AvatarShape } from "../config/types.js";
import { themeStyles } from "./theme.js";

/** What the face needs of `@voqalize/avatar`. Written out so it is not a type dependency either. */
export interface AvatarModuleLike {
  createAvatar(options: { mount: HTMLElement; client: unknown; character: string; motionGain?: number }): {
    destroy(): void;
  };
  preloadAvatar?(character: string): { ready: Promise<unknown> };
}

export type AvatarLoader = () => Promise<AvatarModuleLike>;

// Held in a variable so a bundler does not try to resolve an optional peer
// that is not installed. A page with an import map, or one that calls
// `setAvatarLoader`, gets the avatar; any other gets the still image.
const AVATAR_MODULE = "@voqalize/avatar";

let avatarLoader: AvatarLoader = () => import(/* @vite-ignore */ AVATAR_MODULE) as Promise<AvatarModuleLike>;

/** Say how to load `@voqalize/avatar`, typically `() => import("@voqalize/avatar")`. */
export function setAvatarLoader(loader: AvatarLoader): void {
  avatarLoader = loader;
  modulePromise = null;
}

let modulePromise: Promise<AvatarModuleLike | null> | null = null;

function loadAvatarModule(): Promise<AvatarModuleLike | null> {
  modulePromise ??= avatarLoader()
    .then((m) => (m && typeof m.createAvatar === "function" ? m : null))
    .catch(() => null);
  return modulePromise;
}

const VIDEO = /\.(mp4|webm|mov|m4v|ogv)(\?|#|$)/i;
const URLISH = /^(https?:|blob:|data:image\/|\/|\.\.?\/)/i;

export type ResolvedBackground =
  | { kind: "none" }
  | { kind: "css"; value: string }
  | { kind: "image" | "video"; url: string; fit: "cover" | "contain" };

/** What a configured background is: a CSS value, or an image or video to draw. */
export function resolveBackground(bg: AvatarBackground | undefined | null): ResolvedBackground {
  if (!bg) return { kind: "none" };
  if (typeof bg === "object") {
    return { kind: VIDEO.test(bg.url) ? "video" : "image", url: bg.url, fit: bg.fit ?? "cover" };
  }
  const value = bg.trim();
  if (!value || value === "none") return { kind: "none" };
  if (URLISH.test(value)) return { kind: VIDEO.test(value) ? "video" : "image", url: value, fit: "cover" };
  return { kind: "css", value };
}

export class VqlFace extends LitElement {
  static override properties = {
    shape: { reflect: true },
    framing: { reflect: true },
    background: { attribute: false },
    still: {},
    character: {},
    voiceOnly: { type: Boolean, attribute: "voice-only", reflect: true },
    agentState: { attribute: "agent-state", reflect: true },
    client: { attribute: false },
    scheme: { reflect: true },
    drawn: { state: true },
    slotted: { state: true },
  };

  declare shape: AvatarShape;
  declare framing: AvatarFraming;
  declare background: AvatarBackground | undefined;
  declare still: string | undefined;
  declare character: string | undefined;
  declare voiceOnly: boolean;
  declare agentState: string;
  /** The live client the avatar follows. */
  declare client: unknown;
  declare scheme: string | undefined;
  declare protected drawn: boolean;
  declare protected slotted: boolean;

  private avatar: { destroy(): void } | null = null;
  private mountKey = "";
  private observer: MutationObserver | null = null;

  constructor() {
    super();
    this.shape = "rounded";
    this.framing = "shoulders";
    this.voiceOnly = false;
    this.agentState = "idle";
    this.drawn = false;
    this.slotted = false;
  }

  static override styles = [
    themeStyles,
    css`
      :host {
        display: block;
        position: relative;
        width: 100%;
        height: 100%;
        min-width: 0;
        min-height: 0;
      }
      .frame {
        position: absolute;
        inset: 0;
        overflow: hidden;
        border-radius: var(--_radius);
        background: var(--vql-face-background, var(--_raised));
        isolation: isolate;
      }
      :host([shape="circle"]) .frame {
        border-radius: 999px;
      }
      :host([shape="square"]) .frame {
        border-radius: 0;
      }
      .bg,
      .bg video,
      .bg img,
      .still,
      .avatar,
      ::slotted(*) {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
      }
      .bg video,
      .bg img {
        object-fit: cover;
      }
      .bg.contain video,
      .bg.contain img {
        object-fit: contain;
      }
      .still {
        object-fit: cover;
        object-position: 50% 15%;
        transition: opacity 300ms ease;
      }
      :host([framing="face"]) .still {
        transform: scale(1.35);
        transform-origin: 50% 25%;
      }
      .still.gone {
        opacity: 0;
      }
      .monogram {
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        font-size: 2.5em;
        font-weight: 600;
        color: var(--_on-brand);
        background: var(--_brand);
      }
      .wave {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6%;
        background: var(--_brand);
      }
      .wave span {
        width: 7%;
        height: 18%;
        border-radius: 999px;
        background: var(--_on-brand);
        opacity: 0.9;
      }
      :host([agent-state="speaking"]) .wave span {
        animation: vql-wave 900ms ease-in-out infinite;
      }
      .wave span:nth-child(2) {
        animation-delay: 120ms;
      }
      .wave span:nth-child(3) {
        animation-delay: 240ms;
      }
      .wave span:nth-child(4) {
        animation-delay: 360ms;
      }
      .wave span:nth-child(5) {
        animation-delay: 480ms;
      }
      @keyframes vql-wave {
        0%,
        100% {
          height: 18%;
        }
        50% {
          height: 55%;
        }
      }
    `,
  ];

  /** Start building the face before the call, where the avatar can. Safe to call any number of times. */
  preload(): void {
    if (this.voiceOnly || !this.character) return;
    const character = this.character;
    void loadAvatarModule().then((m) => {
      try {
        m?.preloadAvatar?.(character);
      } catch {
        // Preloading is an optimisation; the mount builds it anyway.
      }
    });
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unmount();
  }

  protected override updated(changed: PropertyValues<this>): void {
    if (changed.has("client") || changed.has("character") || changed.has("voiceOnly") || (changed as Map<PropertyKey, unknown>).has("slotted")) {
      void this.syncAvatar();
    }
  }

  private async syncAvatar(): Promise<void> {
    const want = !this.voiceOnly && !this.slotted && this.client && this.character;
    const key = want ? `${this.character}` : "";
    if (want && key === this.mountKey && this.avatar) return;
    this.unmount();
    if (!want) return;
    this.mountKey = key;
    const m = await loadAvatarModule();
    const mount = this.renderRoot.querySelector<HTMLElement>(".avatar");
    if (!m || !mount || this.mountKey !== key || !this.client) return;
    try {
      this.avatar = m.createAvatar({ mount, client: this.client, character: key });
    } catch {
      this.avatar = null;
      return;
    }
    // The avatar draws into a canvas it adds to the mount; the still goes
    // when that canvas appears.
    this.observer = new MutationObserver(() => {
      if (mount.querySelector("canvas")) this.drawn = true;
    });
    this.observer.observe(mount, { childList: true, subtree: true });
    try {
      void m.preloadAvatar?.(key).ready.then(
        () => {
          if (this.mountKey === key) this.drawn = true;
        },
        () => {},
      );
    } catch {
      // No ready signal; the canvas observer covers it.
    }
  }

  private unmount(): void {
    this.observer?.disconnect();
    this.observer = null;
    try {
      this.avatar?.destroy();
    } catch {
      // Destroy is documented as safe; a broken runtime must not break the widget.
    }
    this.avatar = null;
    this.mountKey = "";
    this.drawn = false;
  }

  private onSlotChange(e: Event): void {
    const slot = e.target as HTMLSlotElement;
    this.slotted = slot.assignedNodes({ flatten: true }).some(
      (n) => n.nodeType === 1 || (n.nodeType === 3 && (n.textContent ?? "").trim() !== ""),
    );
  }

  private renderBackground() {
    const bg = resolveBackground(this.background);
    if (bg.kind === "none") return nothing;
    if (bg.kind === "css") {
      // CSSOM, not a style attribute: allowed under a strict CSP.
      return html`<div class="bg" part="background" ${cssProps({ background: bg.value })}></div>`;
    }
    const cls = bg.fit === "contain" ? "bg contain" : "bg";
    if (bg.kind === "video") {
      return html`<div class=${cls} part="background">
        <video src=${bg.url} autoplay muted loop playsinline disablepictureinpicture aria-hidden="true"></video>
      </div>`;
    }
    return html`<div class=${cls} part="background"><img src=${bg.url} alt="" decoding="async" /></div>`;
  }

  protected override render() {
    if (this.voiceOnly) {
      return html`<div class="frame" part="frame">
        ${this.renderBackground()}
        <div class="wave" part="wave" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
      </div>`;
    }
    const stillGone = this.drawn || this.slotted;
    return html`<div class="frame" part="frame">
      ${this.renderBackground()}
      ${this.still
        ? html`<img class=${stillGone ? "still gone" : "still"} part="still" src=${this.still} alt="" decoding="async" />`
        : stillGone || this.avatar
          ? nothing
          : html`<div class="monogram" part="still" aria-hidden="true">${(this.character ?? "").charAt(0).toUpperCase()}</div>`}
      <div class="avatar" part="avatar"></div>
      <slot @slotchange=${this.onSlotChange}></slot>
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-face": VqlFace;
  }
}
