/**
 * The one store controller. A click and a Stage performer call the same
 * actions; a performer passes `by: "agent"`, so every event the brain hears
 * says who did it.
 *
 * What this browser changed (new and moved appointments, cancellations, the
 * patients it registered, the signed-in patient and the callbacks it asked
 * for) is the session overlay, kept in localStorage under `dantika-demo-v1`
 * and laid over the authored calendar. Everything else is screen state.
 */
import { create } from "zustand";
import { type Category, DATA, type Patient, minutes, normalPhone, room, service } from "../data/clinic";
import {
  type Appt,
  Calendar,
  type Clock,
  type Slot,
  changeTerms,
  checkRule,
  nextOpenDay,
  nowClock,
  sittingWindow,
  weekdayOf,
} from "../data/slots";
import { type By, emit } from "../voice/events";
import type { AppointmentIn } from "../voice/events.gen";
import { LANGS, persona } from "../persona";

const KEY = "dantika-demo-v1";

export interface Callback {
  id: string;
  reason: string;
  urgency: "urgent" | "today" | "routine";
  window: string;
  phone: string | null;
  patient_id: string | null;
  at: number;
}

interface Overlay {
  appts: Appt[];
  patients: Patient[];
  signedIn: string | null;
  callbacks: Callback[];
  seq: number;
}

export interface Hold {
  service: string;
  slot: Slot;
  /** A root canal's later sittings. */
  sittings: Slot[];
}

export type View = "day" | "week";

export interface BookUi {
  /** The service list's open tab. */
  tab: Category;
  service: string | null;
  branch: string | null;
  dentist: string | null;
  resource: string | null;
  date: string;
  view: View;
  /** cal.view: one dentist's or room's calendar, without changing the selection. */
  focus: string | null;
  hold: Hold | null;
  confirmed: { id: string; sittingIds: string[] } | null;
  error: string | null;
}

export interface SignIn {
  phone: string;
  sent: boolean;
  code: string;
  step: "phone" | "code" | "name";
  name: string;
  error: string | null;
  /** The panel is asked for (Confirm pressed while signed out). */
  wanted: boolean;
}

export interface Change {
  apptId: string;
  action: "reschedule" | "cancel";
  fee: number;
  slot: Slot | null;
  done: boolean;
  error: string | null;
}

export interface Picker {
  apptId: string;
  date: string;
  view: View;
  focus: string | null;
}

export interface State extends Overlay {
  clock: Clock;
  cal: Calendar;
  book: BookUi;
  signin: SignIn;
  change: Change | null;
  picker: Picker | null;
  lang: string;
  pendingLang: string | null;
  /** The appointment that just changed: its block and card pulse. */
  pulse: string | null;
  lastCallback: string | null;
}

function load(): Overlay {
  const empty: Overlay = { appts: [], patients: [], signedIn: null, callbacks: [], seq: 0 };
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<Overlay> | null;
    if (!raw) return empty;
    return {
      appts: Array.isArray(raw.appts) ? raw.appts : [],
      patients: Array.isArray(raw.patients) ? raw.patients : [],
      signedIn: typeof raw.signedIn === "string" ? raw.signedIn : null,
      callbacks: Array.isArray(raw.callbacks) ? raw.callbacks : [],
      seq: typeof raw.seq === "number" ? raw.seq : 0,
    };
  } catch {
    return empty;
  }
}

function save(s: Overlay) {
  try {
    const { appts, patients, signedIn, callbacks, seq } = s;
    localStorage.setItem(KEY, JSON.stringify({ appts, patients, signedIn, callbacks, seq }));
  } catch {
    /* storage unavailable: the session just does not survive a reload */
  }
}

const firstDay = (clock: Clock) => (weekdayOf(clock.today) === "sun" ? nextOpenDay(clock.today) : clock.today);

const freshBook = (clock: Clock): BookUi => ({
  tab: "appointment",
  service: null,
  branch: null,
  dentist: null,
  resource: null,
  date: firstDay(clock),
  view: "day",
  focus: null,
  hold: null,
  confirmed: null,
  error: null,
});

const freshSignin = (): SignIn => ({ phone: "", sent: false, code: "", step: "phone", name: "", error: null, wanted: false });

const initial = load();
const clock0 = nowClock();

export const useStore = create<State>(() => ({
  ...initial,
  clock: clock0,
  cal: new Calendar(clock0, initial.appts),
  book: freshBook(clock0),
  signin: freshSignin(),
  change: null,
  picker: null,
  lang: persona.default_language,
  pendingLang: null,
  pulse: null,
  lastCallback: null,
}));

const get = () => useStore.getState();
const set = (patch: Partial<State> | ((s: State) => Partial<State>)) => useStore.setState(patch);

/** Write the overlay (and rebuild the calendar when appointments moved). */
function commit(patch: Partial<Overlay>) {
  const s = get();
  const next = { ...s, ...patch };
  const cal = patch.appts ? new Calendar(s.clock, next.appts) : s.cal;
  set({ ...patch, cal });
  save(next);
}

// ─── Reading ─────────────────────────────────────────────────────────────────

export const allPatients = (s: State = get()): Patient[] => [...DATA.patients, ...s.patients];
export const patientById = (id: string | null | undefined, s: State = get()) => allPatients(s).find((p) => p.id === id);
export const patientByPhone = (phone: string, s: State = get()) => allPatients(s).find((p) => p.phone === normalPhone(phone));
export const signedInPatient = (s: State = get()) => patientById(s.signedIn, s);

export function toWire(a: Appt): AppointmentIn {
  return {
    id: a.id,
    patient_id: a.patient_id,
    service: a.service,
    branch: a.branch,
    date: a.date,
    time: `${String(Math.floor(a.start / 60)).padStart(2, "0")}:${String(a.start % 60).padStart(2, "0")}`,
    duration_min: a.duration_min,
    dentist: a.dentist,
    chair: a.chair,
    resource: a.resource,
    sitting: a.sitting,
    changes: a.changes,
    status: a.status,
  };
}

/** schedule_changed: every appointment this browser made or changed, whole. */
export function sendSchedule(by: By = "visitor") {
  emit("schedule_changed", { appointments: get().appts.map(toWire) }, by);
}

function selectionEvent(by: By) {
  if (by !== "visitor") return;
  const b = get().book;
  emit(
    "selection_changed",
    {
      service_id: b.service,
      branch_id: b.branch,
      dentist_id: b.dentist,
      date: b.date,
      time: b.hold?.slot.time ?? null,
    },
    by,
  );
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function patchBook(patch: Partial<BookUi>) {
  set((s) => ({ book: { ...s.book, ...patch } }));
}

function mint(prefix: string, base: number): string {
  const s = get();
  const seq = s.seq + 1;
  commit({ seq });
  return `${prefix}${base + seq}`;
}

export const actions = {
  /** The clock moves on: slots and "upcoming" are recomputed. */
  tick() {
    const clock = nowClock();
    const s = get();
    if (clock.today === s.clock.today && clock.minute === s.clock.minute) return;
    set({ clock, cal: new Calendar(clock, s.appts) });
  },

  // ── Booking page ──
  selectService(id: string | null, by: By = "visitor") {
    const b = get().book;
    if (b.service === id) return;
    const svc = service(id);
    // Keep a branch or dentist the new service can still use.
    const dentistOk = b.dentist && svc?.dentists?.includes(b.dentist);
    patchBook({
      tab: svc?.category ?? b.tab,
      service: id,
      dentist: dentistOk ? b.dentist : null,
      resource: null,
      hold: null,
      confirmed: null,
      focus: null,
      error: null,
    });
    selectionEvent(by);
  },
  selectBranch(id: string | null, by: By = "visitor") {
    const b = get().book;
    const resource = b.resource && id && room(b.resource)?.branch.id !== id ? null : b.resource;
    patchBook({ branch: id, resource, hold: null, focus: null, error: null });
    selectionEvent(by);
  },
  selectDentist(id: string | null, by: By = "visitor") {
    patchBook({ dentist: id, hold: null, focus: null, error: null });
    selectionEvent(by);
  },
  selectResource(id: string | null, by: By = "visitor") {
    patchBook({ resource: id, hold: null, focus: null, error: null });
    selectionEvent(by);
  },
  setDate(date: string, by: By = "visitor") {
    patchBook({ date });
    selectionEvent(by);
  },
  setTab(tab: Category) {
    patchBook({ tab });
  },
  setView(view: View) {
    patchBook({ view });
  },
  setFocus(focus: string | null) {
    patchBook({ focus });
  },

  /** Hold one free slot: the summary card shows. */
  hold(slot: Slot, by: By = "visitor", sittings?: Slot[]) {
    const s = get();
    const svcId = s.book.service;
    const svc = service(svcId);
    if (!svc || !svcId) return;
    const plan = sittings ?? s.cal.planSittings(svc, slot);
    patchBook({ hold: { service: svcId, slot, sittings: plan }, date: slot.date, confirmed: null, error: null });
    selectionEvent(by);
  },
  clearHold() {
    patchBook({ hold: null, error: null });
  },

  /** Book the held slot. Returns the booking id, or why not. */
  confirm(by: By = "visitor", ids?: { bookingId?: string; sittingIds?: string[] }): { ok: true; id: string } | { ok: false; why: string } {
    const s = get();
    const hold = s.book.hold;
    if (!hold) return { ok: false, why: "nothing is held" };
    const patient = signedInPatient(s);
    if (!patient) {
      set((st) => ({ signin: { ...st.signin, wanted: true } }));
      return { ok: false, why: "the patient is not verified" };
    }
    const svc = service(hold.service)!;
    const fresh = s.cal.slotAt(svc, hold.slot.date, hold.slot.time, {
      branch: hold.slot.branch,
      dentist: hold.slot.dentist,
      resource: hold.slot.resource,
    });
    if (!fresh) {
      patchBook({ error: "That time was just taken. Pick another free time." });
      return { ok: false, why: "the slot was taken" };
    }
    const rule = checkRule(svc, patient, fresh.date, s.cal);
    if (rule.ok === false) {
      patchBook({ error: `${rule.rule?.title}: ${rule.why}.` });
      return { ok: false, why: `${rule.rule?.title ?? "a rule"}: ${rule.why}` };
    }
    const id = ids?.bookingId ?? mint(DATA.booking.id_prefix, 25000);
    const multi = (svc.sittings ?? 1) > 1;
    const made: Appt[] = [fresh, ...hold.sittings].map((slot, i) => ({
      id: i === 0 ? id : (ids?.sittingIds?.[i - 1] ?? mint(DATA.booking.id_prefix, 25000)),
      service: svc.id,
      branch: slot.branch,
      date: slot.date,
      start: slot.start,
      duration_min: svc.duration_min,
      dentist: slot.dentist,
      chair: slot.chair,
      resource: slot.resource,
      patient_id: patient.id,
      sitting: multi ? i + 1 : null,
      changes: 0,
      status: "booked",
    }));
    const keep = get().appts.filter((a) => !made.some((m) => m.id === a.id));
    commit({ appts: [...keep, ...made] });
    patchBook({ hold: null, confirmed: { id, sittingIds: made.slice(1).map((m) => m.id) }, error: null });
    set({ pulse: id });
    emit("booked", { booking_id: id, service_id: svc.id, date: fresh.date, time: fresh.time, dentist_id: fresh.dentist, branch_id: fresh.branch }, by);
    sendSchedule(by);
    return { ok: true, id };
  },

  // ── Sign-in ──
  openSignin() {
    set((s) => ({ signin: { ...s.signin, wanted: true } }));
  },
  setPhone(phone: string) {
    set((s) => ({ signin: { ...s.signin, phone, error: null } }));
  },
  sendCode(phone?: string) {
    const p = normalPhone(phone ?? get().signin.phone);
    if (p.length !== 10) {
      set((s) => ({ signin: { ...s.signin, phone: phone ?? s.signin.phone, error: "Enter a 10-digit mobile number." } }));
      return false;
    }
    set((s) => ({ signin: { ...s.signin, phone: p, sent: true, step: "code", code: "", error: null, wanted: true } }));
    return true;
  },
  setCode(code: string) {
    set((s) => ({ signin: { ...s.signin, code: code.replace(/\D/g, "").slice(0, 4), error: null } }));
  },
  /** Verify the code: signs a known patient in, or asks a new one's name. */
  verify(code: string, by: By = "visitor"): "signed-in" | "need-name" | "wrong" | "no-phone" {
    const s = get();
    if (!s.signin.sent) return "no-phone";
    const digits = code.replace(/\D/g, "");
    if (digits !== DATA.otp.demo_code) {
      set((st) => ({ signin: { ...st.signin, code: digits, error: "That code doesn't match. Check the SMS and try again." } }));
      return "wrong";
    }
    const p = patientByPhone(s.signin.phone);
    if (!p) {
      set((st) => ({ signin: { ...st.signin, code: digits, step: "name", error: null } }));
      return "need-name";
    }
    commit({ signedIn: p.id });
    set({ signin: freshSignin() });
    emit("patient_signed_in", { patient_id: p.id, name: p.name, phone: p.phone, is_new: false }, by);
    return "signed-in";
  },
  setName(name: string) {
    set((s) => ({ signin: { ...s.signin, name, error: null } }));
  },
  /** Register the new patient on the verified number. */
  register(name: string, by: By = "visitor"): Patient | null {
    const s = get();
    const clean = name.trim().replace(/\s+/g, " ");
    if (s.signin.step !== "name" || !clean) return null;
    let n = 2001 + s.patients.length;
    while (allPatients(s).some((p) => p.id === `P-${n}`)) n++;
    const p: Patient = { id: `P-${n}`, name: clean, phone: s.signin.phone, referral: null, history: [] };
    commit({ patients: [...s.patients, p], signedIn: p.id });
    set({ signin: freshSignin() });
    emit("patient_signed_in", { patient_id: p.id, name: p.name, phone: p.phone, is_new: true }, by);
    return p;
  },
  resetSignin() {
    set({ signin: freshSignin() });
  },
  signOut(by: By = "visitor") {
    commit({ signedIn: null });
    set({ change: null, picker: null });
    emit("patient_signed_out", {}, by);
  },

  // ── My appointments ──
  openPicker(apptId: string) {
    const a = get().cal.appts.get(apptId);
    if (!a) return;
    set({ picker: { apptId, date: a.date, view: "day", focus: a.dentist ?? a.resource }, change: null });
  },
  pickerPatch(patch: Partial<Picker>) {
    set((s) => (s.picker ? { picker: { ...s.picker, ...patch } } : {}));
  },
  closePicker() {
    set({ picker: null });
  },
  /** Open the change sheet: old → new, or the cancellation. */
  propose(apptId: string, action: "reschedule" | "cancel", slot: Slot | null, fee?: number) {
    const s = get();
    const a = s.cal.appts.get(apptId);
    if (!a) return;
    const terms = changeTerms(a, s.cal);
    set({ change: { apptId, action, slot, fee: fee ?? terms.fee, done: false, error: null }, picker: null });
  },
  closeChange() {
    set({ change: null });
  },
  /** Make the change the sheet shows. */
  applyChange(by: By = "visitor"): { ok: true; detail: string } | { ok: false; why: string } {
    const s = get();
    const ch = s.change;
    if (!ch) return { ok: false, why: "no change is open" };
    const a = s.cal.appts.get(ch.apptId);
    if (!a) return { ok: false, why: "no such appointment" };
    const terms = changeTerms(a, s.cal);
    if (!terms.allowed) return { ok: false, why: terms.why };
    let next: Appt;
    if (ch.action === "cancel") {
      next = { ...a, status: "cancelled" };
    } else {
      const slot = ch.slot;
      if (!slot) return { ok: false, why: "no new time chosen" };
      const svc = service(a.service)!;
      const fresh = s.cal.slotAt(svc, slot.date, slot.time, {
        branch: slot.branch,
        dentist: slot.dentist,
        resource: slot.resource,
        ignore: a.id,
      });
      if (!fresh) {
        set({ change: { ...ch, error: "That time was just taken. Choose another." } });
        return { ok: false, why: "the new slot was taken" };
      }
      next = {
        ...a,
        date: fresh.date,
        start: fresh.start,
        branch: fresh.branch,
        dentist: fresh.dentist,
        chair: fresh.chair,
        resource: fresh.resource,
        changes: a.changes + 1,
      };
    }
    commit({ appts: [...s.appts.filter((x) => x.id !== a.id), next] });
    set({ change: { ...ch, done: true, error: null }, pulse: a.id });
    emit(
      "appointment_changed",
      {
        appointment_id: a.id,
        action: ch.action,
        date: ch.action === "cancel" ? null : next.date,
        time: ch.action === "cancel" ? null : toWire(next).time,
        fee: ch.fee,
      },
      by,
    );
    sendSchedule(by);
    return { ok: true, detail: ch.action === "cancel" ? "cancelled" : "moved" };
  },

  // ── Callbacks ──
  requestCallback(
    cb: { id?: string; reason: string; urgency: Callback["urgency"]; window?: string; phone?: string | null },
    by: By = "visitor",
  ): Callback {
    const s = get();
    const id = cb.id ?? mint("CB-", 3200);
    const made: Callback = {
      id,
      reason: cb.reason,
      urgency: cb.urgency,
      window: cb.window ?? DATA.clinical.callback_windows[cb.urgency] ?? "",
      phone: cb.phone ? normalPhone(cb.phone) : (signedInPatient(s)?.phone ?? null),
      patient_id: s.signedIn,
      at: Date.now(),
    };
    commit({ callbacks: [...get().callbacks.filter((c) => c.id !== id), made] });
    set({ lastCallback: id });
    if (by === "visitor") emit("callback_requested", { callback_id: id, reason: made.reason, urgency: made.urgency }, by);
    return made;
  },
  dismissCallback() {
    set({ lastCallback: null });
  },

  // ── Language ──
  setLang(lang: string) {
    if (LANGS.includes(lang)) set({ lang, pendingLang: null });
  },
  requestLang(lang: string) {
    set({ pendingLang: lang });
    emit("language_requested", { language: lang as "en" | "hi" }, "visitor");
  },

  /** "Reset demo": forget everything this browser did. */
  reset() {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* nothing stored */
    }
    const clock = nowClock();
    set({
      appts: [],
      patients: [],
      signedIn: null,
      callbacks: [],
      seq: 0,
      clock,
      cal: new Calendar(clock, []),
      book: freshBook(clock),
      signin: freshSignin(),
      change: null,
      picker: null,
      pulse: null,
      lastCallback: null,
    });
  },
};

/** Is a reschedule of `a` to `date` inside a root canal's sitting window? */
export function inWindow(a: Appt, date: string, s: State = get()): boolean {
  const w = sittingWindow(a, s.cal, patientById(a.patient_id, s));
  if (!w) return true;
  return date >= w[0] && date <= w[1];
}

export const timeOf = (t: string) => minutes(t);
