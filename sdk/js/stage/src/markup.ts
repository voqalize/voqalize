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
 *   (`commerce.filter`'s `{filter: Size | King}`, `commerce.variant`'s
 *   `{variant: Size | King}`).
 * - `data-stage-card`: one product card of the listing in front, in the order
 *   the listing shows them; `commerce.compare`'s `{compare: 1 | 3}` counts
 *   them from 1. Its value may be the item's path; it is not read.
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
  card: "data-stage-card",
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

/** The listing's product cards the visitor can see, in document order: card
 *  1 is the first. */
export function cards(root: ParentNode = document): HTMLElement[] {
  return [...root.querySelectorAll(`[${ATTR.card}]`)].filter(visible);
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

/** `{variant: Option | Value}`: ring the product's option, then press it. */
export const pickPart: Performer<{ option: string; value: string }> = async ({ option, value }, c) => {
  const v = (value ?? "").trim();
  if (!v) c.refuse("value", `say which ${option}`, partsOf(option));
  const el = findPart(option, v);
  if (!el || !visible(el)) return c.refuse("value", `${option} has no option "${v}" here`, partsOf(option));
  await c.scrollTo(el);
  await c.ring(el, `${option}: ${v}`);
  await c.beat();
  press(el);
  return `${option} ${v} chosen`;
};

type Place = number | string | null | undefined;

/** `{compare: 1 | 3}`: ring the listing's cards at those places, side by side,
 *  each in its own ring. Nothing on the page changes. */
export const ringCards: Performer<{ first: Place; second: Place; third?: Place; fourth?: Place }> = async (args, c) => {
  const all = cards();
  const offered = all.map((_, i) => String(i + 1));
  const picked: HTMLElement[] = [];
  const said: number[] = [];
  for (const arg of ["first", "second", "third", "fourth"] as const) {
    const raw = args[arg];
    if (raw === null || raw === undefined || String(raw).trim() === "") continue;
    const n = Number(String(raw).trim());
    if (!Number.isInteger(n) || n < 1 || n > all.length) {
      return c.refuse(arg, `the listing here shows ${all.length} card${all.length === 1 ? "" : "s"}`, offered);
    }
    if (said.includes(n)) continue;
    said.push(n);
    picked.push(all[n - 1]!);
  }
  if (picked.length < 2) return c.refuse("second", "name two cards or more to compare", offered);
  const names = picked.map((el) => (el.getAttribute(ATTR.label) ?? accessibleName(el)).trim().slice(0, 60));
  await c.scrollTo(picked[0]!);
  await c.ring(picked, { label: names.filter(Boolean).join(" · ") || undefined, separate: true });
  return `compared ${said.map((n, i) => `${n}${names[i] ? ` ${names[i]}` : ""}`).join("; ")}`;
};
