// Generated from avatar/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types avatar/backend/brain.py -o avatar/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

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
 * Swap the mounted avatar. `voice` rides along so the page can say which
 * voice went with it — it does not select one; the brain already did.
 */
export interface SwitchAvatar {
  key: string;

  name: string;

  renderer: string;

  voice: string;
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

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'switch_avatar'; payload: SwitchAvatar }
  | { command: 'working_on'; payload: WorkingOn }
  | { command: 'show_end_card'; payload: ShowEndCard };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'show_section',
  'switch_avatar',
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
