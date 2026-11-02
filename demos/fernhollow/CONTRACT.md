# Fernhollow — UI ↔ brain contract (v0)

Fernhollow is a fictional home & furniture store and a Voqalize voice demo. Mira, the design adviser,
talks (voice **Emily**, `Voice.OMNIVOICE_EMILY`; face: avatar character `emily`; English only) and drives
the store's screen. Design doc: https://claude.ai/artifact/Venfo8c5tvd8u3iG5Jm3zA

This file is the agreement between `frontend/` (React, Vite) and `backend/` (the brain). Both sides build
against it in parallel; change it only by editing this file in the same PR as the code.

## Data

- `data/catalog.json` — the single source of product truth for both sides: 792 products, 32 categories,
  7 rooms (`living, dining, bedroom, home-office, bath, kitchen, decor`). Built by
  `data/build_catalog.py`. Product `id` = URL handle. Images: `images[].file` is `<id>/<n>`; the frontend
  serves them as `/demos/fernhollow/img/<file>-<400|1000>.webp`.
- **No invented product facts.** Nothing outside catalog fields, words in the product's own
  title/intro/highlights/options, authored store policies and authored editorial content. No dimensions,
  stock levels or delivery dates anywhere in UI or speech.

## Brain → UI actions (`session.dispatch`, RTVI `ui-command`)

Every action carries the full payload its component needs (ids AND the display fields), so the page
renders without a second lookup. Product references are catalog `id`s.

| command | payload | UI |
| --- | --- | --- |
| `navigate` | `page`: `home` \| `room/<room>` \| `category/<slug>` \| `product/<id>` \| `journal` \| `journal/<slug>` \| `cart` \| `policy/<topic>` | route change |
| `show_products` | `title, query, product_ids[], count` | listing grid with these products |
| `apply_filters` | `filters{room?,category?,materials[],colours[],styles[],price_min?,price_max?,on_sale?}, product_ids[], count, assumption?` | filter chips + grid |
| `remove_filter` | `key, product_ids[], count` | chip removed |
| `open_product` | `product_id, variant_id?, focus?` (`options`\|`highlights`\|`price`) | product page, focus section ringed |
| `select_variant` | `product_id, variant_id` | variant picker set + ringed |
| `highlight` | `target` (`product:<id>` \| `filter:<key>` \| `slot:<slot>` \| `button:add-to-cart` \| `section:<name>`) | 300 ms spotlight ring |
| `update_brief` | `brief{room?,uses[],materials[],colours[],styles[],budget?}, products_left` | room-brief chips |
| `show_room_set` | `room, budget, total, pieces[{slot, product_id, variant_id, title, price, compare_at?, image, reason}]` | room board, pieces appear one by one |
| `swap_piece` | `slot, old_product_id, piece{…same as above}, total` | one room-board tile changes |
| `show_compare` | `product_ids[], rows[{label, values[], winner?}], summary` | compare board |
| `show_goes_with` | `anchor_id, items[{product_id, reason}]` | goes-with strip |
| `show_more_like` | `anchor_id, items[{product_id, differences[]}]` | look-alike strip with badges |
| `show_savings` | `swaps[{slot, from_id, to_id, was, now}], saved, moved_to?` | savings badges on room board |
| `update_shortlist` | `product_ids[]` | shortlist tray |
| `confirm_add` | `lines[{product_id, variant_id, qty}], label` | confirm prompt on the Add button |
| `cart_updated` | `lines[], total, saved` | cart drawer opens |
| `suggest_finish` | `product_id, reason` | suggestion card in cart |
| `open_policy` | `topic` (`returns`\|`delivery`\|`assembly`\|`care`) | policy panel |
| `undo` | — | revert last screen-changing action |

## UI → brain events (client message / Stage visitor events)

`page_viewed{path}`, `product_viewed{product_id, variant_id}`, `visible_products{product_ids[]}`,
`variant_selected{product_id, variant_id}`, `filter_changed{filters}`, `room_board_edited{slot, action}`,
`cart_changed{lines[], total}`, `confirm_result{confirmed: bool}`, `shortlist_changed{product_ids[]}`.
Every event says `by: "visitor"` when the shopper did it.

## Frontend rule

Every component that an action drives must ALSO work by click/tap alone — the store is a complete,
usable shop without voice. Actions go through one store controller (`src/voice/controller.ts`) so the
voice layer is a thin adapter. A dev-only action console (`?debug=1`) fires any action by hand.
