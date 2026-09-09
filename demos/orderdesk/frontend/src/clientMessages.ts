/**
 * The browser → brain half of the OrderDesk screen contract (DESIGN.md §3).
 *
 * Both directions are now generated from `backend/brain.py` into `actions.gen.ts` —
 * the `UiAction`s the brain sends and the {@link AppEvent}s this screen sends, off
 * one `voqalize types` run. Nothing about either is written down twice. What is
 * left here is the two things that are not events, and the shape of the channel.
 *
 * ## Two kinds of message, and the difference matters
 *
 * **Requests** — `catalog_search` is the manual search bar asking the brain for
 * rows, answered by `show_search_results`; `list_variants` (`{ item_id, family }`)
 * is a matched row asking for its family's siblings, answered by `show_variants`.
 * Both are questions with answers, and both ride `sendClientMessage`.
 *
 * **Events** — `AppEvent`, generated. Not questions: statements about what the
 * pharmacist just did, addressed by row id, sent the instant he does it, on RTVI's
 * own `sendUIEvent`. `li3 quantity set to 5`, not a cart to be diffed. Nothing
 * comes back; what the brain does with one is the brain's business.
 *
 * There is nothing behind them. `state_sync` — the whole cart, debounced — is gone,
 * so an act the union cannot express is an act the brain never learns about. That
 * is the trade the fine-grained shape makes deliberately (CLAUDE.md): completeness
 * is now a property to hold, and a gap shows up as a gap rather than being quietly
 * reconciled 250 ms later by a snapshot nobody reads.
 */

export const CLIENT_MESSAGE = {
  catalogSearch: "catalog_search",
  listVariants: "list_variants",
} as const;

/** Which gesture put this SKU on this row — see `SkuChosen` in `desk_events.py`. */
export type ChoiceVia = "pill" | "variant" | "search";

/**
 * The store's channels to the brain, as `OrderDeskCall` registers them, or null
 * before the call is live — before connect there is no brain to tell, and the one
 * that starts has an empty order to begin from.
 */
export type AgentSend = {
  /** Ask a question the brain answers with an action. */
  ask: (type: string, data: Record<string, unknown>) => void;
  /** Say what he just did. Nothing comes back. */
  tell: (event: string, payload?: unknown) => void;
} | null;
