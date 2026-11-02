/**
 * The returns desk's data: the fictional demo orders (`data/demo_orders.json`)
 * and the form's fields, whose names and values are the contract
 * (CONTRACT.md, "Returns desk (v1)"). Dates are "days ago", so an order's
 * eligibility holds whenever the demo runs.
 */
import ordersJson from "../../../data/demo_orders.json";
import { getProduct } from "../data/catalog";
import { type PlacedOrder, daysSince, useOrders } from "../state/orders";

export interface OrderLine {
  product_id: string;
  variant_id: string;
  title: string;
  variant: string;
  qty: number;
  unit_price: number;
}

export interface DemoOrder {
  number: string;
  email: string;
  name: string;
  placed_days_ago: number;
  delivered_days_ago: number | null;
  status: string;
  lines: OrderLine[];
  total: number;
}

const data = ordersJson as unknown as { return_window_days: number; orders: DemoOrder[] };
export const RETURN_WINDOW_DAYS = data.return_window_days;
export const ORDERS = data.orders;

/** An order the shopper placed here, as the returns desk reads it: delivered when placed. */
export const asReturnable = (o: PlacedOrder, now = Date.now()): DemoOrder & { placed: true } => ({
  number: o.number,
  email: o.email,
  name: o.name,
  placed_days_ago: daysSince(o.placed_at, now),
  delivered_days_ago: daysSince(o.placed_at, now),
  status: "delivered",
  lines: o.lines,
  total: o.total,
  placed: true,
});

/** Every order the desk can find: the shopper's own (newest first), then the demo orders. */
export function allOrders(placed: PlacedOrder[] = useOrders.getState().orders): (DemoOrder & { placed?: true })[] {
  const own = [...placed].sort((a, b) => b.placed_at.localeCompare(a.placed_at)).map((o) => asReturnable(o));
  return [...own, ...ORDERS.filter((d) => !own.some((o) => o.number === d.number))];
}

export const normalOrderNumber = (s: string) => {
  const digits = s.replace(/\D/g, "");
  return digits ? `FH-${digits}` : s.trim().toUpperCase();
};
export const findOrder = (number: string | null | undefined) =>
  number ? allOrders().find((o) => o.number === normalOrderNumber(number)) : undefined;

export type Eligibility = { kind: "eligible"; daysLeft: number } | { kind: "outside_window"; days: number } | { kind: "not_delivered" };

export function eligibility(order: DemoOrder): Eligibility {
  if (order.status !== "delivered" || order.delivered_days_ago == null) return { kind: "not_delivered" };
  const days = order.delivered_days_ago;
  return days <= RETURN_WINDOW_DAYS ? { kind: "eligible", daysLeft: RETURN_WINDOW_DAYS - days } : { kind: "outside_window", days };
}

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

export const STEPS = [
  { n: 1, title: "Find your order" },
  { n: 2, title: "Items" },
  { n: 3, title: "Reason" },
  { n: 4, title: "Resolution" },
  { n: 5, title: "Collection" },
  { n: 6, title: "Review" },
] as const;

/** Which fields each step holds, for the dwell prompt and the step summaries. */
export const STEP_FIELDS: Record<number, string[]> = {
  1: ["order_number", "email"],
  2: ["items"],
  3: ["reason", "condition"],
  4: ["resolution"],
  5: ["collection", "pickup_window"],
  6: [],
};
