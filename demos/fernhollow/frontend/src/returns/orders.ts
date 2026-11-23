/**
 * The return form's fields, whose names and values are the contract
 * (CONTRACT.md, "Returns desk"): the choices and their labels, the five steps
 * and which fields each holds. The orders themselves (and whether one can be
 * returned) are src/orders/tracking.ts.
 */
import { getProduct } from "../data/catalog";
import type { OrderLine } from "../orders/tracking";

export { RETURN_WINDOW_DAYS } from "../orders/tracking";

/** The other option values the shopper could exchange a line for. */
export function exchangeOptions(line: OrderLine): string[] {
  const p = getProduct(line.product_id);
  if (!p) return [];
  return p.variants.filter((v) => v.id !== line.variant_id).map((v) => v.title);
}

/** Choice fields and their values, in the order the form shows them. */
export const CHOICES = {
  reason: [
    ["changed_mind", "I changed my mind"],
    ["doesnt_suit_room", "It doesn't suit the room"],
    ["arrived_damaged", "It arrived damaged"],
    ["wrong_item", "I received the wrong item"],
    ["not_as_expected", "It's not what I expected"],
  ],
  condition: [
    ["unused_in_packaging", "Unused, in its packaging"],
    ["unused_unpacked", "Unused, unpacked"],
    ["damaged_on_arrival", "Damaged on arrival"],
  ],
  resolution: [
    ["refund", "Refund"],
    ["exchange", "Exchange for another option"],
    ["store_credit", "Store credit"],
  ],
  collection: [
    ["pickup", "Collect it from me"],
    ["drop_off", "I'll drop it off"],
  ],
  pickup_window: [
    ["weekday_morning", "Weekday morning"],
    ["weekday_afternoon", "Weekday afternoon"],
    ["saturday", "Saturday"],
  ],
} as const satisfies Record<string, readonly (readonly [string, string])[]>;

export type ChoiceField = keyof typeof CHOICES;
export const CHOICE_FIELDS = Object.keys(CHOICES) as ChoiceField[];
export const labelOf = (field: ChoiceField, value: string | null | undefined) =>
  CHOICES[field].find(([v]) => v === value)?.[1] ?? "";

/** A choice as the agent says it back to the shopper: "reason set to doesn't suit the room". */
export const SPOKEN: Record<string, string> = {
  changed_mind: "changed your mind",
  doesnt_suit_room: "doesn't suit the room",
  arrived_damaged: "arrived damaged",
  wrong_item: "wrong item received",
  not_as_expected: "not what you expected",
  unused_in_packaging: "unused, in its packaging",
  unused_unpacked: "unused, unpacked",
  damaged_on_arrival: "damaged on arrival",
  refund: "refund",
  exchange: "exchange for another option",
  store_credit: "store credit",
  pickup: "collect it from your home",
  drop_off: "drop it off yourself",
  weekday_morning: "weekday morning",
  weekday_afternoon: "weekday afternoon",
  saturday: "Saturday",
};
export const FIELD_SPOKEN: Record<ChoiceField, string> = {
  reason: "reason",
  condition: "condition",
  resolution: "resolution",
  collection: "collection",
  pickup_window: "collection window",
};

export const STEPS = [
  { n: 1, title: "Items", hint: "Tick what is going back" },
  { n: 2, title: "Reason", hint: "Why, and the condition it is in" },
  { n: 3, title: "Resolution", hint: "Refund, exchange or store credit" },
  { n: 4, title: "Collection", hint: "Collected from you, or dropped off" },
  { n: 5, title: "Review", hint: "Check and submit" },
] as const;
export const LAST_STEP = STEPS.length;

/** Which fields each step holds, for the dwell prompt and the step summaries. */
export const STEP_FIELDS: Record<number, string[]> = {
  1: ["items"],
  2: ["reason", "condition"],
  3: ["resolution"],
  4: ["collection", "pickup_window"],
  5: [],
};

/** The step that holds a field, by its name (exchange_variant_* sits with resolution). */
export function stepOfField(field: string): number | null {
  if (field === "items" || field.startsWith("qty_")) return 1;
  if (field === "reason" || field === "condition") return 2;
  if (field === "resolution" || field.startsWith("exchange_variant_")) return 3;
  if (field === "collection" || field === "pickup_window") return 4;
  return null;
}
