/**
 * Stage on an ordinary page, composed: the timeline fires cues through the
 * page's moves, a tool's move runs now or once the voice is quiet, and every
 * move's result goes back to the agent. A page whose call lives elsewhere (a
 * browser extension's holder) composes the same parts itself.
 */

import { type Attached, attachStage, staleResult, type StageClient } from "./attach.js";
import type { Moves } from "./moves.js";
import { Timeline, withFire } from "./timeline.js";
import type { StageMove, StageResult } from "./wire.gen.js";

/** How long a `when: "quiet"` move waits for the voice at most. */
const QUIET_CAP_MS = 8000;
/** Silence that counts as quiet. */
const QUIET_HOLD_MS = 300;

export interface StagePage extends Attached {
  readonly timeline: Timeline;
}

/** Stage on this page: cues and tool moves made through `moves`, and each
 *  move's progress and result sent to the agent. */
export function stagePage(
  client: StageClient,
  moves: Moves,
  opts: { lang?: string; onSiteCommand?(command: string, payload: unknown): void } = {},
): StagePage {
  let speaking = false;
  let attached: Attached | null = null;
  /** When each cue reached this page, for its timings. */
  const received = new Map<string, number>();
  const timeline = new Timeline(
    async (cue, info) => {
      const at = received.get(cue.call_ref) ?? info.firedAt;
      received.delete(cue.call_ref);
      const result = await moves.run(cue.move, cue.args, cue.call_ref, { receivedAt: at });
      if (result) attached?.send(withFire(result, info, at));
    },
    {
      lang: opts.lang,
      onDrop: (cue) => {
        received.delete(cue.call_ref);
        attached?.send(staleResult(cue));
      },
      onQueued: (cue, info) => {
        moves.hurry();
        const at = received.get(cue.call_ref) ?? info.firedAt;
        attached?.send({ call_ref: cue.call_ref, move: cue.move, phase: "queued", ms: Math.max(0, Date.now() - at) });
      },
    },
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
    const at = Date.now();
    if (m.when === "quiet") await quiet();
    const result: StageResult | null = await moves.run(m.move, m.args, m.call_ref, { receivedAt: at });
    if (result) attached?.send({ ...result, fired: m.when });
  };
  attached = attachStage(client, {
    timeline,
    onCue: (cue) => {
      received.set(cue.call_ref, Date.now());
      timeline.add(cue);
    },
    onMove: (m) => void onMove(m),
    onSiteCommand: opts.onSiteCommand,
    onBotStarted: () => (speaking = true),
    onBotStopped: () => (speaking = false),
  });
  const a = attached;
  const unlisten = moves.listen((p) => a.send(p));
  return {
    timeline,
    send: a.send,
    hello: a.hello,
    detach() {
      unlisten();
      a.detach();
      timeline.clear();
    },
  };
}
