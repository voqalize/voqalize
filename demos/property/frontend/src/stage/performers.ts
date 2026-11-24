/**
 * The agent's moves on Kosha Homes (scene.json), one performer each. Each
 * rings what it touches before anything changes, refuses with what the page
 * offers instead of guessing, writes the same store a click does, and returns
 * one short line the agent can repeat.
 */
import type { MoveContext, Performers } from "@voqalize/stage";
import {
  ALL_AMENITIES,
  CITIES,
  type CityId,
  cleanFilters,
  dateLabel,
  EMI_DEFAULTS,
  emi,
  FILTER_KEYS,
  type Filters,
  getCity,
  getLender,
  getListing,
  getProject,
  LENDERS,
  LISTINGS,
  officesOf,
  placeName,
  priceLabel,
  search,
  slotsFor,
  timeLabel,
  visitDays,
  weekdayLabel,
} from "../data/homes";
import { bookVisit, pickSlot, slotProblem } from "../state/actions";
import { emiOf, takenSlots, useStore } from "../state/store";
import { currentPath, goTo, moves, part, thing, waitFor } from "./host";
import { scene } from "./scene.gen";

type Spec = typeof scene.spec;

const phone = () => window.matchMedia("(max-width: 899px)").matches;

/** X1: show the target's whole group (`c.scrollTo` is `showWhole`, see host.ts), then ring it. */
async function ringScroll(c: MoveContext, el: Element | null | undefined, label: string): Promise<void> {
  if (!el) return;
  await c.scrollTo(el);
  await c.ring(el, label);
}

function listingOr(c: MoveContext, id: string) {
  return getListing(id) ?? c.refuse("listing_id", `there is no listing ${id}`, LISTINGS.slice(0, 12).map((l) => l.id));
}

const PATHS = /^\/(listings|compare|shortlist|visits|listing\/[A-Z]{3}-\d+|project\/[a-z-]+)?$/;

function normalPath(path: string): string {
  let p = path.trim();
  if (!p.startsWith("/")) p = `/${p}`;
  p = p.replace(/^\/demos\/property/, "") || "/";
  p = p.replace(/\/$/, "") || "/";
  const m = /^\/listing\/(.+)$/i.exec(p);
  if (m) p = `/listing/${m[1].toUpperCase()}`;
  return p;
}

/** Each filter key's control, in sidebar order, for the values that changed. */
function changedControls(before: Filters, after: Filters): { key: keyof Filters; part: string; label: string }[] {
  const out: { key: keyof Filters; part: string; label: string }[] = [];
  const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  for (const key of FILTER_KEYS) {
    if (same(before[key], after[key])) continue;
    switch (key) {
      case "city":
        out.push({ key, part: `city:${after.city ?? "any"}`, label: getCity(after.city)?.name ?? "All cities" });
        break;
      case "deal":
        out.push({ key, part: `deal:${after.deal ?? "any"}`, label: after.deal === "rent" ? "Rent" : after.deal === "buy" ? "Buy" : "Buy or rent" });
        break;
      case "bhk": {
        const a = new Set(before.bhk ?? []);
        const b = new Set(after.bhk ?? []);
        const flips = [...new Set([...a, ...b])].filter((n) => a.has(n) !== b.has(n)).sort();
        for (const n of flips) out.push({ key, part: `bhk:${n}`, label: `${n} BHK` });
        break;
      }
      case "budget_min":
      case "budget_max":
        if (!out.some((o) => o.part === "budget")) out.push({ key, part: "budget", label: "Budget" });
        break;
      case "possession":
        out.push({ key, part: `possession:${after.possession ?? "any"}`, label: after.possession === "ready" ? "Ready to move" : after.possession ? "Under construction" : "Any possession" });
        break;
      case "localities": {
        const a = new Set(before.localities ?? []);
        const b = new Set(after.localities ?? []);
        for (const n of [...new Set([...a, ...b])].filter((x) => a.has(x) !== b.has(x))) out.push({ key, part: `locality:${n}`, label: n });
        break;
      }
      case "office":
      case "max_km":
        if (!out.some((o) => o.part === "office")) out.push({ key, part: "office", label: after.office ? `Near ${placeName(after.office)}` : "Commute" });
        break;
      case "school_km":
        out.push({ key, part: "school", label: after.school_km ? `School within ${after.school_km} km` : "Schools" });
        break;
      case "metro_km":
        out.push({ key, part: "metro", label: after.metro_km ? `Metro within ${after.metro_km} km` : "Metro" });
        break;
      case "amenities": {
        const a = new Set(before.amenities ?? []);
        const b = new Set(after.amenities ?? []);
        for (const n of [...new Set([...a, ...b])].filter((x) => a.has(x) !== b.has(x))) out.push({ key, part: `amenity:${n}`, label: n });
        break;
      }
    }
  }
  return out;
}

/** The keys a control sets: the budget block both ends, the commute block office and km. */
const KEYS_OF: Record<string, (keyof Filters)[]> = { budget: ["budget_min", "budget_max"], office: ["office", "max_km"] };

export function performers(): Performers<Spec> {
  return {
    "site.go": async ({ path }, c) => {
      const p = normalPath(path);
      if (!PATHS.test(p)) c.refuse("path", `the site has no page ${path}`, ["/", "/listings", "/compare", "/shortlist", "/visits"]);
      const listing = /^\/listing\/(.+)$/.exec(p)?.[1];
      if (listing && !getListing(listing)) c.refuse("path", `there is no listing ${listing}`, LISTINGS.slice(0, 8).map((l) => `/listing/${l.id}`));
      const project = /^\/project\/(.+)$/.exec(p)?.[1];
      if (project && !getProject(project)) c.refuse("path", `there is no project ${project}`, PROJECTS_PATHS());
      // Ring what leads there: the card, the nav link, or the logo.
      const via =
        (listing && thing(`listing:${listing}`)) ||
        thing(`nav:${p}`) ||
        (project && thing(`project:${project}`)) ||
        thing("nav:/");
      if (via && currentPath() !== p) {
        await c.scrollTo(via);
        await c.ring(via, listing ? getListing(listing)!.title : project ? getProject(project)!.name : "Kosha Homes");
      }
      await goTo(p);
      window.scrollTo({ top: 0, behavior: "smooth" });
      const title = listing ? getListing(listing)!.title : project ? getProject(project)!.name : p === "/" ? "the home page" : p.slice(1);
      return `on ${title}`;
    },

    "listings.filter": async (args, c) => {
      const want = cleanFilters({
        city: args.city ?? null,
        deal: args.deal ?? null,
        bhk: args.bhk ? args.bhk.map(Number).filter((n) => Number.isFinite(n)) : null,
        budget_min: args.budget_min ?? null,
        budget_max: args.budget_max ?? null,
        possession: args.possession ?? null,
        localities: args.localities ?? null,
        office: args.office ?? null,
        max_km: args.max_km ?? null,
        school_km: args.school_km ?? null,
        metro_km: args.metro_km ?? null,
        amenities: args.amenities ?? null,
      });
      // Check every value against what the page offers before touching anything.
      const city = want.city ? getCity(want.city) : undefined;
      for (const n of want.bhk ?? []) if (![1, 2, 3, 4].includes(Number(n))) c.refuse("bhk", `there is no ${n} BHK filter`, ["1", "2", "3", "4"]);
      const localityOptions = (city ? [city] : CITIES).flatMap((x) => x.localities.map((l) => l.name));
      for (const l of want.localities ?? []) {
        if (!localityOptions.includes(l)) c.refuse("localities", `${l} is not a locality${city ? ` in ${city.name}` : ""}`, localityOptions);
      }
      if (want.office) {
        const offices = officesOf((want.city as CityId | undefined) ?? null);
        if (!offices.some((o) => o.id === want.office)) c.refuse("office", `${want.office} is not an office${city ? ` in ${city.name}` : ""}`, offices.map((o) => o.id));
      }
      for (const a of want.amenities ?? []) if (!ALL_AMENITIES.includes(a)) c.refuse("amenities", `no listing lists ${a}`, ALL_AMENITIES);

      await goTo("/listings");
      const sheet = phone();
      if (sheet) {
        useStore.getState().setFiltersOpen(true);
        await waitFor(() => part("deal:buy"), 800);
      }
      const before = useStore.getState().filters;
      for (const control of changedControls(before, want)) {
        const el = await waitFor(() => part(control.part), 900);
        await ringScroll(c, el, control.label);
        const keys = KEYS_OF[control.part] ?? [control.key];
        const patch: Filters = {};
        for (const k of keys) (patch as Record<string, unknown>)[k] = want[k] ?? null;
        if (control.key === "bhk" || control.key === "localities" || control.key === "amenities") {
          // One value at a time, so each tick shows as it is rung.
          const now = useStore.getState().filters[control.key] as (string | number)[] | undefined;
          const value = control.key === "bhk" ? Number(control.part.split(":")[1]) : control.part.split(":").slice(1).join(":");
          const has = (now ?? []).includes(value);
          (patch as Record<string, unknown>)[control.key] = has ? (now ?? []).filter((x) => x !== value) : [...(now ?? []), value];
        }
        useStore.getState().patchFilters(patch);
      }
      useStore.getState().setFilters(want);
      if (sheet) useStore.getState().setFiltersOpen(false);
      const results = search(want);
      c.done(results.length ? `${results.length} homes shown; first ${results[0].id}, ${results[0].title}, ${priceLabel(results[0])}` : "no homes match");
      c.after(async () => {
        const head = await waitFor(() => thing("results"), 600);
        await ringScroll(c, head, `${results.length} homes`);
      });
      return null;
    },

    "listings.show": async ({ listing_id }, c) => {
      const l = listingOr(c, listing_id);
      const found = thing(`listing:${l.id}`);
      if (!found) {
        const visible = [...document.querySelectorAll("[data-stage-thing^='listing:']")].map((e) => e.getAttribute("data-stage-thing")!.slice(8));
        return c.refuse("listing_id", `${l.id} is not on screen`, [...new Set(visible)].slice(0, 12));
      }
      const card: Element = found;
      useStore.getState().setFocus(l.id);
      const pin = thing(`pin:${l.id}`);
      await c.scrollTo(card);
      await c.ring(pin ? [card, pin] : card, { label: `${l.title} · ${priceLabel(l)}`, separate: true });
      return `${l.title}, ${priceLabel(l)}`;
    },

    "compare.show": async ({ ids }, c) => {
      const found = [...new Set(ids.map((id) => id.trim().toUpperCase()))];
      if (found.length < 2 || found.length > 3) c.refuse("ids", "compare two or three homes");
      const homes = found.map((id) => listingOr(c, id));
      for (const l of homes) {
        const box = part(`compare:${l.id}`);
        if (box) await ringScroll(c, box, `Compare ${l.id}`);
      }
      useStore.getState().setCompare(homes.map((l) => l.id));
      await goTo(`/compare?ids=${homes.map((l) => l.id).join(",")}`);
      c.done(`comparing ${homes.map((l) => l.title).join(" and ")}`);
      c.after(async () => {
        const rows = await waitFor(() => document.querySelectorAll("[data-stage-thing^='row:']").length && [...document.querySelectorAll("[data-stage-thing^='row:']")], 800);
        for (const row of (rows || []).slice(0, 4)) {
          await c.scrollTo(row);
          await c.ring(row, { label: row.getAttribute("data-stage-label") ?? undefined, beatMs: 350 });
        }
      });
      return null;
    },

    "emi.show": async ({ listing_id, down_pct, tenure_years, lender }, c) => {
      const l = listingOr(c, listing_id);
      if (l.deal !== "buy" || !l.price) c.refuse("listing_id", `${l.id} is for rent; an EMI is for a home you buy`);
      const now = emiOf(useStore.getState().emi, l.id);
      const down = down_pct ?? now.down_pct;
      const years = tenure_years ?? now.tenure_years;
      const lenderId = lender ?? now.lender;
      if (down < EMI_DEFAULTS.min_down_pct || down > 90) c.refuse("down_pct", `a down payment from ${EMI_DEFAULTS.min_down_pct}% to 90%`);
      if (years < 1 || years > EMI_DEFAULTS.max_tenure_years) c.refuse("tenure_years", `a tenure from 1 to ${EMI_DEFAULTS.max_tenure_years} years`);
      const bank = getLender(lenderId) ?? c.refuse("lender", `there is no lender ${lenderId}`, LENDERS.map((x) => x.id));
      if (bank.id === "kosha-partner" && l.kind !== "new") c.refuse("lender", "the Kosha partner offer is for Kosha projects only", LENDERS.filter((x) => x.id !== "kosha-partner").map((x) => x.id));
      await goTo(`/listing/${l.id}`);
      const box = await waitFor(() => thing("emi"), 900);
      await ringScroll(c, box, "EMI calculator");
      const steps: [string, Partial<typeof now>, string][] = [];
      if (down !== now.down_pct) steps.push(["emi:down", { down_pct: down }, `Down payment ${down}%`]);
      if (years !== now.tenure_years) steps.push(["emi:tenure", { tenure_years: years }, `${years} years`]);
      if (bank.id !== now.lender) steps.push(["emi:lender", { lender: bank.id }, `${bank.name} · ${bank.rate}%`]);
      for (const [name, patch, label] of steps) {
        await ringScroll(c, part(name), label);
        useStore.getState().setEmi(l.id, patch);
      }
      useStore.getState().setEmi(l.id, { down_pct: down, tenure_years: years, lender: bank.id });
      const r = emi(l.price ?? 0, down, years, bank.rate);
      c.done(`EMI ${inrPlain(r.emi)} a month: ${down}% down, ${years} years at ${bank.rate}% with ${bank.name}`);
      c.after(async () => {
        await ringScroll(c, part("emi:result"), `${inrPlain(r.emi)} a month`);
      });
      return null;
    },

    "shortlist.set": async ({ listing_id, on }, c) => {
      const l = listingOr(c, listing_id);
      const want = on ?? true;
      const heart = part(`heart:${l.id}`) ?? thing("nav:/shortlist");
      await ringScroll(c, heart, want ? `Shortlist ${l.id}` : `Remove ${l.id}`);
      useStore.getState().toggleShortlist(l.id, want);
      const count = useStore.getState().shortlist.length;
      return want ? `${l.title} shortlisted; ${count} on the shortlist` : `${l.title} taken off the shortlist; ${count} left`;
    },

    "visit.slots": async ({ listing_id, day, part: dayPart }, c) => {
      const l = listingOr(c, listing_id);
      const days = visitDays();
      if (!days.includes(day)) c.refuse("day", "visits can be booked for the next seven days", days);
      const taken = takenSlots(useStore.getState().bookings, l.id);
      const maybe = slotsFor(l, day, taken);
      if (!maybe) {
        return c.refuse("day", `the team does not take visits on ${weekdayLabel(day)}s`, days.filter((d) => slotsFor(l, d) !== null));
      }
      const slots = maybe;
      await goTo(`/listing/${l.id}`);
      const panel = await waitFor(() => thing("visit"), 900);
      await ringScroll(c, panel, "Book a site visit");
      const tab = await waitFor(() => thing(`visit-day:${day}`), 600);
      await ringScroll(c, tab, `${weekdayLabel(day)} ${dateLabel(day)}`);
      const suits = dayPart ?? "any";
      useStore.getState().setVisit({ listing_id: l.id, day, suits, slot: null });
      const fits = slots.filter((s) => s.free && (suits === "any" || s.part === suits));
      const when = `${weekdayLabel(day)} ${dateLabel(day)}`;
      c.done(
        fits.length
          ? `${when}: ${fits.length} free ${suits === "any" ? "" : `${suits} `}slots, ${fits.map((s) => `${timeLabel(s.time)} (${s.id})`).join(", ")}`
          : `${when}: no free ${suits === "any" ? "" : `${suits} `}slots; free that day: ${slots.filter((s) => s.free).map((s) => timeLabel(s.time)).join(", ") || "none"}`,
      );
      c.after(async () => {
        const els = await waitFor(() => fits.map((s) => part(`slot:${s.id}`)).filter((x): x is Element => !!x), 600);
        if (els && els.length) {
          await c.scrollTo(els[0]!);
          await c.ring(els, { label: "Suits you", separate: true });
        }
      });
      return null;
    },

    "visit.book": async ({ listing_id, slot, name, visitors }, c) => {
      const l = listingOr(c, listing_id);
      const problem = slotProblem(l.id, slot);
      if (problem) {
        const free = (slotsFor(l, slot.slice(0, 10), takenSlots(useStore.getState().bookings, l.id)) ?? []).filter((s) => s.free).map((s) => s.id);
        c.refuse("slot", problem, free);
      }
      if (!name.trim()) c.refuse("name", "say the name the visit is booked under");
      const people = Math.max(1, Math.min(6, Number(visitors) || 1));
      await goTo(`/listing/${l.id}`);
      useStore.getState().setVisit({ listing_id: l.id, day: slot.slice(0, 10) });
      const slotEl = await waitFor(() => part(`slot:${slot}`), 900);
      await ringScroll(c, slotEl, timeLabel(slot.slice(11)));
      pickSlot(l.id, slot);
      const nameEl = await waitFor(() => part("visit:name"), 600);
      await ringScroll(c, nameEl, "Name");
      useStore.getState().setVisit({ name: name.trim(), visitors: people });
      const btn = part("visit:book");
      await ringScroll(c, btn, "Book visit");
      const booking = bookVisit(l.id, slot, name, people);
      c.done(`visit booked, ${booking.reference}: ${weekdayLabel(slot.slice(0, 10))} ${dateLabel(slot.slice(0, 10))}, ${timeLabel(slot.slice(11))}`);
      c.after(async () => {
        const card = await waitFor(() => thing(`visit-card:${booking.reference}`), 800);
        if (card) {
          await c.scrollTo(card);
          await c.ring(card, `Visit ${booking.reference}`);
        }
      });
      return null;
    },
  };
}

const inrPlain = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
const PROJECTS_PATHS = () => ["kosha-aranya", "kosha-meadows", "kosha-skyline", "kosha-riverside", "kosha-orchid", "kosha-heights", "kosha-greens"].map((p) => `/project/${p}`);

scene.registerAll(moves, performers());
