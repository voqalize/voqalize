"""The demo brains — one ``voqalize.sdk.Brain`` per demo.

Each brain subclasses :class:`voqalize_demos.brains._gemini.GeminiBrain` (the
shared Gemini plumbing) and provides its own system prompt, tool schemas, and
opening line. The umbrella app dials each one at ``/{name}/s/{session_id}``.
"""
