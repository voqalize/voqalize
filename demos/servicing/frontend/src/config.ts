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
  // Empty when unprovisioned — the request fails with a clear error the gate shows.
  agentId: (import.meta.env.VITE_AGENT_ID as string | undefined) ?? "",
  publishableKey: import.meta.env.VITE_PUBLISHABLE_KEY as string | undefined,
};

/**
 * Builds the `sessions.connect` request `PipecatAppBase`'s `startBotParams`
 * posts — `init` is opaque business context the brain reads at
 * `on_session_start`; `config` is the rare per-call voice/language override
 * (servicing's brain owns both, so nothing ever passes it).
 */
export function connectRequest(
  init: Record<string, unknown>,
  config?: Record<string, unknown>,
): APIRequest {
  return {
    endpoint: `${demo.apiBase}/sessions.connect`,
    headers: new Headers({ Authorization: `Bearer ${demo.publishableKey ?? ""}` }),
    requestData: {
      agent_id: demo.agentId,
      init,
      ...(config ? { config } : {}),
    } as APIRequest["requestData"],
  };
}

/**
 * Pipecat builds the WebRTC offer request with
 * `Object.fromEntries(headers.entries())` — it expects a constructed `Headers`,
 * and JSON has no such type, so the plain object `sessions.connect`'s parsed
 * body hands back throws a `TypeError` at the offer POST, not at `connect`, and
 * with no message about headers. One line, in one place: `docs/build/connect.md`
 * carries the reasoning.
 */
export function withRealHeaders(response: unknown): unknown {
  const r = response as { webrtc_request_params?: { headers?: HeadersInit } } | null;
  if (!r?.webrtc_request_params) return response;
  return {
    ...r,
    webrtc_request_params: {
      ...r.webrtc_request_params,
      headers: new Headers(r.webrtc_request_params.headers),
    },
  };
}
