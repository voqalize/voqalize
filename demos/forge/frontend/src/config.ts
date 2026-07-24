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
 * to the control plane. Either way the browser calls same-origin.
 */

export interface PipelineConfig {
  stt: { model: string; language?: string };
  tts: { voice: string; language: string };
}

export interface DemoConfig {
  apiBase: string;
  tenantSlug: string;
  agentId: string;
  publishableKey: string | undefined;
  pipeline: PipelineConfig;
}

const TENANT = (import.meta.env.VITE_TENANT as string | undefined) ?? "demo";

export const config: DemoConfig = {
  apiBase: "/api/v1",
  tenantSlug: TENANT,
  agentId: (import.meta.env.VITE_AGENT_ID as string | undefined) ?? "",
  publishableKey: import.meta.env.VITE_PUBLISHABLE_KEY as string | undefined,
  pipeline: {
    stt: { model: "vql-stt", language: "en" },
    tts: { voice: "omnivoice/gauri", language: "en" },
  },
};
