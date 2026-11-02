/**
 * Circle to ask, on screen: the gesture, the glowing stroke, the live
 * highlights while drawing, and — once released — numbered badges on what was
 * circled, with a chip to clear it.
 *
 * The gesture only arms on Shift + drag (mouse) or a 350 ms long-press and
 * drag (touch), so ordinary clicks, scrolling and text selection never start
 * one. While it is armed, the page does not scroll, select text or follow the
 * link under the pointer.
 */
import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useVoiceClient } from "../stage/client";
import {
  type Point,
  type Thing,
  pathLength,
  smoothPath,
  thingKey,
  thingsInLoop,
  thingsOnScreen,
  useSelection,
} from "../voice/circle";
import { useFakeCall } from "../voice/VoiceDock";
import { emit } from "../voice/events";

const LONG_PRESS_MS = 350;
const SLOP = 8;
const MIN_LOOP = 90;

type Mode = "idle" | "drawing" | "fading";

/** The gesture's steps, for the shopper's pointer and for the debug console's fake circle. */
interface CircleApi {
  begin(p: Point): void;
  move(p: Point): void;
  end(additive?: boolean): void;
}
let api: CircleApi | null = null;

const reduced = () => {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};

export function CircleLayer() {
  const location = useLocation();
  const [mode, setMode] = useState<Mode>("idle");
  const [d, setD] = useState("");
  const [head, setHead] = useState<Point | null>(null);
  const [lit, setLit] = useState<{ key: string; left: number; top: number; width: number; height: number }[]>([]);
  const pts = useRef<Point[]>([]);
  const candidates = useRef<ReturnType<typeof thingsOnScreen>>([]);
  const frame = useRef(0);
  const fadeTimer = useRef<number>(undefined);

  const redraw = useCallback(() => {
    frame.current = 0;
    const p = pts.current;
    setD(smoothPath(p));
    setHead(p[p.length - 1] ?? null);
    if (p.length > 4) {
      const keys = new Set(thingsInLoop(p, candidates.current).map(thingKey));
      setLit(
        candidates.current
          .filter((c) => keys.has(thingKey(c.thing)))
          .map((c) => ({ key: thingKey(c.thing), ...c.box })),
      );
    }
  }, []);

  const begin = useCallback((p: Point) => {
    window.clearTimeout(fadeTimer.current);
    candidates.current = thingsOnScreen();
    pts.current = [p];
    setLit([]);
    setMode("drawing");
    document.body.classList.add("is-circling");
    redraw();
  }, [redraw]);

  const move = useCallback(
    (p: Point) => {
      const last = pts.current[pts.current.length - 1];
      if (last && Math.hypot(p.x - last.x, p.y - last.y) < 3) return;
      pts.current.push(p);
      if (!frame.current) frame.current = requestAnimationFrame(redraw);
    },
    [redraw],
  );

  const end = useCallback((additive = false) => {
    document.body.classList.remove("is-circling");
    const p = pts.current;
    const enough = p.length > 6 && pathLength(p) >= MIN_LOOP;
    const things: Thing[] = enough ? thingsInLoop(p, candidates.current) : [];
    const page = location.pathname + location.search;
    if (things.length) {
      if (additive && useSelection.getState().things.length) useSelection.getState().add(things, page);
      else useSelection.getState().select(things, page);
    }
    setD(smoothPath(p, enough));
    setHead(null);
    setLit([]);
    pts.current = [];
    if (reduced()) {
      setMode("idle");
      setD("");
      return;
    }
    setMode("fading");
    fadeTimer.current = window.setTimeout(() => {
      setMode("idle");
      setD("");
    }, 700);
  }, [location.pathname, location.search]);

  /** Esc mid-stroke: no selection, no fade, nothing left on screen. */
  const cancel = useCallback(() => {
    window.clearTimeout(fadeTimer.current);
    document.body.classList.remove("is-circling");
    pts.current = [];
    setLit([]);
    setHead(null);
    setD("");
    setMode("idle");
  }, []);

  // A new page starts with nothing circled.
  const firstKey = useRef(location.pathname);
  useEffect(() => {
    if (location.pathname === firstKey.current) return;
    firstKey.current = location.pathname;
    cancel();
    useSelection.getState().clear();
  }, [location.pathname, cancel]);

  useEffect(() => {
    api = { begin, move, end };
    return () => {
      api = null;
    };
  }, [begin, move, end]);

  // ── The gesture ──
  useEffect(() => {
    let armed = false;
    let additive = false;
    let press: { id: number; x: number; y: number; timer: number } | null = null;
    let swallowClick = false;
    const at = (e: PointerEvent | Touch): Point => ({ x: e.clientX, y: e.clientY });

    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      if (e.pointerType === "mouse") {
        if (!e.shiftKey) return;
        e.preventDefault();
        armed = true;
        // Shift + Alt (Option) adds to what is already circled.
        additive = e.altKey;
        swallowClick = true;
        begin(at(e));
        return;
      }
      // Touch or pen: arm only after holding still.
      const start = at(e);
      press = {
        id: e.pointerId,
        x: start.x,
        y: start.y,
        timer: window.setTimeout(() => {
          if (!press) return;
          armed = true;
          additive = useSelection.getState().addNext;
          swallowClick = true;
          navigator.vibrate?.(8);
          begin({ x: press.x, y: press.y });
        }, LONG_PRESS_MS),
      };
    };
    const moveP = (e: PointerEvent) => {
      if (press && !armed && Math.hypot(e.clientX - press.x, e.clientY - press.y) > SLOP) {
        window.clearTimeout(press.timer);
        press = null;
      }
      if (armed) {
        e.preventDefault();
        move(at(e));
      }
    };
    const up = () => {
      if (press) window.clearTimeout(press.timer);
      press = null;
      if (!armed) return;
      armed = false;
      end(additive);
      // The click that follows the gesture is not a click on the page.
      window.setTimeout(() => (swallowClick = false), 50);
    };
    const touchMove = (e: TouchEvent) => {
      if (!armed) return;
      e.preventDefault();
      const t = e.touches[0];
      if (t) move(at(t));
    };
    const click = (e: MouseEvent) => {
      if (!swallowClick) return;
      e.preventDefault();
      e.stopPropagation();
      swallowClick = false;
    };
    const menu = (e: Event) => {
      if (armed || press) e.preventDefault();
    };
    const select = (e: Event) => {
      if (armed) e.preventDefault();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const drawing = armed;
      if (press) window.clearTimeout(press.timer);
      press = null;
      armed = false;
      if (drawing) cancel();
      if (useSelection.getState().things.length) useSelection.getState().clear();
      else if (drawing) emit("selection_cleared", {});
    };
    // A Shift-drag that starts on a photo or link must not become the browser's own drag.
    const drag = (e: DragEvent) => {
      if (armed || (e as unknown as { shiftKey?: boolean }).shiftKey) e.preventDefault();
    };
    document.addEventListener("pointerdown", down, true);
    window.addEventListener("pointermove", moveP, { passive: false });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    document.addEventListener("touchmove", touchMove, { passive: false });
    document.addEventListener("click", click, true);
    document.addEventListener("contextmenu", menu, true);
    document.addEventListener("selectstart", select, true);
    document.addEventListener("keydown", key);
    document.addEventListener("dragstart", drag, true);
    return () => {
      document.removeEventListener("dragstart", drag, true);
      document.removeEventListener("pointerdown", down, true);
      window.removeEventListener("pointermove", moveP);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      document.removeEventListener("touchmove", touchMove);
      document.removeEventListener("click", click, true);
      document.removeEventListener("contextmenu", menu, true);
      document.removeEventListener("selectstart", select, true);
      document.removeEventListener("keydown", key);
    };
  }, [begin, move, end, cancel]);

  return (
    <>
      {mode !== "idle" ? (
        <svg className={`circle-ink is-${mode}`} aria-hidden data-voqalize>
          <defs>
            {/* A full-spectrum rainbow along the stroke (owner, 2026-11-02). */}
            <linearGradient id="fh-ink" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#ff3b5c" />
              <stop offset="16%" stopColor="#ff9a1f" />
              <stop offset="32%" stopColor="#ffd60a" />
              <stop offset="48%" stopColor="#34d399" />
              <stop offset="64%" stopColor="#22c3ee" />
              <stop offset="80%" stopColor="#4f6bff" />
              <stop offset="92%" stopColor="#a855f7" />
              <stop offset="100%" stopColor="#ff3b5c" />
            </linearGradient>
            <filter id="fh-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="7" />
            </filter>
          </defs>
          {lit.map((b) => (
            <rect key={b.key} className="circle-lit" x={b.left - 4} y={b.top - 4} width={b.width + 8} height={b.height + 8} rx={10} />
          ))}
          <path className="circle-glow" d={d} filter="url(#fh-glow)" />
          <path className="circle-line" d={d} />
          {head ? <circle className="circle-head" cx={head.x} cy={head.y} r={5} /> : null}
        </svg>
      ) : null}
      <SelectionMarks />
      <CircleHint />
    </>
  );
}

/** Numbered badges and a ring on the circled things on this page, plus the chip. */
function SelectionMarks() {
  const things = useSelection((s) => s.things);
  const addNext = useSelection((s) => s.addNext);
  const touch = typeof window !== "undefined" && window.matchMedia("(hover: none)").matches;
  const [boxes, setBoxes] = useState<{ n: number; key: string; left: number; top: number; width: number; height: number }[]>([]);
  useEffect(() => {
    if (!things.length) {
      setBoxes([]);
      return;
    }
    let frame = 0;
    const track = () => {
      const out: typeof boxes = [];
      things.forEach((t, i) => {
        const el = [...document.querySelectorAll(`[data-fh-thing="${CSS.escape(thingKey(t))}"]`)].find(
          (x) => !x.parentElement?.closest("[data-fh-thing]") && x.getBoundingClientRect().width > 0,
        );
        if (!el) return;
        const r = el.getBoundingClientRect();
        if (r.bottom < 0 || r.top > window.innerHeight) return;
        out.push({ n: i + 1, key: thingKey(t), left: r.left, top: r.top, width: r.width, height: r.height });
      });
      setBoxes((prev) => (JSON.stringify(prev) === JSON.stringify(out) ? prev : out));
      frame = requestAnimationFrame(track);
    };
    track();
    return () => cancelAnimationFrame(frame);
  }, [things]);

  if (!things.length) return null;
  return (
    <>
      <div className="selection-marks" aria-hidden data-voqalize>
        {boxes.map((b) => (
          <div key={b.key} className="selection-ring" style={{ left: b.left - 5, top: b.top - 5, width: b.width + 10, height: b.height + 10 }}>
            <span className="selection-glow">
              <span className="selection-band" />
            </span>
            <span className="selection-edge" />
            <span
              className="selection-badge"
              style={{ left: Math.max(-13, 6 - (b.left - 5)), top: Math.max(-13, (document.querySelector(".site-header")?.getBoundingClientRect().bottom ?? 0) + 6 - (b.top - 5)) }}
            >
              {b.n}
            </span>
          </div>
        ))}
      </div>
      <div className="selection-chip" role="status" data-voqalize>
        <span className="selection-count">{things.length}</span>
        <span>
          selected<span className="selection-sep" aria-hidden>
            ·
          </span>
          say what you want
        </span>
        {touch ? (
          <button
            type="button"
            className={`selection-add${addNext ? " is-on" : ""}`}
            aria-pressed={addNext}
            onClick={() => useSelection.setState({ addNext: !addNext })}
          >
            + Add more
          </button>
        ) : null}
        <button type="button" aria-label="Clear the selection" onClick={() => useSelection.getState().clear()}>
          <X size={15} />
        </button>
      </div>
    </>
  );
}

/** Once, while a call is live: how to circle. */
function CircleHint() {
  const live = useVoiceClient((s) => s.live);
  const fake = useFakeCall((s) => s.on);
  const [show, setShow] = useState(false);
  const on = live || fake;
  useEffect(() => {
    if (!on) return;
    let seen = false;
    try {
      seen = localStorage.getItem("fh-circle-hint") === "1";
      localStorage.setItem("fh-circle-hint", "1");
    } catch {
      /* storage unavailable: show it this once anyway */
    }
    if (seen && !fake) return;
    const start = window.setTimeout(() => setShow(true), 1200);
    const stop = window.setTimeout(() => setShow(false), 10200);
    return () => {
      window.clearTimeout(start);
      window.clearTimeout(stop);
    };
  }, [on, fake]);
  if (!show) return null;
  const touch = typeof window !== "undefined" && window.matchMedia("(hover: none)").matches;
  return (
    <div className="circle-hint" role="note">
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
        <path d="M12 4c5 0 8 2.6 8 6.6S16.6 19 11.6 19C6.8 19 4 16.4 4 12.8 4 9 7.6 6.6 12 6.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      {touch ? "Tip: press, hold and circle things to ask Emily · + Add more adds" : "Tip: Shift to circle things for Emily · Shift+Alt to add"}
    </div>
  );
}

/**
 * The debug console's fake circle: a loop drawn round `els` (or the first
 * three cards of the home page's on-sale rail), `upTo` of the way round, and
 * released unless `hold`.
 */
export async function fakeCircle(opts: { els?: Element[]; upTo?: number; hold?: boolean; additive?: boolean } = {}) {
  const all = opts.els ?? [...document.querySelectorAll(".rail .rail-item [data-fh-thing]")];
  // Only what fits across the screen: three cards on a wide one, fewer on a phone.
  const els = opts.els ?? all.filter((e) => e.getBoundingClientRect().right <= window.innerWidth - 8).slice(0, 3);
  if (!api || !els.length) return false;
  els[0].scrollIntoView({ block: "center" });
  await new Promise((r) => setTimeout(r, 350));
  const rects = els.map((e) => e.getBoundingClientRect());
  const left = Math.min(...rects.map((r) => r.left));
  const right = Math.max(...rects.map((r) => r.right));
  const top = Math.min(...rects.map((r) => r.top));
  const bottom = Math.max(...rects.map((r) => r.bottom));
  const cx = (left + right) / 2;
  const cy = (top + bottom) / 2;
  const rx = (right - left) / 2 + 34;
  const ry = (bottom - top) / 2 + 30;
  const steps = 64;
  const upTo = opts.upTo ?? 1.06;
  const n = Math.round(steps * upTo);
  const at = (i: number): Point => {
    const t = -Math.PI * 0.62 + (i / steps) * Math.PI * 2;
    const wobble = 1 + 0.035 * Math.sin(i * 0.7);
    return { x: cx + Math.cos(t) * rx * wobble, y: cy + Math.sin(t) * ry * wobble };
  };
  api.begin(at(0));
  for (let i = 1; i <= n; i++) {
    api.move(at(i));
    await new Promise((r) => setTimeout(r, 12));
  }
  if (!opts.hold) api.end(opts.additive);
  return true;
}
