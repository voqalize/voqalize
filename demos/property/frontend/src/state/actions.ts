/**
 * The acts that also tell the agent: one function per act, called by a click
 * and by a performer alike. Filter and shortlist changes are reported by the
 * shell's store subscription (`stage/report.ts`); the visit acts here.
 */
import { getListing, slotsFor } from "../data/homes";
import { sendEvent } from "../stage/host";
import { type Booking, takenSlots, useStore } from "./store";

export function pickSlot(listingId: string, slot: string): void {
  useStore.getState().setVisit({ listing_id: listingId, day: slot.slice(0, 10), slot });
  sendEvent("visit.slot_picked", { listing_id: listingId, slot });
}

/** Why `slot` cannot be booked for this listing, or null when it can. */
export function slotProblem(listingId: string, slot: string): string | null {
  const l = getListing(listingId);
  if (!l) return `there is no listing ${listingId}`;
  const all = slotsFor(l, slot.slice(0, 10), takenSlots(useStore.getState().bookings, l.id));
  if (!all) return "the sales team does not take visits that day";
  const s = all.find((x) => x.id === slot);
  if (!s) return "that is not one of the visit times";
  if (!s.free) return "that slot is already taken";
  return null;
}

/** A 10-digit Indian mobile number (optionally +91 or a leading 0). */
export function validPhone(raw: string): boolean {
  const digits = raw.replace(/\D/g, "").replace(/^(91|0)(?=\d{10}$)/, "");
  return /^[6-9]\d{9}$/.test(digits);
}

/** The visitor typed in the Mobile box: the agent hears only whether a valid
 * number is in, never the number (X9). Told once per change of that answer. */
export function typePhone(listingId: string, raw: string): void {
  const was = validPhone(useStore.getState().visit.phone);
  useStore.getState().setVisit({ listing_id: listingId, phone: raw });
  const now = validPhone(raw);
  if (now !== was) sendEvent("visit.phone_typed", { listing_id: listingId, typed: now });
}

export function bookVisit(listingId: string, slot: string, name: string, visitors: number): Booking {
  const booking = useStore.getState().book({ listing_id: listingId, slot, name: name.trim(), visitors });
  sendEvent("visit.booked", { listing_id: listingId, slot, reference: booking.reference });
  return booking;
}
