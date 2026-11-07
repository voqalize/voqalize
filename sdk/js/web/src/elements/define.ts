/**
 * Register the elements. Importing a module never registers anything; call
 * `defineElements()` once (the React entry does it for you). A tag that is
 * already defined, by this or another copy of the package, is left alone.
 *
 * `defineElements()` registers the elements a call always shows. The rest
 * (`LAZY_ELEMENTS` in `lazy.ts`) load when first needed; `defineAllElements()`
 * registers those too, for a page that composes its own layout up front.
 */

import { VqlEnd } from "./end.js";
import { VqlFace } from "./face.js";
import { defineLauncher } from "./launcher.js";
import { defineLazyElements } from "./lazy.js";
import { VqlMic } from "./mic.js";
import { VqlStatus } from "./status.js";
import { VqlWidget } from "./widget.js";

/** The elements `defineElements()` registers at once. */
export const ELEMENTS: Readonly<Record<string, CustomElementConstructor>> = {
  "vql-face": VqlFace,
  "vql-mic": VqlMic,
  "vql-status": VqlStatus,
  "vql-end": VqlEnd,
  "vql-widget": VqlWidget,
};

export function defineElements(registry: CustomElementRegistry | undefined = globalThis.customElements): void {
  if (!registry) return;
  defineLauncher(registry);
  for (const [tag, ctor] of Object.entries(ELEMENTS)) {
    if (!registry.get(tag)) registry.define(tag, ctor);
  }
}

/** Register every element, the lazy ones included. Resolves when all are defined. */
export function defineAllElements(registry: CustomElementRegistry | undefined = globalThis.customElements): Promise<void> {
  defineElements(registry);
  return defineLazyElements(registry);
}
