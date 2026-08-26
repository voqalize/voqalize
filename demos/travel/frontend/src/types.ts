/**
 * The Travel Desk itinerary data model.
 *
 * Unlike the orders demo (which mirrors a fixed Python catalog), there is no
 * catalog here: flights, hotels, and activities are INVENTED by the agent and
 * arrive as full objects inside `ui_command` payloads. The browser store is the
 * source of truth for the itinerary; it persists to localStorage and echoes a
 * compact snapshot back to the agent (`state_sync`) so the AI always knows the
 * current on-screen state — including edits the travel agent makes by hand.
 */

/**
 * A family, a flight option and a hotel option are the same on screen as on
 * the wire, so they are the generated shapes rather than a second declaration
 * of them. What follows adds only what the browser knows: a slug id, which
 * option is selected, the day plan, the task tray.
 */

import type { Family, FlightOption, HotelOption } from './actions.gen';

export type { Family, FlightOption, HotelOption };

export type Meal = Family['meal'];

export interface Leg {
  id: string;
  label: string;
  from?: string;
  to?: string;
  date: string;
  options?: FlightOption[];
  selectedId?: string;
}

export interface HotelStay {
  city: string;
  nights?: number;
  options?: HotelOption[];
  selectedId?: string;
}

export interface Activity {
  time?: string;
  title: string;
  detail?: string;
  ticket_included?: boolean;
}

export interface DayPlan {
  day: number;
  date?: string;
  title: string;
  transport?: string;
  breakfast?: string;
  lunch?: string;
  dinner?: string;
  activities: Activity[];
}

export type SpecialRequestType = 'bassinet' | 'assistance' | 'meal' | 'other';

export interface SpecialRequest {
  type?: SpecialRequestType;
  label: string;
  detail?: string;
}

/**
 * A background job the Travel Desk kicked off (a flight/hotel search or a
 * day-plan build). It animates in the task tray for a few seconds, then reveals
 * its result onto the active itinerary — the agent never blocks on it. Mirrors
 * the servicing demo's prep jobs.
 */
export type TaskKind = 'flights' | 'hotels' | 'dayplan';
export type TaskStatus = 'running' | 'done';

export interface Task {
  id: string;
  kind: TaskKind;
  label: string;
  detail?: string;
  status: TaskStatus;
  /** The itinerary this task applies its result to (captured when it started). */
  itineraryId: string;
  /** Which screen to open when a done task is clicked. */
  target?: { legId?: string; city?: string };
  startedAt: number;
}

export interface WhatsAppShare {
  to?: string;
  recipient?: string;
  sentAt: number;
}

export interface Itinerary {
  id: string; // slug derived from the name; the stable identity
  name: string;
  coordinator?: string;
  destination?: string;
  start_date?: string;
  end_date?: string;
  summary?: string;
  families: Family[];
  legs: Leg[];
  hotels: HotelStay[];
  days: DayPlan[];
  specialRequests: SpecialRequest[];
  inclusions: string[];
  exclusions: string[];
  terms: string[];
  patchNote?: string;
  whatsapp?: WhatsAppShare | null;
  createdAt: number;
  updatedAt: number;
}

/** A slug usable as a stable id and for name-based lookup by the agent. */
export function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '') || 'trip'
  );
}

export function selectedFlight(leg: Leg): FlightOption | undefined {
  return leg.options?.find((o) => o.id === leg.selectedId);
}

export function selectedHotel(stay: HotelStay): HotelOption | undefined {
  return stay.options?.find((o) => o.id === stay.selectedId);
}

/** Total adults+children+infants across all families. */
export function paxSummary(it: Itinerary): string {
  let adults = 0;
  let children = 0;
  let infants = 0;
  for (const f of it.families) {
    adults += f.adults ?? 0;
    children += f.children ?? 0;
    infants += f.infants ?? 0;
  }
  const parts: string[] = [];
  if (adults) parts.push(`${adults} adult${adults === 1 ? '' : 's'}`);
  if (children) parts.push(`${children} child${children === 1 ? '' : 'ren'}`);
  if (infants) parts.push(`${infants} infant${infants === 1 ? '' : 's'}`);
  if (it.families.length > 1) parts.push(`${it.families.length} families`);
  return parts.join(' · ');
}
