/**
 * Stage on a page with no build step of its own: a spec, `data-stage-*`
 * attributes in the markup, and one call.
 *
 * ```html
 * <script type="module">
 *   import { attach } from "…/stage.js";            // our bundle of this module
 *   await attach(client, { spec: "/stage/scene.json" });
 * </script>
 * ```
 *
 * Each move the spec declares gets the page's own performer when one is
 * given, else the stock one for its verb (`show` points at a
 * `data-stage-thing`, `filter` presses `data-stage-part`s); a move with
 * neither is left unregistered, and says so, so its result comes back failed
 * rather than a wrong thing being pressed. A single-page app calls
 * `navigated()` after each route change, so the agent hears where it is.
 */

import { type StageClient } from "./attach";
import { pressParts, showThing } from "./markup";
import { Moves, type Performer } from "./moves";
import { type StagePage, stagePage } from "./page";
import { defineScene, type Scene, type SceneSpec } from "./scene";
import { Spotlight, type SpotlightTheme } from "./spotlight";

/** The stock performer for a cue's verb, acting on `data-stage-*` markup. */
export const STOCK: Readonly<Record<string, Performer<never>>> = {
  show: showThing as Performer<never>,
  filter: pressParts as Performer<never>,
};

export interface ScriptOptions {
  /** The spec, or the URL of its JSON. */
  spec: SceneSpec | string;
  theme?: SpotlightTheme;
  lang?: string;
  /** The page's own performers, by move id; they win over the stock ones. */
  performers?: Readonly<Record<string, Performer<never>>>;
}

export interface ScriptStage {
  readonly scene: Scene<SceneSpec>;
  readonly moves: Moves;
  readonly page: StagePage;
  /** The moves the spec declares that nothing here performs. */
  readonly unbound: readonly string[];
  /** The route changed: tell the agent where the page is now. */
  navigated(): void;
  detach(): void;
}

/** A spec from a URL, or as given. */
async function specOf(spec: SceneSpec | string): Promise<SceneSpec> {
  if (typeof spec !== "string") return spec;
  const res = await fetch(spec, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`stage: the spec at ${spec} answered ${res.status}`);
  return (await res.json()) as SceneSpec;
}

/** Stage on this page, from its spec and its markup. */
export async function attach(client: StageClient, opts: ScriptOptions): Promise<ScriptStage> {
  const scene = defineScene(await specOf(opts.spec));
  const moves = new Moves(new Spotlight(opts.theme ?? { color: "#2563eb" }));
  const unbound: string[] = [];
  for (const m of scene.spec.moves) {
    const performer = opts.performers?.[m.id] ?? (m.verb ? STOCK[m.verb] : undefined);
    if (performer) scene.register(moves, m.id, performer as never);
    else unbound.push(m.id);
  }
  if (unbound.length) console.warn(`stage: nothing on this page performs ${unbound.join(", ")}`);
  const page = stagePage(client, moves, { lang: opts.lang });
  return {
    scene,
    moves,
    page,
    unbound,
    navigated: () => page.hello(),
    detach: () => page.detach(),
  };
}
