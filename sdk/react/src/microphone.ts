/**
 * Getting the microphone, and saying so when we can't.
 *
 * A voice agent with no microphone is not a degraded call, it is a broken one:
 * the agent greets, the caller answers, and nothing they say ever leaves the
 * page. So this module refuses to fail quietly. Every way of not getting a
 * microphone becomes a typed {@link MicrophoneError} whose message tells the
 * person in front of the browser what to actually do about it — the causes look
 * identical from the outside ("it didn't work") and have completely different
 * fixes.
 *
 * The two that used to be invisible:
 *
 * - **A permission prompt nobody answered never settles.** `getUserMedia`
 *   returns a promise that stays pending for as long as the dialog is open, so
 *   a caller who missed it (a background tab, a prompt behind another window)
 *   hung on "Connecting…" with nothing on screen suggesting the browser was
 *   waiting on them. Hence both a heads-up callback and a hard deadline.
 * - **An insecure origin has no `navigator.mediaDevices` at all.** Serve the
 *   page over plain `http://` on anything but localhost and the property is
 *   simply `undefined`, which read as "microphone failed" rather than "this
 *   page can never have a microphone".
 */

/** What stopped us getting a microphone. */
export type MicrophoneProblem =
  /** The browser refused: denied, or the prompt was dismissed. */
  | "denied"
  /** The prompt was never answered inside the deadline. */
  | "no-response"
  /** No audio input device exists. */
  | "no-microphone"
  /** A device exists but something else holds it. */
  | "in-use"
  /** The page is not a secure context, so microphones are unavailable. */
  | "insecure-context"
  /** Anything else. */
  | "unknown";

/** A microphone we could not get, and what to do about it. */
export class MicrophoneError extends Error {
  readonly name = "MicrophoneError";
  /** Which failure this is — branch on this, not on the message. */
  readonly problem: MicrophoneProblem;

  constructor(problem: MicrophoneProblem, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.problem = problem;
  }
}

/**
 * How long a permission prompt may go unanswered before we give up.
 *
 * Generous on purpose — this is a human finding and clicking a dialog, which
 * can mean hunting for a window that opened behind the page. The point of the
 * bound is not to be strict, it is that "forever" is not a state anyone can
 * report, retry, or explain.
 */
export const MIC_PROMPT_TIMEOUT_MS = 30_000;

/**
 * How long to wait before telling the UI we are still waiting on the prompt.
 *
 * Long enough that a granted-by-policy or already-allowed microphone (which
 * resolves in a few milliseconds) never flashes a message about permission,
 * short enough that someone staring at a stalled connection learns why.
 */
export const MIC_PROMPT_HINT_MS = 700;

const MESSAGES: Record<MicrophoneProblem, string> = {
  denied:
    "Microphone access was blocked. Allow it for this site — the icon at the " +
    "right of the address bar — and try again.",
  "no-response":
    "The microphone permission prompt wasn't answered. It may be behind " +
    "another window; allow access and try again.",
  "no-microphone": "No microphone was found. Connect one and try again.",
  "in-use":
    "The microphone is being used by another application. Close it and try again.",
  "insecure-context":
    "This page can't use a microphone because it isn't served over HTTPS. " +
    "Use https:// (or localhost during development).",
  unknown: "The microphone could not be started.",
};

/** Map a `getUserMedia` rejection onto a {@link MicrophoneProblem}. */
function classify(err: unknown): MicrophoneProblem {
  const name = (err as { name?: string } | null)?.name;
  switch (name) {
    // Both a denial and a dismissed prompt arrive as NotAllowedError, and no
    // browser distinguishes them — so neither do we, rather than guessing in
    // the message.
    case "NotAllowedError":
    case "SecurityError":
      return "denied";
    case "NotFoundError":
    case "OverconstrainedError":
      return "no-microphone";
    case "NotReadableError":
    case "AbortError":
      return "in-use";
    default:
      return "unknown";
  }
}

/**
 * Request the microphone, or explain why not.
 *
 * Never rejects with a raw DOM exception — the result is always either a
 * `MediaStream` or a {@link MicrophoneError}, because every caller of this has
 * to render the reason and none of them should be pattern-matching on browser
 * error names.
 */
export async function requestMicrophone(options: {
  /** Called once if the prompt is still open after {@link MIC_PROMPT_HINT_MS}. */
  onWaiting?: () => void;
  /** Override the deadline. Testing seam; production uses the default. */
  timeoutMs?: number;
}): Promise<MediaStream | MicrophoneError> {
  const timeoutMs = options.timeoutMs ?? MIC_PROMPT_TIMEOUT_MS;

  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return new MicrophoneError("insecure-context", MESSAGES["insecure-context"]);
  }

  let settled = false;
  const request = navigator.mediaDevices.getUserMedia({ audio: true, video: false });

  const hint = setTimeout(() => {
    if (!settled) options.onWaiting?.();
  }, MIC_PROMPT_HINT_MS);

  try {
    const stream = await Promise.race([
      request,
      new Promise<null>((resolve) => setTimeout(() => resolve(null), timeoutMs)),
    ]);

    if (stream) return stream;

    // Timed out. The prompt is still open, so the request may yet be granted —
    // release whatever it hands us, or the browser keeps showing a recording
    // indicator for a call that has already been abandoned.
    void request
      .then((late) => {
        late.getTracks().forEach((t) => t.stop());
      })
      .catch(() => {
        /* the prompt was denied after we stopped waiting */
      });
    return new MicrophoneError("no-response", MESSAGES["no-response"]);
  } catch (err) {
    const problem = classify(err);
    return new MicrophoneError(problem, MESSAGES[problem], { cause: err });
  } finally {
    settled = true;
    clearTimeout(hint);
  }
}
