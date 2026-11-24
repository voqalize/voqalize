/**
 * `?debug=1`: every move by hand, through a local `Moves` with the same
 * performers and the same spotlight theme, so a ring and its effect look
 * exactly as they do in a call. Also `window.__dentalDebug` for scripts:
 *
 *   await window.__dentalDebug.run("book.hold", { service_id: "scaling", … })
 *   window.__dentalDebug.examples()   // prefilled args for every move
 */
import { Moves, Spotlight } from "@voqalize/stage";
import { DATA, service } from "../data/clinic";
import { addDays, changeTerms, weekdayOf } from "../data/slots";
import { actions, useStore } from "../state/store";
import { performers } from "./performers";
import { scene } from "./scene.gen";
import { STAGE_THEME } from "./theme";
import { useFakeCall } from "../voice/fake";
import { eventLog } from "../voice/events";

let local: Moves | null = null;
let n = 0;

export function debugMoves(): Moves {
  if (!local) {
    local = new Moves(new Spotlight(STAGE_THEME));
    scene.registerAll(local, performers());
  }
  return local;
}

export const MOVE_IDS = scene.spec.moves.map((m) => m.id);

export interface RunLog {
  id: string;
  args: unknown;
  result: unknown;
  at: number;
}
const runs: RunLog[] = [];
const listeners = new Set<() => void>();
export const runLog = () => runs;
export function onRunLog(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export async function runMove(id: string, args: unknown) {
  const result = await debugMoves().run(id, args, `dbg-${++n}`);
  runs.unshift({ id, args, result, at: Date.now() });
  if (runs.length > 20) runs.pop();
  listeners.forEach((l) => l());
  return result;
}

/** The first open day from `from` (today) that has a free slot for `svcId`. */
function dayWithSlots(svcId: string, opts: { branch?: string | null; dentist?: string | null } = {}, from?: string) {
  const s = useStore.getState();
  const svc = service(svcId)!;
  const got = s.cal.nextDays(svc, { ...opts, start: from ?? addDays(s.cal.today, 1), days: 1 })[0];
  return got ?? [addDays(s.cal.today, 1), []];
}

/** Prefilled, real arguments for every move, read off the calendar now. */
export function examples(): Record<string, Record<string, unknown>> {
  const s = useStore.getState();
  const [day, free] = dayWithSlots("scaling", { branch: "indiranagar", dentist: "dr-farah" });
  const hold = s.book.hold?.slot ?? free[Math.min(4, free.length - 1)];
  const held = s.book.hold;
  const svcId = held?.service ?? "scaling";
  const pid = s.signedIn ?? "P-1001";
  const mine = s.signedIn ? s.cal.upcoming(s.signedIn) : [];
  const target = mine.find((a) => a.service === "scaling") ?? mine[0] ?? s.cal.appts.get("DT-24063")!;
  const tsvc = service(target.service)!;
  const [mday, mfree] = dayWithSlots(target.service, { dentist: target.dentist }, addDays(target.date, 1));
  const move = mfree[Math.floor(mfree.length / 2)] ?? mfree[0];
  const terms = changeTerms(target, s.cal);
  const slotArgs = hold
    ? {
        service_id: svcId,
        branch_id: hold.branch,
        date: hold.date,
        time: hold.time,
        dentist_id: hold.dentist,
        chair_id: hold.chair,
        resource_id: hold.resource,
        ...(held?.sittings.length ? { sittings: held.sittings.map((x) => `${x.date} ${x.time} ${x.branch} ${x.chair}`) } : {}),
      }
    : { service_id: "scaling", branch_id: "indiranagar", date: day, time: "16:00", dentist_id: "dr-farah" };
  const viewDay = weekdayOf(s.cal.today) === "sun" ? addDays(s.cal.today, 1) : s.cal.today;
  return {
    "site.go": { page: "book" },
    "site.show": { thing: "parking" },
    "book.slots": { service_id: "scaling", date: day, branch_id: "indiranagar", dentist_id: "dr-farah", view: "day" },
    "book.hold": slotArgs,
    "book.confirm": {
      booking_id: "DT-24117",
      patient_id: pid,
      ...slotArgs,
      ...(held?.sittings.length ? { sitting_ids: held.sittings.map((_, i) => `DT-2411${8 + i}`) } : {}),
    },
    "patient.ask": { field: "phone" },
    "patient.name": { name: "Asha Rao" },
    "appt.focus": { appointment_id: target.id },
    "appt.propose": {
      appointment_id: target.id,
      action: "reschedule",
      fee: terms.fee,
      date: move?.date ?? mday,
      time: move?.time ?? "16:00",
      branch_id: move?.branch ?? target.branch,
      dentist_id: tsvc.resource ? null : (move?.dentist ?? target.dentist),
      chair_id: move?.chair ?? null,
      resource_id: move?.resource ?? null,
    },
    "appt.apply": {
      appointment_id: target.id,
      action: "reschedule",
      fee: terms.fee,
      date: move?.date ?? mday,
      time: move?.time ?? "16:00",
      branch_id: move?.branch ?? target.branch,
      dentist_id: tsvc.resource ? null : (move?.dentist ?? target.dentist),
      chair_id: move?.chair ?? null,
      resource_id: move?.resource ?? null,
    },
    "callback.request": {
      callback_id: "CB-3107",
      reason: "Swelling near the lower left molar since yesterday, asks which painkiller is safe",
      urgency: "today",
      window: DATA.clinical.callback_windows.today,
    },
    "cal.view": { date: viewDay, dentist_id: "dr-kavitha", mode: "week" },
  };
}

/** `window.__dentalDebug`, for screenshots and QA. */
export function installDebugHook() {
  const w = window as unknown as { __dentalDebug?: unknown };
  w.__dentalDebug = {
    run: runMove,
    examples,
    moves: MOVE_IDS,
    /** The first day from tomorrow with a free slot: `nextDay("rct", { dentist: "dr-kavitha" })`. */
    nextDay: (serviceId: string, opts: { branch?: string; dentist?: string } = {}) => dayWithSlots(serviceId, opts)[0],
    events: () => eventLog(),
    store: () => useStore.getState(),
    actions,
    fakeCall: (patch: Partial<ReturnType<typeof useFakeCall.getState>>) => useFakeCall.setState(patch),
    reset: () => actions.reset(),
  };
}
