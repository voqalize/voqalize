# Echo — the smallest Voqalize brain

The zero-dependency "does the loop work?" starter. `EchoBrain` greets and repeats
every turn back as `"You said: {text}"` — no LLM, no API keys, nothing beyond the
SDK itself.

```
brain.py        # EchoBrain: greet returns the opening line, on_user_message echoes
```

## The whole brain

```python
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart


class EchoBrain(Brain):
    async def greet(self, session):
        return "Hi! I'm an echo bot. Say something and I'll repeat it back."

    async def on_user_message(self, session, msg):
        yield SpeechStart()                       # open one unit of speech
        yield Chunk(f"You said: {msg.text}")      # stream text into it
        yield SpeechEnd()                         # close it
```

`greet` answers no user stimulus — it is the one thing the brain says without
being asked. `on_user_message` is an async generator, and the generator is the
mouth: awaiting between the yields is fine, and that is where a tool call goes.

## Run it

A brain is not a server, so there is nothing to run here. Host it from a WebSocket
route your application owns — [`../fastapi_inbound/`](../fastapi_inbound/) is a
runnable FastAPI app with this exact brain, plus a Cloud Run `Dockerfile`:

```bash
cd sdk/python
VOQAL_ALLOW_UNVERIFIED=true \
  uv run uvicorn examples.fastapi_inbound.app:app --host 0.0.0.0 --port 8080
```

Then point a **local** demo agent's `brain_url` at `ws://127.0.0.1:8080` (Voice
appends `/s/{session_id}` itself), open the console, and start a call. You should
hear the greeting, then your own words echoed back.

If your process cannot accept an inbound connection at all, `await serve(EchoBrain,
api_key=..., cortex_url=...)` dials the Cortex relay instead — see
[`../../README.md`](../../README.md).

## Why `VOQAL_ALLOW_UNVERIFIED`

Every Voice→brain connection carries a short-lived RS256 token; the SDK verifies it
by default against the **production** Voqalize public keys embedded in the package.
Your **local** runtime signs with a dev key, so a real check would reject every
local session with close code **4000** (permanent, non-retriable) — and you'd hear
silence. The flag skips verification for local dev. A deployed brain drops it and
gets zero-config prod verification for free.
