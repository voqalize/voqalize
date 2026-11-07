/**
 * Register the elements. Importing a module never registers anything; call
 * `defineElements()` once (the React entry does it for you). A tag that is
 * already defined, by this or another copy of the package, is left alone.
 */

import { VqlCaptions } from "./captions.js";
import { VqlCoach } from "./coach.js";
import { VqlDevices } from "./devices.js";
import { VqlEnd } from "./end.js";
import { VqlFace } from "./face.js";
import { defineLauncher } from "./launcher.js";
import { VqlMic } from "./mic.js";
import { VqlStatus } from "./status.js";
import { VqlWidget } from "./widget.js";

export const ELEMENTS: Readonly<Record<string, CustomElementConstructor>> = {
  "vql-face": VqlFace,
  "vql-mic": VqlMic,
  "vql-devices": VqlDevices,
  "vql-captions": VqlCaptions,
  "vql-coach": VqlCoach,
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
