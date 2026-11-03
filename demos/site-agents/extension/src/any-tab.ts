/**
 * The page events the brain takes from any tab, not only the one in front:
 * the answers to what it asked a page to do (a site tool's `tool_ran` and its
 * companion events, a check read's `site_read`, an Action's `action_failed`),
 * which a tab still owes even if the visitor switched tabs while it ran, and
 * the toggle's request. What a page merely shows (`page_viewed`, the item,
 * the listing, `screen_seen`) is heard from the tab in front only.
 */
export const ANY_TAB = [
  "language_requested",
  "tool_ran",
  "site_read",
  "action_failed",
  "form_filled",
  "search_ran",
  "cart_changed",
  "booking_filled",
  "coupon_applied",
] as const;
