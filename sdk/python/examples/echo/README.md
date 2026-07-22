# Echo — the smallest Voqalize brain

The zero-dependency "does the loop work?" starter. `EchoBrain` greets on session
start and repeats every turn back as `"You said: {transcript}"` — no LLM, no API
keys, nothing beyond the SDK itself.

```
brain.py        # EchoBrain: on_session_start greets, on_interaction echoes
run_direct.py   # serve_direct(EchoBrain, allow_unverified=True) — a localhost WS server
```

## The whole brain

```python
from voqalize.sdk import Brain, Interaction, Session, SessionStart


class EchoBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        async with session.inference() as inf:            # agent-initiated greeting
            await inf.speak("Hi! I'm an echo bot. Say something and I'll repeat it back.")

    async def on_interaction(self, interaction: Interaction) -> None:
        async with interaction.inference() as inf:         # one inference per user turn
            await inf.speak(f"You said: {interaction.transcript}")
```

## Run it

```bash
cd sdk/python
uv run python -m examples.echo.run_direct
# → serving on ws://127.0.0.1:8789/s/{session_id}
```

Then point a **local** demo agent's `brain_url` at `ws://127.0.0.1:8789` (PyGato
appends `/s/{session_id}` itself), open the console, and start a call. You should
hear the greeting, then your own words echoed back.

## Why `allow_unverified=True`

`run_direct.py` passes `allow_unverified=True`. Every PyGato→brain connection
carries a short-lived RS256 token; the SDK verifies it by default against the
**production** Voqalize public keys embedded in the package. Your **local** PyGato
signs with a dev key, so a real check would reject every local session with a
close code **4000** (permanent, non-retriable) — and you'd hear silence. The flag
skips verification for local dev. A deployed brain drops the flag and gets
zero-config prod verification for free. See the top-level
[README](../../README.md) → "Local-dev auth".

## Next step

The direct server here owns its own `websockets` listener — great for a laptop,
not how you deploy. For production, mount `run_session(...)` in your own web
framework: see [`../fastapi_inbound/`](../fastapi_inbound/) for a runnable FastAPI
app (same `EchoBrain`) plus a Cloud Run `Dockerfile`.
