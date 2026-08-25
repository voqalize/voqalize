/**
 * How this demo's UI wires to its backend — the frontend half of one session.
 *
 * A demo page needs two things to start a call against the control plane: the
 * agent's Firestore id, and a publishable (`pk_`) key. Both come from Vite env
 * vars so no environment-specific id is baked into public source — a fresh
 * checkout is provisioned by setting them (see this app's `.env.example`). Vite
 * inlines `import.meta.env.*` at build, and those reads must be **static
 * literals**, so they're spelled out here.
 *
 * The workspace is not one of them: the `pk_` key belongs to exactly one, so the
 * control plane reads it off the key.
 *
 * `apiBase` is always `/api/v1`: in local dev Vite proxies it to the control
 * plane; in a deploy the apex domain that serves the demo UI rewrites `/api/*`
 * to the control plane. Either way the browser calls same-origin, so a
 * publishable key's `allowed_origins` only needs the domain the UI is served on.
 *
 * The rest of this file is the whole Voqalize-specific surface of a page: one
 * request, and one line over the response. There is no client library — a call
 * is a pipecat call, and everything after `connect` is pipecat's own. See
 * `docs/client/handshake` for the same two functions written out for a reader.
 */

import type { APIRequest } from '@pipecat-ai/client-js';

/** Resolved wiring for this demo agent. */
export interface DemoConfig {
  /** Versioned API root the page calls (same-origin; proxied to the control plane). */
  apiBase: string;
  /** Agent Firestore doc id passed to `sessions.connect`. */
  agentId: string;
  /** Publishable key for browser auth. Undefined until the demo is provisioned. */
  publishableKey: string | undefined;
}

export const demo: DemoConfig = {
  apiBase: '/api/v1',
  // Empty when unprovisioned — the control plane answers 401 and the page shows it.
  agentId: (import.meta.env.VITE_AGENT_ID as string | undefined) ?? '',
  publishableKey: import.meta.env.VITE_PUBLISHABLE_KEY as string | undefined,
};

/**
 * The request that starts a call — pipecat's `APIRequest`, filled in with the
 * four facts that are ours: the route, the `Bearer` scheme, the body shape, and
 * nothing else.
 *
 * Two named things ride beside `agent_id`, each named for what it is.
 *
 * `init` is the opaque blob the brain reads back as `session.init` — flat, and
 * uninterpreted by everything between here and there.
 *
 * `config` is this session's configuration: the wire `Config`'s `tts`, `stt`
 * and `idle` sections plus `record`, as canonical proto3 JSON. This page sends
 * none — voice and language belong to the brain, which is the layer that knows
 * who is calling.
 *
 * Both are stored on the session and served to the voice runtime over its own
 * authenticated call, so send identifiers rather than personal data.
 *
 * Hand it to `PipecatAppBase`'s `startBotParams` and memoize it there, since it
 * is a dependency of the connect-on-mount effect and a fresh object every
 * render re-starts the call every render.
 */
export function connectRequest(
  init: Record<string, unknown>,
  config?: Record<string, unknown>,
): APIRequest {
  return {
    endpoint: `${demo.apiBase}/sessions.connect`,
    // `Authorization` only. Pipecat sets `Content-Type: application/json` itself
    // and then spreads these over it — sending it here a second time arrives as
    // `application/json, application/json`, which FastAPI does not read as JSON
    // at all: the body comes through as a *string* and the route answers 422
    // with a validation error about the object it was handed.
    headers: new Headers({ Authorization: `Bearer ${demo.publishableKey ?? ''}` }),
    // Cast, not check: both are this page's own objects and are about to be
    // `JSON.stringify`d either way. Pipecat types `requestData` as its
    // `Serializable`, which it does not export, so the cast is spelled through
    // the interface it does.
    requestData: {
      agent_id: demo.agentId,
      init,
      ...(config ? { config } : {}),
    } as APIRequest['requestData'],
  };
}

/**
 * The one line you write yourself.
 *
 * `sessions.connect` answers with the transport's argument and nothing else —
 * `{ webrtc_request_params: { endpoint, headers }, session_id }` — so a page
 * forwards it rather than reading it. Pipecat snake-to-camels every key it is
 * handed, so those names are already the ones it wants.
 *
 * The single thing it cannot forward verbatim is `headers`: pipecat types it as
 * a `Headers` and reads it as one, and JSON has no `Headers`, so it has to come
 * back as JSON and be turned into one again here.
 */
export function withRealHeaders(response: unknown) {
  const body = response as {
    webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> };
    session_id?: string;
  };
  return {
    ...body,
    webrtc_request_params: {
      ...body.webrtc_request_params,
      headers: new Headers(body.webrtc_request_params?.headers ?? {}),
    },
  };
}
