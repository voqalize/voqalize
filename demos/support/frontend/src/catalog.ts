/**
 * Past-orders catalog — browser mirror of the canonical Python catalog at
 * `demos/support/backend/catalog.py`.
 *
 * The support agent reasons over the Python copy and drives the UI by pushing
 * order/item `id`s in `ui_command` RTVI messages. This file resolves those ids
 * for rendering, so the `id` values here MUST stay in sync with the Python copy.
 */

export type ItemKind = 'phone' | 'accessory';

export interface Item {
  id: string;
  name: string;
  brand: string;
  price: number; // USD
  kind: ItemKind;
  /** Emoji used as a faux product thumbnail. */
  icon: string;
  /** Accent color for the thumbnail tile. */
  accent: string;
}

export interface OrderLine {
  itemId: string;
  qty: number;
}

export interface Order {
  id: string;
  placedOn: string;
  status: string;
  deliveredOn: string;
  lines: OrderLine[];
}

export const ITEMS: Item[] = [
  {
    id: 'bt-mic-pro',
    name: 'AudioPro Clip Wireless Lavalier Mic',
    brand: 'AudioPro',
    price: 79,
    kind: 'accessory',
    icon: '🎙️',
    accent: '#0f766e',
  },
  {
    id: 'buds-sonic',
    name: 'SonicBuds Pro Wireless Earbuds',
    brand: 'SonicBuds',
    price: 129,
    kind: 'accessory',
    icon: '🎧',
    accent: '#4338ca',
  },
  {
    id: 'charger-65w',
    name: 'VoltEdge 65W USB-C Fast Charger',
    brand: 'VoltEdge',
    price: 39,
    kind: 'accessory',
    icon: '🔌',
    accent: '#b45309',
  },
  {
    id: 'pixel-8-pro',
    name: 'Google Pixel 8 Pro',
    brand: 'Google',
    price: 999,
    kind: 'phone',
    icon: '📱',
    accent: '#3b6fb5',
  },
  {
    id: 'case-pixel8pro',
    name: 'Pixel 8 Pro Armor Case',
    brand: 'Voqal',
    price: 29,
    kind: 'accessory',
    icon: '🛡️',
    accent: '#475569',
  },
  {
    id: 'galaxy-a55',
    name: 'Samsung Galaxy A55',
    brand: 'Samsung',
    price: 449,
    kind: 'phone',
    icon: '📱',
    accent: '#9a8cc4',
  },
];

export const ORDERS: Order[] = [
  {
    id: 'VQ-10588',
    placedOn: 'May 28, 2026',
    status: 'Delivered',
    deliveredOn: 'May 31, 2026',
    lines: [
      { itemId: 'bt-mic-pro', qty: 1 },
      { itemId: 'buds-sonic', qty: 1 },
      { itemId: 'charger-65w', qty: 1 },
    ],
  },
  {
    id: 'VQ-10432',
    placedOn: 'May 12, 2026',
    status: 'Delivered',
    deliveredOn: 'May 15, 2026',
    lines: [
      { itemId: 'pixel-8-pro', qty: 1 },
      { itemId: 'case-pixel8pro', qty: 1 },
    ],
  },
  {
    id: 'VQ-10301',
    placedOn: 'April 21, 2026',
    status: 'Delivered',
    deliveredOn: 'April 24, 2026',
    lines: [{ itemId: 'galaxy-a55', qty: 1 }],
  },
];

const ITEMS_BY_ID: Record<string, Item> = Object.fromEntries(ITEMS.map((i) => [i.id, i]));
const ORDERS_BY_ID: Record<string, Order> = Object.fromEntries(ORDERS.map((o) => [o.id, o]));

export function getItem(id: string): Item | undefined {
  return ITEMS_BY_ID[id];
}

export function getOrder(id: string): Order | undefined {
  return ORDERS_BY_ID[id];
}

export function orderTotal(order: Order): number {
  return order.lines.reduce((sum, l) => {
    const item = getItem(l.itemId);
    return sum + (item ? item.price * l.qty : 0);
  }, 0);
}
