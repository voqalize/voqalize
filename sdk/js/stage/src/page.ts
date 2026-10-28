/**
 * Stage on an ordinary page, composed: the timeline fires cues through the
 * page's moves, a tool's move runs now or once the voice is quiet, and every
 * move's result goes back to the agent. A page whose call lives elsewhere (a
 * browser extension's holder) composes the same parts itself.
 */

import { type Attached, attachStage, staleResult, type StageClient } from "./attach";
import type { Moves } from "./moves";
import { Timeline } from "./timeline";
import type { StageMove } from "./wire.gen";

/** How long a `when: "quiet"` move waits for the voice at most. */
const QUIET_CAP_MS = 8000;
/** Silence that counts as quiet. */
const QUIET_HOLD_MS = 300;

export interface StagePage extends Attached {
  readonly timeline: Timeline;
}

export function stagePage(
  client: StageClient,
  moves: Moves,
  opts: { lang?: string; onSiteCommand?(command: string, payload: unknown): void } = {},
): StagePage {
  let speaking = false;
  let attached: Attached | null = null;
  const timeline = new Timeline(
    async (cue) => {
      const result = await moves.run(cue.move, cue.args, cue.call_ref);
      if (result) attached?.send(result);
    },
    { lang: opts.lang, onDrop: (cue) => attached?.send(staleResult(cue)) },
  );
  const quiet = async () => {
    const end = Date.now() + QUIET_CAP_MS;
    while (Date.now() < end) {
      if (!speaking) {
        await new Promise((r) => setTimeout(r, QUIET_HOLD_MS));
        if (!speaking) return;
      }
      await new Promise((r) => setTimeout(r, 50));
    }
  };
  const onMove = async (m: StageMove) => {
    if (m.when === "quiet") await quiet();
    const result = await moves.run(m.move, m.args, m.call_ref);
    if (result) attached?.send(result);
  };
  attached = attachStage(client, {
    timeline,
    onMove: (m) => void onMove(m),
    onSiteCommand: opts.onSiteCommand,
    onBotStarted: () => (speaking = true),
    onBotStopped: () => (speaking = false),
  });
  const a = attached;
  return {
    timeline,
    send: a.send,
    hello: a.hello,
    detach() {
      a.detach();
      timeline.clear();
    },
  };
}
