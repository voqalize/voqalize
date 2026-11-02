/**
 * The returns form's Stage performers: Emily's moves, made on the form as her
 * voice reaches them. Each rings what it touches before anything changes,
 * refuses with the values the form offers instead of guessing, and returns one
 * short line she can repeat. They write the same store the shopper's clicks
 * do; email is never a move, and nothing here ever submits.
 */
import type { MoveContext, Performers } from "@voqalize/stage";
import { getProduct } from "../data/catalog";
import { CHOICE_FIELDS, CHOICES, type ChoiceField, eligibility, exchangeOptions, findOrder, labelOf, normalOrderNumber, STEPS } from "../returns/orders";
import { currentOrder, firstMissing, missingFields, missingInStep, storedReturns, useReturns } from "../returns/store";
import type { scene } from "./scene.gen";

type Spec = typeof scene.spec;

/** Every field a move may set, by the names the form uses. */
function fillableFields(): string[] {
  const order = currentOrder(useReturns.getState());
  const exchange = order?.lines.map((l) => `exchange_variant_${l.product_id}`) ?? [];
  return ["order_number", "email", ...CHOICE_FIELDS, ...exchange];
}

const stepEl = (n: number) => document.querySelector(`[data-stage-thing="step-${n}"]`);
const partEl = (field: string, value: string) => document.querySelector(`[data-stage-part="${CSS.escape(`${field}:${value}`)}"]`);

/** Wait for React to put `find()` on the page (a step that just opened). */
async function appear(find: () => Element | null, ms = 900): Promise<Element | null> {
  const end = Date.now() + ms;
  for (;;) {
    const el = find();
    if (el || Date.now() > end) return el;
    await new Promise((r) => setTimeout(r, 25));
  }
}

/**
 * Bring a step on screen: ring its heading first, then open it. The ring
 * comes before the change, as every move's does.
 */
async function openStep(step: number, c: MoveContext): Promise<void> {
  const s = useReturns.getState();
  if (s.step === step) return;
  const el = stepEl(step);
  if (el) {
    await c.scrollTo(el);
    await c.ring(el, STEPS[step - 1].title);
  }
  useReturns.getState().setStep(step);
}

const STEP_OF: Record<string, number> = {
  order_number: 1,
  reason: 3,
  condition: 3,
  resolution: 4,
  collection: 5,
  pickup_window: 5,
};

/** A label as Emily would say it back: "It doesn't suit the room" → "doesn't suit the room". */
const spoken = (label: string) => label.replace(/^(It's|It|I'll|I)\s+/, "").replace(/^./, (ch) => ch.toLowerCase());

/** The returns form's moves; the listing pages' are in ./listing.ts. */
export type ReturnsPerformers = Pick<Performers<Spec>, Extract<keyof Performers<Spec>, `returns.${string}`>>;

export function returnsPerformers(): ReturnsPerformers {
  return {
    "returns.open_step": async ({ step }, c) => {
      const n = Number(step);
      if (!Number.isInteger(n) || n < 1 || n > 6) c.refuse("step", "the form has six steps", ["1", "2", "3", "4", "5", "6"]);
      const reached = useReturns.getState().reached;
      if (n > reached) {
        c.refuse("step", `step ${n} is not reached yet; the form has reached step ${reached}`, Array.from({ length: reached }, (_, i) => String(i + 1)));
      }
      const el = stepEl(n) ?? c.refuse("step", "the returns form is not on screen");
      await c.scrollTo(el);
      await c.ring(el, STEPS[n - 1].title);
      useReturns.getState().setStep(n);
      return `opened step ${n}, ${STEPS[n - 1].title.toLowerCase()}`;
    },

    "returns.fill": async ({ field, value }, c) => {
      const f = field.trim();
      const v = value.trim();
      if (!stepEl(1)) c.refuse("field", "the returns form is not on screen");

      if (f === "email") {
        if (!/^\S+@\S+\.\S+$/.test(v)) c.refuse("value", `"${v}" is not an email address`);
        await openStep(1, c);
        const input = (await appear(() => document.querySelector('input[name="email"]'))) ?? c.refuse("field", "the email field is not on screen");
        await c.scrollTo(input);
        await c.ring(input, "Email");
        useReturns.getState().setEmail(v, "emily");
        return "email set";
      }

      if (f === "order_number") {
        const number = normalOrderNumber(v);
        if (!findOrder(number)) c.refuse("value", `there is no order ${number}`);
        await openStep(1, c);
        const input = (await appear(() => document.querySelector('input[name="order_number"]'))) ?? c.refuse("field", "the order field is not on screen");
        await c.scrollTo(input);
        await c.ring(input, "Order number");
        useReturns.getState().setOrderNumber(number, "emily");
        return `order number set to ${number}`;
      }

      if (f.startsWith("exchange_variant_")) {
        const productId = f.slice("exchange_variant_".length);
        const order = currentOrder(useReturns.getState()) ?? c.refuse("field", "find the order first");
        const line = order.lines.find((l) => l.product_id === productId) ?? c.refuse("field", "that item is not in this order", order.lines.map((l) => `exchange_variant_${l.product_id}`));
        const options = exchangeOptions(line);
        const pick = options.find((o) => o.toLowerCase() === v.toLowerCase()) ?? c.refuse("value", `${line.title} comes in ${options.join(", ") || "no other option"}`, options);
        await openStep(4, c);
        const s = useReturns.getState();
        if (s.resolution !== "exchange" || !s.items[productId]) {
          const res = (await appear(() => partEl("resolution", "exchange"))) ?? c.refuse("field", "the resolution step is not on screen");
          await c.ring(res, "Exchange");
          if (!s.items[productId]) useReturns.getState().setItem(productId, 1, "emily");
          useReturns.getState().setChoice("resolution", "exchange", "emily");
        }
        const el = (await appear(() => partEl(f, pick))) ?? c.refuse("field", "the exchange options are not on screen");
        await c.scrollTo(el);
        await c.ring(el, `${line.title}: ${pick}`);
        useReturns.getState().setExchange(productId, pick, "emily");
        return `exchange set to ${pick} for the ${line.title.toLowerCase()}`;
      }

      if (f.startsWith("qty_")) c.refuse("field", "choose items and how many with the item move", fillableFields());

      if (!(CHOICE_FIELDS as string[]).includes(f)) c.refuse("field", `the form has no field "${f}"`, fillableFields());
      const choice = f as ChoiceField;
      const values = CHOICES[choice].map(([x]) => x as string);
      if (!values.includes(v)) c.refuse("value", `${choice} is one of ${values.join(", ")}`, values);
      if (choice === "pickup_window" && useReturns.getState().collection !== "pickup") {
        c.refuse("field", "a collection window applies only to a pickup; set collection to pickup first", ["collection"]);
      }
      await openStep(STEP_OF[choice], c);
      const el = (await appear(() => partEl(choice, v))) ?? c.refuse("field", `${choice} is not on screen`);
      await c.scrollTo(el);
      await c.ring(el, labelOf(choice, v));
      useReturns.getState().setChoice(choice, v, "emily");
      return `${choice.replace("_", " ")} set to ${spoken(labelOf(choice, v))}`;
    },

    "returns.submit": async (_args, c) => {
      if (!stepEl(1)) c.refuse("form", "the returns form is not on screen");
      const gap = firstMissing(useReturns.getState());
      if (gap) c.refuse("form", `step ${gap.step}, ${STEPS[gap.step - 1].title.toLowerCase()}: ${gap.why}`);
      await openStep(6, c);
      const button = (await appear(() => document.querySelector('.rform button[type="submit"]'))) ?? c.refuse("form", "the review step is not on screen");
      await c.scrollTo(button);
      await c.ring(button, "Submit return");
      const before = storedReturns().length;
      (button as HTMLButtonElement).click();
      const made = await appear(() => (storedReturns().length > before ? document.body : null), 1500);
      const ref = storedReturns().at(-1)?.reference;
      return made && ref ? `return submitted, reference ${ref}` : "submit pressed";
    },

    "returns.find": async ({ order_number, email }, c) => {
      if (!stepEl(1)) c.refuse("order_number", "the returns form is not on screen");
      const number = normalOrderNumber(order_number);
      const mail = (email ?? "").trim();
      await openStep(1, c);
      const numberInput = (await appear(() => document.querySelector('input[name="order_number"]'))) ?? c.refuse("order_number", "the order field is not on screen");
      await c.scrollTo(numberInput);
      await c.ring(numberInput, "Order number");
      useReturns.getState().setOrderNumber(number, "emily");
      if (mail) {
        const emailInput = (await appear(() => document.querySelector('input[name="email"]'))) ?? c.refuse("email", "the email field is not on screen");
        await c.ring(emailInput, "Email");
        useReturns.getState().setEmail(mail, "emily");
      }
      // The same lookup as the Find / Continue button.
      const order = findOrder(number) ?? c.refuse("order_number", `there is no order ${number}`);
      if (!mail) c.refuse("email", `say the email used for order ${number}`);
      if (mail.toLowerCase() !== order.email.toLowerCase()) c.refuse("email", `that email does not match order ${number}`);
      const e = eligibility(order);
      if (e.kind === "not_delivered") c.refuse("order_number", `order ${number} has not been delivered yet, so it cannot be returned yet`);
      if (e.kind === "outside_window") c.refuse("order_number", `order ${number} was delivered ${e.days} days ago, outside the 30-day window`);
      useReturns.getState().setStep(2);
      const items = order.lines.reduce((n, l) => n + l.qty, 0);
      return `found ${number}, ${items} item${items === 1 ? "" : "s"}; on step 2, items`;
    },

    "returns.next_step": async (_args, c) => {
      if (!stepEl(1)) c.refuse("step", "the returns form is not on screen");
      const s = useReturns.getState();
      if (s.step >= 6) c.refuse("step", "the form is already on step 6, review; the shopper's yes submits it");
      const missing = missingFields(s, s.step);
      const why = missingInStep(s, s.step);
      if (missing.length || why) {
        c.refuse("step", `step ${s.step}, ${STEPS[s.step - 1].title.toLowerCase()}, still needs ${missing.join(", ") || "attention"}: ${why}`, missing);
      }
      const button = document.querySelector('.rstep.is-open .rstep-actions [data-dock-avoid]') ?? stepEl(s.step);
      if (button) {
        await c.scrollTo(button);
        await c.ring(button, "Continue");
      }
      const next = s.step + 1;
      useReturns.getState().setStep(next);
      return `on step ${next}, ${STEPS[next - 1].title.toLowerCase()}`;
    },

    "returns.select_item": async ({ product_id, qty }, c) => {
      const order = currentOrder(useReturns.getState()) ?? c.refuse("product_id", "find the order first: fill order_number");
      const ids = order.lines.map((l) => l.product_id);
      const line = order.lines.find((l) => l.product_id === product_id.trim()) ?? c.refuse("product_id", "that item is not in this order", ids);
      const ok = eligibility(order);
      if (ok.kind === "not_delivered") c.refuse("product_id", "this order has not been delivered yet, so it cannot be returned yet");
      if (ok.kind === "outside_window") c.refuse("product_id", `this order was delivered ${ok.days} days ago, outside the 30-day window`);
      // The wire may carry "1" for 1: coerce before judging it.
      const raw = qty as unknown;
      const n = raw == null || raw === "" ? 1 : Number(String(raw).trim());
      if (!Number.isInteger(n) || n < 0 || n > line.qty) {
        c.refuse("qty", `between 1 and ${line.qty}, or 0 to take it off`, Array.from({ length: line.qty + 1 }, (_, i) => String(i)));
      }
      await openStep(2, c);
      const el = (await appear(() => partEl("items", line.product_id))) ?? c.refuse("product_id", "the items step is not on screen");
      await c.scrollTo(el);
      const title = getProduct(line.product_id)?.title ?? line.title;
      await c.ring(el, title);
      useReturns.getState().setItem(line.product_id, n, "emily");
      return n === 0 ? `took the ${title.toLowerCase()} off the return` : `returning ${n} × ${title.toLowerCase()}`;
    },
  };
}
