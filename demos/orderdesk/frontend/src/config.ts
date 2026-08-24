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
 *
 * OrderDesk is a Hindi call end to end — the pharmacist speaks Hindi, the screen
 * stays English. That language is **not** set here: it is the agent record's
 * default, and a brain overrides it with one `session.configure(...)` — the only
 * place both the STT and the TTS leg move together. A page that set one of them
 * from the browser would be setting exactly half of a pair.
 */

/** Resolved wiring for this demo agent. */
export interface DemoConfig {
  /** Versioned API root the page calls (same-origin; proxied to the control plane). */
  apiBase: string;
  /** Agent Firestore doc id passed to `sessions.create`. */
  agentId: string;
  /** Publishable key for browser auth. Undefined until the demo is provisioned. */
  publishableKey: string | undefined;
}

export const config: DemoConfig = {
  apiBase: "/api/v1",
  // Empty when unprovisioned — the SDK surfaces a clear error the call bar shows.
  agentId: (import.meta.env.VITE_AGENT_ID as string | undefined) ?? "",
  publishableKey: import.meta.env.VITE_PUBLISHABLE_KEY as string | undefined,
};
