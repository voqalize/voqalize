/**
 * Instant start: connect while the browser is still asking for the mic.
 *
 * `VoqalizeMediaManager` (from `@voqalize/client-transport`) acquires the mic
 * inside `initialize()` and `connect()`, and the transport awaits both before
 * it opens the peer connection — so a call waits for the visitor to answer
 * the browser's prompt, which on a first visit always appears and can sit
 * for seconds.
 *
 * This subclass changes only that: in instant mode it starts the acquisition
 * and returns without waiting for it. Nothing else needs to change, because
 * the pieces were already there:
 *
 * - the transport adds its audio transceiver as sendrecv before any track
 *   exists, so the offer already carries a two-way audio channel;
 * - `createVoqalizeTransport()` wires the manager's track changes to
 *   `sender.replaceTrack()` on that transceiver.
 *
 * So the call connects with no track, the greeting plays, and the mic track
 * goes onto the existing sender the moment the browser grants it, with no
 * renegotiation. A refusal arrives through the manager's `onDeviceError` as it
 * always did.
 *
 * Implemented here rather than in `@voqalize/client-transport` on purpose:
 * that library's contract is pipecat's `MediaManager`, whose `connect()`
 * means "media is ready", and changing what it means for every consumer is a
 * release of its own.
 */

import { VoqalizeMediaManager } from "@voqalize/client-transport";

/**
 * The manager's construction-time options. Its public constructor declares
 * none — they are internal to that package — but they exist at run time and
 * the tests inject a fake platform through them. Only the fields this
 * package passes are named.
 */
export interface MediaPlatformOptions {
  mediaDevices?: unknown;
  createAudioContext?: unknown;
  visibility?: unknown;
  gestures?: unknown;
  publishWatchdogMs?: number;
}

const ManagerWithOptions = VoqalizeMediaManager as unknown as new (
  options?: MediaPlatformOptions,
) => VoqalizeMediaManager;

export class InstantStartMediaManager extends ManagerWithOptions {
  /** Whether `initialize()` and `connect()` return before the mic is acquired. */
  instant = false;
  private acquiring: Promise<void> | null = null;

  constructor(options?: MediaPlatformOptions) {
    super(options);
  }

  /** The acquisition in flight, if any: settles once the mic is acquired or refused. */
  get pending(): Promise<void> {
    return this.acquiring ?? Promise.resolve();
  }

  override async initialize(): Promise<void> {
    // The client initialises devices again inside its own connect() while
    // the mic is still being asked for; in instant mode that would queue a
    // second acquisition behind the prompt. The ask in flight answers every call.
    if (this.instant && this.acquiring) return;
    const started = this.track(super.initialize());
    if (!this.instant) return started;
  }

  override async connect(): Promise<void> {
    const started = this.track(super.connect());
    if (!this.instant) return started;
  }

  private track(promise: Promise<void>): Promise<void> {
    const tracked = promise.finally(() => {
      if (this.acquiring === tracked) this.acquiring = null;
    });
    this.acquiring = tracked;
    // In instant mode nobody awaits it; a rejection must not surface as an
    // unhandled one. Errors reach the app through onDeviceError.
    tracked.catch(() => {});
    return tracked;
  }
}

/**
 * Whether this is an iPhone or iPad browser. iPadOS reports itself as a Mac,
 * so a Mac with touch points counts too.
 *
 * Instant start is off on iOS unless the library flag says otherwise:
 * starting capture switches iOS's audio session to play-and-record, which can
 * change the agent's volume or route mid-greeting, and that needs a test on
 * real iPhones first.
 */
export function isIOS(nav: Pick<Navigator, "userAgent" | "maxTouchPoints"> | undefined = globalThis.navigator): boolean {
  if (!nav) return false;
  const ua = nav.userAgent ?? "";
  if (/iPhone|iPad|iPod/u.test(ua)) return true;
  return /Macintosh/u.test(ua) && (nav.maxTouchPoints ?? 0) > 1;
}
