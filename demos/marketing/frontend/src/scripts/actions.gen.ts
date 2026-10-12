// Generated from tanvi.brain by `voqalize types`. Do not edit — regenerate with:
//   voqalize types tanvi.brain -o ../src/scripts/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Open one section of the page beside Tanvi. */
export interface OpenSection {
  section: 'shift' | 'action' | 'ways' | 'handled' | 'worlds' | 'cast' | 'pricing';
}

/** Open the section a target belongs to, then switch, open or point at that target. */
export interface Show {
  target: 'shift.scene1' | 'shift.scene2' | 'shift.scene3' | 'shift.scene4' | 'action.step1' | 'action.step2' | 'action.step3' | 'action.step4' | 'ways.plug_and_play' | 'ways.plug_and_play.step1' | 'ways.plug_and_play.step2' | 'ways.plug_and_play.step3' | 'ways.plug_and_play.step4' | 'ways.plug_and_play.step5' | 'ways.developer' | 'ways.developer.step1' | 'ways.developer.step2' | 'ways.developer.step3' | 'ways.developer.step4' | 'worlds.jewelry' | 'worlds.banking' | 'worlds.forms' | 'worlds.contracts' | 'worlds.cab' | 'worlds.food' | 'cast.tanvi' | 'cast.tara' | 'cast.tushar' | 'cast.tanya' | 'cast.tess' | 'cast.trisha' | 'cast.create_yours' | 'pricing.annual' | 'pricing.monthly' | 'pricing.usd' | 'pricing.inr' | 'pricing.free' | 'pricing.starter' | 'pricing.growth' | 'pricing.enterprise' | 'retail.hero' | 'retail.scene1' | 'retail.scene2' | 'retail.scene3' | 'retail.moments' | 'retail.setup' | 'retail.close' | 'banking.hero' | 'banking.scene1' | 'banking.scene2' | 'banking.scene3' | 'banking.line' | 'banking.setup' | 'banking.close' | 'insurance.hero' | 'insurance.scene1' | 'insurance.scene2' | 'insurance.scene3' | 'insurance.handoff' | 'insurance.setup' | 'insurance.close' | 'healthcare.hero' | 'healthcare.scene1' | 'healthcare.scene2' | 'healthcare.scene3' | 'healthcare.routes' | 'healthcare.setup' | 'healthcare.close' | 'legal.hero' | 'legal.scene1' | 'legal.scene2' | 'legal.scene3' | 'legal.handoff' | 'legal.setup' | 'legal.close' | 'support.hero' | 'support.scene1' | 'support.scene2' | 'support.scene3' | 'support.handoff' | 'support.setup' | 'support.close' | 'about.hero' | 'about.beliefs' | 'about.people' | 'about.more' | 'about.close' | 'story.hero' | 'story.ch-1' | 'story.ch-2' | 'story.ch-3' | 'story.ch-4' | 'story.ch-5' | 'story.today' | 'contact.write' | 'contact.press' | 'contact.ways' | 'security.standards' | 'security.call' | 'security.principles' | 'security.report' | 'experience.demo-aura' | 'experience.demo-servicing' | 'experience.demo-orderdesk' | 'experience.demo-legal' | 'experience.demo-sugar' | 'experience.demo-travel' | 'pricing_details.minute' | 'pricing_details.questions';
}

/** Close the open section and bring Tanvi back to the centre. */
export type CloseSection = Record<string, never>;

/** Switch the page between Talk mode and Read mode. */
export interface SetMode {
  mode: 'talk' | 'read';
}

/** Change the page itself: theme, size, a phone-sized view, the motion, or scrolling. */
export interface SiteCommand {
  command: 'dark' | 'light' | 'bigger' | 'smaller' | 'normal_size' | 'mobile' | 'desktop' | 'pause_motion' | 'play_motion' | 'slower' | 'faster' | 'replay' | 'scroll_down' | 'scroll_up' | 'scroll_top';
}

/** Put a link to a page outside this one under Tanvi, for the visitor to open. */
export interface OpenLink {
  link: 'docs' | 'quickstart' | 'mcp' | 'console' | 'book_call';
}

/** Show one of the site's other pages beside Tanvi, in place of a section. */
export interface OpenPage {
  page: 'retail' | 'banking' | 'insurance' | 'healthcare' | 'legal' | 'support' | 'about' | 'story' | 'contact' | 'security' | 'experience' | 'pricing_details';
}

/** End the call once Tanvi has finished her goodbye, and put the page back to its start. */
export type EndConversation = Record<string, never>;

/** What is on the visitor's screen once it settles: device, layout, where they are, what is in view. */
export interface Viewing {
  device: 'phone' | 'tablet' | 'desktop';

  layout: 'centre' | 'beside' | 'tile';

  section?: string | null;

  page?: string | null;

  path?: string | null;

  title?: string | null;

  rows?: string[][];

  focus?: string | null;

  heading?: string | null;

  progress?: number;

  showing?: string[];
}

/** The visitor opened a section themselves (a suggestion, the nav, or a link). */
export interface SectionOpened {
  section: 'shift' | 'action' | 'ways' | 'handled' | 'worlds' | 'cast' | 'pricing';
}

/** The visitor closed the open section and came back to Tanvi. */
export type SectionClosed = Record<string, never>;

/** The visitor switched between Talk and Read mode. */
export interface ModeChanged {
  mode: 'talk' | 'read';
}

/** The visitor clicked a control themselves: a tab, a step, a scene, a switch. */
export interface ControlUsed {
  target: 'shift.scene1' | 'shift.scene2' | 'shift.scene3' | 'shift.scene4' | 'action.step1' | 'action.step2' | 'action.step3' | 'action.step4' | 'ways.plug_and_play' | 'ways.plug_and_play.step1' | 'ways.plug_and_play.step2' | 'ways.plug_and_play.step3' | 'ways.plug_and_play.step4' | 'ways.plug_and_play.step5' | 'ways.developer' | 'ways.developer.step1' | 'ways.developer.step2' | 'ways.developer.step3' | 'ways.developer.step4' | 'worlds.jewelry' | 'worlds.banking' | 'worlds.forms' | 'worlds.contracts' | 'worlds.cab' | 'worlds.food' | 'cast.tanvi' | 'cast.tara' | 'cast.tushar' | 'cast.tanya' | 'cast.tess' | 'cast.trisha' | 'cast.create_yours' | 'pricing.annual' | 'pricing.monthly' | 'pricing.usd' | 'pricing.inr' | 'pricing.free' | 'pricing.starter' | 'pricing.growth' | 'pricing.enterprise' | 'retail.hero' | 'retail.scene1' | 'retail.scene2' | 'retail.scene3' | 'retail.moments' | 'retail.setup' | 'retail.close' | 'banking.hero' | 'banking.scene1' | 'banking.scene2' | 'banking.scene3' | 'banking.line' | 'banking.setup' | 'banking.close' | 'insurance.hero' | 'insurance.scene1' | 'insurance.scene2' | 'insurance.scene3' | 'insurance.handoff' | 'insurance.setup' | 'insurance.close' | 'healthcare.hero' | 'healthcare.scene1' | 'healthcare.scene2' | 'healthcare.scene3' | 'healthcare.routes' | 'healthcare.setup' | 'healthcare.close' | 'legal.hero' | 'legal.scene1' | 'legal.scene2' | 'legal.scene3' | 'legal.handoff' | 'legal.setup' | 'legal.close' | 'support.hero' | 'support.scene1' | 'support.scene2' | 'support.scene3' | 'support.handoff' | 'support.setup' | 'support.close' | 'about.hero' | 'about.beliefs' | 'about.people' | 'about.more' | 'about.close' | 'story.hero' | 'story.ch-1' | 'story.ch-2' | 'story.ch-3' | 'story.ch-4' | 'story.ch-5' | 'story.today' | 'contact.write' | 'contact.press' | 'contact.ways' | 'security.standards' | 'security.call' | 'security.principles' | 'security.report' | 'experience.demo-aura' | 'experience.demo-servicing' | 'experience.demo-orderdesk' | 'experience.demo-legal' | 'experience.demo-sugar' | 'experience.demo-travel' | 'pricing_details.minute' | 'pricing_details.questions';
}

/** The visitor opened one of the site's other pages themselves (a link on a page beside Tanvi). */
export interface PageOpened {
  page: 'retail' | 'banking' | 'insurance' | 'healthcare' | 'legal' | 'support' | 'about' | 'story' | 'contact' | 'security' | 'experience' | 'pricing_details';
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_section'; payload: OpenSection }
  | { command: 'show'; payload: Show }
  | { command: 'close_section'; payload: CloseSection }
  | { command: 'set_mode'; payload: SetMode }
  | { command: 'site_command'; payload: SiteCommand }
  | { command: 'open_link'; payload: OpenLink }
  | { command: 'open_page'; payload: OpenPage }
  | { command: 'end_conversation'; payload: EndConversation };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_section',
  'show',
  'close_section',
  'set_mode',
  'site_command',
  'open_link',
  'open_page',
  'end_conversation',
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
  | { event: 'viewing'; payload: Viewing }
  | { event: 'section_opened'; payload: SectionOpened }
  | { event: 'section_closed'; payload: SectionClosed }
  | { event: 'mode_changed'; payload: ModeChanged }
  | { event: 'control_used'; payload: ControlUsed }
  | { event: 'page_opened'; payload: PageOpened };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'viewing',
  'section_opened',
  'section_closed',
  'mode_changed',
  'control_used',
  'page_opened',
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
