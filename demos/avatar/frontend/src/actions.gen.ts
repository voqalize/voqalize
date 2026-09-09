// Generated from avatar/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types avatar/backend/brain.py -o avatar/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Scroll the documentation to one section and mark it current.
 *
 * Only the id and the heading travel, and that is the inversion from the
 * earlier slide deck: the page *is* the documentation now, so it already holds
 * every word. Sending prose over the wire would give a visitor two versions of
 * the same paragraph and leave the page unreadable on its own — which is the
 * one thing a page linked from a README cannot be.
 */
export interface ShowSection {
  id: string;

  title: string;
}

/**
 * Paint the working strip. Fired beside the `WORKING` claim, so the face
 * and the page say the same thing about the same seconds.
 */
export interface WorkingOn {
  topic: string;
}

/**
 * The call is over and here is where to go next. `reason` distinguishes
 * the cap from a goodbye, because the card reads differently.
 */
export interface ShowEndCard {
  reason: string;
}

/** The page's data channel is open, so a server message will now arrive. */
export type Ready = Record<string, never>;

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'working_on'; payload: WorkingOn }
  | { command: 'show_end_card'; payload: ShowEndCard };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'show_section',
  'working_on',
  'show_end_card',
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
  | { event: 'ready'; payload: Ready };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'ready',
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
