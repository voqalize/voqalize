/**
 * `data-stage-*`: a page names its things in its own markup, and the stock
 * performers act on them, with no code of the site's.
 *
 * ```html
 * <body data-stage-place="catalog">
 *   <section data-stage-thing="rooms" data-stage-label="Our rooms">…</section>
 *   <aside data-stage-thing="filters">
 *     <a data-stage-part="Size:King">King</a> <a data-stage-part="Color:Blanco">Blanco</a>
 *   </aside>
 * ```
 *
 * - `data-stage-thing="name"`: a thing the agent can point at; its spoken
 *   label is `data-stage-label`, else its accessible name.
 * - `data-stage-part="Facet:Option"`: one option a move presses
 *   (`commerce.filter`'s `{filter: Size | King}`).
 * - `data-stage-place="name"`: where the page is, in the app's own terms.
 *
 * The attributes are locators only. They add no moves, labels or prompt text:
 * the moves are the spec's, and the agent names a thing by what the visitor
 * sees. A name matches its label folded (case, Latin accents), whole first,
 * then as the label's start.
 */

import { accessibleName, press, visible } from "./dom.js";
import type { Performer } from "./moves.js";
import { fold } from "./words.js";

export const ATTR = {
  thing: "data-stage-thing",
  label: "data-stage-label",
  part: "data-stage-part",
  place: "data-stage-place",
} as const;

export interface Thing {
  name: string;
  label: string;
  el: Element;
}

/** The things the page names, in document order. */
export function things(root: ParentNode = document): Thing[] {
  return [...root.querySelectorAll(`[${ATTR.thing}]`)].map((el) => ({
    name: el.getAttribute(ATTR.thing) ?? "",
    label: (el.getAttribute(ATTR.label) ?? accessibleName(el)).trim(),
    el,
  }));
}

/** The thing a said name points at: by its name, then its label whole, then
 *  the label's start; `null` when none does. */
export function findThing(said: string, root: ParentNode = document): Element | null {
  const want = fold(said.trim());
  if (!want) return null;
  const all = things(root);
  return (
    all.find((t) => fold(t.name) === want)?.el ??
    all.find((t) => fold(t.label) === want)?.el ??
    all.find((t) => fold(t.label).startsWith(want))?.el ??
    null
  );
}

/** The option `value` of `facet`, as `data-stage-part="Facet:Value"` names it. */
export function findPart(facet: string, value: string, root: ParentNode = document): Element | null {
  const want = `${fold(facet.trim())}:${fold(value.trim())}`;
  for (const el of root.querySelectorAll(`[${ATTR.part}]`)) {
    const [f = "", ...v] = (el.getAttribute(ATTR.part) ?? "").split(":");
    if (`${fold(f.trim())}:${fold(v.join(":").trim())}` === want) return el;
  }
  return null;
}

/** The options a facet offers, as the page names them. */
export function partsOf(facet: string, root: ParentNode = document): string[] {
  const want = fold(facet.trim());
  return [...root.querySelectorAll(`[${ATTR.part}]`)]
    .map((el) => (el.getAttribute(ATTR.part) ?? "").split(":"))
    .filter(([f = ""]) => fold(f.trim()) === want)
    .map(([, ...v]) => v.join(":").trim());
}

/** Where the page says it is, if it says. */
export function place(root: Document = document): string | null {
  return root.querySelector(`[${ATTR.place}]`)?.getAttribute(ATTR.place) ?? null;
}

/** `{show: Name}`: scroll to the thing named and ring it. */
export const showThing: Performer<{ target: string }> = async ({ target }, c) => {
  const el = findThing(target);
  if (!el) return c.refuse("target", `nothing here is called "${target}"`, things().map((t) => t.label).filter(Boolean));
  await c.reveal(el);
  await c.scrollTo(el);
  await c.ring(el, things().find((t) => t.el === el)?.label);
  return `showed ${target}`;
};

/** `{filter: Facet | Option[, Option]}`: ring each option, then press it. */
export const pressParts: Performer<{ facet: string; value?: string | null }> = async ({ facet, value }, c) => {
  const values = (value ?? "").split(",").map((v) => v.trim()).filter(Boolean);
  if (!values.length) c.refuse("value", "say which option", partsOf(facet));
  const done: string[] = [];
  for (const v of values) {
    const el = findPart(facet, v);
    if (!el || !visible(el)) return c.refuse("value", `${facet} has no option "${v}" here`, partsOf(facet));
    await c.scrollTo(el);
    await c.ring(el, `${facet}: ${v}`);
    await c.beat();
    press(el);
    done.push(v);
  }
  return `${facet} ${done.join(", ")} pressed`;
};
