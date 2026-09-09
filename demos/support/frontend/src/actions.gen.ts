// Generated from support/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types support/backend/brain.py -o support/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

export type OpenOrders = Record<string, never>;

export interface OpenOrder {
  order_id: string;
}

export interface HighlightItem {
  order_id: string;

  item_id: string;
}

export interface StartDiagnostics {
  order_id: string;

  item_id: string;

  steps: string[];
}

export interface RecordDiagnostic {
  step: number;

  summary: string;

  result: 'ok' | 'issue';
}

export interface CompleteDiagnostics {
  resolved: boolean;

  reason: string;
}

export interface StartReturn {
  order_id: string;

  item_id: string;

  reason: string;
}

export type RequestPhoto = Record<string, never>;

export interface SetPhotoCheck {
  matches: boolean;

  box_present: boolean;

  passed: boolean;

  note: string;
}

export interface FillReturnForm {
  reason: string;

  condition: string;

  refund_method: 'original_payment' | 'store_credit';

  notes: string;
}

/** The shopper photographed the item they are returning. */
export interface PhotoUploaded {
  item_id?: string;

  /** A data: URL — the captured frame, base64 in its tail. */
  image?: string;
}

/** The shopper tapped submit, and the browser minted the confirmation number. */
export interface ReturnSubmitted {
  order_id?: string;

  item_id?: string;

  rma?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_orders'; payload: OpenOrders }
  | { command: 'open_order'; payload: OpenOrder }
  | { command: 'highlight_item'; payload: HighlightItem }
  | { command: 'start_diagnostics'; payload: StartDiagnostics }
  | { command: 'record_diagnostic'; payload: RecordDiagnostic }
  | { command: 'complete_diagnostics'; payload: CompleteDiagnostics }
  | { command: 'start_return'; payload: StartReturn }
  | { command: 'request_photo'; payload: RequestPhoto }
  | { command: 'set_photo_check'; payload: SetPhotoCheck }
  | { command: 'fill_return_form'; payload: FillReturnForm };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_orders',
  'open_order',
  'highlight_item',
  'start_diagnostics',
  'record_diagnostic',
  'complete_diagnostics',
  'start_return',
  'request_photo',
  'set_photo_check',
  'fill_return_form',
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
  | { event: 'photo_uploaded'; payload: PhotoUploaded }
  | { event: 'return_submitted'; payload: ReturnSubmitted };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'photo_uploaded',
  'return_submitted',
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
