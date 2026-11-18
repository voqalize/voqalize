/**
 * The page → agent half: each change to the store becomes one of the spec's
 * state events, small and named (never the screen whole). The email itself
 * never leaves the page: the lead slice says only `has_email`.
 */
import type { EventData, EventId } from "@voqalize/stage";
import { quote } from "../lib/pricing";
import { slotById } from "../lib/calendar";
import { type SiteState, suggestedPlan, useSite } from "../state/store";
import type { scene } from "./scene.gen";

type Spec = typeof scene.spec;
type Send = <E extends EventId<Spec>>(id: E, data: EventData<Spec, E>) => void;

function leadData(s: SiteState) {
  const l = s.lead;
  return {
    company: l.company || null,
    name: l.name || null,
    headcount: l.headcount,
    states: l.states,
    current_tool: l.current_tool || null,
    pains: l.pains,
    recommended_plan: l.recommended_plan || suggestedPlan(l) || null,
    modules: s.matched,
    has_email: !!l.email,
    field: s.leadField || null,
  };
}

function filled(s: SiteState): string[] {
  return Object.entries(s.booking.form)
    .filter(([, v]) => v.trim())
    .map(([k]) => k);
}

/** Typing is reported once it pauses, not per keystroke. */
const TYPING_MS = 700;

/** Start reporting; returns the stop. */
export function startReporting(send: Send, agentActing: () => boolean): () => void {
  let leadTimer = 0;
  let lastBooking = "";
  const stop = useSite.subscribe((s, prev) => {
    if (s.lead !== prev.lead || s.matched !== prev.matched) {
      window.clearTimeout(leadTimer);
      const typed = !agentActing() && s.lead !== prev.lead && ["company", "name", "email"].includes(s.leadField);
      if (typed) leadTimer = window.setTimeout(() => send("lead.changed", leadData(useSite.getState())), TYPING_MS);
      else send("lead.changed", leadData(s));
    }
    if (s.pricing !== prev.pricing) {
      const q = quote(s.pricing);
      send("pricing.changed", {
        headcount: s.pricing.headcount,
        modules: s.pricing.modules,
        billing: s.pricing.billing,
        filing: s.pricing.filing,
        plan: q.status === "custom" ? "custom quote" : q.plan_name,
        monthly: q.monthly,
      });
    }
    if (s.booking !== prev.booking) {
      const b = s.booking;
      const slot = b.slotId ? slotById(b.slotId) : null;
      const data = {
        day: b.day || null,
        slot_id: b.slotId || null,
        filled: filled(s),
        status: b.status === "slot_picked" && slot ? `slot picked: ${slot.day} ${slot.time} with ${slot.rep}` : b.status,
        reference: b.reference || null,
      };
      // Only what the agent can use: the day, the slot, which fields hold
      // something and the status; a keystroke inside a filled field is not news.
      const key = JSON.stringify(data);
      if (key === lastBooking) return;
      lastBooking = key;
      if (b.status === "confirmed" && prev.booking.status !== "confirmed") send("booking.confirmed", data);
      else send("booking.changed", data);
    }
  });
  return () => {
    window.clearTimeout(leadTimer);
    stop();
  };
}
