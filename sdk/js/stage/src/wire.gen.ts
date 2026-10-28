// Generated from voqalize.sdk.stage.wire by `voqalize types`. Do not edit — regenerate with:
//   voqalize types voqalize.sdk.stage.wire -o ../sdk/js/stage/src/wire.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * A move written inside the agent's reply, to make when the voice reaches it.
 *
 * `at` is the spoken text that follows the cue, as written, up to a few
 * dozen characters: the page compares it with the words it hears, after
 * segmenting both the same way, in whatever language the call is in. `at`
 * is empty for a cue at the very end of a reply, which fires when the voice
 * stops. `before` counts the characters of the reply said before the cue,
 * for a page that has to time cues by the clock.
 */
export interface StageCue {
  call_ref: string;

  move: string;

  verb: string;

  args: string[];

  at: string;

  before: number;

  unit: number;
}

/**
 * A move made because a tool was called: the page makes it now, or, with
 * `when="quiet"`, once the voice has finished what it is saying.
 */
export interface StageMove {
  call_ref: string;

  move: string;

  args: Record<string, string | number | boolean | string[] | null>;

  when: 'now' | 'quiet';
}

/** What happened to one move: sent exactly once per `call_ref`. */
export interface StageResult {
  call_ref: string;

  move: string;

  outcome: 'applied' | 'partial' | 'refused' | 'failed' | 'undone' | 'unknown';

  detail?: string | null;

  refused?: Refusal[];

  moved?: boolean;

  ms?: number;
}

/** A page running Stage, saying what it is — on connect and on every load. */
export interface StageHello {
  runtime: string;

  contract: number;

  url?: string;

  title?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

/** One argument the page could not use, and what it offers instead. */
export interface Refusal {
  arg: string;

  why: string;

  options?: string[];
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'stage_cue'; payload: StageCue }
  | { command: 'stage_move'; payload: StageMove };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'stage_cue',
  'stage_move',
];

const _known = new Set<string>(UI_ACTION_COMMANDS);

/**
 * Narrow a `ui-command` off the wire. Returns null for a command this file
 * does not declare — a page and a brain ship separately, and an older page
 * receiving a newer action should ignore it, not throw.
 */
export function asUiAction(command: string, payload: unknown): UiAction | null {
  return _known.has(command) ? ({ command, payload } as UiAction) : null;
}

/**
 * Call this in a `switch`'s default arm. Adding an action then fails to
 * compile here until the new case is handled — which is the whole point of
 * generating this file.
 */
export function unhandledUiAction(action: never): never {
  throw new Error(`Unhandled action: ${JSON.stringify(action)}`);
}

/** Everything the person can do on screen, discriminated by `event`. */
export type AppEvent =
  | { event: 'stage_result'; payload: StageResult }
  | { event: 'stage_hello'; payload: StageHello };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'stage_result',
  'stage_hello',
];

/**
 * Send one thing the person did. `send` is a pipecat client's `sendUIEvent`,
 * or null before the call connects — a gesture made off-call is dropped,
 * which is right: there is no brain that missed it.
 *
 * The name picks the payload type, so a field renamed in Python stops
 * compiling here rather than arriving as a shape the brain discards.
 */
export function sendAppEvent(
  send: ((event: string, payload?: unknown) => void) | null | undefined,
  event: AppEvent,
): void {
  send?.(event.event, event.payload);
}
