/**
 * What the visitor does on the page by themselves, for a site that wants the
 * agent to know: the part of the page they stay on, and the forms they fill
 * in. Off unless a site starts them; each reports through a callback, which the
 * site (or the script host) turns into the `watch` kit's state events.
 *
 * - A **part of the page** is a `data-stage-thing`. The one taking most of the
 *   window, held for `dwellMs`, is where they are reading; a scroll past it is
 *   nothing. The same part twice in a row is reported once.
 * - A **form** is a `<form data-stage-form="Enquiry">`. Typing is gathered
 *   until they pause (`quietMs`), then reported once: the names of the fields
 *   that hold something and of the required ones still empty. Never a value,
 *   whatever the field.
 */

import { accessibleName } from "./dom.js";
import { ATTR } from "./markup.js";

export interface Viewed {
  thing: string;
  label: string;
}

export interface FormState {
  form: string;
  filled: string[];
  missing: string[];
  left: number;
  done: boolean;
}

export interface WatchOptions {
  root?: Document;
  /** How long a part must hold the window to count (default 1500 ms). */
  dwellMs?: number;
  /** How long typing must pause before a form is reported (default 1200 ms). */
  quietMs?: number;
}

/** The share of the window `el` takes, from 0 to 1. */
function share(el: Element, view: { w: number; h: number }): number {
  const r = el.getBoundingClientRect();
  const w = Math.max(0, Math.min(r.right, view.w) - Math.max(r.left, 0));
  const h = Math.max(0, Math.min(r.bottom, view.h) - Math.max(r.top, 0));
  return (w * h) / Math.max(1, view.w * view.h);
}

/** Report the part of the page the visitor stays on. Returns a stop. */
export function watchThings(report: (v: Viewed) => void, opts: WatchOptions = {}): () => void {
  const doc = opts.root ?? document;
  const win = doc.defaultView ?? window;
  const dwell = opts.dwellMs ?? 1500;
  let candidate: Element | null = null;
  let reported: Element | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const check = () => {
    const view = { w: win.innerWidth, h: win.innerHeight };
    let best: Element | null = null;
    let most = 0.15; // a sliver is not reading
    for (const el of doc.querySelectorAll(`[${ATTR.thing}]`)) {
      const s = share(el, view);
      if (s > most) [best, most] = [el, s];
    }
    if (best === candidate) return;
    candidate = best;
    clearTimeout(timer);
    if (!best || best === reported) return;
    timer = setTimeout(() => {
      if (candidate !== best) return;
      reported = best;
      const label = (best.getAttribute(ATTR.label) ?? accessibleName(best)).trim().slice(0, 80);
      report({ thing: best.getAttribute(ATTR.thing) ?? "", label });
    }, dwell);
  };
  let pending: ReturnType<typeof setTimeout> | undefined;
  const soon = () => {
    clearTimeout(pending);
    pending = setTimeout(check, 150);
  };
  win.addEventListener("scroll", soon, { passive: true });
  win.addEventListener("resize", soon);
  check();
  return () => {
    win.removeEventListener("scroll", soon);
    win.removeEventListener("resize", soon);
    clearTimeout(timer);
    clearTimeout(pending);
  };
}

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

function fieldsOf(form: HTMLFormElement): Field[] {
  return [...form.elements].filter(
    (el): el is Field =>
      (el instanceof HTMLInputElement && !["hidden", "submit", "button", "reset", "image"].includes(el.type)) ||
      el instanceof HTMLSelectElement ||
      el instanceof HTMLTextAreaElement,
  );
}

const nameOf = (f: Field) => f.name || f.id || f.getAttribute("aria-label") || "";

function holds(f: Field): boolean {
  if (f instanceof HTMLInputElement && (f.type === "checkbox" || f.type === "radio")) return f.checked;
  return f.value.trim() !== "";
}

/** The form's state by field name: what holds something, what required is
 *  still empty. Never a value. */
export function formState(form: HTMLFormElement): FormState {
  const fields = fieldsOf(form).filter((f) => nameOf(f));
  const filled = [...new Set(fields.filter(holds).map(nameOf))];
  const missing = [...new Set(fields.filter((f) => f.required && !holds(f)).map(nameOf))];
  const name = form.getAttribute("data-stage-form") || form.getAttribute("aria-label") || form.name || form.id || "the form";
  return { form: name, filled, missing, left: missing.length, done: missing.length === 0 };
}

/** Report each `form[data-stage-form]` once the visitor pauses in it.
 *  Returns a stop. */
export function watchForms(report: (s: FormState) => void, opts: WatchOptions = {}): () => void {
  const doc = opts.root ?? document;
  const quiet = opts.quietMs ?? 1200;
  const timers = new Map<HTMLFormElement, ReturnType<typeof setTimeout>>();
  const last = new Map<HTMLFormElement, string>();
  const changed = (e: Event) => {
    const form = (e.target as Element | null)?.closest?.("form[data-stage-form]") as HTMLFormElement | null;
    if (!form) return;
    clearTimeout(timers.get(form));
    timers.set(
      form,
      setTimeout(() => {
        const state = formState(form);
        const key = JSON.stringify(state);
        if (last.get(form) === key) return;
        last.set(form, key);
        report(state);
      }, quiet),
    );
  };
  doc.addEventListener("input", changed, true);
  doc.addEventListener("change", changed, true);
  return () => {
    doc.removeEventListener("input", changed, true);
    doc.removeEventListener("change", changed, true);
    for (const t of timers.values()) clearTimeout(t);
  };
}
