/**
 * How each demo UI wires to a backend — the frontend half of the shared spine.
 *
 * A demo page needs three things to mint a session against the control plane:
 * the tenant slug, the agent's Firestore id, and a publishable (`pk_`) key. All
 * three come from Vite env vars so no environment-specific id is baked into public
 * source — a fresh checkout is provisioned by setting them (see `demos/README.md`
 * and the Phase-4 provisioning step). Vite inlines `import.meta.env.*` at build,
 * and those reads must be **static literals**, so each demo is spelled out.
 *
 * `API_BASE` is always `/api/v1`: in local dev Vite proxies it to the control
 * plane; in a deploy the umbrella app reverse-proxies `/api/*` there. Either way
 * the browser calls same-origin, so a publishable key's `allowed_origins` only
 * ever needs the demo's own domain.
 */

import manifest from "../../manifest.json";

/** All demos live in one tenant; `VITE_DEMO_TENANT` selects which. */
const TENANT = (import.meta.env.VITE_DEMO_TENANT as string | undefined) ?? "demo";

/** STT/TTS a demo's session opens with — sourced from `manifest.json` so the
 * pipeline is declared in one place, not duplicated in each page's hook call. */
export interface PipelineConfig {
  stt: { model: string; language?: string };
  tts: { voice: string; language: string };
}

/** Resolved wiring for one demo agent. */
export interface DemoConfig {
  /** Versioned API root the page calls (same-origin; proxied to the control plane). */
  apiBase: string;
  /** Tenant slug for the `/api/v1/{slug}/...` path. */
  tenantSlug: string;
  /** Agent Firestore doc id passed to `sessions.create_and_start`. */
  agentId: string;
  /** Publishable key for browser auth. Undefined until the demo is provisioned. */
  publishableKey: string | undefined;
  /** STT/TTS for the session, straight from the manifest entry. */
  pipeline: PipelineConfig;
}

/** name → { stt, tts } from the manifest — the pipeline's single source of truth. */
const PIPELINES: Record<string, PipelineConfig> = Object.fromEntries(
  manifest.demos.map((d) => [d.name, { stt: d.stt, tts: d.tts }]),
);

function demo(
  name: string,
  agentId: string | undefined,
  publishableKey: string | undefined,
): DemoConfig {
  const pipeline = PIPELINES[name];
  if (!pipeline) {
    throw new Error(`demo "${name}" is wired in config.ts but missing from manifest.json`);
  }
  return {
    apiBase: "/api/v1",
    tenantSlug: TENANT,
    agentId: agentId ?? "",
    publishableKey,
    pipeline,
  };
}

/**
 * Per-demo wiring, keyed by the demo name (its URL segment). Every manifest demo
 * must have an entry here — Vite inlines `import.meta.env.*` only from static
 * literals, so each demo's env reads are spelled out and can't be generated from
 * the manifest at build. The dev-only check below flags a manifest demo that has
 * no entry (its UI would silently never wire up).
 */
export const DEMOS = {
  travel: demo(
    "travel",
    import.meta.env.VITE_TRAVEL_AGENT as string | undefined,
    import.meta.env.VITE_TRAVEL_PK as string | undefined,
  ),
  shopping: demo(
    "shopping",
    import.meta.env.VITE_SHOPPING_AGENT as string | undefined,
    import.meta.env.VITE_SHOPPING_PK as string | undefined,
  ),
  support: demo(
    "support",
    import.meta.env.VITE_SUPPORT_AGENT as string | undefined,
    import.meta.env.VITE_SUPPORT_PK as string | undefined,
  ),
  servicing: demo(
    "servicing",
    import.meta.env.VITE_SERVICING_AGENT as string | undefined,
    import.meta.env.VITE_SERVICING_PK as string | undefined,
  ),
  interview_bot: demo(
    "interview_bot",
    import.meta.env.VITE_INTERVIEW_BOT_AGENT as string | undefined,
    import.meta.env.VITE_INTERVIEW_BOT_PK as string | undefined,
  ),
  sugar: demo(
    "sugar",
    import.meta.env.VITE_SUGAR_AGENT as string | undefined,
    import.meta.env.VITE_SUGAR_PK as string | undefined,
  ),
  legal: demo(
    "legal",
    import.meta.env.VITE_LEGAL_AGENT as string | undefined,
    import.meta.env.VITE_LEGAL_PK as string | undefined,
  ),
  lead_qual: demo(
    "lead_qual",
    import.meta.env.VITE_LEAD_QUAL_AGENT as string | undefined,
    import.meta.env.VITE_LEAD_QUAL_PK as string | undefined,
  ),
  aura: demo(
    "aura",
    import.meta.env.VITE_AURA_AGENT as string | undefined,
    import.meta.env.VITE_AURA_PK as string | undefined,
  ),
} as const;

export type DemoKey = keyof typeof DEMOS;

if (import.meta.env.DEV) {
  for (const d of manifest.demos) {
    if (!(d.name in DEMOS)) {
      const ENV = d.name.toUpperCase();
      console.error(
        `[demos] manifest demo "${d.name}" has no DEMOS entry in config.ts — its UI won't ` +
          `wire up. Add: ${d.name}: demo("${d.name}", import.meta.env.VITE_${ENV}_AGENT, ` +
          `import.meta.env.VITE_${ENV}_PK), plus ${d.name}.html + src/${d.name}/main.tsx ` +
          `and the VITE_${ENV}_* env (see demos/README.md).`,
      );
    }
  }
}
