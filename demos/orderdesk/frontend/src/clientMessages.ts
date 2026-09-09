/**
 * The browser → brain half of the OrderDesk screen contract (DESIGN.md §3).
 *
 * The other direction is `actions.gen.ts`, generated from the six `Action`
 * classes in `backend/brain.py`; nothing about it is written down twice. This
 * side is this side's own, so it is — for now. Its Python twin is
 * `backend/desk_events.py`, and keeping the two in step by hand is exactly the
 * gap that decides whether this shape earns a place in the SDK.
 *
 * ## Two kinds of message, and the difference matters
 *
 * **Requests** — `catalog_search` is the manual search bar asking the brain for
 * rows, answered by `show_search_results`; `list_variants` (`{ item_id, family }`)
 * is a matched row asking for its family's siblings, answered by `show_variants`.
 * Both are questions with answers.
 *
 * **Events** — {@link DeskEvent}. Not questions: statements about what the
 * pharmacist just did, addressed by row id, sent the instant he does it. `li3
 * quantity set to 5`, not a cart to be diffed. Nothing comes back; what the brain
 * does with one is the brain's business.
 *
 * `state_sync` still carries the authoritative cart (`OrderSnapshot` in
 * `types.ts`) as `{ screen: snapshot }`, debounced behind every change. It is the
 * **repair channel** now rather than the news: by the time it lands the brain has
 * already been told what happened, and its diff finds nothing left to report. An
 * event lost on the wire is therefore repaired within 250 ms — which is what lets
 * this be tried without touching the wire contract at all.
 */

export const CLIENT_MESSAGE = {
  stateSync: "state_sync",
  catalogSearch: "catalog_search",
  listVariants: "list_variants",
} as const;

/** Which gesture put this SKU on this row — see `SkuChosen` in `desk_events.py`. */
export type ChoiceVia = "pill" | "variant" | "search";

/**
 * One thing the pharmacist did, as it goes on the wire. `t` is the discriminant
 * *and* the wire name, so a name lives here once and nowhere else; the class
 * names in `desk_events.py` are the same seven, snake-cased.
 */
export type DeskEvent =
  | { t: "sku_chosen"; d: { item_id: string; sku_code: string; sku_name: string; via: ChoiceVia } }
  | {
      t: "row_added";
      d: { item_id: string; sku_code: string; sku_name: string; query: string; quantity: number };
    }
  | { t: "row_removed"; d: { item_id: string; spoken_text: string } }
  | {
      t: "question_answered";
      d: { item_id: string; question: string; answer: string; surviving_codes: string[] };
    }
  | { t: "family_chosen"; d: { item_id: string; family: string; surviving_codes: string[] } }
  | { t: "quantity_set"; d: { item_id: string; quantity: number } }
  | { t: "order_confirmed"; d: { order_no: string; item_count: number; total_mrp: number } };

/** The store's channel to the brain, as `OrderDeskCall` registers it. */
export type AgentSend = ((type: string, data: unknown) => void) | null;

/**
 * Send one event, or drop it silently when there is no call. A gesture before
 * connect is not lost: `rev` bumps too, and the `state_sync` that fires on
 * connect carries the whole cart.
 */
export function sendDeskEvent(send: AgentSend, event: DeskEvent): void {
  send?.(event.t, event.d);
}
