/**
 * Stage, once for the whole site, at module level: one `Moves` with every
 * performer registered (src/stage/performers.ts), alive with or without a call,
 * so the `?debug=1` console runs the same moves the agent does. When the dock
 * has a client, `stagePage` attaches to it and the brain's moves arrive here;
 * every store change goes out as a state event through the same attachment,
 * stamped by `moves.author()` (the agent's while a move acts, else the visitor's).
 */
import { Moves, Spotlight, type StagePage, stagePage } from "@voqalize/stage";
import { useUi } from "../state/ui";
import { useVoiceClient } from "./client";
import { setEventSink } from "./events";
import { performers } from "./performers";
import { scene } from "./scene.gen";
import { showWhole } from "./view";

/** The ring: saffron, the brand's accent, visible on teal and on paper. */
export const RING_COLOR = "#e5791b";

export const moves = new Moves(new Spotlight({ color: RING_COLOR }), {
  fixed: [".site-header"],
  // X1: every scroll a move makes shows the target's whole group, inner scroll
  // areas included, then the window with Stage's own scroll and timing.
  extend: (c) => {
    const windowScroll = c.scrollTo;
    return { scrollTo: (el: Element) => showWhole(el, windowScroll) };
  },
});
scene.registerAll(moves, performers);

let page: StagePage | null = null;
let offReady: (() => void) | null = null;

function attach(client: ReturnType<typeof useVoiceClient.getState>["client"]) {
  offReady?.();
  offReady = null;
  page?.detach();
  page = null;
  setEventSink(null);
  if (!client) return;
  const p = stagePage(client, moves, { lang: useUi.getState().lang });
  page = p;
  setEventSink((id, data) => p.send(scene.event(id, data, moves.author())));
  // The brain learns where the page is as soon as the call is up.
  const ready = () => p.hello();
  client.on("botReady", ready);
  offReady = () => client.off("botReady", ready);
}

attach(useVoiceClient.getState().client);
useVoiceClient.subscribe((s, prev) => {
  if (s.client !== prev.client) attach(s.client);
});

/** The route changed: the brain hears the new path (and switches job). */
export function hello() {
  page?.hello();
}

let n = 0;
/** Run a move by hand (the debug console, Playwright): rings and refusals show as in a call. */
export function runMove(id: string, args: unknown) {
  return moves.run(id, args, `debug-${++n}`);
}
