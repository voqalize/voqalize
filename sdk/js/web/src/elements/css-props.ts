/**
 * Set style properties through the CSSOM, never through a `style` attribute.
 *
 * Lit's own `styleMap` writes a `style="…"` attribute on its first render,
 * and a strict Content-Security-Policy (`style-src` without
 * `'unsafe-inline'`) refuses that. `element.style.setProperty()` is not an
 * inline style in CSP's sense, so this element directive uses only that:
 *
 *   html`<div ${cssProps({ transform: `scale(${k})` })}></div>`
 */

import { noChange } from "lit";
import { Directive, type ElementPart, type PartInfo, PartType, directive } from "lit/directive.js";

export type CssProps = Record<string, string | number | null | undefined>;

function cssName(name: string): string {
  return name.startsWith("--") ? name : name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

class CssPropsDirective extends Directive {
  private previous = new Set<string>();

  constructor(info: PartInfo) {
    super(info);
    if (info.type !== PartType.ELEMENT) throw new Error("cssProps() goes on an element, not in an attribute");
  }

  render(_props: CssProps): unknown {
    return noChange;
  }

  override update(part: ElementPart, [props]: [CssProps]): unknown {
    const style = (part.element as HTMLElement).style;
    if (!style) return noChange;
    const next = new Set<string>();
    for (const [key, value] of Object.entries(props)) {
      const name = cssName(key);
      if (value === null || value === undefined || value === "") continue;
      next.add(name);
      style.setProperty(name, String(value));
    }
    for (const name of this.previous) if (!next.has(name)) style.removeProperty(name);
    this.previous = next;
    return noChange;
  }
}

export const cssProps = directive(CssPropsDirective);
