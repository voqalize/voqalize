/**
 * The concierge's one entry point, inside the phone: a circle with her face
 * that expands on a tap and folds back by itself.
 *
 * - **Collapsed** (the default, before and during a call): a circle with her
 *   face, the still photo when idle and the live avatar in a call, ringed
 *   subtly while she listens or speaks.
 * - **Expanded** (a tap or click on the circle): before a call, her name, her
 *   job on this tab and Talk; in a call, a larger face with what she is doing
 *   and exactly two buttons, Mute and End. No minimise button: after
 *   `COLLAPSE_MS` with no interaction it folds back to the circle, and a tap
 *   on the face or Escape folds it at once.
 *
 * One element for the app's whole life, so the avatar inside it (passed as
 * `children`) is never re-created; only its box changes. It sits bottom right
 * above the tab bar, moves to another corner when a guest-only or primary
 * button (`data-dock-avoid`) would be under it, and to the top right while a
 * sheet is open (`data-overlay`), so it never covers the tab bar or a sheet's
 * main button. Everything is measured inside `#screen`, which contains it.
 */
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { PERSONA, roleFor } from "../persona";
import type { CallState } from "./fake";
import { LangToggle } from "./LangToggle";
import { avoidRects, bottomBar, raisedCorner, screenBox } from "./useDockMode";

/** How long the expanded widget stays open with nothing touched. */
export const COLLAPSE_MS = 4500;
const MARGIN = 12;

type Anchor = "br" | "bl" | "mr" | "ml" | "tr" | "tl";
const ORDER: Anchor[] = ["br", "bl", "mr", "ml", "tr", "tl"];

const LABEL: Record<CallState, string> = {
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Could not connect",
};

function statusTop(): number {
  return document.querySelector("#screen .status-bar")?.getBoundingClientRect().height ?? 0;
}
function headerBottom(): number {
  const s = screenBox();
  const h = document.querySelector("#screen .page-header")?.getBoundingClientRect();
  return Math.max(statusTop(), h ? h.bottom - s.top : 0);
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}
function boxAt(a: Anchor, w: number, h: number, overHeader: boolean): Box {
  const { width: vw, height: vh } = screenBox();
  const top0 = (overHeader ? statusTop() : headerBottom()) + 8;
  const left = a.endsWith("l") ? MARGIN : vw - w - MARGIN;
  const bottom = vh - bottomBar() - MARGIN - h;
  const top = a[0] === "t" ? top0 : a[0] === "m" ? (vh - h) / 2 : bottom;
  return { left, top: Math.max(top0, top), width: w, height: h };
}
const overlaps = (a: Box, b: DOMRect) => a.left < b.right && a.left + a.width > b.left && a.top < b.bottom && a.top + a.height > b.top;

export function Widget({
  live,
  state,
  muted,
  onMute,
  onEnd,
  onTalk,
  talkDisabled = false,
  talkTitle,
  status,
  children,
}: {
  /** A call is up (or faked from the debug console). */
  live: boolean;
  state: CallState;
  muted: boolean;
  onMute: () => void;
  onEnd: () => void;
  /** Start a call (the expanded widget's action before a call). */
  onTalk?: () => void;
  talkDisabled?: boolean;
  talkTitle?: string;
  /** A line in place of the role (an error, "Getting ready…"). */
  status?: string | null;
  /** The face: the avatar mount, kept for the element's whole life. */
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState<Box | null>(null);
  const [raised, setRaised] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  const role = roleFor(useLocation().pathname);

  // ── Folding back by itself ──
  const arm = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(false), COLLAPSE_MS);
  }, []);
  useEffect(() => {
    if (open) arm();
    else window.clearTimeout(timer.current);
    return () => window.clearTimeout(timer.current);
  }, [open, arm]);
  // An error is shown, not hidden in the circle.
  useEffect(() => {
    if (status && !live) setOpen(true);
  }, [status, live]);

  // ── Where it sits (a poll: a sheet opened by a move, a button scrolled under it, have no event) ──
  const place = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth || 60;
    const h = el.offsetHeight || 60;
    const corner = raisedCorner();
    setRaised(!!corner);
    if (corner) {
      setBox(boxAt(corner, w, h, true));
      return;
    }
    const blockers = avoidRects();
    const pick = ORDER.find((a) => !blockers.some((r) => overlaps(boxAt(a, w, h, false), r))) ?? "br";
    setBox(boxAt(pick, w, h, false));
  }, []);
  useLayoutEffect(() => {
    place();
    const t = window.setInterval(place, 300);
    window.addEventListener("resize", place);
    return () => {
      window.clearInterval(t);
      window.removeEventListener("resize", place);
    };
  }, [place, open, live, status]);

  const shown = muted && state === "listening" ? "muted" : state;
  const faceLabel = open
    ? `Hide the ${live ? "call controls" : "concierge"}`
    : live
      ? `Call with ${PERSONA.name}, ${LABEL[state].toLowerCase()}. Show the call controls`
      : `${PERSONA.name}, ${role}. Show`;

  return (
    <div
      ref={ref}
      className={`bw is-${open ? "open" : "closed"} is-${live ? "live" : "idle"} is-${shown}${raised ? " is-raised" : ""}${box ? "" : " is-parked"}`}
      style={box ? { left: box.left, top: box.top } : undefined}
      role="region"
      aria-label={`${PERSONA.name}, ${role}`}
      data-voqalize
      onPointerDown={open ? arm : undefined}
      onFocus={open ? arm : undefined}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          setOpen(false);
          e.stopPropagation();
        } else if (open) arm();
      }}
    >
      <button type="button" className="bw-face" aria-expanded={open} aria-label={faceLabel} title={faceLabel} onClick={() => setOpen(!open)}>
        <span className="bw-face-img">{children}</span>
        <span className="bw-ring" aria-hidden />
      </button>
      {open ? (
        live ? (
          <div className="bw-panel is-call">
            <p className="bw-name">{PERSONA.name}</p>
            <p className={`bw-state is-${shown}`} aria-live="polite">
              {muted && state === "listening" ? "Microphone off" : LABEL[state]}
            </p>
            <LangToggle />
            <div className="bw-controls">
              <button type="button" className="bw-btn" aria-pressed={muted} aria-label={muted ? "Turn microphone on" : "Turn microphone off"} title={muted ? "Unmute" : "Mute"} onClick={onMute}>
                {muted ? <MicOff size={18} /> : <Mic size={18} />}
                <span>{muted ? "Unmute" : "Mute"}</span>
              </button>
              <button type="button" className="bw-btn bw-end" aria-label="End the call" title="End call" onClick={onEnd}>
                <PhoneOff size={18} />
                <span>End</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="bw-panel is-idle">
            <p className="bw-name">{PERSONA.name}</p>
            <p className="bw-role" aria-live="polite">
              {status ?? role}
            </p>
            <LangToggle />
            <button
              type="button"
              className="bw-talk"
              disabled={talkDisabled}
              title={talkTitle ?? `Talk to ${PERSONA.name}`}
              onClick={() => {
                onTalk?.();
                arm();
              }}
            >
              <Mic size={16} aria-hidden /> Talk to {PERSONA.name}
            </button>
          </div>
        )
      ) : null}
    </div>
  );
}
