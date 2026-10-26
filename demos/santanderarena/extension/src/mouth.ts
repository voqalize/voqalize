/**
 * His lips on the still a page shows while its face is not drawing yet.
 *
 * On a full page load in a call, the early shell (`shell.ts`) puts a still of
 * his face where his face goes, and his voice carries on from the holder for
 * the second or two until the live face draws. The still is his mouth strip
 * (`MOUTH_STRIP`: four frames of the face's box, identical but for the mouth,
 * closed to open) on the avatar's host, and the frame shown follows the
 * loudness the holder measures (`meter.ts`, `level.ts`), which the bridge
 * passes to the page as it passes everything (`voqalize:in`) from
 * `document_start`, before `content.ts` has loaded. Nothing else moves.
 *
 * Should the strip not load, the still is the last frame his face drew (or
 * the character's still), and the level changes nothing that shows.
 */

import { Mouth, type Shape } from "./level";
import type { Widget } from "./widget";

declare const __MOUTH_STRIP__: string;

/** His mouth strip, on the avatar host this build's runtime comes from
 *  (`build.mjs`); empty for none. */
export const MOUTH_STRIP: string = __MOUTH_STRIP__;

const IN = "voqalize:in";
/** How often the shown frame is looked at while there is a level. */
const TICK_MS = 20;

let loading: Promise<boolean> | null = null;

/** Load the strip into the browser's cache and decode it: whether it can show. */
export function loadStrip(): Promise<boolean> {
  if (!MOUTH_STRIP) return Promise.resolve(false);
  loading ??= (() => {
    const img = new Image();
    img.src = MOUTH_STRIP;
    return img.decode().then(
      () => img.naturalWidth > 0,
      () => false,
    );
  })();
  return loading;
}

/**
 * Put the strip on the widget's poster, and move its mouth with his voice
 * until the poster is handed over to the live face. `loadedBefore`: the last
 * page of this tab loaded the strip, so it is in the cache and goes up at
 * once; otherwise the still shows until it has loaded.
 */
export function voiceMouth(widget: Widget, loadedBefore: boolean): void {
  if (!MOUTH_STRIP) return;
  if (loadedBefore) widget.setMouthStrip(MOUTH_STRIP);
  void loadStrip().then((ok) => widget.setMouthStrip(ok ? MOUTH_STRIP : null));

  const mouth = new Mouth();
  let timer: ReturnType<typeof setInterval> | null = null;
  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
  };
  const tick = () => {
    const now = performance.now();
    widget.setMouth(mouth.at(now));
    if (!mouth.busy(now)) stop();
  };
  const heard = (e: MessageEvent) => {
    if (e.source !== window) return;
    const msg = (e.data as Record<string, unknown> | null)?.[IN] as { k?: string; m?: Shape } | undefined;
    if (msg?.k !== "level") return;
    // The live face has his mouth now: this page is done with the still.
    if (!widget.posterShowing()) {
      window.removeEventListener("message", heard);
      stop();
      widget.setMouth(0);
      return;
    }
    mouth.hear(msg.m ?? 0, performance.now());
    timer ??= setInterval(tick, TICK_MS);
    tick();
  };
  window.addEventListener("message", heard);
}
