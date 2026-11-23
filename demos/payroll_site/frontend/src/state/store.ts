/**
 * The one store controller. A click, a Stage performer (the agent's move) and
 * the `?debug=1` console all change the page through these actions, so the
 * site works completely by hand and the voice layer is a thin adapter over it.
 * What changed is reported to the agent as Stage state events by
 * `stage/report.ts`, which subscribes here; nothing in this file knows a call
 * exists.
 */
import { create } from "zustand";
import { LEAD, painById, type PlanId } from "../data/product";
import { businessDays, reference, slotById, todayIst } from "../lib/calendar";
import { type Billing, choosePlan, type PriceInput } from "../lib/pricing";
import { PERSONA } from "../persona";

export type LeadField = "company" | "name" | "headcount" | "states" | "current_tool" | "pains" | "recommended_plan" | "email";
export type BookingField = "company" | "name" | "headcount" | "topic" | "email";

export interface Lead {
  company: string;
  name: string;
  headcount: number | null;
  states: string[];
  current_tool: string;
  pains: string[];
  /** Set by the agent (or the visitor); else the card shows `suggestedPlan(lead)`. */
  recommended_plan: PlanId | "";
  email: string;
}

export interface Booking {
  day: string;
  slotId: string;
  form: Record<BookingField, string>;
  status: "choosing" | "slot_picked" | "confirmed";
  reference: string;
}

export interface SiteState {
  lang: string;
  lead: Lead;
  /** The field the last change touched, for the agent's note. */
  leadField: LeadField | "";
  leadOpen: boolean;
  /** Module cards marked "Fits your team". */
  matched: string[];
  pricing: PriceInput;
  booking: Booking;
  /** Slots confirmed this visit: taken from now on, like the authored ones. */
  booked: string[];
}

const EMPTY_LEAD: Lead = {
  company: "",
  name: "",
  headcount: null,
  states: [],
  current_tool: "",
  pains: [],
  recommended_plan: "",
  email: "",
};

const firstDay = () => businessDays(todayIst())[0];

const initial = (): SiteState => ({
  lang: PERSONA.default_language,
  lead: { ...EMPTY_LEAD },
  leadField: "",
  leadOpen: false,
  matched: [],
  pricing: { headcount: 56, modules: [], billing: "monthly", filing: false },
  booking: {
    day: firstDay(),
    slotId: "",
    form: { company: "", name: "", headcount: "", topic: "walkthrough", email: "" },
    status: "choosing",
    reference: "",
  },
  booked: [],
});

export const useSite = create<SiteState>(initial);

/** The modules the visitor's pains point at, in the order they came up. */
export function painModules(pains: string[]): string[] {
  return [...new Set(pains.flatMap((p) => painById(p)?.modules ?? []))];
}

/** The plan the lead card suggests when nobody set one: the pricing rule on
 *  the headcount and the modules its pains point at. */
export function suggestedPlan(lead: Lead): PlanId | "" {
  if (!lead.headcount) return "";
  return choosePlan(lead.headcount, painModules(lead.pains), false).plan ?? "";
}

export const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());

// ─── Actions ────────────────────────────────────────────────────────────────

export const actions = {
  reset: () => useSite.setState(initial()),
  setLang: (lang: string) => useSite.setState({ lang }),

  openLead: (open: boolean) => useSite.setState({ leadOpen: open }),

  /** One field of the lead card. Lists replace; a headcount is a whole number. */
  setLead(field: LeadField, value: string | number | string[] | null) {
    useSite.setState((s) => {
      const lead = { ...s.lead };
      switch (field) {
        case "headcount": {
          const n = Number(value);
          lead.headcount = value === null || value === "" || !Number.isFinite(n) || n <= 0 ? null : Math.round(n);
          break;
        }
        case "states":
        case "pains":
          lead[field] = Array.isArray(value) ? [...new Set(value)] : String(value ?? "").split(",").map((x) => x.trim()).filter(Boolean);
          break;
        case "recommended_plan":
          lead.recommended_plan = (String(value ?? "") as PlanId) || "";
          break;
        default:
          lead[field] = String(value ?? "");
      }
      return { lead, leadField: field, leadOpen: true };
    });
  },

  toggleLeadItem(field: "states" | "pains", item: string) {
    const list = useSite.getState().lead[field];
    actions.setLead(field, list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  },

  setMatched: (ids: string[]) => useSite.setState({ matched: [...new Set(ids)] }),
  toggleMatched(id: string) {
    const m = useSite.getState().matched;
    actions.setMatched(m.includes(id) ? m.filter((x) => x !== id) : [...m, id]);
  },

  setPricing: (patch: Partial<PriceInput>) =>
    useSite.setState((s) => ({ pricing: { ...s.pricing, ...patch, headcount: Math.max(1, Math.round(patch.headcount ?? s.pricing.headcount)) } })),
  togglePricingModule(id: string) {
    const m = useSite.getState().pricing.modules;
    actions.setPricing({ modules: m.includes(id) ? m.filter((x) => x !== id) : [...m, id] });
  },
  setBilling: (billing: Billing) => actions.setPricing({ billing }),

  pickDay: (day: string) => useSite.setState((s) => ({ booking: { ...s.booking, day } })),

  /** Select a slot; refused (returns why) when it is taken or not on the calendar. */
  pickSlot(id: string): string | null {
    const slot = slotById(id);
    const s = useSite.getState();
    if (!slot) return "no such slot";
    if (!businessDays(todayIst()).includes(slot.day)) return "that day is not on the calendar";
    if (slot.taken || s.booked.includes(slot.id)) return "that slot is already taken";
    if (s.booking.status === "confirmed") return "a demo is already booked";
    useSite.setState({ booking: { ...s.booking, day: slot.day, slotId: slot.id, status: "slot_picked" } });
    return null;
  },

  setBookingField: (field: BookingField, value: string) =>
    useSite.setState((s) => ({ booking: { ...s.booking, form: { ...s.booking.form, [field]: value } } })),

  /** What still stops Confirm booking, by field name. */
  bookingMissing(): string[] {
    const b = useSite.getState().booking;
    const missing: string[] = [];
    if (!b.slotId) missing.push("slot");
    if (!b.form.name.trim()) missing.push("name");
    if (!b.form.company.trim()) missing.push("company");
    if (!isEmail(b.form.email)) missing.push("email");
    return missing;
  },

  /** Press Confirm booking. Returns the reference, or the missing fields. */
  confirmBooking(): { reference: string } | { missing: string[] } {
    const missing = actions.bookingMissing();
    if (missing.length) return { missing };
    const s = useSite.getState();
    const slot = slotById(s.booking.slotId)!;
    const ref = reference(slot);
    useSite.setState({
      booking: { ...s.booking, status: "confirmed", reference: ref },
      booked: [...s.booked, slot.id],
    });
    return { reference: ref };
  },

  newBooking: () =>
    useSite.setState((s) => ({ booking: { ...initial().booking, form: { ...s.booking.form }, day: s.booking.day } })),
};

/** The lead card's value for a field, as the card would print it. */
export function leadValue(lead: Lead, field: LeadField): string {
  switch (field) {
    case "headcount":
      return lead.headcount ? String(lead.headcount) : "";
    case "states":
      return lead.states.join(", ");
    case "pains":
      return lead.pains.map((p) => painById(p)?.label ?? p).join(", ");
    case "current_tool":
      return LEAD.current_tools.find((t) => t.id === lead.current_tool)?.label ?? lead.current_tool;
    default:
      return String(lead[field] ?? "");
  }
}

if (import.meta.env.DEV) {
  (window as unknown as { __paynora?: unknown }).__paynora = { useSite, actions };
}
