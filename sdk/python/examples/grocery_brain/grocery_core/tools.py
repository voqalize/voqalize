"""The tools we expose to the agent (the Swiggy MCP is hidden behind these).

Every tool is fast and non-blocking: ``add_items`` notes items instantly and
the slow MCP search happens in the background. The agent reasons over the short
strings these return; the live UI is driven by the service's notify pushes, not
by the agent. Tools read their per-session ``GroceryService`` from the run
context (``Runner.run_streamed(agent, input, context=service)``).
"""

from __future__ import annotations

from agents import RunContextWrapper, Tool, function_tool

from .models import Item, ItemState
from .service import GroceryService

Ctx = RunContextWrapper[GroceryService]

_STATE_WORD = {
    ItemState.DRAFT: "noted",
    ItemState.RESOLVING: "looking it up",
    ItemState.NEEDS_CLARIFICATION: "needs a choice",
    ItemState.MATCHED: "matched",
    ItemState.CONFIRMED: "confirmed",
    ItemState.UNAVAILABLE: "not found",
}


def _line(item: Item) -> str:
    bits = [f"[{item.id}] {item.raw_text} x{item.quantity} — {_STATE_WORD[item.state]}"]
    if item.chosen:
        bits.append(
            f"→ {item.chosen.product.brand} {item.chosen.product.name} "
            f"({item.chosen.variant.qty_desc}, ₹{item.chosen.price:g})"
        )
    if item.state == ItemState.NEEDS_CLARIFICATION:
        opts = "; ".join(
            f"{n + 1}) {c.product.brand} {c.product.name} ({c.variant.qty_desc}, ₹{c.price:g})"
            for n, c in enumerate(item.candidates)
        )
        bits.append(f"options: {opts}")
    return " ".join(bits)


@function_tool
async def add_items(ctx: Ctx, items: list[str]) -> str:
    """Note one or more grocery items on the shopping list, exactly as the customer
    said them (e.g. ["atta", "2 packs of dahi", "lays"]). Returns instantly; each
    item is matched to real products in the background. Call this the moment the
    customer mentions things — don't wait, don't search first.
    """
    created = ctx.context.add_items(items)
    if not created:
        return "No items to add."
    return "Added to the list (resolving in background): " + "; ".join(
        f"{i.raw_text} [{i.id}]" for i in created
    )


@function_tool
async def view_list(ctx: Ctx) -> str:
    """Return the current shopping list with each item's state, chosen product,
    and any pending options. Use to check progress before summarising or checking out.
    """
    items = ctx.context.ordered()
    if not items:
        return "The shopping list is empty."
    head = f"{len(items)} item(s); cart total ₹{ctx.context.total():g}:"
    return head + "\n" + "\n".join(_line(i) for i in items)


@function_tool
async def pending_clarifications(ctx: Ctx) -> str:
    """Return the items that came back ambiguous and need the customer to choose.
    Call this after adding items (or when the customer pauses) and ask about each
    one in plain language. Empty result means nothing needs clarifying yet.
    """
    pend = ctx.context.pending_clarifications()
    if not pend:
        return "Nothing needs clarification right now."
    return "Needs a choice:\n" + "\n".join(_line(i) for i in pend)


@function_tool
async def clarify_item(ctx: Ctx, item_id: str, choice: str) -> str:
    """Resolve an ambiguous item by picking one of its options. ``choice`` can be
    an option number ("2") or words ("the Amul one", "multigrain"). Confirms the item.
    """
    item = ctx.context.clarify(item_id, choice)
    if item is None:
        return f"Couldn't match that choice for {item_id}. Try the option number."
    assert item.chosen is not None
    return (
        f"Confirmed {item.raw_text}: {item.chosen.product.brand} {item.chosen.product.name} "
        f"({item.chosen.variant.qty_desc}, ₹{item.chosen.price:g})."
    )


@function_tool
async def set_quantity(ctx: Ctx, item_id: str, quantity: int) -> str:
    """Set how many units of an item the customer wants."""
    item = ctx.context.set_quantity(item_id, quantity)
    if item is None:
        return f"No item {item_id}."
    return f"Set {item.raw_text} to x{item.quantity}."


@function_tool
async def confirm_item(ctx: Ctx, item_id: str) -> str:
    """Confirm a matched item as-is (keep the proposed product)."""
    item = ctx.context.confirm(item_id)
    if item is None:
        return f"Can't confirm {item_id} yet (no product matched)."
    return f"Confirmed {item.raw_text}."


@function_tool
async def remove_item(ctx: Ctx, item_id: str) -> str:
    """Remove an item from the shopping list."""
    return "Removed." if ctx.context.remove(item_id) else f"No item {item_id}."


@function_tool
async def checkout(ctx: Ctx) -> str:
    """Add every matched/confirmed item to the Swiggy cart for the customer to pay.
    Only do this when the customer asks to check out. Summarise the total afterwards.
    """
    items = ctx.context.cart_items()
    if not items:
        return "Nothing on the list is ready to check out yet."
    summary = await ctx.context.checkout()
    return (
        f"Added {summary['added']} item(s) to the cart, total ₹{summary['total']:g}. "
        f"{'Some failed.' if summary['failed'] else 'Ready to pay in the app.'}"
    )


ALL_TOOLS: list[Tool] = [
    add_items,
    view_list,
    pending_clarifications,
    clarify_item,
    set_quantity,
    confirm_item,
    remove_item,
    checkout,
]
