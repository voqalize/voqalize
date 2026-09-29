// The site adapter's surface, as `qween-actions.js` installs it on `window`.

export interface QweenAdapter {
  /** Perform one of the brain's Actions on Qween's page. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the shopper is looking at now, as a `page_changed` payload. */
  context(): unknown;
  /** Report route changes and dialogs through `emit` until the returned stop. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  readonly commands: readonly string[];
}

declare global {
  interface Window {
    voqalizeQween?: QweenAdapter;
  }
}
