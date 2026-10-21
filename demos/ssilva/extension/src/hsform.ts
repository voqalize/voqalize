/**
 * Inside the HubSpot form frame on a Ssilva project page — the quote form.
 *
 * Each project's "cotiza" form is a HubSpot form (React, `hsfc-*` classes) in
 * a cross-origin frame from js.hsforms.net, so the page's own script cannot
 * reach into it. This script runs in that frame only when the page holding it
 * is Ssilva's (`location.ancestorOrigins`), and takes its orders from the page
 * over `postMessage`:
 *
 *   - `state`: report the form — its step, what is filled, what is empty, each
 *     dropdown's options on this project's form, and the errors it shows;
 *   - `fill`: fill in what the visitor said, the way typing would, so React's
 *     state takes it; a value for the other step is kept until that step
 *     shows; with `next_step`, press "Siguiente" once step 1 is complete.
 *
 * Every change it sees, whoever caused it — the visitor typing too — goes back
 * to the page as `{ voqalizeHs: state }`. It never presses "Enviar": that is
 * the visitor's. While `BLOCK_SUBMIT` is on, their press is reported and
 * stopped, so a preview call never sends a lead to Ssilva.
 */

declare const __SSILVA_BLOCK_SUBMIT__: boolean;

const BLOCK_SUBMIT = __SSILVA_BLOCK_SUBMIT__;
const PARENTS = /^https:\/\/(www\.)?ssilva\.cl$/;
const WAIT_MS = 4000;

/** The form's fields by the keys the brain uses, and the HubSpot names they
 *  carry. `phone` is the visible tel input of the phone field. */
const FIELDS = {
  firstname: "0-1/firstname",
  lastname: "0-1/lastname",
  rut: "0-1/rut_principal",
  email: "0-1/email",
  phone: "0-1/hs_whatsapp_phone_number",
  motivo: "0-1/motivo_de_compra",
  tipologia: "0-1/tipologia_de_interes",
  ingreso: "0-1/ingresos_liquidos",
  pie: "0-1/pie_disponible",
} as const;
type Key = keyof typeof FIELDS;
const KEYS = Object.keys(FIELDS) as Key[];
const DROPDOWNS: Key[] = ["motivo", "tipologia", "ingreso", "pie"];
const STEP_ONE: Key[] = ["firstname", "lastname", "rut", "email", "phone", "motivo"];

type Fill = Partial<Record<Key, string | null>> & { next_step?: boolean };

interface State {
  step: "contact" | "details" | "sent";
  filled: Partial<Record<Key, string>>;
  missing: Key[];
  options: Partial<Record<Key, string[]>>;
  errors: string[];
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/** For matching what the brain said against an option: case, accents and
 *  spacing aside. */
const norm = (s: string | null | undefined) =>
  clean(s)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[.:?!¿¡\s]+$/, "")
    // A range said "entre 2 y 5 millones" reads "Entre $2.000.000 a $5.000.000".
    .replace(/\s(y|hasta|to|and)\s/g, " a ");
/** The same, with only letters and digits: "$2.000.000" is "2000000". */
const bare = (s: string | null | undefined) => norm(s).replace(/[^a-z0-9]/g, "");

async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(80);
  }
}

function parentOrigin(): string | null {
  const origins = location.ancestorOrigins;
  const top = origins && origins.length ? origins[0] : "";
  return PARENTS.test(top) ? top : null;
}

// ─── Reading the form ───────────────────────────────────────────────────

const shown = (el: Element | null | undefined): el is HTMLElement =>
  !!el && (el as HTMLElement).getClientRects().length > 0;

/** The field (`.hsfc-*Field`) holding HubSpot's input `name`. */
function fieldBox(key: Key): HTMLElement | null {
  const input = document.querySelector<HTMLInputElement>(`input[name="${FIELDS[key]}"]`);
  return input?.closest<HTMLElement>("[class*='Field']") ?? null;
}

/** The input the visitor types in or sees: the text input, the phone's
 *  visible tel input, or a dropdown's combobox. */
function visibleInput(key: Key): HTMLInputElement | null {
  if (key === "phone") return fieldBox(key)?.querySelector<HTMLInputElement>("input[type=tel]") ?? null;
  if (DROPDOWNS.includes(key)) return fieldBox(key)?.querySelector<HTMLInputElement>("input.hsfc-TextInput--button") ?? null;
  return document.querySelector<HTMLInputElement>(`input[name="${FIELDS[key]}"]`);
}

function value(key: Key): string {
  const shownValue = clean(visibleInput(key)?.value);
  if (key === "phone") {
    // The tel input holds the national number; an untouched one may hold
    // only the country code the picker put there.
    const hidden = clean(document.querySelector<HTMLInputElement>(`input[name="${FIELDS.phone}"]`)?.value);
    return hidden && shownValue ? shownValue : "";
  }
  return shownValue || clean(document.querySelector<HTMLInputElement>(`input[name="${FIELDS[key]}"]`)?.value);
}

function options(key: Key): string[] {
  const box = fieldBox(key);
  if (!box) return [];
  return [...box.querySelectorAll("[role=option]")].map((o) => clean(o.textContent)).filter(Boolean);
}

function form(): HTMLFormElement | null {
  return document.querySelector<HTMLFormElement>("form.hsfc-Form, form");
}

const button = (label: RegExp) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => shown(b) && label.test(clean(b.textContent))) ??
  null;
const submitButton = () => document.querySelector<HTMLButtonElement>("form button[type=submit]");

function step(): State["step"] {
  // After a real "Enviar" HubSpot swaps the form for its thank-you message.
  if (document.querySelector("[class*='PostSubmit'], [class*='ThankYou'], [class*='SubmittedMessage']")) return "sent";
  const f = form();
  if (!f) return "sent";
  if (shown(visibleInput("firstname"))) return "contact";
  if (DROPDOWNS.slice(1).some((k) => shown(fieldBox(k)))) return "details";
  return "contact";
}

function state(): State {
  const filled: State["filled"] = {};
  const missing: Key[] = [];
  const opts: State["options"] = {};
  for (const key of KEYS) {
    if (!fieldBox(key)) continue;
    const v = value(key);
    if (v) filled[key] = v;
    else missing.push(key);
    if (DROPDOWNS.includes(key)) opts[key] = options(key);
  }
  const errors = [...document.querySelectorAll(".hsfc-ErrorAlert")]
    .filter(shown)
    .map((e) => {
      const label = clean(e.closest("[class*='Field']")?.querySelector("label")?.textContent).replace(/\*$/, "");
      const text = clean(e.textContent);
      return label ? `${label}: ${text}` : text;
    })
    .filter(Boolean);
  return { step: step(), filled, missing, options: opts, errors };
}

// ─── Acting in it ───────────────────────────────────────────────────────

/** Set a value the way typing would, so React's state takes it. */
function type(el: HTMLInputElement, text: string): void {
  el.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, text);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
  el.blur();
}

/** The option `said` names: the same words, then one that starts with them,
 *  then one that holds them. */
function findOption(key: Key, said: string): HTMLElement | null {
  const all = [...(fieldBox(key)?.querySelectorAll<HTMLElement>("[role=option]") ?? [])];
  const want = norm(said);
  const wantBare = bare(said);
  if (!want) return null;
  const t = (o: HTMLElement) => norm(o.textContent);
  const b = (o: HTMLElement) => bare(o.textContent);
  return (
    all.find((o) => t(o) === want) ??
    all.find((o) => wantBare && b(o) === wantBare) ??
    all.find((o) => t(o).startsWith(want)) ??
    all.find((o) => t(o).includes(want)) ??
    all.find((o) => wantBare.length > 2 && b(o).includes(wantBare)) ??
    all.find((o) => t(o).length > 2 && want.includes(t(o))) ??
    null
  );
}

async function choose(key: Key, said: string): Promise<string | null> {
  const box = fieldBox(key);
  const combo = visibleInput(key);
  if (!box || !combo) return `the form has no ${key} question`;
  const option = findOption(key, said);
  if (!option) return `"${said}" is not an option for ${key}; the options are: ${options(key).join(" | ")}`;
  if (norm(value(key)) === norm(option.textContent)) return null;
  combo.click();
  await waitFor(() => combo.getAttribute("aria-expanded") === "true" || shown(option), 1500);
  // Picked in the same tick as it opened, the list takes the pick and stays open.
  await sleep(200);
  option.click();
  await waitFor(() => norm(value(key)) === norm(option.textContent), 1500);
  await sleep(200);
  // A list left open covers the fields below it.
  const list = () => shown(box.querySelector("[role=listbox]"));
  if (list()) {
    combo.click();
    await sleep(200);
  }
  if (list()) close(combo);
  return norm(value(key)) === norm(option.textContent) ? null : `${key} did not take "${clean(option.textContent)}"`;
}

/** Close a dropdown's list the way a visitor would: Escape. */
function close(combo: HTMLInputElement): void {
  for (const type of ["keydown", "keyup"]) {
    combo.dispatchEvent(new KeyboardEvent(type, { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
  }
}

/** What the visitor said, kept until its step shows. */
let pending: Partial<Record<Key, string>> = {};

/** Fill every pending field on the step that shows; keep the rest. The
 *  problems, as words. */
async function applyPending(): Promise<string[]> {
  const problems: string[] = [];
  for (const key of KEYS) {
    const said = pending[key];
    if (!said) continue;
    const box = fieldBox(key);
    if (!box) {
      delete pending[key];
      problems.push(`this form has no ${key} question`);
      continue;
    }
    if (!shown(box)) continue;
    delete pending[key];
    if (DROPDOWNS.includes(key)) {
      const why = await choose(key, said);
      if (why) problems.push(why);
    } else {
      const el = visibleInput(key);
      if (el && clean(el.value) !== clean(said)) type(el, said);
    }
    await sleep(60);
  }
  return problems;
}

async function fill(order: Fill): Promise<string | null> {
  for (const key of KEYS) {
    const v = order[key];
    if (typeof v === "string" && v.trim()) pending[key] = v.trim();
  }
  const problems = await applyPending();
  if (order.next_step && step() === "contact") {
    const empty = STEP_ONE.filter((k) => fieldBox(k) && !value(k));
    if (empty.length) {
      problems.push(`step 1 still needs: ${empty.join(", ")}`);
    } else {
      const next = button(/^siguiente$/i);
      if (!next) problems.push("there is no Siguiente button on this form");
      else {
        next.click();
        const moved = await waitFor(() => step() === "details", 2500);
        if (!moved) {
          const errs = state().errors;
          problems.push(`the form stayed on step 1${errs.length ? `: ${errs.join("; ")}` : ""}`);
        } else {
          await sleep(200);
          problems.push(...(await applyPending()));
        }
      }
    }
  }
  const left = Object.keys(pending);
  if (left.length && !order.next_step && step() === "contact") {
    // Kept for step 2; said so the brain knows they are not on screen yet.
    problems.push(`kept for step 2, after Siguiente: ${left.join(", ")}`);
  }
  return problems.length ? problems.join("; ") : null;
}

// ─── Talking to the page ────────────────────────────────────────────────

function start(): void {
  const parent = parentOrigin();
  if (!parent) return;
  let last = "";
  const report = (force = false) => {
    if (!form()) return;
    const s = state();
    const key = JSON.stringify(s);
    if (!force && key === last) return;
    const initial = !last;
    last = key;
    window.parent.postMessage({ voqalizeHs: { ...s, initial } }, parent);
  };

  window.addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== parent || e.source !== window.parent) return;
    const msg = (e.data as { voqalizeHsCmd?: { id: number; cmd: string; fill?: Fill } })?.voqalizeHsCmd;
    if (!msg) return;
    const reply = (error: string | null) => {
      const s = state();
      last = JSON.stringify(s);
      window.parent.postMessage({ voqalizeHsDone: { id: msg.id, error, state: s } }, parent);
    };
    if (!form()) return reply("the form has not loaded yet");
    if (msg.cmd === "state") return reply(null);
    if (msg.cmd === "fill") {
      void fill(msg.fill ?? {})
        .catch((error: unknown) => String(error))
        .then((error) => reply(error));
    }
  });

  // What the visitor typed or picked, and the step they moved to: reported
  // as it settles. A step that appears takes what was kept for it.
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastStep = step();
  const settle = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const now = step();
      if (now !== lastStep) {
        lastStep = now;
        if (Object.keys(pending).length) void applyPending().then(() => report());
      }
      report();
    }, 400);
  };
  new MutationObserver(settle).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["value", "aria-invalid", "style", "class"],
  });
  document.addEventListener("input", settle, true);
  document.addEventListener("change", settle, true);
  document.addEventListener("focusout", settle, true);

  // "Enviar" is the visitor's. In a preview it is reported, then stopped.
  const onSubmit = (e: Event) => {
    if (e.type === "click") {
      const b = (e.target as Element | null)?.closest?.("button");
      if (!b || b !== submitButton()) return;
    }
    window.parent.postMessage({ voqalizeHsSubmitted: { blocked: BLOCK_SUBMIT, state: state() } }, parent);
    if (!BLOCK_SUBMIT) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    note();
  };
  window.addEventListener("click", onSubmit, true);
  window.addEventListener("submit", onSubmit, true);
  // Enter in a field submits a form without a click on its button.
  window.addEventListener(
    "keydown",
    (e: KeyboardEvent) => {
      if (!BLOCK_SUBMIT || e.key !== "Enter") return;
      const t = e.target as HTMLElement | null;
      if (!t || t.tagName !== "INPUT" || t.getAttribute("role") === "combobox" || t.getAttribute("role") === "searchbox") return;
      if (step() !== "details") return;
      e.preventDefault();
      e.stopImmediatePropagation();
    },
    true,
  );

  report(true);
}

/** Say, under the form, that the press went nowhere. A block of its own after
 *  the form, so the form's own layout is untouched. */
function note(): void {
  const f = form();
  if (!f || document.querySelector("[data-voqalize=toast]")) return;
  const p = document.createElement("p");
  p.setAttribute("data-voqalize", "toast");
  p.textContent = "Vista previa: este formulario no se envió a Ssilva.";
  Object.assign(p.style, {
    display: "block",
    margin: "12px 0 0",
    padding: "8px 12px",
    borderRadius: "8px",
    background: "#ffffff",
    color: "#192965",
    font: "600 13px/1.4 system-ui, sans-serif",
    textAlign: "center",
  });
  f.insertAdjacentElement("afterend", p);
  setTimeout(() => p.remove(), 6000);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
else start();

export {};
