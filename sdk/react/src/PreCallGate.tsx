/**
 * PreCallGate — the screen a person sees before a microphone ever opens.
 *
 * A voice agent is the one embed that starts taking input the moment it loads.
 * Everything else on a page waits to be clicked; a call does not, and a person
 * who did not expect one has already been recorded by the time they work out
 * what happened. This component makes that impossible: it covers the app until
 * someone has read one sentence about what they are joining, ticked a box, and
 * pressed a button.
 *
 * It is deliberately opinionated about *structure* and deliberately silent about
 * *wording*. The three slots — `blurb`, `consent`, `joinLabel` — are all caller
 * supplied, because what has to be disclosed depends on who is disclosing it and
 * under which law. Voqalize is a processor for the calls its customers run: they
 * decide whether to record and they own the consent, so an SDK that shipped
 * default consent copy would be writing a legal position on their behalf. This
 * one ships the mechanism and none of the language.
 *
 * Two things it does enforce, because they are the whole point:
 *   - `onJoin` cannot fire until the consent box is ticked, and
 *   - nothing behind the gate is reachable while it is open (`inert` on the app
 *     is the caller's job; the overlay covers and traps focus).
 *
 * Self-contained like {@link AmbientPresence}: no CSS import, no dependencies
 * beyond React, styled through CSS custom properties so it can be tinted to any
 * host app in one prop.
 *
 * @example
 * ```tsx
 * const [joined, setJoined] = useState(false);
 * const { connect, connectionState } = useVoqalSession({ ...cfg });
 *
 * <PreCallGate
 *   open={!joined}
 *   title="Travel Desk"
 *   blurb="Talk to a trip planner and watch it build the itinerary on screen as you speak."
 *   consent={<>I understand this call is recorded. <a href="/privacy">Privacy</a></>}
 *   busy={connectionState === "connecting"}
 *   onJoin={async () => { await connect(); setJoined(true); }}
 * />
 * ```
 */

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface PreCallGateProps {
  /** Whether the gate covers the app. Render it always and drive this. */
  open: boolean;
  /** Agent or demo name, shown as the heading. */
  title: ReactNode;
  /**
   * One sentence on what this is and what to do — the thing a person needs in
   * order to decide. Keep it to a sentence; nobody reads a modal.
   */
  blurb: ReactNode;
  /**
   * The consent line, rendered beside the checkbox. Supply the whole thing,
   * including any link to your privacy notice. The SDK writes none of this.
   */
  consent: ReactNode;
  /** Button text. Default `"Join call"`. */
  joinLabel?: string;
  /**
   * Called when the button is pressed with consent ticked. May be async — the
   * button shows {@link busyLabel} until it settles, and a rejection is surfaced
   * in place rather than thrown away.
   */
  onJoin: () => void | Promise<void>;
  /**
   * Externally-driven busy state (e.g. `connectionState === "connecting"`).
   * OR-ed with the gate's own pending state, so either source disables the
   * button.
   */
  busy?: boolean;
  /** Button text while connecting. Default `"Connecting…"`. */
  busyLabel?: string;
  /** Error to show in the gate — pass `session.error` to keep a failure visible. */
  error?: string | null;
  /**
   * A short line under the button: mic requirement, "works best with
   * headphones", browser support. Optional, and optional for a reason — every
   * extra line costs you a reader.
   */
  footnote?: ReactNode;
  /**
   * Allow dismissing without joining (Escape / the backdrop / a close button).
   * Default `false`: this is a gate, not a popup. Turning it on gives you an
   * `onDismiss` and a way past the notice, so only do it where the page is
   * genuinely usable without the call.
   */
  dismissible?: boolean;
  /** Called when a dismissible gate is dismissed. */
  onDismiss?: () => void;
  /** Text for the dismiss affordance. Default `"Not now"`. */
  dismissLabel?: string;
  /** Accent colour for the button, checkbox and links. Default Voqalize teal. */
  accent?: string;
  /** Panel treatment. Default `"dark"`. */
  theme?: "light" | "dark";
  /** Stacking order. Default `1000` — above `AmbientPresence`'s ring (90). */
  zIndex?: number;
  /**
   * Extra content between the blurb and the consent row — a language picker, a
   * scenario chooser, a "call from" field. Anything a demo needs collected
   * before the call rather than during it.
   */
  children?: ReactNode;
}

const TEAL = "#10C5B4";

const INK = "#06121A";

/** `#abc` / `#aabbcc` → `[r,g,b]` in 0–255, or null if it isn't a plain hex. */
function parseHex(value: string): [number, number, number] | null {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(value.trim())?.[1];
  if (!hex) return null;
  const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) as [number, number, number];
}

/** WCAG relative luminance. */
function luminance([r, g, b]: [number, number, number]): number {
  const f = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
const toHex = ([r, g, b]: [number, number, number]) =>
  "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

/**
 * Resolve the join button's two colours — the fill and the label on it.
 *
 * Neither can be a constant. `accent` is whatever palette the host hands us, and
 * across our own gallery alone that spans a pale gold to a near-black maroon: a
 * fixed dark label reads 7:1 on the gold and 2.6:1 on the maroon. So pick the
 * label from the accent's own luminance — dark above the crossover at ~0.191,
 * light below it.
 *
 * That still leaves a band around the crossover where *neither* label reaches
 * AA's 4.5:1, because a mid-luminance fill simply cannot carry black or white
 * text. One of our own accents sits in it. So when the better label still falls
 * short, deepen (or lift) the fill in small steps until it clears. The button
 * then drifts a shade off the host's ring, which is the right trade: a slightly
 * darker purple is a design detail, an unreadable button is a defect.
 *
 * Accents we can't measure — a CSS variable, `color-mix()`, a named colour —
 * pass through untouched with the documented dark label rather than a guess.
 */
function resolveAccent(accent: string): { fill: string; label: string } {
  const rgb = parseHex(accent);
  if (!rgb) return { fill: accent, label: INK };

  const inkL = luminance(parseHex(INK)!);
  const pick = (l: number) =>
    contrast(l, inkL) >= contrast(l, 1) ? { label: INK, ratio: contrast(l, inkL) } : { label: "#FFFFFF", ratio: contrast(l, 1) };

  let current = rgb;
  let best = pick(luminance(current));
  // Eight 6% steps is enough to cross the band from either side without ever
  // walking a colour far enough to stop reading as the host's own.
  for (let step = 0; step < 8 && best.ratio < 4.5; step++) {
    const toward = best.label === INK ? 255 : 0;
    current = current.map((v) => v + (toward - v) * 0.06) as [number, number, number];
    best = pick(luminance(current));
  }
  return { fill: toHex(current), label: best.label };
}

/**
 * The accent as a colour that can be *read* on the panel — the privacy link, and
 * the focus ring that has to be visible to a keyboard user.
 *
 * The raw accent usually can't be. A brand colour is chosen to sit on that
 * brand's own page, and most of them are mid-to-dark; dropped onto this panel
 * they land between 2.3:1 and 3.7:1. That is survivable for a decorative rule
 * and not survivable for the privacy link, which is the one thing in a consent
 * notice a person has to be able to find. So lift it toward the panel's light
 * end (or push it toward the dark end on a light panel) until it clears.
 *
 * The result stays recognisably the host's hue — this brightens a colour, it
 * does not replace it.
 */
function legibleOn(accent: string, panel: string): string {
  const rgb = parseHex(accent);
  const bg = parseHex(panel);
  if (!rgb || !bg) return accent;

  const bgL = luminance(bg);
  const toward = bgL < 0.5 ? 255 : 0;
  let current = rgb;
  for (let step = 0; step < 14 && contrast(luminance(current), bgL) < 4.5; step++) {
    current = current.map((v) => v + (toward - v) * 0.1) as [number, number, number];
  }
  return toHex(current);
}

export function PreCallGate({
  open,
  title,
  blurb,
  consent,
  joinLabel = "Join call",
  onJoin,
  busy = false,
  busyLabel = "Connecting…",
  error = null,
  footnote,
  dismissible = false,
  onDismiss,
  dismissLabel = "Not now",
  accent = TEAL,
  theme = "dark",
  zIndex = 1000,
  children,
}: PreCallGateProps) {
  const [agreed, setAgreed] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const checkRef = useRef<HTMLInputElement | null>(null);
  const uid = useId();

  const working = busy || pending;
  const shown = error ?? failure;

  // Focus the consent box when the gate opens: the first thing a keyboard user
  // needs is the control that unlocks the button, not the heading above it.
  useEffect(() => {
    if (open) checkRef.current?.focus();
  }, [open]);

  // Keep focus inside the panel, and let Escape out only if this gate is one a
  // person is allowed to walk away from.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && dismissible) {
        onDismiss?.();
        return;
      }
      if (e.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !panel.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, dismissible, onDismiss]);

  if (!open) return null;

  const join = async () => {
    if (!agreed || working) return;
    setFailure(null);
    setPending(true);
    try {
      await onJoin();
    } catch (e) {
      // The gate stays open on failure. A modal that closes onto a dead call is
      // worse than one that says what went wrong.
      setFailure(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const dark = theme === "dark";
  const panel = dark ? "#0F1E3A" : "#FFFFFF";
  const { fill, label } = resolveAccent(accent);

  return (
    <div
      className="vq-gate"
      style={
        {
          zIndex,
          // The raw `accent` is never painted directly: at both places it shows
          // up, something has to stay readable against it, and most brand
          // colours miss AA on one side or the other. Two derivations instead.
          //
          // The fill is the accent adjusted until its label clears 4.5:1, used
          // only where text sits on top of it (the join button, the ticked
          // checkbox).
          "--vq-fill": fill,
          "--vq-on-fill": label,
          // The accent as it can actually be read *on the panel*: the consent
          // link, the hover border, the focus ring. Different background, so a
          // different adjustment — hence two variables rather than one.
          "--vq-link": legibleOn(accent, panel),
          "--vq-panel": panel,
          "--vq-fg": dark ? "#EAF1FD" : "#0E1B33",
          "--vq-soft": dark ? "#A8BDDF" : "#4A5A75",
          "--vq-faint": dark ? "#7E96BE" : "#6B7A91",
          "--vq-line": dark ? "rgba(120,165,240,.18)" : "rgba(14,27,51,.12)",
          "--vq-scrim": dark ? "rgba(6,12,26,.72)" : "rgba(14,27,51,.42)",
        } as React.CSSProperties
      }
      onMouseDown={(e) => {
        if (dismissible && e.target === e.currentTarget) onDismiss?.();
      }}
    >
      <div
        ref={panelRef}
        className="vq-gate-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${uid}-title`}
        aria-describedby={`${uid}-blurb`}
      >
        <h2 id={`${uid}-title`} className="vq-gate-title">
          {title}
        </h2>
        <p id={`${uid}-blurb`} className="vq-gate-blurb">
          {blurb}
        </p>

        {children ? <div className="vq-gate-slot">{children}</div> : null}

        <label className="vq-gate-consent" htmlFor={`${uid}-agree`}>
          <input
            ref={checkRef}
            id={`${uid}-agree`}
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            disabled={working}
          />
          <span>{consent}</span>
        </label>

        {shown ? (
          <p className="vq-gate-error" role="alert">
            {shown}
          </p>
        ) : null}

        <div className="vq-gate-actions">
          <button
            type="button"
            className="vq-gate-join"
            onClick={() => void join()}
            disabled={!agreed || working}
          >
            {working ? busyLabel : joinLabel}
          </button>
          {dismissible ? (
            <button type="button" className="vq-gate-skip" onClick={() => onDismiss?.()}>
              {dismissLabel}
            </button>
          ) : null}
        </div>

        {footnote ? <p className="vq-gate-foot">{footnote}</p> : null}
      </div>

      <style>{`
        .vq-gate {
          position: fixed;
          inset: 0;
          display: grid;
          place-items: center;
          padding: 24px;
          background: var(--vq-scrim);
          backdrop-filter: blur(6px);
          -webkit-backdrop-filter: blur(6px);
          animation: vq-gate-in .18s ease-out;
        }
        .vq-gate-panel {
          width: min(480px, 100%);
          box-sizing: border-box;
          background: var(--vq-panel);
          color: var(--vq-fg);
          border: 1px solid var(--vq-line);
          border-radius: 18px;
          padding: 28px 28px 24px;
          box-shadow: 0 24px 64px rgba(6,12,26,.42);
          font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
          animation: vq-gate-rise .22s cubic-bezier(.2,.7,.3,1);
        }
        .vq-gate-title {
          margin: 0;
          font-size: 21px;
          font-weight: 750;
          letter-spacing: -.02em;
          line-height: 1.2;
        }
        .vq-gate-blurb {
          margin: 10px 0 0;
          font-size: 14.5px;
          line-height: 1.6;
          color: var(--vq-soft);
        }
        .vq-gate-slot { margin-top: 18px; }
        .vq-gate-consent {
          display: flex;
          gap: 11px;
          align-items: flex-start;
          margin-top: 22px;
          padding: 13px 14px;
          border: 1px solid var(--vq-line);
          border-radius: 11px;
          font-size: 13px;
          line-height: 1.55;
          color: var(--vq-soft);
          cursor: pointer;
        }
        .vq-gate-consent:hover { border-color: var(--vq-link); }
        .vq-gate-consent input {
          appearance: none;
          -webkit-appearance: none;
          flex: none;
          width: 17px;
          height: 17px;
          margin: 1px 0 0;
          border: 1.5px solid var(--vq-faint);
          border-radius: 5px;
          cursor: pointer;
          position: relative;
        }
        .vq-gate-consent input:checked {
          background: var(--vq-fill);
          border-color: var(--vq-fill);
        }
        .vq-gate-consent input:checked::after {
          content: "";
          position: absolute;
          left: 5px;
          top: 1.5px;
          width: 4px;
          height: 8px;
          border: solid var(--vq-on-fill);
          border-width: 0 2px 2px 0;
          transform: rotate(45deg);
        }
        .vq-gate-consent input:focus-visible {
          outline: 2px solid var(--vq-link);
          outline-offset: 2px;
        }
        .vq-gate-consent a { color: var(--vq-link); }
        .vq-gate-error {
          margin: 14px 0 0;
          font-size: 13px;
          line-height: 1.5;
          color: #FF8A8A;
        }
        .vq-gate-actions {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-top: 20px;
        }
        .vq-gate-join {
          flex: 1;
          border: none;
          border-radius: 11px;
          padding: 13px 18px;
          background: var(--vq-fill);
          color: var(--vq-on-fill);
          font: 650 15px system-ui, -apple-system, sans-serif;
          letter-spacing: -.01em;
          cursor: pointer;
          transition: opacity .15s ease, transform .15s ease;
        }
        .vq-gate-join:hover:not(:disabled) { transform: translateY(-1px); }
        .vq-gate-join:disabled { opacity: .38; cursor: not-allowed; }
        .vq-gate-skip {
          border: none;
          background: none;
          color: var(--vq-faint);
          font: 500 13.5px system-ui, -apple-system, sans-serif;
          cursor: pointer;
          padding: 8px 4px;
        }
        .vq-gate-skip:hover { color: var(--vq-fg); }
        .vq-gate-foot {
          margin: 14px 0 0;
          font-size: 12px;
          line-height: 1.5;
          color: var(--vq-faint);
        }
        @keyframes vq-gate-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes vq-gate-rise {
          from { opacity: 0; transform: translateY(8px) scale(.985) }
          to   { opacity: 1; transform: none }
        }
        @media (prefers-reduced-motion: reduce) {
          .vq-gate, .vq-gate-panel { animation: none }
          .vq-gate-join:hover:not(:disabled) { transform: none }
        }
      `}</style>
    </div>
  );
}
