/**
 * The click path for every voice surface. Each builder returns exactly the
 * payload the brain would send for the same surface, from catalog fields only,
 * so one component renders both — Emily's version and the shopper's own.
 */
import {
  type Product,
  type RoomId,
  bestSaving,
  categoriesIn,
  collectionName,
  defaultVariant,
  differences,
  getProduct,
  hash,
  lookAlikes,
  money,
  productsByIds,
  productsInCategory,
  sameCollection,
} from "../data/catalog";
import type { Commands, CompareRow, Piece } from "./types";

/** The pieces a room board is built from, in the order a room is furnished. */
const ROOM_SLOTS: Record<RoomId, string[]> = {
  living: ["sofas", "coffee-tables", "rugs", "floor-lamps", "throw-pillows", "artwork"],
  dining: ["dining-tables", "dining-chairs", "chandeliers", "dinnerware", "serveware", "barware"],
  bedroom: ["beds-bed-frames", "bed-sheets", "quilts-comforters", "table-lamps", "curtains-drapes"],
  "home-office": ["desks", "office-chairs", "shelving"],
  bath: ["bath-towels-washcloths", "bath-mats-rugs"],
  kitchen: ["cookware", "food-storage"],
  decor: ["vases", "candle-holders", "picture-frames", "household-storage-baskets", "artificial-flora"],
};

export function slotsFor(room: RoomId): string[] {
  const known = new Set(categoriesIn(room).map((c) => c.slug));
  const listed = ROOM_SLOTS[room].filter((s) => known.has(s));
  return listed.length ? listed : [...known];
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)] ?? 0;
};

export function pieceFor(p: Product, reason: string, slot = p.categorySlug): Piece {
  const v = defaultVariant(p);
  return {
    slot,
    product_id: p.id,
    variant_id: v.id,
    title: p.title,
    price: v.price,
    compare_at: v.compareAtPrice,
    image: p.images[0],
    reason,
  };
}

/** A sensible starting set for a room at a budget: each slot gets its share. */
export function suggestedBudget(room: RoomId): number {
  const total = slotsFor(room).reduce((sum, s) => sum + median(productsInCategory(s).map((p) => p.priceMin)), 0);
  const step = total > 2000 ? 500 : 100;
  return Math.max(step, Math.round(total / step) * step);
}

export function buildRoomSet(room: RoomId, budget: number): Commands["show_room_set"] {
  const slots = slotsFor(room);
  const medians = slots.map((s) => median(productsInCategory(s).map((p) => p.priceMin)));
  const weight = medians.reduce((a, b) => a + b, 0) || 1;
  const pieces = slots.map((slot, i) => {
    const share = (budget * medians[i]) / weight;
    const list = productsInCategory(slot);
    const under = list.filter((p) => p.priceMin <= share);
    const pool = under.length ? under : list;
    const pick = [...pool].sort((a, b) => Math.abs(a.priceMin - share) - Math.abs(b.priceMin - share) || hash(a.id) - hash(b.id))[0];
    const reason = under.length
      ? `Closest to its share of your budget, about ${money(Math.round(share))}`
      : `The lowest-priced ${pick.category.toLowerCase()} we carry`;
    return pieceFor(pick, reason, slot);
  });
  return { room, budget, total: totalOf(pieces), pieces };
}

export const totalOf = (pieces: Piece[]) => Math.round(pieces.reduce((s, p) => s + p.price, 0) * 100) / 100;

/** The next alternative for a slot, cycling through its category by price. */
export function nextInSlot(piece: Piece, direction: 1 | -1 = 1): Product | undefined {
  const current = getProduct(piece.product_id);
  if (!current) return undefined;
  const list = productsInCategory(current.categorySlug).sort((a, b) => a.priceMin - b.priceMin || a.id.localeCompare(b.id));
  const i = list.findIndex((p) => p.id === current.id);
  return list[(i + direction + list.length) % list.length];
}

export function findSavings(pieces: Piece[]): Commands["show_savings"] {
  const swaps = pieces
    .map((piece) => {
      const current = getProduct(piece.product_id);
      if (!current) return null;
      const cheaper = productsInCategory(current.categorySlug)
        .filter((p) => p.id !== current.id && p.priceMin < piece.price * 0.85)
        .sort((a, b) => Number(b.onSale) - Number(a.onSale) || b.priceMin - a.priceMin)[0];
      return cheaper ? { slot: piece.slot, from_id: current.id, to_id: cheaper.id, was: piece.price, now: cheaper.priceMin } : null;
    })
    .filter((s): s is NonNullable<typeof s> => !!s)
    .sort((a, b) => b.was - b.now - (a.was - a.now))
    .slice(0, 2);
  const saved = Math.round(swaps.reduce((s, x) => s + x.was - x.now, 0) * 100) / 100;
  return { swaps, saved, moved_to: null };
}

export function buildCompare(ids: string[]): Commands["show_compare"] {
  const list = productsByIds(ids).slice(0, 4);
  const prices = list.map((p) => defaultVariant(p).price);
  const minIdx = prices.indexOf(Math.min(...prices));
  const savings = list.map((p) => bestSaving(p).pct);
  const maxSave = Math.max(...savings);
  const rows: CompareRow[] = [
    { label: "Price", values: list.map((p) => (p.priceMin === p.priceMax ? money(p.priceMin) : `From ${money(p.priceMin)}`)), winner: minIdx },
    {
      label: "On sale",
      values: list.map((p) => {
        const s = bestSaving(p);
        return s.pct ? `Save ${s.pct}%, was ${money(s.compare ?? 0)}` : "Full price";
      }),
      winner: maxSave > 0 ? savings.indexOf(maxSave) : null,
    },
    { label: "Category", values: list.map((p) => p.category) },
    { label: "Collection", values: list.map((p) => collectionName(p.collections[0])) },
  ];
  const names = [...new Set(list.flatMap((p) => p.options.map((o) => o.name)))];
  for (const name of names)
    rows.push({ label: name, values: list.map((p) => p.options.find((o) => o.name === name)?.values.join(", ") ?? "—") });
  const cheapest = list[minIdx];
  const summary =
    list.length < 2
      ? "Add another piece to compare side by side."
      : maxSave > 0 && savings.indexOf(maxSave) !== minIdx
        ? `${cheapest.title} is the lowest price; ${list[savings.indexOf(maxSave)].title} has the biggest saving.`
        : `${cheapest.title} is the lowest price of the ${list.length}.`;
  return { product_ids: list.map((p) => p.id), rows, summary };
}

export function goesWith(p: Product): Commands["show_goes_with"] {
  const items = sameCollection(p, 12)
    .filter((x) => x.categorySlug !== p.categorySlug)
    .filter((x, i, arr) => arr.findIndex((y) => y.categorySlug === x.categorySlug) === i)
    .slice(0, 5)
    .map((x) => ({ product_id: x.id, reason: `Same ${collectionName(p.collections[0])} collection` }));
  return { anchor_id: p.id, items };
}

export function moreLike(p: Product): Commands["show_more_like"] {
  return {
    anchor_id: p.id,
    items: lookAlikes(p, 6).map((x) => ({ product_id: x.id, differences: differences(p, x) })),
  };
}
