/**
 * The page's state, told to the brain as the events CONTRACT.md declares:
 * `catalogue.changed` when filters, picks or the comparison change, and
 * `application.changed` / `step_reached` / `submitted` as the form moves.
 * Personal values (names, date of birth, mobile, email, parent's name) never
 * leave the page: only that they are filled.
 */
import { missingIn } from "../data/application";
import { useApplication, filledFields } from "../state/application";
import { filterLabels, listed, matching, useFinder } from "../state/finder";
import { sendEvent } from "./host";

const SHARED = ["program", "campus", "intake", "class12_stream", "class12_percent", "graduation_percent", "entrance_exam", "hostel", "room_type", "scholarship"] as const;

export function catalogueSnapshot() {
  const s = useFinder.getState();
  const { pinned, results } = listed(s);
  return {
    filters: filterLabels(s.filters),
    count: matching(s.filters).length,
    top: [...pinned, ...results].slice(0, 6).map((p) => p.id),
    picks: s.picks,
    compared: s.compared,
  };
}

export function applicationSnapshot(field?: string | null) {
  const s = useApplication.getState();
  const shared: Record<string, string | null> = {};
  for (const k of SHARED) shared[k] = s.values[k] ?? null;
  return {
    ...(field ? { field } : {}),
    filled: filledFields(s.values),
    missing: missingIn(s.step, s.values),
    step: s.step,
    ...shared,
  };
}

let started = false;
/** Subscribe once, at load: every change, whoever made it, is reported. */
export function startReporting(): void {
  if (started) return;
  started = true;
  useFinder.subscribe((next, prev) => {
    if (next.filters === prev.filters && next.picks === prev.picks && next.compared === prev.compared && next.sort === prev.sort) return;
    sendEvent("catalogue.changed", catalogueSnapshot());
  });
  useApplication.subscribe((next, prev) => {
    if (next.values !== prev.values) sendEvent("application.changed", applicationSnapshot(next.lastField));
    if (next.step !== prev.step) sendEvent("application.step_reached", { step: next.step });
    if (next.submitted && next.submitted !== prev.submitted) sendEvent("application.submitted", { reference: next.submitted.reference });
  });
}

/** What the brain hears when the call comes up on this page. */
export function sendSnapshot(path: string): void {
  if (path.startsWith("/programs")) sendEvent("catalogue.changed", catalogueSnapshot());
  if (path.startsWith("/apply")) sendEvent("application.changed", applicationSnapshot());
}
