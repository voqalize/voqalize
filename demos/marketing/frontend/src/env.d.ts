/// <reference types="astro/client" />

interface ImportMetaEnv {
  /** Dev agent id (cortex mode). Set in .env.local. */
  readonly PUBLIC_AGENT_ID?: string;
  /** Publishable key whose allowed origins include this site. Set in .env.local. */
  readonly PUBLIC_PUBLISHABLE_KEY?: string;
  /** Override for the sessions API root; defaults to the same-origin /api/v1. */
  readonly PUBLIC_API_BASE?: string;
  /** PostHog project token; defaults to the Voqalize Marketing Website project. */
  readonly PUBLIC_POSTHOG_KEY?: string;
  /** PostHog ingestion host; https://t.voqalize.com once the reverse proxy resolves. */
  readonly PUBLIC_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
