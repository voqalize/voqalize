"""ShoppingBrain — the "Mobile Expert" voice shopping agent.

A :class:`voqalize_demos.GeminiBrain` (LLM + screen-driving tools + session
state). Voqalize dials this brain's WebSocket per session; the tool loop is
google-genai's own automatic function calling, run by the inherited
``respond``. Each tool is a bound method — its docstring is the description
the model reads — and its body drives the browser with
``self.session.dispatch(...)``, the RTVI ``ui-command`` the ``/mobile`` UI
renders, while returning catalog data so the model can talk about what's on
screen.

The LLM's ``genai.Client`` is **dependency-injected**; the brain owns
only the prompt, the tools, and this session's cart/wishlist. The conversation
record is framework-owned, rebuilt into Gemini's working context each turn by
the ``GeminiBrain`` base.

Catalog data lives in :mod:`.catalog`. Every dispatched action references a
product by its catalog ``id``, which the UI mirrors.
"""

from __future__ import annotations

from typing import Any, Literal

from google import genai
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain

from voqalize.sdk import Action, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

from .catalog import (
    CATALOG,
    VALID_BRANDS,
    VALID_CATEGORIES,
    Category,
    SortKey,
    as_category,
    as_sort_key,
    catalog_for_prompt,
    get_product,
    search_catalog,
    sort_catalog,
    summary,
)

STORE_NAME = "Voqal Mobile"

# Highlightable spec sections on the product page. Must match the
# `data-feature` anchors rendered in frontend/src/pages.tsx.
Feature = Literal[
    "display", "camera", "battery", "performance", "charging", "colors", "specs", "reviews"
]

# Topics the FAQ page can scroll to. Must match the `data-topic` anchors in
# frontend/src/pages.tsx.
FaqTopic = Literal[
    "shipping", "returns", "warranty", "payment", "trade-in", "price-match", "activation"
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


# ─── Tool parameters (the model's own request — not rendered) ─────────────────


class SearchQuery(BaseModel):
    """The one parameter of ``search_products``."""

    query: str = Field(
        default="",
        description="Free-text search, e.g. 'best camera', 'small phone', 'long battery'. Optional.",
    )
    brand: str | None = Field(
        default=None, description=f"Restrict to one brand: {', '.join(VALID_BRANDS)}. Optional."
    )
    max_price: int | None = Field(
        default=None, description="Maximum price in US dollars. Optional."
    )
    category: str | None = Field(
        default=None, description=f"Restrict to a tier: {', '.join(VALID_CATEGORIES)}. Optional."
    )
    sort_by: str | None = Field(
        default=None,
        description=(
            "Order the results: 'price_low', 'price_high', 'rating' (top rated "
            "first), or 'newest'. Optional."
        ),
    )


class FilterQuery(BaseModel):
    """The one parameter of ``apply_filters``."""

    brand: str | None = Field(default=None, description="Brand filter. Optional.")
    max_price: int | None = Field(default=None, description="Maximum price in dollars. Optional.")
    min_price: int | None = Field(default=None, description="Minimum price in dollars. Optional.")
    category: str | None = Field(
        default=None, description=f"Tier filter: {', '.join(VALID_CATEGORIES)}. Optional."
    )


class CompareRequest(BaseModel):
    """The one parameter of ``compare_products``."""

    product_ids: list[str] = Field(description="Two or three catalog ids to compare.")


class AddToCartRequest(BaseModel):
    """The one parameter of ``add_to_cart``."""

    product_id: str = Field(description="The catalog id of the phone to add.")


class AddToWishlistRequest(BaseModel):
    """The one parameter of ``add_to_wishlist``."""

    product_id: str = Field(description="The catalog id of the phone to save.")


# ─── Actions (browser render contract) ─────────────────────────────────────────


class ShowSearch(Action):
    query: str
    brand: str | None
    max_price: int | None
    category: Category | None
    sort_by: SortKey | None
    result_ids: list[str]


class OpenProduct(Action):
    product_id: str = Field(description="The id of the phone to open.")


class ApplyFilters(Action):
    brand: str | None
    max_price: int | None
    min_price: int | None
    category: Category | None
    result_ids: list[str]


class ClearFilters(Action):
    pass


class NavigateHome(Action):
    pass


class Highlight(Action):
    product_id: str = Field(description="The phone whose section to highlight.")
    feature: Feature = Field(description="Which spec section to highlight.")


class Compare(Action):
    product_ids: list[str]


class AddToCart(Action):
    product_id: str
    cart_count: int


class Sort(Action):
    sort_by: SortKey = Field(
        description=(
            "'price_low' (cheapest first), 'price_high' (most expensive first), "
            "'rating' (top rated first), or 'newest'."
        )
    )


class AddToWishlist(Action):
    product_id: str
    wishlist_count: int


class OpenFaq(Action):
    topic: FaqTopic | None = Field(default=None, description="Which policy topic to scroll to.")


class ShoppingBrain(GeminiBrain):
    """One per session. Owns this session's cart/wishlist and the eleven
    screen-driving tools. Each tool drives the browser via
    ``self.session.dispatch(...)`` and returns catalog data to the model."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # Brain-owned domain state only. The conversation record is framework-owned.
        self.cart: list[str] = []
        self.wishlist: list[str] = []

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV, language=Language.EN),
                stt=SttConfig(language=Language.EN),
            )
        )

    async def greet(self, session: Session) -> str:
        """The opener is fixed — no model call, no first-token wait — so the
        shopper hears the assistant the instant the session connects."""
        return _GREETING

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The eleven the shopper's voice may drive."""
        return [
            self.search_products,
            self.open_product,
            self.apply_filters,
            self.clear_filters,
            self.go_home,
            self.highlight_feature,
            self.compare_products,
            self.add_to_cart,
            self.sort_results,
            self.add_to_wishlist,
            self.open_faq,
        ]

    async def search_products(self, query: SearchQuery) -> str:
        """Search the store and show the results on the shopper's screen. Use
        whenever the shopper wants to browse or find phones by need, brand, or
        budget. Returns matching phones and opens the search results page."""
        matches = search_catalog(
            query=query.query,
            brand=query.brand,
            max_price=query.max_price,
            category=query.category,
            sort_by=query.sort_by,
        )
        logger.info(
            "shopping: search q={!r} brand={!r} max={!r} sort={!r} → {}",
            query.query,
            query.brand,
            query.max_price,
            query.sort_by,
            len(matches),
        )
        self.session.dispatch(
            ShowSearch(
                query=query.query,
                brand=query.brand,
                max_price=query.max_price,
                category=as_category(query.category),
                sort_by=as_sort_key(query.sort_by),
                result_ids=[p["id"] for p in matches],
            )
        )
        return str({"count": len(matches), "results": [summary(p) for p in matches]})

    async def open_product(self, action: OpenProduct) -> str:
        """Open one phone's detail page on the shopper's screen and get its full
        specs. Use when the shopper wants to look at or hear about a specific
        phone."""
        product = get_product(action.product_id)
        if product is None:
            return str({"error": f"unknown product '{action.product_id}'"})
        logger.info("shopping: open_product {}", action.product_id)
        self.session.dispatch(action)
        return str({"product": product})

    async def apply_filters(self, query: FilterQuery) -> str:
        """Filter the search results by brand, price, or tier and show them. Use
        when the shopper narrows down what they want. Opens the results page."""
        matches = search_catalog(
            brand=query.brand,
            max_price=query.max_price,
            min_price=query.min_price,
            category=query.category,
        )
        logger.info(
            "shopping: apply_filters brand={!r} max={!r} → {}",
            query.brand,
            query.max_price,
            len(matches),
        )
        self.session.dispatch(
            ApplyFilters(
                brand=query.brand,
                max_price=query.max_price,
                min_price=query.min_price,
                category=as_category(query.category),
                result_ids=[p["id"] for p in matches],
            )
        )
        return str({"count": len(matches), "results": [summary(p) for p in matches]})

    async def clear_filters(self) -> str:
        """Clear all active filters and show the full catalog again."""
        logger.info("shopping: clear_filters")
        self.session.dispatch(ClearFilters())
        return str({"status": "cleared"})

    async def go_home(self) -> str:
        """Return the shopper to the store home page."""
        logger.info("shopping: go_home")
        self.session.dispatch(NavigateHome())
        return str({"status": "home"})

    async def highlight_feature(self, action: Highlight) -> str:
        """Highlight and scroll to one spec section on the currently open
        product page, so the shopper's eye follows what you are describing.
        Open the product first with open_product if it is not already
        showing."""
        logger.info("shopping: highlight {} {}", action.product_id, action.feature)
        self.session.dispatch(action)
        product = get_product(action.product_id)
        detail: Any = None
        if product is not None:
            if action.feature == "reviews":
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
                }.get(action.feature, "highlights")
                detail = product.get(field)
        return str({"status": "highlighted", "feature": action.feature, "detail": detail})

    async def compare_products(self, request: CompareRequest) -> str:
        """Show a side-by-side comparison of two or three phones on screen and
        get their specs. Use when the shopper is deciding between options."""
        products = [get_product(i) for i in request.product_ids]
        products = [p for p in products if p is not None]
        logger.info("shopping: compare {}", request.product_ids)
        self.session.dispatch(Compare(product_ids=[p["id"] for p in products]))
        return str({"products": products})

    async def add_to_cart(self, request: AddToCartRequest) -> str:
        """Add a phone to the shopper's cart. Confirm the choice first."""
        product = get_product(request.product_id)
        if product is None:
            return str({"error": f"unknown product '{request.product_id}'"})
        if request.product_id not in self.cart:
            self.cart.append(request.product_id)
        logger.info("shopping: add_to_cart {} (cart={})", request.product_id, len(self.cart))
        self.session.dispatch(AddToCart(product_id=request.product_id, cart_count=len(self.cart)))
        return str({"status": "added", "name": product["name"], "cart_count": len(self.cart)})

    async def sort_results(self, action: Sort) -> str:
        """Re-order the phones currently shown on the search results page. Use
        when the shopper wants them sorted, e.g. 'cheapest first', 'show the
        best rated', or 'newest'. Opens the results page if needed."""
        logger.info("shopping: sort_results by={!r}", action.sort_by)
        self.session.dispatch(action)
        # Return the catalog ordered the same way so the model can talk
        # through the new top results.
        ordered = sort_catalog(list(CATALOG), action.sort_by)
        return str(
            {
                "status": "sorted",
                "sort_by": action.sort_by,
                "results": [summary(p) for p in ordered[:5]],
            }
        )

    async def add_to_wishlist(self, request: AddToWishlistRequest) -> str:
        """Save a phone to the shopper's wishlist (a shortlist of phones they
        like but are not buying yet). Use when the shopper wants to remember
        or compare a phone later rather than add it to the cart."""
        product = get_product(request.product_id)
        if product is None:
            return str({"error": f"unknown product '{request.product_id}'"})
        if request.product_id not in self.wishlist:
            self.wishlist.append(request.product_id)
        logger.info(
            "shopping: add_to_wishlist {} (wishlist={})", request.product_id, len(self.wishlist)
        )
        self.session.dispatch(
            AddToWishlist(product_id=request.product_id, wishlist_count=len(self.wishlist))
        )
        return str(
            {"status": "saved", "name": product["name"], "wishlist_count": len(self.wishlist)}
        )

    async def open_faq(self, action: OpenFaq) -> str:
        """Open the store's FAQ / help page and scroll to a topic, then answer
        the shopper's policy question. Use for shipping, returns, warranty,
        payment, trade-in, price match, or activation questions."""
        logger.info("shopping: open_faq topic={!r}", action.topic)
        self.session.dispatch(action)
        return str({"status": "opened", "topic": action.topic})
