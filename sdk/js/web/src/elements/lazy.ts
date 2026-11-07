/**
 * The elements a page pays for only when it uses them. Each is its own
 * chunk, loaded and registered the first time something needs it:
 *
 * - `vql-devices`, when the device menu opens;
 * - `vql-coach`, when a coach mark shows;
 * - `vql-captions`, when captions are on;
 * - `vql-mic-pill`, when the mic needs the visitor.
 *
 * The widget loads them itself. A page composing its own layout calls
 * `loadElement(tag)` (or `defineAllElements()`) before it uses one; React's
 * wrappers do it for you.
 */

type Loader = () => Promise<CustomElementConstructor>;

export const LAZY_ELEMENTS: Readonly<Record<string, Loader>> = {
  "vql-devices": () => import("./devices.js").then((m) => m.VqlDevices),
  "vql-coach": () => import("./coach.js").then((m) => m.VqlCoach),
  "vql-captions": () => import("./captions-feature.js").then((m) => m.VqlCaptions),
  "vql-mic-pill": () => import("./mic-pill.js").then((m) => m.VqlMicPill),
};

const loading = new Map<string, Promise<void>>();

/** Whether `tag` is one of the lazy elements. */
export function isLazyElement(tag: string): boolean {
  return Object.hasOwn(LAZY_ELEMENTS, tag);
}

/**
 * Load a lazy element's chunk and register it. Resolves once the tag is
 * defined; a tag already defined (by this or another copy) resolves at once.
 */
export function loadElement(tag: string, registry: CustomElementRegistry | undefined = globalThis.customElements): Promise<void> {
  if (!registry || registry.get(tag)) return Promise.resolve();
  const load = LAZY_ELEMENTS[tag];
  if (!load) return Promise.reject(new Error(`[vql] not a lazy element: ${tag}`));
  let pending = loading.get(tag);
  if (!pending) {
    pending = load().then((ctor) => {
      if (!registry.get(tag)) registry.define(tag, ctor);
    });
    pending.catch(() => loading.delete(tag));
    loading.set(tag, pending);
  }
  return pending;
}

/** Load and register every lazy element. */
export function defineLazyElements(registry: CustomElementRegistry | undefined = globalThis.customElements): Promise<void> {
  return Promise.all(Object.keys(LAZY_ELEMENTS).map((tag) => loadElement(tag, registry))).then(() => {});
}
