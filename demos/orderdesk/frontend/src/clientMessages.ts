/**
 * The browser → brain half of the OrderDesk screen contract (DESIGN.md §3).
 *
 * The other direction is `actions.gen.ts`, generated from the six `Action`
 * classes in `backend/brain.py`; nothing about it is written down twice. These
 * three are this side's own, so they are.
 *
 * `state_sync` carries the authoritative cart (`OrderSnapshot` in `types.ts`)
 * as `{ screen: snapshot }`; `catalog_search` is the manual search bar asking
 * the brain for rows, answered by `show_search_results`; `list_variants`
 * (`{ item_id, family }`) is a matched row asking for its family's siblings,
 * answered by `show_variants`.
 */

export const CLIENT_MESSAGE = {
  stateSync: "state_sync",
  catalogSearch: "catalog_search",
  listVariants: "list_variants",
} as const;
