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

import { type StageClient } from "./attach.js";
import { pressParts, showThing } from "./markup.js";
import { Moves, type Performer } from "./moves.js";
import { type StagePage, stagePage } from "./page.js";
import { defineScene, type Scene, type SceneSpec } from "./scene.js";
import { watchForms, type WatchOptions, watchThings } from "./watch.js";
import { Spotlight, type SpotlightTheme } from "./spotlight.js";

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
  /** Timing for the watchers a spec taking the `watch` kit starts. */
  watch?: WatchOptions;
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
  // A spec that takes the `watch` kit wants the agent to know what the
  // visitor does here: the parts they stay on, the forms they fill in.
  const declares = (id: string) => scene.spec.events?.some((e) => e.id === id) ?? false;
  const send = (id: string, data: unknown) => page.send(scene.event(id as never, data as never, moves.author()));
  const stops: (() => void)[] = [];
  if (declares("view.changed")) stops.push(watchThings((v) => send("view.changed", v), opts.watch));
  if (declares("form.changed")) stops.push(watchForms((f) => send("form.changed", f), opts.watch));
  return {
    scene,
    moves,
    page,
    unbound,
    navigated: () => page.hello(),
    detach: () => {
      for (const stop of stops) stop();
      page.detach();
    },
  };
}
