/**
 * How this demo's UI wires to its backend — the frontend half of one session.
 *
 * A demo page needs three things to mint a session against the control plane:
 * the tenant slug, the agent's Firestore id, and a publishable (`pk_`) key. All
 * three come from Vite env vars so no environment-specific id is baked into public
 * source — a fresh checkout is provisioned by setting them (see this app's
 * `.env.example`). Vite inlines `import.meta.env.*` at build, and those reads must
 * be **static literals**, so they're spelled out here.
 *
 * `apiBase` is always `/api/v1`: in local dev Vite proxies it to the control
 * plane; in a deploy the apex domain that serves the demo UI rewrites `/api/*`
 * to the control plane. Either way the browser calls same-origin, so a
 * publishable key's `allowed_origins` only needs the domain the UI is served on.
 *
 * OrderDesk is a Hindi call end to end — the pharmacist speaks Hindi, the screen
 * stays English — so the pipeline below opens in `hi` on both legs.
 */

/** Resolved wiring for this demo agent. */
export interface DemoConfig {
  /** Versioned API root the page calls (same-origin; proxied to the control plane). */
  apiBase: string;
  /** Tenant slug for the `/api/v1/{slug}/...` path. */
  tenantSlug: string;
  /** Agent Firestore doc id passed to `sessions.create_and_start`. */
  agentId: string;
  /** Publishable key for browser auth. Undefined until the demo is provisioned. */
  publishableKey: string | undefined;
}

/** All demos live in one tenant; `VITE_TENANT` selects which (default `demo`). */
const TENANT = (import.meta.env.VITE_TENANT as string | undefined) ?? "demo";

export const config: DemoConfig = {
  apiBase: "/api/v1",
  tenantSlug: TENANT,
  // Empty when unprovisioned — the SDK surfaces a clear error the call bar shows.
  agentId: (import.meta.env.VITE_AGENT_ID as string | undefined) ?? "",
  publishableKey: import.meta.env.VITE_PUBLISHABLE_KEY as string | undefined,
};
