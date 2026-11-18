/**
 * The agent's moves on the Tankora site (scene.json), one performer each. Each
 * rings what it touches before anything changes, refuses with what the page
 * offers instead of guessing, changes the page only through the same store
 * actions a click uses, and returns one short line the agent can repeat.
 */
import { findThing, type MoveContext, type Performers, things } from "@voqalize/stage";
import { LEAD, MODULES, moduleById, painById, PLANS, SITE, toolLabel } from "../data/product";
import { dmy, inr, time12, weekday } from "../lib/format";
import { businessDays, repById, slotById, slotsOn, todayIst } from "../lib/calendar";
import { quote } from "../lib/pricing";
import { actions, type BookingField, isEmail, type LeadField, useSite } from "../state/store";
import { currentPath, goTo, part, thing, titleOf, waitFor } from "./host";
import type { scene } from "./scene.gen";

type Spec = typeof scene.spec;

const PAGES = Object.keys(SITE.pages);

function normalPath(path: string): string {
  let p = path.trim();
  if (!p.startsWith("/")) p = `/${p}`;
  p = p.replace(/^\/demos\/payroll_site/, "") || "/";
  return p.replace(/\/$/, "") || "/";
}

/** Open `path` the way a visitor would: ring the link that leads there, then go. */
async function open(path: string, c: MoveContext): Promise<void> {
  if (currentPath() === path) return;
  const via = path.startsWith("/modules/")
    ? thing(`module:${path.split("/")[2]}`) ?? thing("nav:/modules")
    : thing(`nav:${path}`);
  if (via) await c.ring(via, titleOf(path));
  await goTo(path);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function ringAt(c: MoveContext, el: Element | null, label: string): Promise<void> {
  if (!el) return;
  await c.scrollTo(el);
  await c.ring(el, label);
}

const leadLabel = (f: LeadField) => (LEAD.labels as Record<string, string>)[f] ?? f;
const MODULE_IDS = MODULES.map((m) => m.id);

/** Wait for the lead card to be drawn, opening it (ringed) when it is closed. */
async function leadCard(c: MoveContext): Promise<Element | null> {
  if (currentPath() !== "/") return null;
  if (!useSite.getState().leadOpen) {
    const opener = thing("lead-open") ?? thing("lead-open-hero") ?? thing("modules");
    if (opener) await c.ring(opener, "Your plan");
    actions.openLead(true);
  }
  return waitFor(() => thing("lead-card"), 900);
}

/** The value a lead field takes from a move, or a refusal. */
function leadValue(field: LeadField, value: string | null | undefined, items: string[] | null | undefined, c: MoveContext) {
  const v = (value ?? "").trim();
  switch (field) {
    case "headcount": {
      const n = Number(v.replace(/,/g, ""));
      if (!Number.isFinite(n) || n <= 0) c.refuse("value", "a headcount is a positive number");
      return { set: Math.round(n), say: String(Math.round(n)) };
    }
    case "states": {
      const list = items ?? v.split(",").map((x) => x.trim()).filter(Boolean);
      const bad = list.filter((x) => !LEAD.states.includes(x));
      if (bad.length) c.refuse("items", `not a state on the card: ${bad.join(", ")}`, LEAD.states);
      return { set: list, say: list.join(", ") };
    }
    case "pains": {
      const list = items ?? v.split(",").map((x) => x.trim()).filter(Boolean);
      const bad = list.filter((x) => !painById(x));
      if (bad.length) c.refuse("items", `not a pain the card lists: ${bad.join(", ")}`, LEAD.pains.map((p) => p.id));
      return { set: list, say: list.map((p) => painById(p)!.label.toLowerCase()).join(", ") };
    }
    case "current_tool": {
      if (!LEAD.current_tools.some((t) => t.id === v)) c.refuse("value", "not one of the card's options", LEAD.current_tools.map((t) => t.id));
      return { set: v, say: toolLabel(v).toLowerCase() };
    }
    case "recommended_plan": {
      if (!PLANS.some((p) => p.id === v)) c.refuse("value", "not a plan", PLANS.map((p) => p.id));
      return { set: v, say: PLANS.find((p) => p.id === v)!.name };
    }
    case "email":
      if (!isEmail(v)) c.refuse("value", "not an email address");
      return { set: v.toLowerCase(), say: v.toLowerCase() };
    default:
      if (!v) c.refuse("value", "nothing to put there");
      return { set: v, say: v };
  }
}

/** Open /book-demo and the day holding `day`, ringing the day first. */
async function showDay(day: string, c: MoveContext): Promise<void> {
  await open("/book-demo", c);
  const btn = await waitFor(() => part(`day:${day}`), 1500);
  if (!btn) c.refuse("day", "the calendar is not on screen");
  if (useSite.getState().booking.day !== day) {
    await ringAt(c, btn, `${weekday(day)} ${dmy(day)}`);
    actions.pickDay(day);
  }
}

const BOOKING_FIELDS: BookingField[] = ["company", "name", "headcount", "topic", "email"];

export function performers(): Performers<Spec> {
  return {
    "site.go": async ({ path }, c) => {
      const p = normalPath(path);
      const mod = /^\/modules\/(.+)$/.exec(p)?.[1];
      if (!PAGES.includes(p) && !(mod && moduleById(mod))) {
        c.refuse("path", `the site has no page ${path}`, [...PAGES, ...MODULE_IDS.map((m) => `/modules/${m}`)]);
      }
      await open(p, c);
      return `on ${p === "/" ? "the home page" : titleOf(p)}`;
    },

    "site.show": async ({ thing: name }, c) => {
      const el =
        findThing(name) ??
        c.refuse("thing", `no section "${name}" on this page`, things().map((t) => t.label).filter((l) => !/^(nav|module|plan):/.test(l)));
      await c.reveal(el);
      await ringAt(c, el, el.getAttribute("data-stage-label") ?? name);
      return `showing ${el.getAttribute("data-stage-label") ?? name}`;
    },

    "modules.show": async ({ id }, c) => {
      const m = moduleById(id.trim().toLowerCase()) ?? c.refuse("id", `no module ${id}`, MODULE_IDS);
      const el = thing(`module:${m.id}`) ?? c.refuse("id", "module cards are on the home and modules pages", ["/", "/modules"]);
      await ringAt(c, el, m.name);
      return `${m.name} ringed`;
    },

    "modules.highlight": async ({ ids }, c) => {
      const list = [...new Set(ids.map((i) => i.trim().toLowerCase()))];
      const bad = list.filter((i) => !moduleById(i));
      if (bad.length) c.refuse("ids", `no module ${bad.join(", ")}`, MODULE_IDS);
      const grid = thing("modules");
      if (!grid) {
        actions.setMatched(list);
        return `marked ${list.join(", ")} (the module cards are on the home page)`;
      }
      const marked: string[] = [];
      for (const id of list) {
        const card = thing(`module:${id}`);
        if (card) await ringAt(c, card, `Fits: ${moduleById(id)!.name}`);
        marked.push(id);
        actions.setMatched([...marked]);
      }
      return `marked ${list.map((i) => moduleById(i)!.name).join(", ")} as a fit`;
    },

    "lead.fill": async ({ field, value, items }, c) => {
      const f = field as LeadField;
      const v = leadValue(f, value, items, c);
      const card = await leadCard(c);
      if (card) {
        const row = (await waitFor(() => part(`lead:${f}`), 600)) ?? card;
        await c.ring(row, `${leadLabel(f)}: ${v.say}`);
      }
      actions.setLead(f, v.set as never);
      return `${leadLabel(f).toLowerCase()} set to ${v.say}${card ? "" : " (the lead card is on the home page)"}`;
    },

    "pricing.set": async ({ headcount, modules, billing, filing }, c) => {
      const n = Math.round(Number(headcount));
      if (!Number.isFinite(n) || n <= 0) c.refuse("headcount", "a headcount is a positive number");
      const extra = MODULES.filter((m) => m.min_plan !== "starter").map((m) => m.id);
      const mods = [...new Set(modules ?? [])];
      const bad = mods.filter((m) => !extra.includes(m));
      if (bad.length) c.refuse("modules", `not a module the calculator adds: ${bad.join(", ")}`, extra);
      await open("/pricing", c);
      const calc = (await waitFor(() => thing("calculator"), 1500)) ?? c.refuse("headcount", "the calculator is not on screen");
      await c.scrollTo(calc);
      const s = useSite.getState().pricing;
      if (s.headcount !== n) {
        await c.ring(part("pricing:headcount") ?? calc, `${n} employees`);
        actions.setPricing({ headcount: n });
      }
      for (const id of extra) {
        if (mods.includes(id) !== useSite.getState().pricing.modules.includes(id)) {
          await c.ring(part(`pricing:module:${id}`) ?? calc, moduleById(id)!.name);
          actions.togglePricingModule(id);
        }
      }
      const b = billing ?? "monthly";
      if (useSite.getState().pricing.billing !== b) {
        await c.ring(part("pricing:billing") ?? calc, b === "annual" ? "Annual billing" : "Monthly billing");
        actions.setBilling(b);
      }
      const fl = !!filing;
      if (useSite.getState().pricing.filing !== fl) {
        await c.ring(part("pricing:filing") ?? calc, fl ? "Filing service on" : "Filing service off");
        actions.setPricing({ filing: fl });
      }
      const q = quote(useSite.getState().pricing);
      c.done(q.status === "custom" ? "above 1,000 employees: custom quote" : `${q.plan_name}, ${inr(q.monthly)} a month before GST`);
      c.after(async () => {
        const total = await waitFor(() => part("line:total"), 600);
        if (total) await c.ring(total, `${inr(q.monthly_total)} a month with GST`);
      });
      return null;
    },

    "pricing.line": async ({ item }, c) => {
      const offered = () => [...document.querySelectorAll("[data-stage-part^='line:']")].map((e) => e.getAttribute("data-stage-part")!.slice(5));
      const el = part(`line:${item}`) ?? c.refuse("item", "that line is not in the breakdown on screen", offered());
      await ringAt(c, el, el.getAttribute("data-stage-label") ?? item);
      return `${item} line ringed`;
    },

    "calendar.show": async ({ day }, c) => {
      const days = businessDays(todayIst());
      if (!days.includes(day)) c.refuse("day", "not a day on the calendar", days);
      await showDay(day, c);
      const booked = useSite.getState().booked;
      const free = slotsOn(day).filter((s) => !s.taken && !booked.includes(s.id));
      c.done(`showing ${weekday(day)} ${dmy(day)}: ${free.length} free slots`);
      c.after(async () => {
        const list = await waitFor(() => thing("calendar"), 600);
        const slots = free.map((s) => part(`slot:${s.id}`)).filter((e): e is Element => !!e);
        if (slots.length) await c.ring(slots, "Free slots");
        else if (list) await c.ring(list, "No free slots");
      });
      return null;
    },

    "booking.pick": async ({ slot_id }, c) => {
      const slot = slotById(slot_id) ?? c.refuse("slot_id", "not a slot on the calendar");
      await showDay(slot.day, c);
      const el = await waitFor(() => part(`slot:${slot.id}`), 900);
      const free = slotsOn(slot.day).filter((s) => !s.taken && !useSite.getState().booked.includes(s.id)).map((s) => s.id);
      if (!el || !free.includes(slot.id)) c.refuse("slot_id", "that slot is taken", free);
      const rep = repById(slot.rep)!;
      await ringAt(c, el, `${time12(slot.time)} with ${rep.name}`);
      const why = actions.pickSlot(slot.id);
      if (why) c.refuse("slot_id", why, free);
      return `picked ${weekday(slot.day)} ${dmy(slot.day)} ${time12(slot.time)} IST with ${rep.name}`;
    },

    "booking.fill": async ({ field, value }, c) => {
      const f = field as BookingField;
      if (!BOOKING_FIELDS.includes(f)) c.refuse("field", "not a field of the booking form", BOOKING_FIELDS);
      let v = value.trim();
      if (f === "topic" && !SITE.book_page.topics.some((t) => t.id === v)) {
        c.refuse("value", "not a topic", SITE.book_page.topics.map((t) => t.id));
      }
      if (f === "email") {
        if (!isEmail(v)) c.refuse("value", "not an email address");
        v = v.toLowerCase();
      }
      if (f === "headcount" && !(Number(v) > 0)) c.refuse("value", "a headcount is a positive number");
      if (currentPath() !== "/book-demo") await open("/book-demo", c);
      const el = (await waitFor(() => part(`booking:${f}`), 1200)) ?? c.refuse("field", "the booking form is not on screen");
      const shown = f === "topic" ? SITE.book_page.topics.find((t) => t.id === v)!.label : v;
      await ringAt(c, el, shown);
      actions.setBookingField(f, v);
      return `${f} set to ${shown}`;
    },

    "booking.confirm": async (_args, c) => {
      const el = part("booking:confirm") ?? c.refuse("booking", "the booking form is not on screen");
      const missing = actions.bookingMissing();
      if (missing.length) c.refuse("booking", `still missing: ${missing.join(", ")}`, missing);
      await ringAt(c, el, "Confirm booking");
      const r = actions.confirmBooking();
      if ("missing" in r) return c.refuse("booking", `still missing: ${r.missing.join(", ")}`, r.missing);
      c.done(`booked, reference ${r.reference}`);
      c.after(async () => {
        const done = await waitFor(() => thing("booking-confirmed"), 900);
        if (done) await ringAt(c, done, r.reference);
      });
      return null;
    },
  };
}
