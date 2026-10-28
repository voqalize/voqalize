// Generated from explora/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types explora/backend/brain.py -o explora/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * The call's language moved, by the toggle, by voice or by
 * `set_language`: the widget's toggle follows at once, and the tab keeps
 * it for the rest of the call, on every page and both hosts.
 */
export interface LanguageChanged {
  language: 'en' | 'es';

  site: 'follow' | 'stay';
}

/**
 * Send Message was pressed on a complete form: the page is posting it.
 * `by` says who pressed it.
 */
export interface EnquirySent {
  expedition?: string;

  by?: 'javier' | 'visitor';
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/**
 * Every Explora tab the visitor has open, and the one in front: the whole
 * list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

/**
 * How the tab found the page a `navigate` named in the call's language,
 * just before it loaded it: the brain names English paths, and a Spanish
 * call loads each page's Spanish twin. Sent so a page that came up in the
 * wrong language can be traced to why.
 */
export interface TwinLookup {
  path: string;

  language: 'en' | 'es';

  url?: string;

  source?: 'as-is' | 'here' | 'cache' | 'fetch' | 'hub' | 'fallback' | 'timeout';

  ms?: number;

  error?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface TabInfo {
  tab_id: string;

  url?: string;

  title?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'language_changed',
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
  | { event: 'enquiry_sent'; payload: EnquirySent }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'tabs_changed'; payload: TabsChanged }
  | { event: 'twin_lookup'; payload: TwinLookup };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'enquiry_sent',
  'language_requested',
  'tabs_changed',
  'twin_lookup',
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
