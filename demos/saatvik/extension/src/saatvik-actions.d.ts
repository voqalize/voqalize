// The site adapter's surface, as `saatvik-actions.js` installs it on `window`.

export interface SaatvikAdapter {
  /** Perform one of the brain's page Actions on Saatvik's page. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the person is looking at now, as a `page_changed` payload. */
  context(): unknown;
  /** Report route changes, the forms' SUBMITs and the results of the
   *  adapter's own moves through `emit`, until the returned stop. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs; the viewer and the brief are the widget's. */
  readonly commands: readonly string[];
  /** Whether SUBMIT on an enquiry form is stopped before it reaches Saatvik. */
  readonly demoBlocksSubmit: boolean;
}

declare global {
  interface Window {
    voqalizeSaatvik?: SaatvikAdapter;
  }
}
