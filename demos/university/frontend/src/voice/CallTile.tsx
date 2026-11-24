/**
 * The agent's face, as ONE fixed element for the page's whole life, in three
 * shapes:
 *
 * - **docked**: sitting exactly on the idle dock's face slot, before and after
 *   a call;
 * - **tile**: a floating call card once the call connects (the dock goes
 *   away), with the name tag, what the agent is doing, the language toggle and
 *   mute / minimise / end;
 * - **mini**: a small bubble at the tile's place, after Minimise.
 *
 * Being one element, the avatar inside it (passed as `children`) is never
 * re-created: popping out, dragging, minimising and going back into the dock
 * only change its box. The tile drags with mouse or touch, snaps to the nearest
 * corner or side on release, stays below the top bar, steps aside for primary
 * actions (`data-dock-avoid`), moves to a top corner while a drawer or dialog
 * is open (`raisedCorner`), and remembers where it was.
 */
import { Maximize2, Mic, MicOff, Minus, PhoneOff } from "lucide-react";
import { type ReactNode, useCallback, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { PERSONA, roleFor } from "../data/persona";
import type { CallState } from "./fake";
import { LangToggle } from "./LangToggle";
import { avoidRects, isPhone, raisedCorner } from "./useDockMode";

type Anchor = "tl" | "tr" | "ml" | "mr" | "bl" | "br";
const ANCHORS: Anchor[] = ["tl", "tr", "ml", "mr", "bl", "br"];
const KEY = "varenya-call-tile";
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
  // Bottom right, where the idle dock sat; a primary action under it
  // (`data-dock-avoid`: Continue, Pay, the compare bar) moves it aside.
  return { anchor: "br", mini: false };
}
function save(s: Saved) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: the tile starts bottom right next time */
  }
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The tile's size: a small framed portrait over a bar of controls. */
function tileSize(mini: boolean): { width: number; height: number; face: number } {
  if (mini) return { width: 64, height: 64, face: 64 };
  const phone = isPhone();
  const width = phone ? 128 : 172;
  const face = Math.round(width * (phone ? 0.92 : 1.02));
  return { width, height: face + (phone ? 72 : 78), face };
}

function headerBottom(): number {
  const h = document.querySelector(".site-header")?.getBoundingClientRect();
  return Math.max(0, h ? h.bottom : 0);
}

function boxAt(anchor: Anchor, size: { width: number; height: number }, overHeader = false): Box {
  const top0 = overHeader ? MARGIN : headerBottom() + MARGIN;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const left = anchor.endsWith("l") ? MARGIN : vw - size.width - MARGIN;
  const top = anchor[0] === "t" ? top0 : anchor[0] === "m" ? Math.max(top0, (vh - size.height) / 2) : vh - size.height - MARGIN;
  return { left, top: Math.max(top0, top), ...size };
}

const overlaps = (a: Box, b: DOMRect) => a.left < b.right && a.left + a.width > b.left && a.top < b.bottom && a.top + a.height > b.top;

/** The visitor's anchor, unless it would cover a primary action. */
function clearAnchor(want: Anchor, size: { width: number; height: number }): Anchor {
  const blockers = avoidRects();
  const free = (a: Anchor) => !blockers.some((r) => overlaps(boxAt(a, size), r));
  if (free(want)) return want;
  const h = want[1];
  const o = h === "r" ? "l" : "r";
  const order = [`b${o}`, `m${h}`, `t${h}`, `m${o}`, `t${o}`] as Anchor[];
  return order.find(free) ?? want;
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
  const [raised, setRaised] = useState<"tl" | "tr" | null>(null);
  const [drag, setDrag] = useState<{ dx: number; dy: number; left: number; top: number } | null>(null);
  // On a phone a drawer is the whole screen: while one is open the tile
  // shrinks to the bubble (tap it to open the controls again).
  const [opened, setOpened] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const autoMini = !!raised && isPhone() && !opened;
  const mode: "docked" | "tile" | "mini" = !live ? "docked" : saved.mini || autoMini ? "mini" : "tile";
  const role = roleFor(useLocation().pathname);

  // Where the element sits right now, recomputed on scroll, resize and a poll
  // (an overlay opened by a move, the dock moving, have no event of their own).
  const place = useCallback(() => {
    if (mode === "docked") {
      const slotEl = document.querySelector(".dock-face-slot");
      const slot = slotEl?.getBoundingClientRect();
      const dock = slotEl?.closest<HTMLElement>(".dock");
      const hidden = !!dock?.classList.contains("is-hidden");
      // The idle pill raised over a drawer: the face rides above it too.
      setRaised(dock?.classList.contains("is-raised") ? "tr" : null);
      setBox(slot && slot.width && !hidden ? { left: slot.left, top: slot.top, width: slot.width, height: slot.height } : null);
      return;
    }
    const corner = raisedCorner();
    setRaised(corner);
    if (!corner) setOpened(false);
    const size = tileSize(mode === "mini" || (!!corner && isPhone() && !opened));
    setBox(corner ? boxAt(corner, size, true) : boxAt(clearAnchor(saved.anchor, size), size));
  }, [mode, saved.anchor, opened]);

  useLayoutEffect(() => {
    place();
    let frame = 0;
    const soon = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    window.addEventListener("scroll", soon, { passive: true });
    window.addEventListener("resize", soon);
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
    if (!mini && autoMini) {
      setOpened(true);
      return;
    }
    const next = { ...saved, mini };
    setSaved(next);
    save(next);
  };

  // Keyboard: arrows move the tile between corners.
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

  // With nowhere to sit (the dock hidden) it is parked out of sight; leaving
  // the park jumps straight to the slot rather than flying in from a corner.
  const parked = !box;
  const wasParked = useRef(true);
  const snap = wasParked.current && !parked;
  useLayoutEffect(() => {
    if (snap) void ref.current?.offsetHeight;
    wasParked.current = parked;
  });
  const at = box ?? { left: -200, top: -200, width: 44, height: 44 };
  const pos = drag ? { left: drag.left, top: drag.top } : { left: at.left, top: at.top };
  const face = mode === "tile" ? tileSize(false).face : at.height;
  const LABEL: Record<CallState, string> = {
    connecting: "Connecting…",
    listening: muted ? "Microphone off" : "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    error: "Could not connect",
  };
  const shown = muted && state === "listening" ? "muted" : state;

  return (
    <div
      ref={ref}
      className={`call-tile is-${mode} is-${state}${drag ? " is-dragging" : ""}${parked ? " is-parked" : ""}${snap ? " is-snap" : ""}${raised ? " is-raised" : ""}`}
      style={{ left: pos.left, top: pos.top, width: at.width, height: at.height }}
      role={mode === "docked" ? undefined : "region"}
      aria-label={mode === "docked" ? undefined : `Call with ${PERSONA.name}, ${role}. Drag, or use the arrow keys, to move it.`}
      tabIndex={mode === "docked" ? -1 : 0}
      data-voqalize
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
              {PERSONA.name}
            </span>
            <span className={`call-state is-${shown}`} aria-live="polite">
              {LABEL[state]}
            </span>
          </>
        ) : null}
        {mode === "mini" ? (
          <button type="button" className="call-expand" aria-label={`Show the call with ${PERSONA.name}`} onClick={() => setMini(false)}>
            <Maximize2 size={14} />
          </button>
        ) : null}
      </div>
      {mode === "tile" ? (
        <div className="call-bar">
          <LangToggle />
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
