/**
 * The agent's face, as one fixed element that moves between three shapes:
 *
 * - **docked**: sitting exactly on the dock pill's face slot, before and after
 *   a call;
 * - **tile**: a floating call window once the call connects, with the name, a
 *   state chip, the EN / हिंदी toggle and mute / minimise / end. While it is up
 *   the dock pill fades away, so there is one control surface at a time;
 * - **mini**: a small bubble at the tile's place, after Minimise.
 *
 * It is one element for the page's whole life, so the avatar inside it (the
 * `@voqalize/avatar` mount the caller passes as `children`) is never
 * re-created: popping out, dragging, minimising and going back into the dock
 * only change its box. The tile drags with mouse or touch, snaps to the
 * nearest corner or side on release, remembers where it was, keeps off the
 * page's primary buttons, and moves to a top corner while a bottom sheet is
 * open (`raisedCorner`). It never shows what the visitor said.
 */
import { Maximize2, Mic, MicOff, Minus, PhoneOff } from "lucide-react";
import { type ReactNode, useCallback, useLayoutEffect, useRef, useState } from "react";
import { PERSONA } from "../persona";
import { useSite } from "../state/store";
import { isPhone, raisedCorner, tileBlockers } from "./useDockMode";

export type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";
type Anchor = "tl" | "tr" | "ml" | "mr" | "bl" | "br";
const ANCHORS: Anchor[] = ["tl", "tr", "ml", "mr", "bl", "br"];
const KEY = "paynora-call-tile";
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
  // Bottom left: clear of the brief, which opens on the right.
  return { anchor: "bl", mini: false };
}
function save(s: Saved) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: the tile starts bottom left next time */
  }
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The tile's size: a small framed portrait over a two-row bar (language,
 *  then the buttons), smaller on a phone. */
export function tileSize(mini: boolean): { width: number; height: number; face: number } {
  if (mini) return { width: 64, height: 64, face: 64 };
  const phone = isPhone();
  const width = phone ? 128 : 164;
  const face = phone ? 120 : 168;
  return { width, height: face + (phone ? 74 : 80), face };
}

function headerBottom(): number {
  const h = document.querySelector(".site-header")?.getBoundingClientRect();
  return Math.max(0, h ? h.bottom : 0);
}

function boxAt(anchor: Anchor, size: { width: number; height: number }, overHeader = false): Box {
  const top0 = overHeader ? MARGIN : headerBottom() + MARGIN;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const m = isPhone() ? 12 : MARGIN;
  const left = anchor.endsWith("l") ? m : vw - size.width - m;
  const top = anchor[0] === "t" ? top0 : anchor[0] === "m" ? Math.max(top0, (vh - size.height) / 2) : vh - size.height - m;
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

/** The visitor's anchor, unless it would cover a primary button, the brief or the phone menu. */
function clearAnchor(want: Anchor, size: { width: number; height: number }): Anchor {
  const blockers = tileBlockers();
  const free = (a: Anchor) => !blockers.some((r) => overlaps(boxAt(a, size), r));
  if (free(want)) return want;
  const h = want[1];
  const o = h === "r" ? "l" : "r";
  const order = [`b${h}`, `m${h}`, `t${h}`, `b${o}`, `m${o}`, `t${o}`] as Anchor[];
  return order.find(free) ?? want;
}

export function CallTile({
  live,
  state,
  muted,
  onMute,
  onEnd,
  onLanguage,
  children,
}: {
  live: boolean;
  state: CallState;
  muted: boolean;
  onMute: () => void;
  onEnd: () => void;
  /** The visitor pressed a language on the tile's toggle. */
  onLanguage: (code: string) => void;
  /** The face: the avatar mount, kept for the element's whole life. */
  children: ReactNode;
}) {
  const lang = useSite((s) => s.lang);
  const [saved, setSaved] = useState<Saved>(load);
  const [box, setBox] = useState<Box | null>(null);
  const [raised, setRaised] = useState<"tl" | "tr" | null>(null);
  const [drag, setDrag] = useState<{ dx: number; dy: number; left: number; top: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const mode: "docked" | "tile" | "mini" = !live ? "docked" : saved.mini ? "mini" : "tile";

  // Where the element sits right now, recomputed on scroll, resize and a poll.
  const place = useCallback(() => {
    if (mode === "docked") {
      const slotEl = document.querySelector(".dock-face-slot");
      const slot = slotEl?.getBoundingClientRect();
      const dock = slotEl?.closest<HTMLElement>(".dock");
      const hidden = !!dock?.classList.contains("is-hidden");
      // Where the slot sits once the dock is at rest: the face runs the
      // dock's entrance slide itself, so counting it here would double it.
      const [dx, dy] = restOffset(dock);
      setBox(slot && slot.width && !hidden ? { left: slot.left - dx, top: slot.top - dy, width: slot.width, height: slot.height } : null);
      setRaised(null);
      return;
    }
    const size = tileSize(mode === "mini");
    const corner = raisedCorner();
    setRaised(corner);
    setBox(corner ? boxAt(corner, size, true) : boxAt(clearAnchor(saved.anchor, size), size));
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
    // The dock moves (raised, hidden) and overlays open without an event here.
    const t = window.setInterval(soon, 400);
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
  // to sit (the dock stepped aside) it is parked out of sight.
  const parked = !box;
  // Leaving the park jumps straight to the slot instead of flying in.
  const wasParked = useRef(true);
  const snap = wasParked.current && !parked;
  useLayoutEffect(() => {
    if (snap) void ref.current?.offsetHeight;
    wasParked.current = parked;
  });
  const at = box ?? { left: -200, top: -200, width: 44, height: 44 };
  const pos = drag ? { left: drag.left, top: drag.top } : { left: at.left, top: at.top };
  const face = mode === "tile" ? tileSize(false).face : at.height;
  const name = PERSONA.display_name;
  const LABEL: Record<CallState, string> = {
    idle: "Connecting…",
    connecting: "Connecting…",
    listening: muted ? "Microphone off" : "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    error: "Could not connect",
  };

  return (
    <div
      ref={ref}
      className={`call-tile is-${mode} is-${state}${muted ? " is-muted" : ""}${drag ? " is-dragging" : ""}${parked ? " is-parked" : ""}${snap ? " is-snap" : ""}${raised ? " is-raised" : ""}`}
      style={{ left: pos.left, top: pos.top, width: at.width, height: at.height }}
      role={mode === "docked" ? undefined : "region"}
      aria-label={mode === "docked" ? undefined : `Call with ${name}. Drag, or use the arrow keys, to move it.`}
      tabIndex={mode === "docked" ? -1 : 0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onKeyDown}
      data-call-tile
    >
      <div className="call-face" style={{ height: face }}>
        {children}
        {mode === "tile" ? (
          <>
            <span className="call-tag">{name}</span>
            <span className={`call-state is-${muted && state === "listening" ? "muted" : state}`} aria-live="polite">
              {LABEL[state]}
            </span>
          </>
        ) : null}
        {mode === "mini" ? (
          <button type="button" className="call-expand" aria-label={`Show the call with ${name}`} onClick={() => setMini(false)}>
            <Maximize2 size={14} />
          </button>
        ) : null}
      </div>
      {mode === "tile" ? (
        <div className="call-bar">
          <div className="call-lang" role="group" aria-label="Language">
            {PERSONA.languages.map((l) => (
              <button
                key={l.code}
                type="button"
                lang={l.code}
                className={lang === l.code ? "is-on" : ""}
                aria-pressed={lang === l.code}
                aria-label={`Speak ${l.label}`}
                onClick={() => onLanguage(l.code)}
              >
                {l.toggle}
              </button>
            ))}
          </div>
          <div className="call-controls">
            <button type="button" className="call-btn" aria-pressed={muted} aria-label={muted ? "Turn microphone on" : "Turn microphone off"} onClick={onMute}>
              {muted ? <MicOff size={15} /> : <Mic size={15} />}
            </button>
            <button type="button" className="call-btn" aria-label="Minimise the call" onClick={() => setMini(true)}>
              <Minus size={15} />
            </button>
            <button type="button" className="call-btn call-end" aria-label="End the call" onClick={onEnd}>
              <PhoneOff size={15} />
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
