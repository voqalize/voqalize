/**
 * Shared chrome for the demo gallery — currently one thing, and it is the one
 * thing that must not differ between demos.
 *
 * Every demo on voqalize.com opens a real microphone and records the call. That
 * makes us the controller for those recordings, not a processor acting for a
 * customer, so the notice a visitor sees is *ours* to get right — and eleven
 * separately-worded notices is eleven chances to get it wrong, plus a guarantee
 * that fixing one leaves the other ten stale. So the wording lives here, once,
 * and the demos supply only what genuinely differs: what the demo is and what to
 * do with it.
 *
 * The mechanism ({@link PreCallGate}) ships in the public SDK and is deliberately
 * copy-free, because a customer's disclosure obligations are theirs, not ours to
 * pre-write. This package is the other half: our own copy, for our own gallery.
 *
 * If you change {@link CONSENT} or {@link RETENTION_DAYS}, change
 * `frontend/apps/marketing/src/pages/privacy.astro` in the private repo in the
 * same window, and change the bucket lifecycle rule that actually enforces it.
 * The three are one claim, and a number that appears in only two of them is a
 * finding waiting to be written up.
 */

import { PreCallGate } from "@voqalize/client-react";
import type { ReactNode } from "react";

/**
 * How long a demo recording lives. Enforced by a GCS lifecycle rule on the
 * recordings bucket — not by this constant, which only describes it.
 */
export const RETENTION_DAYS = 30;

/** Where the notice lives. Root-relative: the demos are served from the same
 *  origin as the marketing site, so this resolves per environment. */
export const PRIVACY_HREF = "/privacy";

/** The consent line. One sentence, and every clause in it is load-bearing. */
export const CONSENT: ReactNode = (
  <>
    I understand this is a demo, that the call is recorded and deleted after{" "}
    {RETENTION_DAYS} days, and I agree to the{" "}
    <a href={PRIVACY_HREF} target="_blank" rel="noopener noreferrer">
      privacy notice
    </a>
    .
  </>
);

/** Shown under the button on every demo. */
export const FOOTNOTE: ReactNode =
  "Your browser will ask for microphone access. Please don't tell a demo anything personal or confidential.";

export interface DemoGateProps {
  /** Whether the gate is covering the demo. */
  open: boolean;
  /** The demo's name, as it appears in the gallery. */
  title: ReactNode;
  /**
   * One sentence: what this demo is, and what the visitor should do. Per demo,
   * because it is the only part that legitimately differs.
   */
  blurb: ReactNode;
  /**
   * What "join" means here. In the demos that put you straight into a call this
   * connects; in the ones that open on a scenario picker or a form it just
   * uncovers the demo, and the microphone opens later in their own flow.
   */
  onJoin: () => void | Promise<void>;
  /** Button text. Default `"Join call"` — override where joining isn't calling. */
  joinLabel?: string;
  /** Pass `connectionState === "connecting"` where the gate connects directly. */
  busy?: boolean;
  /** Pass `session.error` so a failed connect stays visible in the gate. */
  error?: string | null;
  /** Tint, to sit inside the host demo's palette rather than on top of it. */
  accent?: string;
  /** Panel treatment. Default `"dark"`. */
  theme?: "light" | "dark";
  /** Anything the demo needs chosen before the call — a language, a scenario. */
  children?: ReactNode;
}

/**
 * The notice a visitor sees before any demo opens a microphone.
 *
 * @example
 * ```tsx
 * const [joined, setJoined] = useState(false);
 * <DemoGate
 *   open={!joined}
 *   title="Travel Desk"
 *   blurb="Plan a trip out loud and watch the itinerary build itself on screen."
 *   busy={connectionState === "connecting"}
 *   error={error}
 *   onJoin={async () => { await connect(); setJoined(true); }}
 * />
 * ```
 */
export function DemoGate({
  open,
  title,
  blurb,
  onJoin,
  joinLabel = "Join call",
  busy,
  error,
  accent,
  theme = "dark",
  children,
}: DemoGateProps) {
  return (
    <PreCallGate
      open={open}
      title={title}
      blurb={blurb}
      consent={CONSENT}
      footnote={FOOTNOTE}
      joinLabel={joinLabel}
      busy={busy}
      error={error}
      accent={accent}
      theme={theme}
      onJoin={onJoin}
    >
      {children}
    </PreCallGate>
  );
}
