/**
 * The planner's moves, made on the page. One performer per move in the spec
 * (scene.json; `Performers<Spec>` makes a missing one a compile error). Each:
 *
 * - takes the app where it needs to be itself (the planner may speak from the
 *   home page about a hotel) — a route change, then a step of the builder;
 * - refuses, with what the page offers, an id the inventory does not have or a
 *   change the trip cannot take (a day without that slot, a city with no
 *   nights) — never a guess;
 * - brings what it rings fully into view first, with its whole group, inner
 *   scroll areas included (X1: `inView`, `stage/view.ts`), then rings it before
 *   changing it, then calls the same controller function a click calls
 *   (`state/trip.ts`);
 * - returns one short line the agent can repeat.
 */
import { type MoveContext, type PerformResult, type Performer, type Performers, showThing, waitFor } from "@voqalize/stage";
import { DESTINATIONS, ORIGINS, RULES, flightsFor, getActivity, getCity, getDestination, getFlight, getHotel } from "../data";
import { cannotPlace, days, missing, price, splitOf, stays, validSplit } from "../engine";
import { money } from "../format";
import {
  type Step,
  addActivity,
  pickFlight,
  pickHotel,
  removeActivity,
  setBrief,
  setFlightSort,
  setHotelCity,
  setHotelWant,
  setSplit,
  setStep,
  useTrip,
} from "../state/trip";
import { currentPath, navigate } from "./nav";
import type { scene } from "./scene.gen";
import { ringWhole, showWhole } from "./view";

type Spec = typeof scene.spec;

const $ = (sel: string) => document.querySelector(sel);
const thing = (name: string) => $(`[data-stage-thing="${CSS.escape(name)}"]`);
/** Wait for React to put an element on the page (a route or step that just opened). */
const appear = (find: () => Element | null, ms = 2500) => waitFor(() => find(), ms);

const PAGE_PATH = { home: "/", plan: "/plan", checkout: "/checkout" } as const;

async function toPage(page: keyof typeof PAGE_PATH, c: MoveContext): Promise<void> {
  const path = PAGE_PATH[page];
  if (currentPath() === path) return;
  const link = thing(`nav-${page}`);
  if (link) await ringWhole(c, link, { label: page === "plan" ? "Plan a trip" : page === "home" ? "Destinations" : "Checkout", beatMs: 300 });
  navigate(path);
  await appear(() => $(`[data-stage-place="${page}"]`));
}

const STEP_NEEDS: Record<Step, "none" | "brief" | "flight"> = { brief: "none", flights: "brief", hotels: "brief", days: "brief", package: "brief" };
const FIELD_WORDS: Record<string, string> = { from_city: "the city they fly from", destination: "the destination", start_date: "the date", nights: "the nights" };

/** Open a step of the builder (going to /plan first), ringing its tab. */
async function toStep(step: Step, c: MoveContext, ring = true): Promise<void> {
  if (STEP_NEEDS[step] === "brief") {
    const gaps = missing(useTrip.getState().trip.brief);
    if (gaps.length) c.refuse("step", `the trip still needs ${gaps.map((g) => FIELD_WORDS[g]).join(", ")}`, ["brief"]);
  }
  await toPage("plan", c);
  if (useTrip.getState().step === step) return;
  const tab = await appear(() => thing(`step-${step}`));
  if (tab && ring) await ringWhole(c, tab, { label: tab.getAttribute("data-stage-label") ?? step, beatMs: 300 });
  setStep(step);
  await appear(() => $(`[data-step-panel="${step}"]`));
}

async function ringThen(sel: () => Element | null, label: string, c: MoveContext, beatMs?: number): Promise<void> {
  const el = await appear(sel);
  if (!el) return;
  await ringWhole(c, el, beatMs ? { label, beatMs } : label);
}

function checkFlight(id: string, c: MoveContext) {
  const f = getFlight(id);
  const b = useTrip.getState().trip.brief;
  const offered = flightsFor(b.from_city, b.destination).map((x) => x.id);
  if (!f || f.origin !== b.from_city || f.destination !== b.destination) {
    c.refuse("flight_id", `no flight ${id} for ${b.from_city ?? "?"} to ${b.destination ?? "?"}`, offered);
  }
  return f!;
}

function checkHotel(city: string, hotelId: string, roomId: string, c: MoveContext) {
  const t = useTrip.getState().trip;
  const here = stays(t).map((s) => s.city.id);
  if (!here.includes(city)) c.refuse("city", `${getCity(city)?.name ?? city} has no nights in this trip`, here);
  const h = getHotel(city, hotelId) ?? c.refuse("hotel_id", `no hotel ${hotelId} in ${getCity(city)?.name}`, getCity(city)!.hotels.map((x) => x.id));
  const room = h.rooms.find((r) => r.id === roomId) ?? c.refuse("room_id", `${h.name} has no room ${roomId}`, h.rooms.map((r) => r.id));
  return { h, room };
}

const WANTS = ["beach", "pool", "luxury", "budget", "family", "honeymoon", "relaxed", "adventure", "culture"];
export const hotelMatches = (want: string | null, h: { tags: string[]; stars: number; rooms: { name: string }[]; inclusions: string[] }) => {
  if (!want) return true;
  if (want === "luxury") return h.stars >= 5;
  if (want === "pool") return h.rooms.some((r) => /pool/i.test(r.name)) || h.tags.includes("pool");
  return h.tags.includes(want);
};

/**
 * X1: the move's `scrollTo` becomes `showWhole` (the target and its whole
 * `data-stage-group`, inner scroll areas first, then the window under the
 * header and clear of the dock), so every scroll a performer makes, Stage's
 * own `showThing` included, shows the whole thing it is about to ring.
 */
export function inView(c: MoveContext): MoveContext {
  return { ...c, scrollTo: (el: Element) => showWhole(el) };
}
const whole =
  <A>(p: Performer<A>): Performer<A> =>
  (args, c) =>
    p(args, inView(c));

const raw: Performers<Spec> = {
  "trip.go": async ({ page }, c) => {
    if (page === "checkout") {
      const t = useTrip.getState().trip;
      const lines = stays(t);
      if (!t.flight_id || lines.some((s) => !t.hotels[s.city.id])) c.refuse("page", "the package needs a flight and a hotel in every city before checkout", ["plan"]);
    }
    await toPage(page, c);
    return `the ${page === "home" ? "destinations page" : page === "plan" ? "trip planner" : "checkout"} is up`;
  },

  "trip.step": async ({ step }, c) => {
    await toStep(step, c);
    return `the ${step} step is open`;
  },

  "trip.show": async (args, c) => showThing(args, c),

  "trip.brief": async (args, c) => {
    const changes: Record<string, unknown> = {};
    if (args.from_city != null) {
      const code = args.from_city.toUpperCase();
      if (!ORIGINS.some((o) => o.id === code)) c.refuse("from_city", `we fly from ${ORIGINS.map((o) => o.city).join(", ")}`, ORIGINS.map((o) => o.id));
      changes.from_city = code;
    }
    if (args.destination != null) {
      const d = getDestination(args.destination.toLowerCase()) ?? c.refuse("destination", `no destination ${args.destination}`, DESTINATIONS.map((x) => x.id));
      changes.destination = d.id;
    }
    if (args.start_date != null) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(args.start_date)) c.refuse("start_date", "a date is YYYY-MM-DD");
      changes.start_date = args.start_date;
    }
    const dest = getDestination((changes.destination as string) ?? useTrip.getState().trip.brief.destination);
    if (args.nights != null) {
      if (dest && (args.nights < dest.nights[0] || args.nights > dest.nights[1])) {
        c.refuse("nights", `${dest.name} trips are ${dest.nights[0]} to ${dest.nights[1]} nights`, [String(dest.nights[0]), String(dest.nights[1])]);
      }
      changes.nights = args.nights;
    }
    if (args.adults != null) {
      if (args.adults < 1 || args.adults > RULES.max_travellers) c.refuse("adults", `1 to ${RULES.max_travellers} adults`);
      changes.adults = args.adults;
    }
    if (args.kids != null) {
      const ages = args.kids.map((a) => Number.parseInt(String(a), 10));
      if (ages.some((a) => !Number.isInteger(a) || a < 0 || a > RULES.child_max_age)) c.refuse("kids", `children are 0 to ${RULES.child_max_age}; older travellers count as adults`);
      changes.kids = ages;
    }
    if (args.budget != null) changes.budget = Math.max(0, args.budget);
    if (args.style != null) changes.style = args.style;
    const fields = Object.keys(changes);
    if (!fields.length) c.refuse("from_city", "nothing to fill in");
    await toPage("plan", c);
    if (useTrip.getState().step !== "brief") {
      const tab = thing("step-brief");
      if (tab) await ringWhole(c, tab, { label: "Trip", beatMs: 250 });
      setStep("brief");
    }
    for (const f of fields) {
      await ringThen(() => $(`[data-stage-part="brief:${f}"]`), BRIEF_LABEL[f] ?? f, c, 300);
      setBrief({ [f]: changes[f] });
    }
    return `filled ${fields.map((f) => BRIEF_LABEL[f]?.toLowerCase() ?? f).join(", ")}`;
  },

  "trip.flights": async ({ sort }, c) => {
    await toStep("flights", c);
    if (sort && sort !== useTrip.getState().flightSort) {
      await ringThen(() => $(`[data-stage-part="sort:${sort}"]`), `Sort: ${sort}`, c, 250);
      setFlightSort(sort);
    }
    const list = await appear(() => thing("flight-list"));
    if (list) c.after(() => ringWhole(c, list, "Flight options"));
    const n = document.querySelectorAll("[data-flight]").length;
    return `${n} flight options on screen`;
  },

  "trip.flight": async ({ flight_id }, c) => {
    const f = checkFlight(flight_id, c);
    await toStep("flights", c, false);
    await ringThen(() => $(`[data-flight="${CSS.escape(flight_id)}"]`), `${f.airline_name}`, c);
    const err = pickFlight(flight_id);
    if (err) c.refuse("flight_id", err);
    return `${f.airline_name} selected`;
  },

  "trip.hotels": async ({ city, want }, c) => {
    const t = useTrip.getState().trip;
    const here = stays(t);
    const stay = here.find((s) => s.city.id === city) ?? c.refuse("city", `${getCity(city)?.name ?? city} has no nights in this trip`, here.map((s) => s.city.id));
    await toStep("hotels", c, false);
    if (useTrip.getState().hotelCity !== city) {
      await ringThen(() => $(`[data-city-tab="${CSS.escape(city)}"]`), stay.city.name, c, 250);
      setHotelCity(city);
    }
    const w = want ? want.toLowerCase().trim() : null;
    if (w && !WANTS.includes(w)) {
      setHotelWant(null);
      return { outcome: "partial", detail: `no filter "${w}"; filters are ${WANTS.join(", ")}`, refused: [{ arg: "want", why: "not a filter", options: WANTS }] } satisfies PerformResult;
    }
    if (w && !stay.city.hotels.some((h) => hotelMatches(w, h))) {
      setHotelWant(null);
      return {
        outcome: "partial",
        detail: `no hotel in ${stay.city.name} is ${w}${stay.city.inland ? ` (${stay.city.name} is inland)` : ""}; all ${stay.city.hotels.length} are shown`,
      } satisfies PerformResult;
    }
    if (w) {
      await ringThen(() => $(`[data-stage-part="want:${w}"]`), `Filter: ${w}`, c, 250);
    }
    setHotelWant(w);
    const shown = stay.city.hotels.filter((h) => hotelMatches(w, h)).length;
    return `${shown} hotels in ${stay.city.name}${w ? `, ${w}` : ""}`;
  },

  "trip.hotel": async ({ city, hotel_id, room_id }, c) => {
    const { h, room } = checkHotel(city, hotel_id, room_id, c);
    await toStep("hotels", c, false);
    if (useTrip.getState().hotelCity !== city) {
      await ringThen(() => $(`[data-city-tab="${CSS.escape(city)}"]`), getCity(city)!.name, c, 250);
      setHotelCity(city);
    }
    if (!hotelMatches(useTrip.getState().hotelWant, h)) setHotelWant(null);
    await ringThen(() => $(`[data-room="${CSS.escape(`${hotel_id}:${room_id}`)}"]`), `${h.name}, ${room.name}`, c);
    const err = pickHotel(city, hotel_id, room_id);
    if (err) c.refuse("hotel_id", err);
    return `${h.name}, ${room.name}, in ${getCity(city)!.name}`;
  },

  "trip.nights": async ({ split: raw }, c) => {
    const split = raw.map((n) => Number.parseInt(String(n), 10));
    const t = useTrip.getState().trip;
    const d = getDestination(t.brief.destination) ?? c.refuse("split", "choose a destination first");
    if (!validSplit(t, split)) {
      c.refuse("split", `${d.cities.map((x) => x.name).join(", ")}: one number each, adding up to ${t.brief.nights}`, [JSON.stringify(splitOf(t))]);
    }
    await toStep("hotels", c, false);
    await ringThen(() => thing("nights"), "Nights in each city", c);
    const err = setSplit(split);
    if (err) c.refuse("split", err);
    return d.cities.map((x, i) => `${x.name} ${split[i]}`).join(", ");
  },

  "trip.add": async ({ activity_id, day }, c) => {
    const a = getActivity(activity_id) ?? c.refuse("activity_id", `no activity ${activity_id}`);
    const t = useTrip.getState().trip;
    const d = days(t).find((x) => x.day === day) ?? c.refuse("day", `the trip has days 1 to ${days(t).length}`);
    const why = cannotPlace(t, activity_id, day);
    if (why) c.refuse("day", why, days(t).filter((x) => cannotPlace(t, activity_id, x.day) === null).map((x) => String(x.day)));
    await toStep("days", c, false);
    await ringThen(() => thing(`day-${day}`), `Day ${day}, ${d.city.name}`, c);
    const err = addActivity(activity_id, day);
    if (err) c.refuse("day", err);
    return `${a.name} added to day ${day}`;
  },

  "trip.remove": async ({ activity_id, day }, c) => {
    const t = useTrip.getState().trip;
    const a = getActivity(activity_id);
    if (!t.activities.some((p) => p.activity_id === activity_id && p.day === day)) {
      c.refuse("activity_id", `that is not on day ${day}`, t.activities.map((p) => `${p.day}:${p.activity_id}`));
    }
    await toStep("days", c, false);
    await ringThen(() => $(`[data-planned="${CSS.escape(`${day}:${activity_id}`)}"]`), `${a?.name ?? activity_id}`, c);
    removeActivity(activity_id, day);
    return `${a?.name ?? activity_id} removed from day ${day}`;
  },

  "trip.build": async ({ flight_id, hotels, activities }, c) => {
    const t0 = useTrip.getState().trip;
    if (missing(t0.brief).length) c.refuse("flight_id", `the trip still needs ${missing(t0.brief).map((g) => FIELD_WORDS[g]).join(", ")}`);
    checkFlight(flight_id, c);
    const hs = hotels.map((s) => {
      const [city = "", hotel = "", room = ""] = s.split(":");
      checkHotel(city, hotel, room, c);
      return { city, hotel, room };
    });
    const acts = activities.map((s) => {
      const [dayS = "", id = ""] = s.split(":");
      if (!getActivity(id)) c.refuse("activities", `no activity ${id}`);
      return { day: Number(dayS), id };
    });
    // The flight.
    await toStep("flights", c);
    await ringThen(() => $(`[data-flight="${CSS.escape(flight_id)}"]`), getFlight(flight_id)!.airline_name, c, 350);
    pickFlight(flight_id);
    // A hotel per city.
    await toStep("hotels", c);
    for (const h of hs) {
      setHotelCity(h.city);
      setHotelWant(null);
      await ringThen(() => $(`[data-room="${CSS.escape(`${h.hotel}:${h.room}`)}"]`), getHotel(h.city, h.hotel)!.name, c, 350);
      pickHotel(h.city, h.hotel, h.room);
    }
    // The days.
    await toStep("days", c);
    for (const p of useTrip.getState().trip.activities) removeActivity(p.activity_id, p.day);
    const skipped: string[] = [];
    for (const a of acts) {
      const day = thing(`day-${a.day}`);
      if (day) {
        await ringWhole(c, day, { label: `Day ${a.day}: ${getActivity(a.id)!.name}`, beatMs: 220 });
      }
      const err = addActivity(a.id, a.day);
      if (err) skipped.push(`${getActivity(a.id)!.name} (${err})`);
    }
    // The priced package.
    await toStep("package", c);
    const total = price(useTrip.getState().trip).total;
    const result: string | PerformResult = skipped.length
      ? { outcome: "partial", detail: `package built, ${money(total)}; left out: ${skipped.join("; ")}` }
      : `package built, ${money(total)} in all`;
    c.done(result);
    c.after(async () => {
      const el = thing("total");
      if (el) await ringWhole(c, el, "Total price");
    });
    return result;
  },
};

export const performers = Object.fromEntries(Object.entries(raw).map(([id, p]) => [id, whole(p as Performer<unknown>)])) as unknown as Performers<Spec>;

const BRIEF_LABEL: Record<string, string> = {
  from_city: "Flying from",
  destination: "Destination",
  start_date: "Departure",
  nights: "Nights",
  adults: "Adults",
  kids: "Children",
  budget: "Budget",
  style: "Style",
};
