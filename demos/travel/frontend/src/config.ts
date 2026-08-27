/**
 * How this demo's UI wires to its backend — the frontend half of one session.
 *
 * A demo page needs two things to mint a session against the control plane: the
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
 */

import type { APIRequest } from "@pipecat-ai/client-js";

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
  apiBase: "/api/v1",
  // Empty when unprovisioned — the connect request 401s with a clear message.
  agentId: (import.meta.env.VITE_AGENT_ID as string | undefined) ?? "",
  publishableKey: import.meta.env.VITE_PUBLISHABLE_KEY as string | undefined,
};

/**
 * The request that starts a call — pipecat's `APIRequest`, filled in with the
 * bearer and agent id every session needs. `init` is whatever the page has
 * decided by connect time (here, just the calling surface); Travel Desk's voice
 * and language are declared on the brain itself (`backend/brain_gemini.py`), so
 * there is no `config` leg to pass.
 */
export function connectRequest(init: Record<string, unknown>): APIRequest {
  return {
    endpoint: `${demo.apiBase}/sessions.connect`,
    headers: new Headers({ Authorization: `Bearer ${demo.publishableKey ?? ""}` }),
    requestData: {
      agent_id: demo.agentId,
      init,
    } as APIRequest["requestData"],
  };
}

/**
 * `sessions.connect`'s response carries `webrtc_request_params.headers` as a
 * plain object (it went through JSON), but pipecat's offer request builds itself
 * with `Object.fromEntries(headers.entries())` and expects a real `Headers`
 * instance there. Left alone, the offer POST throws a `TypeError` with no
 * message about headers — not at `connect`, and not caught by the compiler,
 * since pipecat types connect params as `unknown`. This is the one line that
 * turns the parsed body back into what pipecat actually wants.
 */
export function withRealHeaders(response: unknown) {
  const r = response as {
    webrtc_request_params?: { headers?: HeadersInit };
    [key: string]: unknown;
  };
  return {
    ...r,
    webrtc_request_params: {
      ...r.webrtc_request_params,
      headers: new Headers(r.webrtc_request_params?.headers),
    },
  };
}
