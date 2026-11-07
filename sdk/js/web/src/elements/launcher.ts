/**
 * `<vql-launcher>`: the closed widget, the invitation to talk.
 *
 * Written without Lit and without any import, so a loader can show it
 * before anything else has downloaded; everything else loads on the click.
 * Its size is measured on every build (`pnpm size`).
 *
 *   <vql-launcher variant="pill" name="Emily" label="Talk to Emily"
 *                 tagline="Ask me anything" still="https://…/emily.webp">
 *
 * Attributes: `variant` (`pill`, `face` or `card`), `name`, `label`,
 * `tagline`, `still` (an image URL; without one the face is the name's
 * initial), `aria-label` for the button, and `scheme`. It is `variant`
 * rather than `style` because `style` is the browser's own attribute.
 *
 * Events, which bubble and cross shadow roots:
 * - `vql-launch` on a click or Enter: open the call.
 * - `vql-preload` once, on the first hover or focus, so the face can start
 *   building before the click.
 *
 * Parts: `button`, `face`, `text`, `label`, `tagline`.
 *
 * Styles are a constructed stylesheet (`adoptedStyleSheets`), which a strict
 * Content-Security-Policy allows; nothing sets a style attribute.
 */

const CSS = `
:host{--_brand:var(--vql-brand,var(--_vql-cfg-brand,#c2410c));--_on-brand:var(--vql-on-brand,var(--_vql-cfg-on-brand,#fff));--_surface:var(--vql-surface,var(--_vql-cfg-surface,#fff));--_ink:var(--vql-ink,var(--_vql-cfg-ink,#1c1917));--_muted:var(--vql-muted,#6b6560);--_line:var(--vql-line,rgba(28,25,23,.14));--_shadow:var(--vql-shadow,0 10px 30px rgba(28,25,23,.18),0 2px 6px rgba(28,25,23,.12));--_radius:var(--vql-radius,var(--_vql-cfg-radius,16px));display:inline-block;font-family:var(--vql-font,var(--_vql-cfg-font,inherit));color:var(--_ink)}
@media (prefers-color-scheme:dark){:host(:not([scheme=light])){--_surface:var(--vql-surface,var(--_vql-cfg-surface,#1c1b1a));--_ink:var(--vql-ink,var(--_vql-cfg-ink,#f5f3f0));--_muted:var(--vql-muted,#a8a29e);--_line:var(--vql-line,rgba(245,243,240,.16))}}
:host([scheme=dark]){--_surface:var(--vql-surface,var(--_vql-cfg-surface,#1c1b1a));--_ink:var(--vql-ink,var(--_vql-cfg-ink,#f5f3f0));--_muted:var(--vql-muted,#a8a29e);--_line:var(--vql-line,rgba(245,243,240,.16))}
:host([hidden]){display:none}
button{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:12px;cursor:pointer;background:var(--_surface);color:var(--_ink);border:1px solid var(--_line);box-shadow:var(--_shadow);border-radius:999px;padding:6px 18px 6px 6px;max-width:320px;transition:transform .15s ease}
button:hover{transform:translateY(-1px)}
button:focus-visible{outline:2px solid var(--_brand);outline-offset:3px}
.f{flex:none;display:grid;place-items:center;width:48px;height:48px;border-radius:999px;overflow:hidden;background:var(--_brand);color:var(--_on-brand);font-weight:600;font-size:20px;box-shadow:0 0 0 2px var(--_surface),0 0 0 4px var(--_brand)}
.f img{width:100%;height:100%;object-fit:cover;object-position:50% 20%}
.t{display:grid;min-width:0;text-align:start}
.l{font-weight:600;font-size:15px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.g{font-size:13px;line-height:1.3;color:var(--_muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.g:empty{display:none}
:host([variant=face]) button{padding:0;border-radius:999px}
:host([variant=face]) .f{width:64px;height:64px;font-size:26px}
:host([variant=face]) .t{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
:host([variant=card]) button{flex-direction:column;align-items:stretch;gap:0;padding:0;border-radius:var(--_radius);width:220px;overflow:hidden}
:host([variant=card]) .f{width:100%;height:160px;border-radius:0;box-shadow:none;font-size:48px}
:host([variant=card]) .t{padding:12px 14px}
@media (prefers-reduced-motion:reduce){button{transition:none}button:hover{transform:none}}
`;

let sheet: CSSStyleSheet | null | undefined;

function styleSheet(): CSSStyleSheet | null {
  if (sheet !== undefined) return sheet;
  try {
    sheet = new CSSStyleSheet();
    sheet.replaceSync(CSS);
  } catch {
    sheet = null;
  }
  return sheet;
}

const OBSERVED = ["variant", "name", "label", "tagline", "still", "aria-label"] as const;

// A server render imports this module with no DOM; the class must still evaluate.
const Base = (globalThis.HTMLElement ?? class {}) as typeof HTMLElement;

export class VqlLauncher extends Base {
  static readonly observedAttributes = OBSERVED;
  private readonly button: HTMLButtonElement;
  private readonly face: HTMLSpanElement;
  private readonly labelEl: HTMLSpanElement;
  private readonly taglineEl: HTMLSpanElement;
  private preloaded = false;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    const s = styleSheet();
    if (s && "adoptedStyleSheets" in root) {
      root.adoptedStyleSheets = [s];
    } else {
      // Browsers without constructed stylesheets; a strict CSP refuses this
      // fallback, but every browser the widget supports has the former.
      const style = document.createElement("style");
      style.textContent = CSS;
      root.append(style);
    }
    const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, part: string) => {
      const node = document.createElement(tag);
      node.className = cls;
      node.setAttribute("part", part);
      return node;
    };
    this.button = el("button", "b", "button");
    this.button.type = "button";
    this.face = el("span", "f", "face");
    this.face.setAttribute("aria-hidden", "true");
    const text = el("span", "t", "text");
    this.labelEl = el("span", "l", "label");
    this.taglineEl = el("span", "g", "tagline");
    text.append(this.labelEl, this.taglineEl);
    this.button.append(this.face, text);
    root.append(this.button);

    this.button.addEventListener("click", () => this.fire("vql-launch"));
    const preload = () => {
      if (this.preloaded) return;
      this.preloaded = true;
      this.fire("vql-preload");
    };
    this.button.addEventListener("pointerenter", preload);
    this.button.addEventListener("focus", preload);
    this.render();
  }

  attributeChangedCallback(): void {
    this.render();
  }

  override focus(options?: FocusOptions): void {
    this.button.focus(options);
  }

  private fire(type: string): void {
    this.dispatchEvent(new CustomEvent(type, { bubbles: true, composed: true }));
  }

  private render(): void {
    const name = this.getAttribute("name") ?? "";
    const label = this.getAttribute("label") ?? (name ? `Talk to ${name}` : "Talk to us");
    this.labelEl.textContent = label;
    this.taglineEl.textContent = this.getAttribute("tagline") ?? "";
    this.button.setAttribute("aria-label", this.getAttribute("aria-label") ?? label);

    const still = this.getAttribute("still");
    const img = this.face.querySelector("img");
    if (still) {
      if (img) {
        if (img.getAttribute("src") !== still) img.src = still;
      } else {
        const next = document.createElement("img");
        next.alt = "";
        next.decoding = "async";
        next.src = still;
        this.face.replaceChildren(next);
      }
    } else {
      this.face.textContent = (name.trim().charAt(0) || "•").toUpperCase();
    }
  }
}

/** Register `<vql-launcher>` under its name, once. */
export function defineLauncher(registry: CustomElementRegistry | undefined = globalThis.customElements): void {
  if (registry && !registry.get("vql-launcher")) registry.define("vql-launcher", VqlLauncher);
}

declare global {
  interface HTMLElementTagNameMap {
    "vql-launcher": VqlLauncher;
  }
}
