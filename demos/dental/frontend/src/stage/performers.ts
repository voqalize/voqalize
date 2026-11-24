/**
 * Every Stage move of the front desk (scene.json), registered once for the
 * whole app. A performer opens the page it needs first (ringing the header
 * link), waits for what it touches to be on screen, rings it, then changes
 * the same store a click changes — with `by: "agent"` — and returns one short
 * line. It refuses, with what the page offers instead, rather than guess.
 */
import type { MoveContext, Performers } from "@voqalize/stage";
import { DATA, branch, dentist, minutes, normalPhone, room, service, showPhone, time12 } from "../data/clinic";
import { type Slot, changeTerms, daysBetween, addDays, shortDate, sittingWindow, weekdayOf } from "../data/slots";
import { actions, inWindow, patientById, signedInPatient, useStore } from "../state/store";
import { PATH, type Page, currentPage, navigate } from "./nav";
import type { scene } from "./scene.gen";
import { ringAll, wholeView } from "./view";

type Spec = typeof scene.spec;

const PAGE_LABEL: Record<Page, string> = { home: "home", book: "booking", "my-appointments": "My appointments" };
/** Parts only the home page has: site.show opens home first for these. */
export const HOME_THINGS = [
  "services",
  "dentists",
  "branches",
  "visit-info",
  "payment",
  "insurance",
  "parking",
  "eating",
  "aftercare",
  "emergency",
  "hours",
  "policy",
];
const BOOK_THINGS = ["calendar", "summary", "signin", "service-list", "choose"];
const APPT_THINGS = ["appointments", "past-visits", "callback-form"];

const $ = (sel: string) => document.querySelector<HTMLElement>(sel);
const thing = (name: string) => $(`[data-stage-thing="${CSS.escape(name)}"]`);

/** Wait for React to put `find()` on the page. */
export async function appear<T extends Element>(find: () => T | null, ms = 1600): Promise<T | null> {
  const end = Date.now() + ms;
  for (;;) {
    const el = find();
    if (el || Date.now() > end) return el;
    await new Promise((r) => setTimeout(r, 30));
  }
}

const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

/** Open `page` if it is not in front: ring its header link, then route. */
async function goTo(page: Page, c: MoveContext): Promise<void> {
  if (currentPage() === page) return;
  const link = $(`.site-nav [data-nav="${page}"]`) ?? $(`[data-nav="${page}"]`);
  if (link && link.getBoundingClientRect().width > 0) await c.ring(link, PAGE_LABEL[page]);
  navigate(PATH[page], "agent");
  await appear(() => $(`[data-page="${page}"]`));
  await frame();
}

async function show(el: Element, c: MoveContext, label?: string) {
  await c.reveal(el);
  await c.scrollTo(el);
  await c.ring(el, label);
}

const isDate = (d: string | null | undefined): d is string => !!d && /^\d{4}-\d{2}-\d{2}$/.test(d);
const isTime = (t: string | null | undefined): t is string => !!t && /^\d{1,2}:\d{2}$/.test(t);
const pad = (t: string) => (t.length === 4 ? `0${t}` : t);

function needService(id: string, c: MoveContext) {
  return service(id) ?? c.refuse("service_id", `no service ${id}`, DATA.services.map((s) => s.id));
}

function needDay(date: string | null | undefined, c: MoveContext, arg = "date"): string {
  if (!isDate(date)) return c.refuse(arg, "a date is YYYY-MM-DD");
  const cal = useStore.getState().cal;
  if (!cal.bookableDay(date)) {
    c.refuse(arg, `bookable days run from ${cal.today} to ${addDays(cal.today, DATA.booking.horizon_days)}`);
  }
  if (weekdayOf(date) === "sun") return c.refuse(arg, "the clinic is closed on Sundays", [addDays(date, 1)]);
  return date;
}

/** The free times nearest `time` (for a refusal's options). */
function nearest(slots: Slot[], time: string, n = 5): string[] {
  const t = minutes(time);
  return [...new Set([...slots].sort((a, b) => Math.abs(a.start - t) - Math.abs(b.start - t)).map((s) => s.time))].slice(0, n);
}

const who = (s: Slot) => (s.dentist ? dentist(s.dentist)?.short : room(s.resource)?.room.label) ?? "";
const where = (id: string) => branch(id)?.short ?? id;
const when = (s: Slot) => `${shortDate(s.date)} at ${time12(s.time)}`;

/** Put the service on screen and select it: its tab, a ring on its card. */
async function chooseService(id: string, c: MoveContext) {
  const svc = service(id)!;
  const st = useStore.getState().book;
  if (st.service === id) return;
  actions.setTab(svc.category);
  const card = await appear(() => $(`[data-service="${id}"]`));
  if (card) await show(card, c, svc.name);
  actions.selectService(id, "agent");
}

/** "2026-11-30 10:00 indiranagar ind-c1" → a slot with the first sitting's dentist. */
function parseSitting(raw: string, dentistId: string | null): Slot | null {
  const [date, time, br, ch] = raw.trim().split(/\s+/);
  if (!isDate(date) || !isTime(time) || !branch(br)) return null;
  return { date, start: minutes(pad(time)), time: pad(time), branch: br, dentist: dentistId, chair: ch ?? null, resource: null };
}

/** Make the slot in `args` the held one, if it is free: the shared half of hold and confirm. */
function findSlot(
  args: { service_id: string; branch_id: string; date: string; time: string; dentist_id?: string | null; resource_id?: string | null },
  c: MoveContext,
): Slot {
  const svc = needService(args.service_id, c);
  const date = needDay(args.date, c);
  if (!isTime(args.time)) return c.refuse("time", "a time is HH:MM, 24-hour");
  if (!branch(args.branch_id)) return c.refuse("branch_id", `no branch ${args.branch_id}`, DATA.branches.map((b) => b.id));
  const cal = useStore.getState().cal;
  const opts = { branch: args.branch_id, dentist: svc.resource ? null : (args.dentist_id ?? null), resource: args.resource_id ?? null };
  const slot = cal.slotAt(svc, date, pad(args.time), opts);
  if (!slot) {
    const free = cal.slots(svc, date, opts);
    c.refuse(
      "time",
      free.length ? `${pad(args.time)} is not free on ${shortDate(date)}` : `no free times on ${shortDate(date)} for that choice`,
      nearest(free, pad(args.time)),
    );
  }
  return slot;
}

/** Bring the calendar to the slot's day, showing the slot's dentist or room. */
function aimCalendar(slot: Slot) {
  const b = useStore.getState().book;
  if (b.branch && b.branch !== slot.branch) actions.selectBranch(slot.branch, "agent");
  if (slot.dentist && b.dentist && b.dentist !== slot.dentist) actions.selectDentist(slot.dentist, "agent");
  if (slot.resource && b.resource && b.resource !== slot.resource) actions.selectResource(slot.resource, "agent");
  const after = useStore.getState().book;
  if (after.focus && after.focus !== (slot.dentist ?? slot.resource)) actions.setFocus(null);
  actions.setDate(slot.date, "agent");
  if (after.view === "week") actions.setView("day");
}

function upcomingIds(): string[] {
  const s = useStore.getState();
  return s.signedIn ? s.cal.upcoming(s.signedIn).map((a) => a.id) : [];
}

/** The signed-in patient's upcoming appointment, or a refusal. */
function needAppt(id: string, c: MoveContext) {
  const s = useStore.getState();
  if (!s.signedIn) return c.refuse("appointment_id", "no patient is signed in on this page");
  const a = s.cal.appts.get(id);
  if (!a || a.patient_id !== s.signedIn) return c.refuse("appointment_id", `no appointment ${id} for this patient`, upcomingIds());
  return a;
}

type ChangeArgs = {
  appointment_id: string;
  action: "reschedule" | "cancel";
  fee?: number | null;
  date?: string | null;
  time?: string | null;
  branch_id?: string | null;
  dentist_id?: string | null;
  chair_id?: string | null;
  resource_id?: string | null;
};

/** The new slot of a reschedule, checked against the calendar and the sitting window. */
function newSlot(args: ChangeArgs, c: MoveContext): Slot | null {
  const a = needAppt(args.appointment_id, c);
  const terms = changeTerms(a, useStore.getState().cal);
  if (!terms.allowed) return c.refuse("action", terms.why);
  if (args.action === "cancel") return null;
  if (args.action !== "reschedule") return c.refuse("action", "reschedule or cancel", ["reschedule", "cancel"]);
  const svc = service(a.service)!;
  const date = needDay(args.date, c);
  if (!isTime(args.time)) return c.refuse("time", "a reschedule needs the new time, HH:MM");
  const s = useStore.getState();
  if (!inWindow(a, date, s)) {
    const w = sittingWindow(a, s.cal, patientById(a.patient_id, s));
    c.refuse("date", DATA.policies.cancellation.rct_text, w ? [w[0], w[1]] : []);
  }
  const opts = {
    branch: args.branch_id ?? null,
    dentist: svc.resource ? null : (args.dentist_id ?? null),
    resource: args.resource_id ?? null,
    ignore: a.id,
  };
  const slot = s.cal.slotAt(svc, date, pad(args.time), opts);
  if (!slot) return c.refuse("time", `${pad(args.time)} is not free on ${shortDate(date)}`, nearest(s.cal.slots(svc, date, opts), pad(args.time)));
  return slot;
}

function sameChange(args: ChangeArgs, slot: Slot | null): boolean {
  const ch = useStore.getState().change;
  if (!ch || ch.done || ch.apptId !== args.appointment_id || ch.action !== args.action) return false;
  if (!slot) return true;
  return !!ch.slot && ch.slot.date === slot.date && ch.slot.start === slot.start && ch.slot.branch === slot.branch;
}

/** Every performer, each `c.scrollTo` showing its target's whole group (X1, `view.ts`). */
export function performers(): Performers<Spec> {
  return wholeView(rawPerformers());
}

function rawPerformers(): Performers<Spec> {
  return {
    "site.go": async ({ page }, c) => {
      if (!(page in PATH)) return c.refuse("page", `no page ${page}`, Object.keys(PATH));
      const p = page as Page;
      if (currentPage() === p) {
        const link = $(`.site-nav [data-nav="${p}"]`);
        if (link && link.getBoundingClientRect().width > 0) await c.ring(link, PAGE_LABEL[p]);
        window.scrollTo({ top: 0, behavior: "smooth" });
        return `already on the ${PAGE_LABEL[p]} page`;
      }
      await goTo(p, c);
      return `opened the ${PAGE_LABEL[p]} page`;
    },

    "site.show": async ({ thing: name }, c) => {
      const key = String(name ?? "").trim().toLowerCase().replace(/\s+/g, "-");
      let el = thing(key);
      if (!el && HOME_THINGS.includes(key)) {
        await goTo("home", c);
        el = await appear(() => thing(key));
      } else if (!el && BOOK_THINGS.includes(key)) {
        await goTo("book", c);
        el = await appear(() => thing(key));
      } else if (!el && APPT_THINGS.includes(key)) {
        await goTo("my-appointments", c);
        el = await appear(() => thing(key));
      }
      if (!el) {
        const here = [...document.querySelectorAll<HTMLElement>("main [data-stage-thing]")].map((e) => e.dataset.stageThing!);
        return c.refuse("thing", `nothing called ${key} on this page`, [...new Set([...here, ...HOME_THINGS])].slice(0, 20));
      }
      const label = el.dataset.stageLabel ?? key.replace(/-/g, " ");
      await show(el, c, label);
      return `showing ${label}`;
    },

    "book.slots": async ({ service_id, date, branch_id, dentist_id, view }, c) => {
      const svc = needService(service_id, c);
      const day = needDay(date, c);
      if (branch_id && !branch(branch_id)) return c.refuse("branch_id", `no branch ${branch_id}`, DATA.branches.map((b) => b.id));
      if (dentist_id && !svc.resource && !svc.dentists?.includes(dentist_id)) {
        c.refuse("dentist_id", `${dentist(dentist_id)?.name ?? dentist_id} does not do ${svc.name}`, svc.dentists ?? []);
      }
      if (svc.resource && branch_id && !branch(branch_id)!.imaging.some((r) => r.does.includes(svc.resource!))) {
        const where = DATA.branches.filter((b) => b.imaging.some((r) => r.does.includes(svc.resource!))).map((b) => b.id);
        c.refuse("branch_id", `${svc.name} is not done at ${branch(branch_id)!.short}`, where);
      }
      await goTo("book", c);
      await chooseService(service_id, c);
      const b = useStore.getState().book;
      if ((branch_id ?? null) !== b.branch) actions.selectBranch(branch_id ?? null, "agent");
      if (svc.resource) {
        const r = branch_id ? branch(branch_id)!.imaging.find((x) => x.does.includes(svc.resource!)) : undefined;
        actions.selectResource(r?.id ?? null, "agent");
      } else if ((dentist_id ?? null) !== useStore.getState().book.dentist) {
        actions.selectDentist(dentist_id ?? null, "agent");
      }
      actions.setFocus(null);
      const cal = (await appear(() => thing("calendar")))!;
      await c.scrollTo(cal);
      await c.ring(cal, "Calendar");
      actions.setView(view === "week" ? "week" : "day");
      actions.setDate(day, "agent");
      const st = useStore.getState();
      const opts = { branch: branch_id ?? null, dentist: svc.resource ? null : (dentist_id ?? null) };
      const free = st.cal.slots(svc, day, opts);
      const whoText = dentist_id ? ` with ${dentist(dentist_id)?.short}` : "";
      const atText = branch_id ? ` at ${where(branch_id)}` : "";
      let line: string;
      if (free.length) {
        const first = free[0];
        line = `${free.length} free start times for ${svc.name}${whoText}${atText} on ${shortDate(day)}, from ${time12(first.time)}`;
      } else {
        const next = st.cal.nextDays(svc, { ...opts, start: addDays(day, 1), days: 1 })[0];
        line = `no free times for ${svc.name}${whoText}${atText} on ${shortDate(day)}${next ? `; the next is ${shortDate(next[0])}, from ${time12(next[1][0].time)}` : ""}`;
      }
      c.done(line);
      c.after(async () => {
        await frame();
        const els = [...document.querySelectorAll<HTMLElement>(`.cal [data-slot^="${day}"]`)].slice(0, 16);
        await ringAll(c, els, "Free times");
      });
      return line;
    },

    "book.hold": async (args, c) => {
      const svc = needService(args.service_id, c);
      const slot = findSlot(args, c);
      let sittings: Slot[] | undefined;
      if ((svc.sittings ?? 1) > 1 && args.sittings?.length) {
        const parsed = args.sittings.map((x) => parseSitting(String(x), slot.dentist));
        if (parsed.every(Boolean)) sittings = parsed as Slot[];
      }
      await goTo("book", c);
      await chooseService(svc.id, c);
      aimCalendar(slot);
      const key = `${slot.date} ${slot.time}`;
      const subject = slot.dentist ?? slot.resource ?? "";
      const el = await appear(
        () => $(`.cal [data-slot="${key}"][data-subject="${subject}"]`) ?? $(`.cal [data-slot="${key}"]`),
      );
      if (el) await show(el, c, `${time12(slot.time)}`);
      actions.hold(slot, "agent", sittings);
      const held = useStore.getState().book.hold!;
      const later = held.sittings.length ? `; sittings 2 and 3 pencilled for ${held.sittings.map(when).join(" and ")}` : "";
      const line = `holding ${svc.name} ${when(slot)} with ${who(slot)} at ${where(slot.branch)}${later}; Confirm is on screen`;
      c.done(line);
      c.after(async () => {
        const card = await appear(() => thing("summary"));
        if (card) {
          await c.scrollTo(card);
          await c.ring(card, "Summary");
        }
      });
      return line;
    },

    "book.confirm": async (args, c) => {
      const s0 = useStore.getState();
      if (!s0.book.hold) return c.refuse("booking_id", "nothing is held: hold a slot first");
      if (!s0.signedIn) return c.refuse("patient_id", "no patient is verified on this page");
      if (args.patient_id !== s0.signedIn) return c.refuse("patient_id", `the verified patient here is ${s0.signedIn}`, [s0.signedIn!]);
      const slot = findSlot(args, c);
      await goTo("book", c);
      const h = useStore.getState().book.hold;
      const same = h && h.service === args.service_id && h.slot.date === slot.date && h.slot.start === slot.start && h.slot.branch === slot.branch;
      if (!same) {
        if (useStore.getState().book.service !== args.service_id) actions.selectService(args.service_id, "agent");
        aimCalendar(slot);
        const sit = args.sittings?.map((x) => parseSitting(String(x), slot.dentist));
        actions.hold(slot, "agent", sit && sit.every(Boolean) ? (sit as Slot[]) : undefined);
      }
      const btn = await appear(() => thing("confirm"));
      if (btn) await show(btn, c, "Confirm");
      const got = actions.confirm("agent", {
        bookingId: args.booking_id,
        sittingIds: (args.sitting_ids ?? []).map(String),
      });
      if (!got.ok) return c.refuse(got.why.includes("slot") ? "time" : "booking_id", got.why);
      const svc = service(args.service_id)!;
      const sittingIds = useStore.getState().book.confirmed?.sittingIds ?? [];
      const line = `booked ${got.id}: ${svc.name} ${when(slot)} with ${who(slot)} at ${where(slot.branch)}${sittingIds.length ? `, with sittings ${sittingIds.join(" and ")}` : ""}`;
      c.done(line);
      c.after(async () => {
        const block = await appear(() => $(`.cal [data-appt="${got.id}"]`));
        if (block) await show(block, c, "Your appointment");
      });
      return line;
    },

    "patient.phone": async ({ phone }, c) => {
      const digits = normalPhone(String(phone ?? ""));
      if (digits.length !== 10) return c.refuse("phone", "a mobile number has ten digits");
      const me = signedInPatient();
      if (me && me.phone === digits) return `already signed in as ${me.name}`;
      if (currentPage() === "home") await goTo(useStore.getState().book.hold ? "book" : "my-appointments", c);
      if (me) actions.signOut("agent");
      actions.openSignin();
      if (useStore.getState().signin.step !== "phone") actions.resetSignin();
      actions.openSignin();
      const field = await appear(() => $('[data-stage-thing="signin"] [name="phone"]'));
      const panel = thing("signin");
      if (field) await show(field, c, "Mobile number");
      else if (panel) await show(panel, c, "Sign in");
      actions.setPhone(digits);
      await c.beat(300);
      actions.sendCode(digits);
      return `code sent to ${showPhone(digits)}; the demo SMS shows it on screen`;
    },

    "patient.otp": async ({ code }, c) => {
      const s = useStore.getState().signin;
      if (!s.sent || s.step === "phone") return c.refuse("code", "no code has been sent yet: send one to the phone first");
      if (s.step === "name") return c.refuse("code", "the code is already verified; the new patient's name is needed");
      const field = await appear(() => $('[data-stage-thing="signin"] [name="code"]'));
      if (field) await show(field, c, "Code");
      actions.setCode(String(code ?? ""));
      await c.beat(300);
      const got = actions.verify(String(code ?? ""), "agent");
      if (got === "wrong") return c.refuse("code", "that code does not match the one sent");
      if (got === "need-name") return `verified; new number ${showPhone(s.phone)}, name needed`;
      const p = signedInPatient()!;
      const n = useStore.getState().cal.upcoming(p.id).length;
      return `signed in as ${p.name} (${p.id}), ${n} upcoming appointment${n === 1 ? "" : "s"}`;
    },

    "patient.name": async ({ name }, c) => {
      const s = useStore.getState().signin;
      if (s.step !== "name") return c.refuse("name", s.sent ? "verify the code first" : "no new number is being registered");
      const clean = String(name ?? "").trim();
      if (clean.length < 2) return c.refuse("name", "a full name is needed");
      const field = await appear(() => $('[data-stage-thing="signin"] [name="name"]'));
      if (field) await show(field, c, "Name");
      actions.setName(clean);
      await c.beat(300);
      const p = actions.register(clean, "agent")!;
      return `registered ${p.name} as new patient ${p.id}`;
    },

    "appt.focus": async ({ appointment_id }, c) => {
      const a = needAppt(appointment_id, c);
      await goTo("my-appointments", c);
      const el = await appear(() => thing(`appt-${a.id}`));
      if (!el) return c.refuse("appointment_id", `${a.id} is not on screen`, upcomingIds());
      await show(el, c, a.id);
      const svc = service(a.service)!;
      return `${a.id}: ${svc.name} on ${shortDate(a.date)} at ${time12(`${String(Math.floor(a.start / 60)).padStart(2, "0")}:${String(a.start % 60).padStart(2, "0")}`)}${a.status === "cancelled" ? " (cancelled)" : ""}`;
    },

    "appt.propose": async (args, c) => {
      const slot = newSlot(args, c);
      const a = useStore.getState().cal.appts.get(args.appointment_id)!;
      await goTo("my-appointments", c);
      const card = await appear(() => thing(`appt-${a.id}`));
      if (card) await show(card, c, a.id);
      actions.propose(a.id, args.action, slot, args.fee ?? 0);
      const fee = args.fee ? `a ₹${args.fee} late-change fee` : "no fee";
      const line =
        args.action === "cancel"
          ? `the cancellation sheet for ${a.id} is open, ${fee}; Confirm or Keep`
          : `the change sheet for ${a.id} is open: to ${when(slot!)} with ${who(slot!)} at ${where(slot!.branch)}, ${fee}; Confirm or Keep`;
      c.done(line);
      c.after(async () => {
        const sheet = await appear(() => thing("change-sheet"));
        if (sheet) await show(sheet, c, "Change");
      });
      return line;
    },

    "appt.apply": async (args, c) => {
      const slot = newSlot(args, c);
      await goTo("my-appointments", c);
      if (!sameChange(args, slot)) actions.propose(args.appointment_id, args.action, slot, args.fee ?? 0);
      const btn = await appear(() => $('[data-stage-thing="change-sheet"] [data-confirm]'));
      if (btn) await show(btn, c, "Confirm");
      const got = actions.applyChange("agent");
      if (!got.ok) return c.refuse(got.why.includes("slot") ? "time" : "appointment_id", got.why);
      const line = args.action === "cancel" ? `${args.appointment_id} is cancelled` : `${args.appointment_id} moved to ${when(slot!)} at ${where(slot!.branch)}`;
      c.done(line);
      c.after(async () => {
        const card = await appear(() => thing(`appt-${args.appointment_id}`));
        if (card) await show(card, c, args.appointment_id);
      });
      return line;
    },

    "callback.request": async ({ callback_id, reason, urgency, window: win, phone }, c) => {
      if (!["urgent", "today", "routine"].includes(urgency)) return c.refuse("urgency", `no urgency ${urgency}`, ["urgent", "today", "routine"]);
      if (!String(reason ?? "").trim()) return c.refuse("reason", "say what the dentist should call about");
      if (phone && normalPhone(phone).length !== 10) return c.refuse("phone", "a mobile number has ten digits");
      if (!phone && !signedInPatient()) return c.refuse("phone", "no number to call: ask for one, or sign the patient in");
      const cb = actions.requestCallback(
        { id: callback_id, reason: String(reason), urgency: urgency as "urgent" | "today" | "routine", window: win ?? undefined, phone },
        "agent",
      );
      const card = await appear(() => thing("callback"));
      if (card) await show(card, c, cb.id);
      return `callback ${cb.id} requested: a dentist calls ${showPhone(cb.phone ?? "")} ${cb.window}`;
    },

    "cal.view": async ({ date, dentist_id, resource_id, mode }, c) => {
      if (!isDate(date)) return c.refuse("date", "a date is YYYY-MM-DD");
      if (dentist_id && !dentist(dentist_id)) return c.refuse("dentist_id", `no dentist ${dentist_id}`, DATA.dentists.map((d) => d.id));
      if (resource_id && !room(resource_id)) {
        c.refuse("resource_id", `no imaging room ${resource_id}`, DATA.branches.flatMap((b) => b.imaging.map((r) => r.id)));
      }
      const today = useStore.getState().cal.today;
      if (daysBetween(today, date) < -7 || daysBetween(today, date) > DATA.booking.horizon_days + 7) {
        c.refuse("date", `the calendar shows ${today} to ${addDays(today, DATA.booking.horizon_days)}`);
      }
      const subject = dentist_id ?? resource_id ?? null;
      const view = mode === "day" ? "day" : "week";
      const picker = useStore.getState().picker;
      if (currentPage() === "my-appointments" && picker) {
        const cal = await appear(() => thing("calendar"));
        if (cal) await show(cal, c, "Calendar");
        actions.pickerPatch({ date, view, focus: subject ?? picker.focus });
      } else {
        await goTo("book", c);
        const cal = (await appear(() => thing("calendar")))!;
        await c.scrollTo(cal);
        await c.ring(cal, "Calendar");
        actions.setFocus(subject);
        actions.setView(view);
        actions.setDate(date, "agent");
      }
      const name = dentist_id ? dentist(dentist_id)!.name : resource_id ? `${room(resource_id)!.room.label}, ${room(resource_id)!.branch.short}` : "the calendar";
      return view === "week" ? `showing ${name}'s week of ${shortDate(date)}` : `showing ${name} on ${shortDate(date)}`;
    },
  };
}
