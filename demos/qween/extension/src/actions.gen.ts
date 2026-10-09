// Generated from qween/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types qween/backend/brain.py -o qween/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** The listing, filtered: Qween's facet keys → codes. */
export interface OpenCatalog {
  params: Record<string, string[]>;
}

/** A collection's own editorial page. */
export interface OpenCollection {
  slug: string;

  plp: boolean;
}

/** A piece's page, at one variant. */
export interface OpenProduct {
  slug: string;

  variant_code: string | null;
}

/** Any other page of Qween's, by path. */
export interface OpenPage {
  path: string;
}

/** Click a metal swatch on the open piece: the swatch's own label. */
export interface SelectMetal {
  name: string;
}

/** Scroll to a section of the open piece and ring it, choosing its tab if any. */
export interface ShowSection {
  section: 'product_description' | 'material_specs' | 'customisation' | 'store_locator' | 'concierge' | 'qween_difference' | 'styling_tips' | 'finest_craftsmanship' | 'gifting';

  tab: 'METAL' | 'DIAMOND' | 'GEMSTONE' | null;
}

/** Open one of the open piece's dialogs — or the concierge's, on any page. */
export interface OpenModal {
  modal: 'price_breakup' | 'size_guide' | 'delivery' | 'try_on' | 'gemstone_details' | 'concierge' | 'assurance';

  which: 'natural_stones' | 'igi_certified' | 'stone_value' | 'buyback_exchange' | null;
}

/** Open one of the FAQs on the open piece, by its own title. */
export interface OpenFaq {
  topic: string;
}

/** Switch the open piece's gallery to its 3D view. */
export type View3D = Record<string, never>;

/** Close whichever dialog or 3D view is open. */
export type CloseModal = Record<string, never>;

/** Ring the nth product card on the page, in the order shown. */
export interface HighlightCard {
  index: number;
}

/** A command the agent sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  error: string;
}

/** The open dialog closed. */
export type DialogClosed = Record<string, never>;

/** A dialog opened on Qween's page, whoever opened it, with its own words. */
export interface DialogOpened {
  title?: string | null;

  text?: string;
}

/** The route changed — the shopper's click or the agent's move. */
export interface PageChanged {
  path: string;

  kind: 'home' | 'catalog' | 'category' | 'collection' | 'product' | 'page';

  params?: Record<string, string[]>;

  dialog_open?: boolean;

  slug?: string | null;

  variant_code?: string | null;

  name?: string | null;

  composition?: string | null;

  cards?: Card[];
}

// ── Shapes used by the messages above ──────────────────────────────

/** One product card in a listing, in the order the page shows them. */
export interface Card {
  n: number;

  slug?: string | null;

  text?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_catalog'; payload: OpenCatalog }
  | { command: 'open_collection'; payload: OpenCollection }
  | { command: 'open_product'; payload: OpenProduct }
  | { command: 'open_page'; payload: OpenPage }
  | { command: 'select_metal'; payload: SelectMetal }
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'open_modal'; payload: OpenModal }
  | { command: 'open_faq'; payload: OpenFaq }
  | { command: 'view_3d'; payload: View3D }
  | { command: 'close_modal'; payload: CloseModal }
  | { command: 'highlight_card'; payload: HighlightCard };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_catalog',
  'open_collection',
  'open_product',
  'open_page',
  'select_metal',
  'show_section',
  'open_modal',
  'open_faq',
  'view_3d',
  'close_modal',
  'highlight_card',
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
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'dialog_closed'; payload: DialogClosed }
  | { event: 'dialog_opened'; payload: DialogOpened }
  | { event: 'page_changed'; payload: PageChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_failed',
  'dialog_closed',
  'dialog_opened',
  'page_changed',
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
