# Grocery brain — voice shopping list over the Swiggy Instamart MCP

The cortex-mode brain for the **voice-grocery demo** (Swiggy/Zepto pitch), on the
ergonomic `Brain` SDK + the **OpenAI Agents SDK**. The customer talks; items land
on a live **Shopping List** the instant they're mentioned and resolve to real SKUs
in the background.

## The idea

The conversation must never wait on the (slow) Swiggy MCP. So:

- The **MCP is hidden** from the agent. The agent only sees our fast tools
  (`grocery_core/tools.py`): `add_items`, `pending_clarifications`, `clarify_item`,
  `set_quantity`, `confirm_item`, `remove_item`, `view_list`, `checkout`.
- `add_items` notes items **instantly** (state `resolving`) and returns; a
  deterministic Python **resolver** searches the MCP in a **background task** per
  item and moves it to `matched` (one confident SKU) or `needs_clarification` (a
  few options) — or `unavailable`.
- Every state change is **pushed to the browser** as a `ui_command`, so the
  on-screen list updates live (chips to pick, prices, % off, promoted 🏷️). The
  customer clarifies by **voice** (agent asks) or by **tapping** a chip
  (browser → `on_app_event` → resolver).

The Shopping List is the latency sponge: spoken items appear immediately; matching
catches up and confirms or asks — never blocking the next utterance.

## Layout

```
grocery_core/            # pure-Python core, no voice/agent deps
  models.py              # Variant/Product/Address + Item state machine
  mcp_client.py          # SwiggyMcp (hidden, call_tool) over the live MCP
  resolver.py            # deterministic rank() + decide() (match vs clarify)
  service.py             # GroceryService: list + background resolve + notify(ui)
  tools.py               # the @function_tool surface the agent sees
  catalog.py             # system prompt + catalog tree (~3-4k tokens)
brain.py                 # GroceryBrain: wires the above onto cortex + the agent
run.py                   # serve() as PLATFORM:voqal-grocery
build_catalog_prompt.py  # offline: regenerate the catalog tree from live data
```

## The Swiggy token

The browser pastes a **real Swiggy access token** into the `/grocery` page; it
rides `session.init["swiggy_token"]` → `MCPServerStreamableHttp` → the live
Swiggy Instamart account. Generate one with the OAuth spike:

```bash
python3 backend/agent-sdk/examples/swiggy_oauth_spike/run.py generate
```

(phone + OTP once; prints a token to paste. It expires in ~1h — re-run for a fresh one.)

## Run it

```bash
pm2 start ecosystem.config.cjs            # cortex + pygato + console + seed
backend/.venv/bin/python backend/agent-sdk/examples/grocery_brain/run.py
# open http://localhost:5740/grocery → paste a Swiggy token → Start Call
```

Needs `OPENAI_API_KEY` in the repo-root `.env`. Model via `GROCERY_MODEL`
(default `gpt-5.4-mini`).

## Limits (still a demo)

- One MCP (Instamart), full-history replay per turn, in-memory list per session.
- The pasted access token expires (~1h); re-`generate`. Refresh lifecycle is later.
- `update_cart`'s exact params are verified against the live schema before real
  checkout. Party planning + upsell are prompt-driven (the agent suggests from
  the catalog tree).
