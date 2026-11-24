/**
 * The guide's face, as one fixed element that moves between three shapes:
 *
 * - **docked**: sitting exactly on the idle dock's face slot (the still photo),
 *   before and after a call;
 * - **tile**: a floating call card once the call connects (the dock goes away),
 *   with the name tag, what she is doing, the EN / हिंदी toggle and
 *   mute / minimise / end. No transcript is shown;
 * - **mini**: a small bubble at the tile's place, after Minimise.
 *
 * It is one element for the whole page life, so the avatar inside it (the
 * `@voqalize/avatar` mount the caller passes as `children`) is never re-created:
 * popping out, dragging, minimising and going back into the dock only change
 * its box. The tile drags with mouse or touch (pointer events), snaps to the
 * nearest corner or side on release, stays below the header, steps aside for
 * Submit and Continue buttons (`data-dock-avoid`), moves to a top corner clear
 * of an open menu, drawer or sheet (`data-overlay`), and remembers where it was.
 */
import { Maximize2, Mic, MicOff, Minus, PhoneOff } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { create } from "zustand";
import { persona, roleFor } from "../persona";
import { debugMode } from "./debug";
import type { CallState } from "./fake";
import { LanguageToggle } from "./LanguageToggle";
import { avoidRects, isPhone, overlayRects } from "./useDockMode";

export type { CallState };
type Anchor = "tl" | "tr" | "ml" | "mr" | "bl" | "br";
const ANCHORS: Anchor[] = ["tl", "tr", "ml", "mr", "bl", "br"];
const KEY = "chhatri-call-tile";
const MARGIN = 16;

interface Saved {
  anchor: Anchor;
  mini: boolean;
}

function load(): Saved {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<Saved> | null;
    if (s && ANCHORS.includes(s.anchor as Anchor)) return { anchor: s.anchor as Anchor, mini: !!s.mini };
  } catch {
    /* storage unavailable */
  }
  // Bottom right on a wide screen, where the idle pill was: past the right
  // edge of the page's column, under the price breakdown, so it covers no
  // form field (the left one sat over the quote form). Top right on a phone,
  // clear of the Continue and Submit buttons at the bottom of the claim's
  // steps. Either way it steps aside for a primary action (`clearAnchor`).
  return { anchor: isPhone() ? "tr" : "br", mini: false };
}
function save(s: Saved) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: the tile just starts bottom-left next time */
  }
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The tile's size: a small framed portrait over a bar of controls (the
 *  language toggle above mute / minimise / end), smaller on a phone. */
function tileSize(mini: boolean): { width: number; height: number; face: number } {
  if (mini) return { width: 64, height: 64, face: 64 };
  const phone = isPhone();
  const width = phone ? 124 : 160;
  const face = Math.round(width * (phone ? 1 : 1.08));
  return { width, height: face + (phone ? 72 : 76), face };
}

/**
 * The side the agent wants the tile on, so it covers what it is not talking
 * about. `n` counts requests, so asking for the same side again after a drag
 * moves it back.
 */
export const useTileSide = create<{ side: "l" | "r" | null; n: number }>(() => ({ side: null, n: 0 }));
export const preferTileSide = (side: "l" | "r") => useTileSide.setState((s) => ({ side, n: s.n + 1 }));

function headerBottom(): number {
  const h = document.querySelector(".site-header")?.getBoundingClientRect();
  return Math.max(0, h ? h.bottom : 0);
}

function boxAt(anchor: Anchor, size: { width: number; height: number }): Box {
  const top0 = headerBottom() + MARGIN;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const left = anchor.endsWith("l") ? MARGIN : vw - size.width - MARGIN;
  const top =
    anchor[0] === "t" ? top0 : anchor[0] === "m" ? Math.max(top0, (vh - size.height) / 2) : vh - size.height - MARGIN - (isPhone() ? 8 : 12);
  return { left, top: Math.max(top0, top), ...size };
}

/** The dock's in-flight CSS `translate` (its entrance slide), in px. */
function restOffset(dock: HTMLElement | null | undefined): [number, number] {
  const t = dock ? getComputedStyle(dock).translate : "none";
  if (!t || t === "none") return [0, 0];
  const [x = 0, y = 0] = t.split(" ").map((v) => parseFloat(v) || 0);
  return [x, y];
}

const overlaps = (a: Box, b: DOMRect) => a.left < b.right && a.left + a.width > b.left && a.top < b.bottom && a.top + a.height > b.top;

/** The anchor to use: the visitor's, unless it would cover a Submit or Continue button. */
function clearAnchor(want: Anchor, size: { width: number; height: number }): Anchor {
  const blockers = avoidRects();
  const free = (a: Anchor) => !blockers.some((r) => overlaps(boxAt(a, size), r));
  if (free(want)) return want;
  const order: Anchor[] = [want[1] === "r" ? "tr" : "tl", want[1] === "r" ? "mr" : "ml", want[1] === "r" ? "tl" : "tr", "ml", "mr", "bl", "br"];
  return order.find(free) ?? want;
}

/**
 * With a menu, drawer or sheet open (`data-overlay`), the place clear of it:
 * a top corner first (the visitor's side, then the other), else the nearest
 * free place, so neither the overlay nor the agent hides the other. Null when
 * nothing is open.
 */
function overlayAnchor(want: Anchor, size: { width: number; height: number }): Anchor | null {
  const overlays = overlayRects();
  if (!overlays.length) return null;
  const blockers = [...overlays, ...avoidRects()];
  const free = (a: Anchor) => !blockers.some((r) => overlaps(boxAt(a, size), r));
  const h = want[1];
  const o = h === "r" ? "l" : "r";
  const order = [`t${h}`, `t${o}`, `m${h}`, `m${o}`, `b${h}`, `b${o}`] as Anchor[];
  return order.find(free) ?? order.find((a) => !overlays.some((r) => overlaps(boxAt(a, size), r))) ?? `t${o}`;
}

export function CallTile({
  live,
  state,
  muted,
  onMute,
  onEnd,
  children,
}: {
  live: boolean;
  state: CallState;
  muted: boolean;
  onMute: () => void;
  onEnd: () => void;
  /** The face: the avatar mount, kept for the element's whole life. */
  children: ReactNode;
}) {
  const [saved, setSaved] = useState<Saved>(load);
  const [box, setBox] = useState<Box | null>(null);
  const [raised, setRaised] = useState(false);
  const [drag, setDrag] = useState<{ dx: number; dy: number; left: number; top: number } | null>(null);
  const [, setTick] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  // Dev-only handle (?debug=1): the SPA check holds this to one mount for the whole visit.
  const mountId = useRef(Math.random().toString(36).slice(2));
  useEffect(() => {
    if (!debugMode()) return;
    const w = window as unknown as { __chhatriVoice?: Record<string, unknown> };
    w.__chhatriVoice = { ...w.__chhatriVoice, face: mountId.current };
  }, []);
  const mode: "docked" | "tile" | "mini" = !live ? "docked" : saved.mini ? "mini" : "tile";
  const role = roleFor(useLocation().pathname);

  // The agent's side: the same height, the other side. Not saved — the visitor's
  // own drag is what the next visit remembers.
  const side = useTileSide();
  useEffect(() => {
    const want = side.side;
    if (!want) return;
    setSaved((s) => (s.anchor[1] === want ? s : { ...s, anchor: `${s.anchor[0]}${want}` as Anchor }));
  }, [side.n]); // eslint-disable-line react-hooks/exhaustive-deps

  // Where the element sits right now, recomputed on scroll and resize.
  const place = useCallback(() => {
    if (mode === "docked") {
      const slotEl = document.querySelector(".dock-face-slot");
      const slot = slotEl?.getBoundingClientRect();
      const dock = slotEl?.closest<HTMLElement>(".dock");
      const hidden = !!dock?.classList.contains("is-hidden");
      // Where the slot sits once the dock is at rest. The dock slides in
      // (`dock-in`) and the face runs the same slide itself, so measuring
      // mid-slide would count the offset twice: the face sat low on load,
      // then glided up at the next poll.
      const [dx, dy] = restOffset(dock);
      setRaised(false);
      setBox(
        slot && slot.width && !hidden
          ? { left: slot.left - dx, top: slot.top - dy, width: slot.width, height: slot.height }
          : null,
      );
      return;
    }
    const size = tileSize(mode === "mini");
    const aside = overlayAnchor(saved.anchor, size);
    setRaised(!!aside);
    setBox(boxAt(aside ?? clearAnchor(saved.anchor, size), size));
  }, [mode, saved.anchor]);

  useLayoutEffect(() => {
    place();
    let frame = 0;
    const soon = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    window.addEventListener("scroll", soon, { passive: true });
    window.addEventListener("resize", soon);
    // The dock moving, the menu opening, have no scroll event of their own.
    const t = window.setInterval(soon, 300);
    return () => {
      cancelAnimationFrame(frame);
      window.clearInterval(t);
      window.removeEventListener("scroll", soon);
      window.removeEventListener("resize", soon);
    };
  }, [place]);

  // ── Dragging ──
  const onPointerDown = (e: React.PointerEvent) => {
    if (mode === "docked" || !box || (e.target as Element).closest("button")) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDrag({ dx: e.clientX - box.left, dy: e.clientY - box.top, left: box.left, top: box.top });
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag || !box) return;
    const top0 = headerBottom() + 8;
    const left = Math.min(Math.max(8, e.clientX - drag.dx), window.innerWidth - box.width - 8);
    const top = Math.min(Math.max(top0, e.clientY - drag.dy), window.innerHeight - box.height - 8);
    setDrag({ ...drag, left, top });
  };
  const onPointerUp = () => {
    if (!drag || !box) return;
    const cx = drag.left + box.width / 2;
    const cy = drag.top + box.height / 2;
    const size = { width: box.width, height: box.height };
    let best: Anchor = saved.anchor;
    let dist = Number.POSITIVE_INFINITY;
    for (const a of ANCHORS) {
      const b = boxAt(a, size);
      const d = Math.hypot(b.left + b.width / 2 - cx, b.top + b.height / 2 - cy);
      if (d < dist) [best, dist] = [a, d];
    }
    const next = { ...saved, anchor: best };
    setSaved(next);
    save(next);
    setDrag(null);
  };

  const setMini = (mini: boolean) => {
    const next = { ...saved, mini };
    setSaved(next);
    save(next);
    setTick((n) => n + 1);
  };

  // Keyboard: arrows move the tile between corners, for anyone not dragging.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (mode === "docked" || (e.target as Element).closest("button")) return;
    const v = saved.anchor[0];
    const h = saved.anchor[1];
    const map: Record<string, Anchor> = {
      ArrowLeft: `${v}l` as Anchor,
      ArrowRight: `${v}r` as Anchor,
      ArrowUp: `${v === "b" ? "m" : "t"}${h}` as Anchor,
      ArrowDown: `${v === "t" ? "m" : "b"}${h}` as Anchor,
    };
    const next = map[e.key];
    if (!next) return;
    e.preventDefault();
    const s = { ...saved, anchor: next };
    setSaved(s);
    save(s);
  };

  // One element always, so the avatar inside is never re-created; with nowhere
  // to sit (the dock hidden) it is parked out of sight.
  const parked = !box;
  // Leaving the park jumps straight to the slot: easing `left`/`top` from
  // the park would fly the face in from the top-left corner.
  const wasParked = useRef(true);
  const snap = wasParked.current && !parked;
  useLayoutEffect(() => {
    // Commit the jump while transitions are off: a render in the same frame
    // that drops `is-snap` would otherwise ease from the park after all.
    if (snap) void ref.current?.offsetHeight;
    wasParked.current = parked;
  });
  const at = box ?? { left: -200, top: -200, width: 46, height: 46 };
  const pos = drag ? { left: drag.left, top: drag.top } : { left: at.left, top: at.top };
  const face = mode === "tile" ? tileSize(false).face : at.height;
  const shown = muted && state === "listening" ? "muted" : state;
  const LABEL: Record<CallState, string> = {
    connecting: "Connecting…",
    listening: muted ? "Microphone off" : "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    error: "Could not connect",
  };

  return (
    <div
      ref={ref}
      className={`call-tile is-${mode} is-${state}${drag ? " is-dragging" : ""}${parked ? " is-parked" : ""}${snap ? " is-snap" : ""}${raised ? " is-raised" : ""}`}
      style={{ left: pos.left, top: pos.top, width: at.width, height: at.height }}
      role={mode === "docked" ? undefined : "region"}
      aria-label={mode === "docked" ? undefined : `Call with ${persona.name}, ${role}. Drag, or use the arrow keys, to move it.`}
      tabIndex={mode === "docked" ? -1 : 0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onKeyDown}
    >
      <div className="call-face" style={{ height: face }}>
        {children}
        {mode === "tile" ? (
          <>
            <span className="call-tag" title={role}>
              {persona.name}
            </span>
            <span className={`call-state is-${shown}`} aria-live="polite">
              {LABEL[state]}
            </span>
          </>
        ) : null}
        {mode === "mini" ? (
          <button type="button" className="call-expand" aria-label={`Show the call with ${persona.name}`} onClick={() => setMini(false)}>
            <Maximize2 size={14} />
          </button>
        ) : null}
      </div>
      {mode === "tile" ? (
        <div className="call-bar">
          <LanguageToggle />
          <div className="call-controls">
            <button type="button" className="call-btn" aria-pressed={muted} aria-label={muted ? "Turn microphone on" : "Turn microphone off"} title={muted ? "Unmute" : "Mute"} onClick={onMute}>
              {muted ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
            <button type="button" className="call-btn" aria-label="Minimise the call" title="Minimise" onClick={() => setMini(true)}>
              <Minus size={16} />
            </button>
            <button type="button" className="call-btn call-end" aria-label="End the call" title="End call" onClick={onEnd}>
              <PhoneOff size={16} />
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
