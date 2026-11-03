/**
 * The snippet's two Stage performers (`call/stage.ts`: `openPage` for
 * `site.page`, `showRegion` for `site.show`), which that module keeps to
 * itself. `build.mjs` exports them from the snippet's own source when it
 * bundles (the `snippet-stage-moves` module), so they are run as written there
 * and never copied here.
 */
declare module "snippet-stage-moves" {
  import type { MoveContext } from "@voqalize/stage";
  import type { StageDeps } from "@snippet/call/stage";

  export function openPage(id: string, c: MoveContext, deps: StageDeps): Promise<string | null>;
  export function showRegion(id: string, c: MoveContext, deps: StageDeps): Promise<string>;
}
