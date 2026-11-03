/**
 * The brain's note cards (`show_note`): the snippet's own (`call/notes.ts`,
 * one card at a time, a status chip, the site's contact links on a `contact`
 * note, text set with `textContent` only), drawn in a panel of the
 * extension's just above the widget, in a shadow root of its own so neither
 * the site's styles nor the page digest reach it.
 */

import type { HumanContact } from "@snippet/bundle.gen";
import { CSS } from "@snippet/call/styles";
import { createNotes, type Notes } from "@snippet/call/notes";
import type { ShowNote } from "@snippet/vocabulary.gen";

import { SITE_AGENT } from "./site";

const GAP = 12;

export interface NotePanel extends Notes {
  destroy(): void;
}

/** The widget's drawn box: its host and what its shadow root draws. */
function widgetBox(): DOMRect | null {
  const host = document.querySelector('[data-voqalize="widget"]');
  if (!host) return null;
  const boxes = [host, ...Array.from(host.shadowRoot?.children ?? [])]
    .map((e) => e.getBoundingClientRect())
    .filter((r) => r.width > 0 && r.height > 0);
  if (!boxes.length) return null;
  const left = Math.min(...boxes.map((r) => r.left));
  const top = Math.min(...boxes.map((r) => r.top));
  const right = Math.max(...boxes.map((r) => r.right));
  const bottom = Math.max(...boxes.map((r) => r.bottom));
  return new DOMRect(left, top, right - left, bottom - top);
}

export function notePanel(contact: HumanContact | undefined): NotePanel {
  const t = SITE_AGENT.theme;
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "notes");
  host.setAttribute("translate", "no");
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = `${CSS}
:host{all:initial}
.panel{position:fixed;z-index:2147483646;box-sizing:border-box;width:300px;max-width:calc(100vw - 32px);
padding:12px 14px;border-radius:${t.radius ?? 10}px;background:${t.card};color:${t.ink};
font:14px/1.4 ${t.font ?? "system-ui, sans-serif"};box-shadow:0 12px 36px rgba(0,0,0,.28);
--vq-accent:${t.brand};--vq-on-accent:${t.onBrand ?? "#fff"};--vq-bg:${t.card};--vq-text:${t.ink}}
.panel[hidden]{display:none}
.vq-links a{color:${t.ink}}`;
  const panel = document.createElement("div");
  panel.className = "panel";
  panel.hidden = true;
  shadow.append(style, panel);
  document.body.append(host);
  const notes = createNotes(panel, contact);

  function place(): void {
    if (panel.hidden) return;
    const box = widgetBox();
    const right = SITE_AGENT.corner !== "left";
    const side = box ? (right ? Math.max(GAP, innerWidth - box.right) : Math.max(GAP, box.left)) : 20;
    const bottom = box ? Math.max(GAP, innerHeight - box.top + GAP) : 120;
    panel.style.left = right ? "" : `${side}px`;
    panel.style.right = right ? `${side}px` : "";
    panel.style.bottom = `${bottom}px`;
  }

  // Shown while it holds a card or a chip; kept above the widget as it moves.
  const watch = new MutationObserver(() => {
    panel.hidden = !panel.childElementCount;
    place();
  });
  watch.observe(panel, { childList: true });
  const timer = setInterval(place, 800);
  addEventListener("resize", place);

  return {
    show: (note: ShowNote) => notes.show(note),
    clear: () => notes.clear(),
    destroy() {
      watch.disconnect();
      clearInterval(timer);
      removeEventListener("resize", place);
      notes.clear();
      host.remove();
    },
  };
}
