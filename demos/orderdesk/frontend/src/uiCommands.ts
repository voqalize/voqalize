/**
 * The OrderDesk screen contract — the browser half.
 *
 * **`demos/orderdesk/backend/brain.py` is the source of truth.** Every interface
 * here mirrors one `voqalize.sdk.Action` subclass declared there, field for field,
 * and the key it is filed under is that action's wire name (derived from the Python
 * class name: `UpsertItems` → `upsert_items`). Change one side and the other must
 * move with it. DESIGN.md §3 is the written contract for both halves.
 *
 * These are **wire** shapes. Every field is always present, because a pydantic
 * `Action` emits its whole declared shape (no `exclude_none`) — so nothing here is
 * optional; only genuinely nullable fields are `| null`. The per-item render state
 * (`LineItemView`) and the catalog rows (`SkuWire`, `FamilyWire`) live in
 * `types.ts`, shared with the store and the scenario data; they are re-exported
 * below so a reader of this file sees the whole contract in one place.
 *
 * The `useUiCommand` hook (`@voqalize/client-react`) checks a handler map against
 * `OrderDeskCommands`: an action name the brain doesn't declare is a compile error,
 * and each handler's argument is that action's args — no coercion, no null-checks.
 */

import type { FamilyWire, LineItemView, SkuWire } from "./types";

export type { FamilyWire, LineItemView, SkuWire };

/**
 * Wire name → argument shape, for every `ui_command` the OrderDesk brain fires.
 * The six keys are the six `Action` subclasses in `brain.py` (DESIGN.md §3).
 */
export interface OrderDeskCommands {
  /** Add or update line items — full render state per item; the store diffs by `id`. */
  upsert_items: { items: LineItemView[] };
  /** The agent dropped items from the order ("वोलिनी हटा दो"). */
  remove_items: { ids: string[] };
  /** The agent is asking about this row — scroll to it, pulse it, show the note. */
  highlight_item: { id: string; note: string | null };
  /** Answer to the manual search bar's `catalog_search` (floor-free, no speech). */
  show_search_results: { query: string; results: SkuWire[] };
  /**
   * Answer to a row's `list_variants` — the siblings of a matched SKU inside the
   * family it is already locked to, for the row's inline "Change variant" strip.
   * Floor-free like `show_search_results`: no inference, no speech, so browsing
   * variants can never interrupt the call. `results` is capped at 24 and may be
   * empty (a legitimate answer); `differing_axes` is a subset of the four axes
   * and labels the pills.
   */
  show_variants: {
    item_id: string;
    family: string;
    results: SkuWire[];
    differing_axes: string[];
  };
  /** One-line banner above the list — a scheme or stock callout. */
  order_note: { text: string };
}

/**
 * The other direction — the three silent client messages this app sends
 * (DESIGN.md §3). `state_sync` carries the authoritative cart (`OrderSnapshot`
 * in `types.ts`) as `{ screen: snapshot }`; `catalog_search` is the manual
 * search bar asking the brain for rows, answered by `show_search_results`;
 * `list_variants` (`{ item_id, family }`) is a matched row asking for its
 * family's siblings, answered by `show_variants`.
 */
export const CLIENT_MESSAGE = {
  stateSync: "state_sync",
  catalogSearch: "catalog_search",
  listVariants: "list_variants",
} as const;
