/**
 * The concierge's moves, made in the app. One performer per move in the spec
 * (scene.json; `Performers<Spec>` makes a missing one a compile error). Each:
 *
 * - takes the app where it needs to be itself (she may speak from Home about
 *   the spa): the page's tab is ringed, then the route changes;
 * - refuses, with what the app offers, an id the data does not have or a
 *   change the stay cannot take (a slot that is not free, a step not reached,
 *   a period that is closed) — never a guess;
 * - brings what it rings fully into view first, with its whole group (X1:
 *   `inView`, `stage/view.ts`), rings it before changing it, then calls the
 *   same store function a tap calls (`state/store.ts`);
 * - never presses a guest-only button (Place order, Book, Approve, Complete
 *   check-in, Check out): those are the guest's;
 * - returns one short line the agent can repeat.
 */
import { type MoveContext, type Performer, type Performers, showThing, waitFor } from "@voqalize/stage";
import { ACTIVITIES, BAR, CHECKIN, DINING, INFO, LATE, MEETINGS, REQUESTS, SPA, getActivity, getItem, getMeetingRoom, getTherapist, getTreatment } from "../data";
import { clock, day, money } from "../lib/format";
import { activityTimes, blockSpan, bookableDates, cabanaOpen, earlyAvailable, earlyOffered, groupsOf, meetingQuote, orderTotals, periodOpen, roomFree, spaSlots } from "../lib/rules";
import {
  type CheckinStep,
  type Page,
  addFromSheet,
  closeSheet,
  confirmReservation,
  folio,
  openActivity,
  openCart,
  openDispute,
  openExpect,
  openInfo,
  openItem,
  openMeeting,
  openRequest,
  openTreatment,
  openVisitor,
  pickLate,
  pickSpaSlot,
  reachable,
  removeLine,
  requestBlocked,
  requestFee,
  roomFor,
  sendDispute,
  sendRequest,
  setCabana,
  setCheckinStep,
  setCheckoutPart,
  setDeliverTo,
  setEarly,
  setItemQty,
  setMeetingFilter,
  setPref,
  setSection,
  setSpaCategory,
  setTip,
  showOnMap,
  stayClock,
  toggleChoice,
  useStay,
} from "../state/store";
import { PAGE_PATH, currentPath, navigate } from "./nav";
import type { scene } from "./scene.gen";
import { ringWhole, showWhole } from "./view";

type Spec = typeof scene.spec;

const $ = (sel: string) => document.querySelector(sel);
const thing = (name: string) => $(`[data-stage-thing="${CSS.escape(name)}"]`);
const appear = (find: () => Element | null, ms = 2500) => waitFor(() => find(), ms);
const hm = (t: string) => t.replace(":", "");
const st = () => useStay.getState();

const TAB_OF: Record<Page, string> = {
  home: "home",
  info: "home",
  dining: "dining",
  bar: "dining",
  spa: "experiences",
  activities: "experiences",
  meetings: "experiences",
  requests: "requests",
  visitors: "requests",
  stay: "stay",
  checkin: "stay",
  checkout: "stay",
};
const PAGE_WORDS: Record<Page, string> = {
  home: "Home",
  dining: "the in-room dining menu",
  bar: "the drinks menu",
  spa: "the spa",
  activities: "activities and the resort map",
  meetings: "meeting rooms",
  requests: "front desk requests",
  visitors: "visitors",
  stay: "your stay",
  checkin: "check-in",
  checkout: "check-out",
  info: "hotel information",
};

/** Go to a page (closing any sheet), ringing its tab first. */
async function toPage(page: Page, c: MoveContext): Promise<void> {
  const path = PAGE_PATH[page];
  if (currentPath() === path) {
    if (st().sheet) closeSheet();
    return;
  }
  if (st().sheet) closeSheet();
  const tab = thing(`tab-${TAB_OF[page]}`);
  if (tab) await c.ring(tab, { label: tab.getAttribute("data-stage-label") ?? page, beatMs: 300 });
  navigate(path);
  await appear(() => $(`[data-stage-place="${page}"]`));
}

/** Ring something once it is on screen, if it comes. */
async function ringThen(name: string, label: string | undefined, c: MoveContext, beatMs?: number): Promise<Element | null> {
  const el = await appear(() => thing(name));
  if (!el) return null;
  await ringWhole(c, el, { label: label ?? el.getAttribute("data-stage-label") ?? name, ...(beatMs ? { beatMs } : {}) });
  return el;
}

/** X1: every scroll a performer makes (Stage's own `showThing` too) shows the whole group. */
export function inView(c: MoveContext): MoveContext {
  return { ...c, scrollTo: (el: Element) => showWhole(el) };
}
const whole =
  <A>(p: Performer<A>): Performer<A> =>
  (args, c) =>
    p(args, inView(c));

const yes = (v: string | null | undefined) => v === "yes";

const raw: Performers<Spec> = {
  "app.go": async ({ page }, c) => {
    await toPage(page, c);
    return `${PAGE_WORDS[page]} is open`;
  },

  "app.show": async (args, c) => showThing(args, c),

  "sheet.close": async (_a, c) => {
    const s = st().sheet;
    if (!s) return "nothing was open";
    const head = $(".sheet-head");
    if (head) await c.ring(head, { label: "Close", beatMs: 250 });
    closeSheet();
    return "closed";
  },

  "info.open": async ({ topic }, c) => {
    const s = INFO.find((x) => x.id === topic) ?? c.refuse("topic", `no section ${topic}`, INFO.map((x) => x.id));
    await toPage("info", c);
    openInfo(s.id);
    const el = await appear(() => thing(`info-${s.id}`));
    if (el) {
      await new Promise((r) => setTimeout(r, 120));
      await ringWhole(c, el, s.title);
    }
    return `${s.title} is open`;
  },

  // ─── Check-in ───────────────────────────────────────────────────────
  "checkin.open": async ({ step }, c) => {
    if (st().checkedIn) c.refuse("step", "the guest is already checked in", []);
    const want = (step ?? "reservation") as CheckinStep;
    const r = reachable();
    if (!r.includes(want)) c.refuse("step", `check-in has not reached ${want} yet; next is ${r[r.length - 1]}`, r);
    await toPage("checkin", c);
    const tab = thing(`checkin-step-${want}`);
    if (tab) await c.ring(tab, { label: want, beatMs: 250 });
    setCheckinStep(want);
    return `check-in is on the ${want} step`;
  },

  "checkin.confirm": async (_a, c) => {
    if (st().checkedIn) c.refuse("step", "already checked in", []);
    await toPage("checkin", c);
    setCheckinStep("reservation");
    const btn = await ringThen("checkin-confirm", "Yes, that's my reservation", c);
    if (!btn) c.refuse("step", "the reservation step is not showing", []);
    confirmReservation();
    return "reservation confirmed; next the guest scans their ID";
  },

  "checkin.prefs": async (args, c) => {
    if (st().checkedIn) c.refuse("step", "already checked in", []);
    if (!reachable().includes("room")) c.refuse("step", "the guest has to confirm the reservation and scan their ID first", reachable());
    await toPage("checkin", c);
    setCheckinStep("room");
    const set: string[] = [];
    if (args.arrival) {
      await ringThen(`arrival-${hm(args.arrival)}`, undefined, c);
      setPref("arrival", args.arrival);
      set.push(`arrival ${args.arrival === "now" ? "now" : clock(args.arrival)}`);
    }
    if (args.floor) {
      await ringThen(`floor-${args.floor}`, undefined, c);
      setPref("floor", args.floor);
      set.push(`${args.floor} floor`);
    }
    if (args.bed) {
      await ringThen(`bed-${args.bed}`, undefined, c);
      setPref("bed", args.bed);
      set.push(args.bed === "king" ? "one king" : "two queens");
    }
    if (args.quiet) {
      await ringThen("quiet", "Quiet room", c);
      setPref("quiet", yes(args.quiet));
      set.push(yes(args.quiet) ? "quiet room" : "any room");
    }
    if (!set.length) c.refuse("arrival", "nothing to set", CHECKIN.arrival_times.map((a) => a.id));
    const room = roomFor();
    // With the arrival known, the wizard moves on: to early check-in when it applies, else to the review.
    const next = st().checkin.arrival ? reachable()[reachable().length - 1] : null;
    c.done(`set ${set.join(", ")}; that gets room ${room.room} (floor ${room.floor})`);
    c.after(async () => {
      const el = thing("room-preview");
      if (el) await ringWhole(c, el, `Room ${room.room}`);
      if (next && next !== "room") {
        await new Promise((r) => setTimeout(r, 900));
        setCheckinStep(next);
      }
    });
    return null;
  },

  "checkin.early": async ({ want }, c) => {
    const ci = st().checkin;
    if (!earlyOffered(ci.arrival, stayClock().now)) c.refuse("want", "early check-in only applies when arriving before 4:00 PM", []);
    if (yes(want) && ci.arrival && !earlyAvailable(roomFor(), ci.arrival, stayClock().now)) c.refuse("want", "the room is not ready by then", ["no"]);
    await toPage("checkin", c);
    setCheckinStep("early");
    await ringThen(`early-${want}`, undefined, c);
    setEarly(yes(want));
    c.after(async () => {
      await new Promise((r) => setTimeout(r, 700));
      setCheckinStep("review");
      const el = await appear(() => thing("checkin-complete"));
      if (el) await ringWhole(c, el, "Complete check-in");
    });
    return yes(want) ? `early check-in added, ${money(CHECKIN.early.fee)}` : "no early check-in";
  },

  // ─── Check-out ──────────────────────────────────────────────────────
  "checkout.open": async ({ part }, c) => {
    const p = part ?? "folio";
    await toPage("checkout", c);
    const seg = thing(`checkout-${p}`);
    if (seg) await c.ring(seg, { label: seg.getAttribute("data-stage-label") ?? p, beatMs: 250 });
    setCheckoutPart(p);
    return `check-out is open at the ${p === "folio" ? "bill" : p === "late" ? "late check-out options" : "express check-out review"}`;
  },

  "folio.dispute": async ({ line_id, reason, send }, c) => {
    const line = folio().find((l) => l.id === line_id) ?? c.refuse("line_id", `no charge ${line_id}`, folio().map((l) => l.id));
    if (line.amount < 0) c.refuse("line_id", "that is a payment, not a charge", []);
    await toPage("checkout", c);
    setCheckoutPart("folio");
    await ringThen(`line-${line.id}`, line.label, c);
    openDispute(line.id, reason);
    const field = await appear(() => thing("dispute-reason"));
    if (field) await ringWhole(c, field, "Your question");
    if (send) {
      const btn = thing("dispute-send");
      if (btn) await c.ring(btn, "Send");
      sendDispute();
      return `sent to the front desk: ${line.label}`;
    }
    return `the question about ${line.label} is ready to send`;
  },

  "late.pick": async ({ time }, c) => {
    const o = LATE.options.find((x) => x.id === time) ?? c.refuse("time", `no option ${time}`, LATE.options.map((x) => x.id));
    if (!o.available) c.refuse("time", `${o.label} is ${o.note ?? "not available"}`, LATE.options.filter((x) => x.available).map((x) => x.id));
    await toPage("checkout", c);
    setCheckoutPart("late");
    await ringThen(`late-${hm(o.id)}`, o.label, c);
    pickLate(o.id);
    c.after(async () => {
      const b = thing("late-request");
      if (b) await ringWhole(c, b, "Request");
    });
    return `${o.label} selected${o.fee ? `, ${money(o.fee)}` : ", complimentary"}; the guest presses Request`;
  },

  // ─── Dining and drinks ──────────────────────────────────────────────
  "menu.open": async ({ outlet, section }, c) => {
    const sections = outlet === "dining" ? DINING.periods.map((p) => p.id) : useBarSections();
    if (section && !sections.includes(section)) c.refuse("section", `no section ${section}`, sections);
    await toPage(outlet, c);
    if (section) {
      await ringThen(`section-${section}`, undefined, c, 250);
      setSection(outlet, section);
    }
    return `the ${outlet === "dining" ? "in-room dining" : "drinks"} menu is open${section ? ` at ${section.replace("_", " ")}` : ""}`;
  },

  "menu.item": async ({ outlet, item_id, qty, choices, note, add }, c) => {
    const item = getItem(outlet, item_id) ?? c.refuse("item_id", `no ${outlet} item ${item_id}`, [...(outlet === "dining" ? DINING.periods.flatMap((p) => p.items.map((i) => i.id)) : useBarItems())]);
    if (outlet === "dining") {
      const p = DINING.periods.find((x) => x.id === item.section)!;
      if (!periodOpen(p, stayClock().now)) c.refuse("item_id", `${p.label} is served ${p.hours}`, DINING.periods.filter((x) => periodOpen(x, stayClock().now)).flatMap((x) => x.items.map((i) => i.id)));
    }
    const groups = groupsOf(item);
    const picked: [string, string, boolean][] = [];
    for (const raw of choices ?? []) {
      const [g, ch] = raw.includes(":") ? raw.split(":", 2) : ["", raw];
      const hit =
        groups.find(([gid, grp]) => (!g || g === gid) && grp.choices.some(([cid]) => cid === ch)) ??
        c.refuse("choices", `${raw} is not an option for ${item.name}`, groups.flatMap(([gid, grp]) => grp.choices.map(([cid]) => `${gid}:${cid}`)));
      picked.push([hit[0], ch, hit[1].pick]);
    }
    const missing = groups.filter(([gid, g]) => g.pick && !picked.some(([pg]) => pg === gid)).map(([gid]) => gid);
    if (add !== false && missing.length) c.refuse("choices", `${item.name} needs a choice of ${missing.join(", ")}`, groups.filter(([gid]) => missing.includes(gid)).flatMap(([gid, grp]) => grp.choices.map(([cid]) => `${gid}:${cid}`)));
    await toPage(outlet, c);
    if (st().section[outlet] !== item.section) setSection(outlet, item.section);
    await ringThen(`item-${item.id}`, item.name, c);
    openItem(outlet, item.id, { note: note ?? "" });
    await appear(() => thing("item-add"));
    for (const [gid, cid, pick] of picked) {
      const el = thing(`choice-${gid}-${cid}`);
      if (el) await ringWhole(c, el, { label: el.getAttribute("data-stage-label") ?? cid, beatMs: 250 });
      toggleChoice(gid, cid, pick);
    }
    if ((qty ?? 1) !== 1) {
      const q = thing("qty");
      if (q) await ringWhole(c, q, `${qty}`);
      setItemQty(qty ?? 1);
    }
    if (add === false) return `${item.name} is open with those choices`;
    const btn = thing("item-add");
    if (btn) await ringWhole(c, btn, { label: "Add to order", beatMs: 250 });
    addFromSheet();
    const t = orderTotals(outlet, st().carts[outlet], 0);
    return `added ${qty ?? 1} ${item.name}; the order is ${money(t.subtotal)} before charges`;
  },

  "cart.remove": async ({ outlet, item_id }, c) => {
    const i = st().carts[outlet].findIndex((l) => l.item_id === item_id);
    if (i < 0) c.refuse("item_id", `no ${item_id} in the order`, st().carts[outlet].map((l) => l.item_id));
    if (st().sheet?.kind !== "cart") {
      await toPage(outlet, c);
      openCart(outlet);
    }
    await ringThen(`cart-line-${i}`, getItem(outlet, item_id)?.name, c);
    removeLine(outlet, i);
    return `${getItem(outlet, item_id)?.name} taken off`;
  },

  "cart.open": async ({ outlet, tip, deliver_to, cabana }, c) => {
    if (!st().carts[outlet].length) c.refuse("outlet", "the order is empty", []);
    if (tip != null && ![0, 10, 15, 20].includes(tip)) c.refuse("tip", "tips are 0, 10, 15 or 20 percent", ["0", "10", "15", "20"]);
    if (deliver_to && outlet !== "bar") c.refuse("deliver_to", "in-room dining goes to the room", []);
    if (deliver_to === "cabana" && !cabanaOpen(stayClock().now)) c.refuse("deliver_to", "cabana delivery is while the pool bar is open, 11:00 AM to 6:00 PM", ["room"]);
    if (st().sheet?.kind !== "cart") {
      await toPage(outlet, c);
      const bar = thing("cart-bar");
      if (bar) await ringWhole(c, bar, { label: "View order", beatMs: 250 });
      openCart(outlet);
    }
    await appear(() => thing("order-total"));
    if (deliver_to) {
      await ringThen(`deliver-${deliver_to}`, undefined, c, 250);
      setDeliverTo(deliver_to);
    }
    if (cabana) {
      await ringThen(`cabana-${cabana}`, `Cabana ${cabana}`, c, 250);
      setCabana(cabana);
    }
    if (tip != null) {
      await ringThen(`tip-${tip}`, tip ? `${tip}%` : "No tip", c, 250);
      setTip(outlet, tip);
    }
    const t = orderTotals(outlet, st().carts[outlet], st().tip[outlet] ?? 0);
    c.done(`the order is open, ${money(t.total)} in all; the guest presses Place order`);
    c.after(async () => {
      const el = thing("order-total");
      if (el) await ringWhole(c, el, "Total");
    });
    return null;
  },

  // ─── Spa ────────────────────────────────────────────────────────────
  "spa.open": async ({ category }, c) => {
    await toPage("spa", c);
    if (category) {
      await ringThen(`spa-cat-${category}`, undefined, c, 250);
      setSpaCategory(category);
    }
    return `the spa menu is open${category ? ` at ${category}` : ""}`;
  },

  "spa.treatment": async ({ treatment_id, date, therapist }, c) => {
    const t = getTreatment(treatment_id) ?? c.refuse("treatment_id", `no treatment ${treatment_id}`, SPA.treatments.map((x) => x.id));
    const dates = bookableDates(stayClock());
    if (date && !dates.includes(date)) c.refuse("date", `the spa can be booked ${day(dates[0])} to ${day(dates[dates.length - 1])}`, dates);
    await toPage("spa", c);
    if (st().spaCategory && st().spaCategory !== t.category) setSpaCategory(null);
    await ringThen(`treatment-${t.id}`, `${t.name}, ${t.minutes} min`, c);
    openTreatment(t.id, date ?? undefined, therapist ?? undefined);
    const slots = spaSlots(stayClock(), t.id, date ?? stayClock().today, therapist ?? "any");
    c.done(slots.length ? `${slots.length} times on screen` : "no times left that day");
    c.after(async () => {
      const el = await appear(() => thing(slots.length ? `slot-${hm(slots[0][0])}-${slots[0][1]}` : "spa-summary"));
      if (el) await ringWhole(c, el.closest("[data-stage-group]") ?? el, "Times");
    });
    return null;
  },

  "spa.slot": async ({ treatment_id, date, time, therapist_id }, c) => {
    const t = getTreatment(treatment_id) ?? c.refuse("treatment_id", `no treatment ${treatment_id}`, SPA.treatments.map((x) => x.id));
    const slots = spaSlots(stayClock(), t.id, date, "any");
    if (!slots.some(([x, th]) => x === time && th === therapist_id)) {
      c.refuse("time", `${clock(time)} with ${getTherapist(therapist_id)?.name ?? therapist_id} is not free`, slots.slice(0, 10).map(([x, th]) => `${x} ${th}`));
    }
    const sheet = st().sheet;
    if (sheet?.kind !== "spa" || sheet.treatment_id !== t.id || sheet.date !== date) {
      await toPage("spa", c);
      openTreatment(t.id, date, "any");
    } else if (sheet.pref !== "any" && !spaSlots(stayClock(), t.id, date, sheet.pref).some(([x, th]) => x === time && th === therapist_id)) {
      openTreatment(t.id, date, "any");
    }
    await ringThen(`slot-${hm(time)}-${therapist_id}`, `${clock(time)} with ${getTherapist(therapist_id)?.name}`, c);
    pickSpaSlot(time, therapist_id);
    c.after(async () => {
      const el = thing("spa-book");
      if (el) await ringWhole(c, el, "Book");
    });
    return `${t.name} ${day(date)} at ${clock(time)} with ${getTherapist(therapist_id)?.name} is selected; the guest presses Book`;
  },

  // ─── Activities ─────────────────────────────────────────────────────
  "activity.show": async ({ activity_id, map }, c) => {
    const a = getActivity(activity_id) ?? c.refuse("activity_id", `no activity ${activity_id}`, useActivityIds());
    await toPage("activities", c);
    if (map) {
      showOnMap(a.place);
      const pin = await appear(() => thing(`pin-${a.place}`));
      if (pin) {
        const m = thing("map");
        if (m) await showWhole(m);
        await c.ring(pin, a.name);
      }
      return `${a.name} is pinned on the map`;
    }
    await ringThen(`activity-${a.id}`, a.name, c);
    return `${a.name} is on screen`;
  },

  "activity.pick": async ({ activity_id, date, time, guests }, c) => {
    const a = getActivity(activity_id) ?? c.refuse("activity_id", `no activity ${activity_id}`, useActivityIds());
    if (!a.bookable) c.refuse("activity_id", `${a.name} needs no booking`, useActivityIds(true));
    const dates = bookableDates(stayClock());
    if (!dates.includes(date)) c.refuse("date", "dates of the stay only", dates);
    const times = activityTimes(stayClock(), a.id, date);
    if (!times.includes(time)) c.refuse("time", `${a.name} on ${day(date)} runs at ${times.map(clock).join(", ") || "no more times"}`, times);
    if (a.capacity && (guests ?? 1) > a.capacity) c.refuse("guests", `at most ${a.capacity}`, []);
    await toPage("activities", c);
    await ringThen(`activity-${a.id}`, a.name, c);
    openActivity(a.id, { date, time, guests: guests ?? 1 });
    await appear(() => thing("act-book"));
    const el = thing(`act-time-${hm(time)}`);
    if (el) await ringWhole(c, el, clock(time));
    return `${a.name} on ${day(date)} at ${clock(time)} for ${guests ?? 1} is set up; the guest presses Book`;
  },

  // ─── Meetings ───────────────────────────────────────────────────────
  "meeting.filter": async ({ headcount, layout, date }, c) => {
    if (date && !MEETINGS.dates.includes(date)) c.refuse("date", "dates on the calendar", MEETINGS.dates);
    await toPage("meetings", c);
    if (headcount) {
      await ringThen("meeting-headcount", `${headcount} people`, c, 250);
      setMeetingFilter({ headcount });
    }
    if (layout) {
      await ringThen(`meeting-layout-${layout}`, undefined, c, 250);
      setMeetingFilter({ layout });
    }
    if (date) {
      await ringThen(`meeting-date-${date}`, day(date), c, 250);
      setMeetingFilter({ date });
    }
    return "meeting rooms filtered";
  },

  "meeting.pick": async (args, c) => {
    const r = getMeetingRoom(args.room_id) ?? c.refuse("room_id", `no room ${args.room_id}`, MEETINGS.rooms.map((x) => x.id));
    if (!(args.layout in r.layouts)) c.refuse("layout", `${r.name} sets up as ${Object.keys(r.layouts).join(", ")}`, Object.keys(r.layouts));
    if (args.headcount > r.layouts[args.layout]) c.refuse("headcount", `${r.name} seats ${r.layouts[args.layout]} ${args.layout}`, []);
    if (!MEETINGS.dates.includes(args.date)) c.refuse("date", "dates on the calendar", MEETINGS.dates);
    const span = blockSpan(args.block, args.start ?? null, args.hours ?? null) ?? c.refuse("block", "by the hour needs a start and hours", []);
    if (!roomFree(r.id, args.date, span)) c.refuse("block", `${r.name} is taken then on ${day(args.date)}`, MEETINGS.blocks.map((b) => b.id));
    await toPage("meetings", c);
    await ringThen(`room-${r.id}`, r.name, c);
    openMeeting(r.id, { date: args.date, block: args.block, start: args.start ?? null, hours: args.hours ?? null, headcount: args.headcount, layout: args.layout, catering: args.catering ?? [], av: args.av ?? [] });
    const q = meetingQuote(r.id, args.block, args.hours ?? null, args.headcount, args.catering ?? [], args.av ?? []);
    c.done(`the booking form is filled, estimated ${money(q.total)}; the guest presses Request booking`);
    c.after(async () => {
      for (const name of [`mtg-block-${args.block}`, `mtg-layout-${args.layout}`, ...(args.catering ?? []).map((x) => `mtg-catering-${x}`), "mtg-total"]) {
        const el = thing(name);
        if (el) await ringWhole(c, el, { label: el.getAttribute("data-stage-label") ?? name, beatMs: 200 });
      }
    });
    return null;
  },

  // ─── Visitors ───────────────────────────────────────────────────────
  "visitor.open": async ({ visitor_id, meet }, c) => {
    const v = st().visitors.find((x) => x.id === visitor_id) ?? c.refuse("visitor_id", `no visitor ${visitor_id}`, st().visitors.map((x) => x.id));
    if (v.status !== "pending") c.refuse("visitor_id", `${v.name} was already ${v.status}`, st().visitors.filter((x) => x.status === "pending").map((x) => x.id));
    await toPage("visitors", c);
    await ringThen(`visitor-${v.id}`, v.name, c);
    openVisitor(v.id, meet ?? null);
    if (meet) {
      const el = await appear(() => thing(`meet-${meet}`));
      if (el) await ringWhole(c, el, el.getAttribute("data-stage-label") ?? meet);
    }
    return `${v.name}'s request is open; the guest presses Approve or Decline`;
  },

  "visitor.expect": async ({ name, arrive_from: from, arrive_to: to, meet, note }, c) => {
    if (!name.trim()) c.refuse("name", "a visitor needs a name", []);
    if (from >= to) c.refuse("to", "the window ends after it starts", []);
    if (to > "22:00") c.refuse("to", "visitors are welcome until 10:00 PM", ["22:00"]);
    await toPage("visitors", c);
    const b = thing("visitor-expect");
    if (b) await ringWhole(c, b, { label: "Add a visitor", beatMs: 250 });
    openExpect({ name, from, to, meet: meet ?? null, note: note ?? "" });
    const add = await appear(() => thing("expect-add"));
    for (const n of ["expect-name", "expect-from", "expect-to", ...(meet ? [`meet-${meet}`] : [])]) {
      const el = thing(n);
      if (el) await ringWhole(c, el, { label: el.getAttribute("data-stage-label") ?? n, beatMs: 200 });
    }
    if (add) await ringWhole(c, add, "Add visitor");
    return `${name}, ${clock(from)} to ${clock(to)}, is filled in; the guest presses Add visitor`;
  },

  // ─── Requests ───────────────────────────────────────────────────────
  "request.fill": async (args, c) => {
    const R = REQUESTS;
    const items = args.items ?? [];
    if (args.kind === "housekeeping") for (const i of items) if (!R.housekeeping.items.some((x) => x.id === i)) c.refuse("items", `no item ${i}`, R.housekeeping.items.map((x) => x.id));
    if (args.issue && !R.maintenance.issues.some((x) => x.id === args.issue)) c.refuse("issue", `no issue ${args.issue}`, R.maintenance.issues.map((x) => x.id));
    if (args.option && !R.transport.options.some((x) => x.id === args.option)) c.refuse("option", `no ride ${args.option}`, R.transport.options.map((x) => x.id));
    if (args.date && !bookableDates(stayClock()).includes(args.date)) c.refuse("date", "dates of the stay only", bookableDates(stayClock()));
    await toPage("requests", c);
    const tile = thing(`request-${args.kind}`);
    if (tile) await ringWhole(c, tile, { label: tile.getAttribute("data-stage-label") ?? args.kind, beatMs: 250 });
    openRequest(args.kind, { items, issue: args.issue ?? null, option: args.option ?? null, date: args.date ?? null, time: args.time ?? null, details: args.details ?? "" });
    await appear(() => thing("req-send"));
    const names = [...items.map((i) => `req-item-${i}`), ...(args.issue ? [`req-issue-${args.issue}`] : []), ...(args.option ? [`req-option-${args.option}`] : []), ...(args.date ? [`req-date-${args.date}`] : []), ...(args.time ? ["req-time"] : []), ...(args.details ? ["req-details"] : [])];
    for (const n of names) {
      const el = thing(n);
      if (el) await ringWhole(c, el, { label: el.getAttribute("data-stage-label") ?? n, beatMs: 200 });
    }
    const s = st().sheet;
    if (s?.kind !== "request") return "the request is open";
    const blocked = requestBlocked(s);
    if (args.send) {
      if (blocked) c.refuse("send", blocked, []);
      if (requestFee(s) > 0) c.refuse("send", `this costs ${money(requestFee(s))}, so the guest presses Send`, []);
      const btn = thing("req-send");
      if (btn) await ringWhole(c, btn, "Send");
      sendRequest();
      return "sent";
    }
    return blocked ? `the request is open; still needed: ${blocked}` : "the request is filled in and ready to send";
  },
};

function useBarSections(): string[] {
  return BAR.sections.map((x) => x.id);
}
function useBarItems(): string[] {
  return BAR.sections.flatMap((x) => x.items.map((i) => i.id));
}
function useActivityIds(bookableOnly = false): string[] {
  return ACTIVITIES.filter((a) => !bookableOnly || a.bookable).map((a) => a.id);
}

export const performers = Object.fromEntries(Object.entries(raw).map(([id, p]) => [id, whole(p as Performer<unknown>)])) as unknown as Performers<Spec>;
