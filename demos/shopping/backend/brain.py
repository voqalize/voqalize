"""ShoppingBrain — the "Mobile Expert" voice shopping agent.

A ``voqalize.sdk.Brain`` (LLM + screen-driving tools + session state). Voqalize
dials this brain's WebSocket per session; the inherited tool-loop ``on_interaction``
runs a manual Gemini function-calling loop where **each LLM call is one
``interaction.inference()`` bracket** (1:1 with the wire). Each tool body drives
the browser via ``interaction.action(name, {...})`` — the RTVI ``ui_command`` the
``/mobile`` UI renders — while returning catalog data to the model so it can talk
about what's on screen.

The LLM is **dependency-injected** as a :class:`GeminiProvider`; the brain owns
only the prompt, the tool schemas, and this session's cart/wishlist. The
conversation record is framework-owned (``interaction.conversation``), rebuilt
into Gemini's working context each turn by the GeminiBrain base.

Catalog data lives in :mod:`voqalize_demos.brains.shopping.catalog`. Every
``ui_command`` references a product by its catalog ``id``, which the UI mirrors.
"""

from __future__ import annotations

from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

from .catalog import (
    CATALOG,
    VALID_BRANDS,
    VALID_CATEGORIES,
    VALID_IDS,
    VALID_SORTS,
    catalog_for_prompt,
    get_product,
    search_catalog,
    sort_catalog,
    summary,
)

STORE_NAME = "Voqal Mobile"

# Highlightable spec sections on the product page. Must match the
# `data-feature` anchors rendered in console/src/mobile/pages.tsx.
_FEATURES = [
    "display",
    "camera",
    "battery",
    "performance",
    "charging",
    "colors",
    "specs",
    "reviews",
]

# Topics the FAQ page can scroll to. Must match the FAQ anchors in the console.
_FAQ_TOPICS = [
    "shipping",
    "returns",
    "warranty",
    "payment",
    "trade-in",
    "price-match",
    "activation",
]


# Store facts the agent answers FAQ questions from. Mirrored as visible copy on
# the console FAQ page — keep the two in sync.
_FAQ_FACTS = f"""STORE FACTS ({STORE_NAME}) — answer policy questions only from these:
- Shipping: Free 2-day shipping on orders over 50 dollars. Ships from US warehouses. Same-day dispatch before 2pm.
- Returns: 30-day free returns, item must be in original condition with all accessories.
- Warranty: Every phone includes a 1-year manufacturer warranty. Optional 2-year protection plan for 79 dollars covers accidental damage.
- Payment: Credit and debit cards, PayPal, and 0 percent APR financing over 12 or 24 months on orders above 500 dollars.
- Trade-in: Trade in your old phone for up to 600 dollars of instant credit toward a new one.
- Price match: We price-match any authorized retailer within 14 days of purchase.
- Activation: All phones are unlocked and work with every major carrier. Free SIM included."""


_SYSTEM_INSTRUCTION = f"""You are the Mobile Expert, a warm, knowledgeable voice shopping assistant for {STORE_NAME}, an online mobile-phone store. The shopper is browsing the store on their phone and talking to you live. You help them find the right phone, answer questions, and — this is important — you drive their screen as you talk.

YOU CONTROL THE SCREEN. Whenever you mention products, you MUST call the matching tool so the shopper SEES what you are talking about. Do not just describe — show. Examples:
- Shopper asks for camera phones → call search_products, then talk about the results on screen.
- Shopper asks about one phone → call open_product so its page opens, then answer.
- You mention a phone's battery or camera → call highlight_feature so that section is highlighted.
- Shopper asks how a phone is rated or what reviewers say → call highlight_feature with feature "reviews" to show its ratings, then answer.
- Shopper narrows by brand or budget → call apply_filters.
- Shopper wants results ordered ("cheapest first", "best rated", "newest") → call sort_results.
- Shopper likes a phone but is not ready to buy → offer to save it and call add_to_wishlist.
- Shopper asks about shipping, returns, warranty → call open_faq with the topic, then answer.
Always call the tool BEFORE or AS you start describing, so the screen and your words stay in sync.

KEEP THE SHOPPER WITH YOU. A tool call takes a moment to run. Always say a brief spoken line FIRST — a handful of words — before you call the tool, so the shopper is never left in silence while the screen updates. For example: "Sure, let me pull those up." then call search_products; or "One sec, opening that now." then call open_product. Never call a tool without speaking that short line first.

CATALOG — these are the only phones in the store. Refer to them by name; use the bracketed id only for tool arguments:
{catalog_for_prompt()}

{_FAQ_FACTS}

CONVERSATION STYLE:
- This is voice. START every reply with a very short sentence — a handful of words — so audio begins instantly; then continue only if needed. Keep replies short — usually one or two sentences, never more than three.
- Ask one question at a time. Be friendly and concise, not salesy.
- Recommend honestly: match phones to what the shopper actually needs (budget, camera, battery, size, ecosystem).
- When comparing, give the one-line difference that matters, then ask which way they lean.
- Never invent specs, prices, or policies. If something is not in the catalog or store facts, say you are not sure.
- Speak prices naturally ("nine hundred ninety nine dollars"), and never read out the product ids.
- Open with a quick welcome and ask what kind of phone they are looking for."""


# Fixed opener — spoken straight to TTS with no LLM call, so the demo greets the
# instant the session connects (the model's ~1s first token is off the start path).
_GREETING = f"Welcome to {STORE_NAME}! What kind of phone are you looking for?"


# ─── Tool schemas (JSON-schema dicts) ──────────────────────────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "search_products",
        "Search the store and show the results on the shopper's screen. Use "
        "whenever the shopper wants to browse or find phones by need, brand, "
        "or budget. Returns matching phones and opens the search results page.",
        {
            "query": {
                "type": "string",
                "description": "Free-text search, e.g. 'best camera', 'small phone', 'long battery'. Optional.",
            },
            "brand": {
                "type": "string",
                "enum": VALID_BRANDS,
                "description": "Restrict to one brand. Optional.",
            },
            "max_price": {
                "type": "integer",
                "description": "Maximum price in US dollars. Optional.",
            },
            "category": {
                "type": "string",
                "enum": VALID_CATEGORIES,
                "description": "Restrict to a tier. Optional.",
            },
            "sort_by": {
                "type": "string",
                "enum": VALID_SORTS,
                "description": (
                    "Order the results: 'price_low', 'price_high', 'rating' "
                    "(top rated first), or 'newest'. Optional."
                ),
            },
        },
        [],
    ),
    (
        "open_product",
        "Open one phone's detail page on the shopper's screen and get its full "
        "specs. Use when the shopper wants to look at or hear about a specific phone.",
        {
            "product_id": {
                "type": "string",
                "enum": VALID_IDS,
                "description": "The id of the phone to open.",
            },
        },
        ["product_id"],
    ),
    (
        "apply_filters",
        "Filter the search results by brand, price, or tier and show them. Use "
        "when the shopper narrows down what they want. Opens the results page.",
        {
            "brand": {
                "type": "string",
                "enum": VALID_BRANDS,
                "description": "Brand filter. Optional.",
            },
            "max_price": {"type": "integer", "description": "Maximum price in dollars. Optional."},
            "min_price": {"type": "integer", "description": "Minimum price in dollars. Optional."},
            "category": {
                "type": "string",
                "enum": VALID_CATEGORIES,
                "description": "Tier filter. Optional.",
            },
        },
        [],
    ),
    (
        "clear_filters",
        "Clear all active filters and show the full catalog again.",
        {},
        [],
    ),
    (
        "go_home",
        "Return the shopper to the store home page.",
        {},
        [],
    ),
    (
        "highlight_feature",
        "Highlight and scroll to one spec section on the currently open product "
        "page, so the shopper's eye follows what you are describing. Open the "
        "product first with open_product if it is not already showing.",
        {
            "product_id": {
                "type": "string",
                "enum": VALID_IDS,
                "description": "The phone whose section to highlight.",
            },
            "feature": {
                "type": "string",
                "enum": _FEATURES,
                "description": "Which spec section to highlight.",
            },
        },
        ["product_id", "feature"],
    ),
    (
        "compare_products",
        "Show a side-by-side comparison of two or three phones on screen and get "
        "their specs. Use when the shopper is deciding between options.",
        {
            "product_ids": {
                "type": "array",
                "items": {"type": "string", "enum": VALID_IDS},
                "description": "Two or three phone ids to compare.",
            },
        },
        ["product_ids"],
    ),
    (
        "add_to_cart",
        "Add a phone to the shopper's cart. Confirm the choice first.",
        {
            "product_id": {"type": "string", "enum": VALID_IDS, "description": "The phone to add."},
        },
        ["product_id"],
    ),
    (
        "sort_results",
        "Re-order the phones currently shown on the search results page. Use "
        "when the shopper wants them sorted, e.g. 'cheapest first', 'show the "
        "best rated', or 'newest'. Opens the results page if needed.",
        {
            "sort_by": {
                "type": "string",
                "enum": VALID_SORTS,
                "description": (
                    "'price_low' (cheapest first), 'price_high' (most expensive "
                    "first), 'rating' (top rated first), or 'newest'."
                ),
            },
        },
        ["sort_by"],
    ),
    (
        "add_to_wishlist",
        "Save a phone to the shopper's wishlist (a shortlist of phones they "
        "like but are not buying yet). Use when the shopper wants to remember "
        "or compare a phone later rather than add it to the cart.",
        {
            "product_id": {
                "type": "string",
                "enum": VALID_IDS,
                "description": "The phone to save.",
            },
        },
        ["product_id"],
    ),
    (
        "open_faq",
        "Open the store's FAQ / help page and scroll to a topic, then answer the "
        "shopper's policy question. Use for shipping, returns, warranty, payment, "
        "trade-in, price match, or activation questions.",
        {
            "topic": {
                "type": "string",
                "enum": _FAQ_TOPICS,
                "description": "Which policy topic to scroll to.",
            },
        },
        [],
    ),
]

_JSON_TO_GENAI = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "object": types.Type.OBJECT,
    "array": types.Type.ARRAY,
}


def _to_schema(d: dict[str, Any]) -> types.Schema:
    """Convert a JSON-schema dict to a google-genai Schema (recursive)."""
    kw: dict[str, Any] = {"type": _JSON_TO_GENAI[d["type"]]}
    if d.get("description"):
        kw["description"] = d["description"]
    if d.get("enum"):
        kw["enum"] = d["enum"]
    if d["type"] == "object":
        props = d.get("properties") or {}
        kw["properties"] = {k: _to_schema(v) for k, v in props.items()}
        if d.get("required"):
            kw["required"] = d["required"]
    if d["type"] == "array":
        kw["items"] = _to_schema(d["items"])
    return types.Schema(**kw)


def _tools() -> types.ToolListUnion:
    decls = [
        types.FunctionDeclaration(
            name=name,
            description=desc,
            parameters=_to_schema({"type": "object", "properties": props, "required": req}),
        )
        for name, desc, props, req in _TOOLSPECS
    ]
    tools: types.ToolListUnion = [types.Tool(function_declarations=decls)]
    return tools


class ShoppingBrain(GeminiBrain):
    """One per session. Owns this session's cart/wishlist + screen-driving tools.
    ``on_interaction`` is the inherited tool-loop ``respond``; :meth:`dispatch_tool`
    runs each call, driving the browser and feeding catalog data back to the model."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_INSTRUCTION, tools=_tools(), model=model
        )
        # Brain-owned domain state only. The conversation record is framework-owned.
        self.cart: list[str] = []
        self.wishlist: list[str] = []

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        await self.say(session, _GREETING)

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: drive the browser via ``interaction.action(...)`` (the
        RTVI ui_command the /mobile UI renders) and return catalog data to the
        model."""
        act = interaction.action
        if name == "search_products":
            query = str(args.get("query") or "")
            brand = args.get("brand")
            max_price = args.get("max_price")
            category = args.get("category")
            sort_by = args.get("sort_by")
            matches = search_catalog(
                query=query,
                brand=str(brand) if brand else None,
                max_price=int(max_price) if max_price is not None else None,
                category=str(category) if category else None,
                sort_by=str(sort_by) if sort_by else None,
            )
            logger.info(
                "shopping: search q={!r} brand={!r} max={!r} sort={!r} → {}",
                query,
                brand,
                max_price,
                sort_by,
                len(matches),
            )
            act(
                "show_search",
                {
                    "query": query,
                    "brand": brand,
                    "max_price": max_price,
                    "category": category,
                    "sort_by": sort_by,
                    "result_ids": [p["id"] for p in matches],
                },
            )
            return str({"count": len(matches), "results": [summary(p) for p in matches]})
        if name == "open_product":
            product_id = str(args.get("product_id", ""))
            product = get_product(product_id)
            if product is None:
                return str({"error": f"unknown product '{product_id}'"})
            logger.info("shopping: open_product {}", product_id)
            act("open_product", {"product_id": product_id})
            return str({"product": product})
        if name == "apply_filters":
            brand = args.get("brand")
            max_price = args.get("max_price")
            min_price = args.get("min_price")
            category = args.get("category")
            matches = search_catalog(
                brand=str(brand) if brand else None,
                max_price=int(max_price) if max_price is not None else None,
                min_price=int(min_price) if min_price is not None else None,
                category=str(category) if category else None,
            )
            logger.info(
                "shopping: apply_filters brand={!r} max={!r} → {}", brand, max_price, len(matches)
            )
            act(
                "apply_filters",
                {
                    "brand": brand,
                    "max_price": max_price,
                    "min_price": min_price,
                    "category": category,
                    "result_ids": [p["id"] for p in matches],
                },
            )
            return str({"count": len(matches), "results": [summary(p) for p in matches]})
        if name == "clear_filters":
            logger.info("shopping: clear_filters")
            act("clear_filters")
            return str({"status": "cleared"})
        if name == "go_home":
            logger.info("shopping: go_home")
            act("navigate_home")
            return str({"status": "home"})
        if name == "highlight_feature":
            product_id = str(args.get("product_id", ""))
            feature = str(args.get("feature", ""))
            logger.info("shopping: highlight {} {}", product_id, feature)
            act("highlight", {"product_id": product_id, "feature": feature})
            product = get_product(product_id)
            detail: Any = None
            if product is not None:
                if feature == "reviews":
                    detail = {
                        "rating": product["rating"],
                        "review_count": product["review_count"],
                        "pros": product["pros"],
                        "cons": product["cons"],
                    }
                else:
                    field = {
                        "display": "display",
                        "camera": "rear_camera",
                        "battery": "battery_mah",
                        "performance": "processor",
                        "charging": "charging",
                        "colors": "colors",
                        "specs": "highlights",
                    }.get(feature, "highlights")
                    detail = product.get(field)
            return str({"status": "highlighted", "feature": feature, "detail": detail})
        if name == "compare_products":
            ids = [str(x) for x in (args.get("product_ids") or [])]
            products = [get_product(i) for i in ids]
            products = [p for p in products if p is not None]
            logger.info("shopping: compare {}", ids)
            act("compare", {"product_ids": [p["id"] for p in products]})
            return str({"products": products})
        if name == "add_to_cart":
            product_id = str(args.get("product_id", ""))
            product = get_product(product_id)
            if product is None:
                return str({"error": f"unknown product '{product_id}'"})
            if product_id not in self.cart:
                self.cart.append(product_id)
            logger.info("shopping: add_to_cart {} (cart={})", product_id, len(self.cart))
            act("add_to_cart", {"product_id": product_id, "cart_count": len(self.cart)})
            return str({"status": "added", "name": product["name"], "cart_count": len(self.cart)})
        if name == "sort_results":
            sort_by = str(args.get("sort_by", ""))
            logger.info("shopping: sort_results by={!r}", sort_by)
            act("sort", {"sort_by": sort_by})
            # Return the catalog ordered the same way so the model can talk through
            # the new top results.
            ordered = sort_catalog(list(CATALOG), sort_by)
            return str(
                {
                    "status": "sorted",
                    "sort_by": sort_by,
                    "results": [summary(p) for p in ordered[:5]],
                }
            )
        if name == "add_to_wishlist":
            product_id = str(args.get("product_id", ""))
            product = get_product(product_id)
            if product is None:
                return str({"error": f"unknown product '{product_id}'"})
            if product_id not in self.wishlist:
                self.wishlist.append(product_id)
            logger.info(
                "shopping: add_to_wishlist {} (wishlist={})", product_id, len(self.wishlist)
            )
            act(
                "add_to_wishlist",
                {"product_id": product_id, "wishlist_count": len(self.wishlist)},
            )
            return str(
                {"status": "saved", "name": product["name"], "wishlist_count": len(self.wishlist)}
            )
        if name == "open_faq":
            topic = args.get("topic")
            logger.info("shopping: open_faq topic={!r}", topic)
            act("open_faq", {"topic": topic})
            return str({"status": "opened", "topic": topic})
        return "unknown tool"
