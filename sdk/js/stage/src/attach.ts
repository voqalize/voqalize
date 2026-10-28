/**
 * Stage on a pipecat client that already exists.
 *
 * `attachStage` only subscribes and sends: it never makes, connects or wraps
 * the client, and it hands nothing of pipecat's back. It reads the agent's
 * `ui-command`s (Stage's `stage_cue` and `stage_move`, and anything else for
 * the site), the spoken text as the voice plays it, and who is speaking; it
 * sends Stage's results and hello as `ui-event`s.
 *
 * Give it a `Timeline` and it feeds it (spoken text, speaking, stopped, and
 * the person talking over the voice, whose dropped cues it reports as
 * `refused` with why `interrupted`); or leave the timeline out and use the
 * hooks.
 */

import type { Timeline } from "./timeline";
import { asUiAction, sendAppEvent, type StageCue, type StageHello, type StageMove, type StageResult } from "./wire.gen";

/** The contract version this runtime speaks, sent in `stage_hello`. */
export const STAGE_CONTRACT = 1;
export const STAGE_RUNTIME = "@voqalize/stage";

/** A handler of one of the client's events. */
export type ClientHandler = (...args: any[]) => void;

/**
 * What `attachStage` uses of a pipecat client, written out rather than
 * imported, so a `PipecatClient` of any version in the peer range (and of any
 * copy of the package, which a linked or bundled site may have two of) fits:
 * `on`/`off` for `uiCommand`, `botOutput`, `botTtsText`,
 * `botStartedSpeaking`, `botStoppedSpeaking` and `userStartedSpeaking`, and
 * `sendUIEvent`.
 */
export interface StageClient {
  on(event: string, handler: ClientHandler): unknown;
  off(event: string, handler: ClientHandler): unknown;
  sendUIEvent(event: string, payload?: unknown): void;
}

export interface AttachOptions {
  onCue?(cue: StageCue): void;
  onMove(move: StageMove): void;
  /** A `ui-command` that is not Stage's: the site's own Actions. */
  onSiteCommand?(command: string, payload: unknown): void;
  /** Fed with what the voice says and who speaks; its cues are `onCue`'s
   *  default. */
  timeline?: Timeline;
  /** Spoken text as it plays (after `botOutput` is preferred over
   *  `botTtsText`). */
  onHeard?(text: string): void;
  onBotStarted?(): void;
  onBotStopped?(): void;
  /** The person started speaking; `dropped` holds the timeline's cues that
   *  were dropped, already reported. */
  onUserStarted?(dropped: StageCue[]): void;
}

export interface Attached {
  send(ev: StageResult | StageHello): void;
  /** `stage_hello` for this page. */
  hello(): void;
  detach(): void;
}

type Spoken = { text?: string; spoken?: boolean; will_be_spoken?: boolean; output_type?: string };

export function attachStage(client: StageClient, opts: AttachOptions): Attached {
  const tl = opts.timeline;
  let outputSeen = false;

  const send = (ev: StageResult | StageHello) => {
    const sender = (event: string, payload?: unknown) => client.sendUIEvent(event, payload);
    if ("call_ref" in ev) sendAppEvent(sender, { event: "stage_result", payload: ev });
    else sendAppEvent(sender, { event: "stage_hello", payload: ev });
  };

  const heard = (text: string) => {
    tl?.hear(text);
    opts.onHeard?.(text);
  };

  const handlers: [string, ClientHandler][] = [
    [
      "uiCommand",
      (({ command, payload }: { command: string; payload: unknown }) => {
        const action = asUiAction(command, payload);
        if (!action) return opts.onSiteCommand?.(command, payload);
        if (action.command === "stage_cue") {
          if (opts.onCue) opts.onCue(action.payload);
          else tl?.add(action.payload);
        } else {
          opts.onMove(action.payload);
        }
      }),
    ],
    [
      "botOutput",
      ((d: Spoken) => {
        outputSeen = true;
        if (!d?.text || d.spoken === false || d.will_be_spoken === false || d.output_type === "backchannel") return;
        heard(d.text);
      }),
    ],
    [
      "botTtsText",
      ((d: Spoken) => {
        if (outputSeen || !d?.text) return;
        heard(d.text);
      }),
    ],
    [
      "botStartedSpeaking",
      (() => {
        tl?.speaking();
        opts.onBotStarted?.();
      }),
    ],
    [
      "botStoppedSpeaking",
      (() => {
        tl?.stopped();
        opts.onBotStopped?.();
      }),
    ],
    [
      "userStartedSpeaking",
      (() => {
        const dropped = tl?.interrupted() ?? [];
        for (const cue of dropped) send(interruptedResult(cue));
        opts.onUserStarted?.(dropped);
      }),
    ],
  ];
  for (const [name, fn] of handlers) client.on(name, fn);

  return {
    send,
    hello() {
      send({ runtime: STAGE_RUNTIME, contract: STAGE_CONTRACT, url: location.href, title: document.title });
    },
    detach() {
      for (const [name, fn] of handlers) client.off(name, fn);
    },
  };
}

/** The result for a cue the person talked over before the voice reached it. */
export function interruptedResult(cue: StageCue): StageResult {
  return {
    call_ref: cue.call_ref,
    move: cue.move,
    outcome: "refused",
    detail: "interrupted",
    refused: [{ arg: cue.verb, why: "interrupted" }],
    moved: false,
    ms: 0,
  };
}

/** The result for a cue whose words never came. */
export function staleResult(cue: StageCue): StageResult {
  return {
    call_ref: cue.call_ref,
    move: cue.move,
    outcome: "refused",
    detail: "stale",
    refused: [{ arg: cue.verb, why: "its words were never heard" }],
    moved: false,
    ms: 0,
  };
}
