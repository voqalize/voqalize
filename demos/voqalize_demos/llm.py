"""The Gemini client seam — a horizontal dependency the demo brains run on.

One instance per process, constructed from ``GEMINI_API_KEY`` and injected into
every demo's ``build(llm)``. A brain hands :attr:`GeminiProvider.client` to
:class:`voqalize.sdk.gemini.GeminiBrain`, so the model is dependency-injected
rather than reached for — the same shape a customer would use to hold one client
for a process and hand it to each session's brain.
"""

from __future__ import annotations

from google import genai


class GeminiProvider:
    """Holds one ``genai.Client``, built on first use.

    Laziness is the whole job: the umbrella builds its app graph in every
    environment — tests, CI, a container that has not been given a key yet — and
    ``genai.Client(api_key="")`` raises at construction. The key is only needed
    once a session is actually dialed, which is when a brain first reads
    :attr:`client`.
    """

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client
