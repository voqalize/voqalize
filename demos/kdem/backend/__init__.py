"""KDEM: Aria, the voice agent on karnatakadigital.in — brain, route and knowledge base.

See `routes.py` for the route, `brain.py` for Aria and `knowledge.py` for the
pages she answers from.
"""

from .routes import NAME, build, router

__all__ = ["NAME", "build", "router"]
