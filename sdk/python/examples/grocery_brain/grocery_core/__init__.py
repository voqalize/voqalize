"""Core of the voice grocery demo — shopping list, resolver, tools, catalog.

Pure-Python and provider-neutral; the brain (``brain.py``) wires this onto the
OpenAI Agents SDK + the Swiggy MCP. Importable and testable on its own.
"""

from __future__ import annotations

from . import resolver
from .catalog import build_system_prompt
from .mcp_client import SwiggyMcp
from .models import CARTABLE, Address, Candidate, Item, ItemState, Product, Variant
from .service import GroceryService
from .tools import ALL_TOOLS

__all__ = [
    "ALL_TOOLS",
    "CARTABLE",
    "Address",
    "Candidate",
    "GroceryService",
    "Item",
    "ItemState",
    "Product",
    "SwiggyMcp",
    "Variant",
    "build_system_prompt",
    "resolver",
]
