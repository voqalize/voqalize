"""Shared machinery for framework integrations.

A framework integration hands the SDK a *native* agent (an ADK ``LlmAgent``) and
lets the SDK drive its run loop — the *SDK-drives-the-loop* north star. Two
concerns are identical across every such integration, so they live here rather
than in any one adapter:

* :mod:`.context` — the ``voice()`` accessor a native tool uses to reach the live
  turn (a :class:`~contextvars.ContextVar` the adapter sets around the driven run).
* :mod:`.heard` — composing the model's contents from the framework-owned
  **heard-truth** conversation, so past turns are what the user actually heard,
  never the generated tail of a barged-in reply.

Internal package (underscore-prefixed): the public surface is re-exported from
the adapter package (``voqalize.google_adk``). Importing this pulls google-genai
types (via :mod:`.heard`); ``import voqalize.sdk`` does not, keeping the core
dependency-light.
"""
