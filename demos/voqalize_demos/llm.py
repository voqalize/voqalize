"""The Gemini client seam — a horizontal dependency the demo brains run on.

One instance per process, constructed from ``GEMINI_API_KEY`` and injected into
every brain (see :mod:`voqalize_demos.brains._gemini`). Brains depend on this
concrete provider, not on ``google-genai`` directly, so the LLM is
dependency-injected exactly like it is in the platform's own hosted brains — the
same shape a customer would use to wrap their model of choice.

(There is deliberately no abstraction layer; if a demo ever needed multi-provider
routing, a differently-backed provider can be swapped in behind the same
``stream``.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types


class GeminiProvider:
    """Wraps one ``genai.Client``. Brains call :meth:`stream` per inference.

    The client is created lazily on first use so an empty ``api_key`` doesn't fail
    process startup — the app graph is built in every environment, but the key is
    only needed once a brain is actually dialed."""

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key
        self._client: genai.Client | None = None

    def _client_or_build(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def stream(
        self,
        *,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """Run one streaming ``generate_content`` call and yield its chunks."""
        return await self._client_or_build().aio.models.generate_content_stream(
            model=model, contents=contents, config=config
        )
