/**
 * `?debug=1` — fires every CONTRACT.md command by hand, with payloads built
 * from real catalog products, through the same `dispatch` the voice adapter
 * uses. Development and screenshots only; it never renders without the flag.
 */
import { Bug, ChevronDown, X } from "lucide-react";
import { useEffect, useState } from "react";
import { bestSaving, defaultVariant, getProduct, matchContractFilters, products, productsInCategory } from "../data/catalog";
import { dispatch, useMira } from "./controller";
import { eventLog, onEventLog } from "./events";
import { buildCompare, buildRoomSet, findSavings, goesWith, moreLike, pieceFor } from "./local";
import { COMMAND_NAMES, type CommandName, type Commands } from "./types";

const ANCHOR = "weathered-oak-dining-table";

function currentProductId(): string {
  const m = /\/product\/([^/?#]+)/.exec(window.location.pathname);
  return m && getProduct(m[1]) ? m[1] : ANCHOR;
}

export function samplePayloads(): { [K in CommandName]: Commands[K] } {
  const anchor = getProduct(currentProductId())!;
  const sofas = productsInCategory("sofas").slice(0, 3);
  const set = buildRoomSet("living", 4500);
  const board = useMira.getState().board ?? set;
  const swapSlot = board.pieces[1] ?? board.pieces[0];
  const swapTo = productsInCategory(getProduct(swapSlot.product_id)?.categorySlug ?? "rugs").find((p) => p.id !== swapSlot.product_id)!;
  const swappedPiece = pieceFor(swapTo, "Warmer tone, and it sits lower beside the sofa", swapSlot.slot);
  const filters = { room: "living", category: null, materials: ["oak"], colours: [], styles: [], price_min: null, price_max: 1500, on_sale: null };
  const filtered = matchContractFilters(filters);
  const lamps = products.filter((p) => p.categorySlug === "floor-lamps" && p.onSale).slice(0, 6);
  const saleSofa = sofas.find((p) => bestSaving(p).pct) ?? sofas[0];
  const variant = anchor.variants[1] ?? defaultVariant(anchor);
  return {
    navigate: { page: "room/bedroom" },
    show_products: { title: "Floor lamps on sale", query: "a floor lamp that is on sale", product_ids: lamps.map((p) => p.id), count: lamps.length },
    apply_filters: {
      filters,
      product_ids: filtered.map((p) => p.id),
      count: filtered.length,
      assumption: "I took “not too pricey” to mean under $1,500 a piece.",
    },
    remove_filter: (() => {
      const without = matchContractFilters({ ...filters, price_max: null });
      return { key: "price", product_ids: without.map((p) => p.id), count: without.length };
    })(),
    open_product: { product_id: anchor.id, variant_id: variant.id, focus: "options" },
    select_variant: { product_id: anchor.id, variant_id: variant.id },
    highlight: { target: "button:add-to-cart" },
    update_brief: {
      brief: { room: "living", uses: ["reading", "guests"], materials: ["oak", "linen"], colours: ["warm neutrals"], styles: ["calm"], budget: 4500 },
      products_left: 42,
    },
    show_room_set: {
      ...set,
      pieces: set.pieces.map((p, i) => ({
        ...p,
        reason: ["Low and deep, in the linen you asked for", "Oak top to match the floor", "Grounds the seating", "Light for reading in the corner", "Texture against the linen", "One quiet piece for the wall"][i] ?? p.reason,
      })),
    },
    swap_piece: {
      slot: swapSlot.slot,
      old_product_id: swapSlot.product_id,
      piece: swappedPiece,
      total: Math.round((board.total - swapSlot.price + swappedPiece.price) * 100) / 100,
    },
    show_compare: buildCompare(sofas.map((p) => p.id)),
    show_goes_with: goesWith(anchor),
    show_more_like: moreLike(anchor),
    show_savings: { ...findSavings(board.pieces), moved_to: null },
    update_shortlist: { product_ids: sofas.map((p) => p.id) },
    confirm_add: { lines: [{ product_id: anchor.id, variant_id: variant.id, qty: 1 }], label: `Add the ${anchor.title} in ${variant.title} to your cart?` },
    cart_updated: (() => {
      const lines = [
        { product_id: saleSofa.id, variant_id: defaultVariant(saleSofa).id, qty: 1 },
        { product_id: anchor.id, variant_id: variant.id, qty: 1 },
      ];
      const total = lines.reduce((s, l) => s + (getProduct(l.product_id)!.variants.find((v) => v.id === l.variant_id)!.price ?? 0) * l.qty, 0);
      return { lines, total, saved: 0 };
    })(),
    suggest_finish: { product_id: anchor.id, reason: "The walnut finish would sit closer to the sofa legs you chose." },
    open_policy: { topic: "returns" },
    undo: {},
  };
}

export function DebugConsole() {
  const [open, setOpen] = useState(true);
  const [picked, setPicked] = useState<CommandName | null>(null);
  const [, tick] = useState(0);
  useEffect(() => {
    const off = onEventLog(() => tick((n) => n + 1));
    return () => {
      off();
    };
  }, []);
  const events = eventLog().slice(-6).reverse();
  if (!open)
    return (
      <button type="button" className="debug-fab" onClick={() => setOpen(true)} aria-label="Open action console">
        <Bug size={16} /> Actions
      </button>
    );
  return (
    <aside className="debug" aria-label="Action console">
      <div className="debug-head">
        <strong>Action console</strong>
        <span className="small">brain → UI, by hand</span>
        <button type="button" className="icon-btn" aria-label="Close action console" onClick={() => setOpen(false)}>
          <X size={16} />
        </button>
      </div>
      <ul className="debug-list">
        {COMMAND_NAMES.map((c) => (
          <li key={c}>
            <button type="button" className="debug-fire" data-command={c} onClick={() => dispatch(c, samplePayloads()[c])}>
              {c}
            </button>
            <button type="button" className="debug-peek" aria-label={`Show ${c} payload`} onClick={() => setPicked(picked === c ? null : c)}>
              <ChevronDown size={14} />
            </button>
            {picked === c ? <pre className="debug-pre">{JSON.stringify(samplePayloads()[c], null, 1).slice(0, 1600)}</pre> : null}
          </li>
        ))}
      </ul>
      <div className="debug-events">
        <p className="small">UI → brain (latest)</p>
        <ul>
          {events.map((e, i) => (
            <li key={`${e.at}${i}`}>
              <code>{e.event}</code> <span className="small">{JSON.stringify(e.payload).slice(0, 90)}</span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
