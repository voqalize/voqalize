/**
 * The document tab (`doc.html`): one of Saatvik's PDFs, full tab, at the page
 * Sunny is reading from, with the line she quotes marked. The request rides in
 * the URL's hash, so the next document Sunny opens reuses this tab. Its button
 * takes the visitor back to the Saatvik tab the call is in.
 */

import { mountViewer, type OpenRequest } from "./pdf-viewer";
import type { WorkerAsk } from "./tabs-protocol";

const viewer = mountViewer(
  { opened: () => {}, closed: () => {}, covering: () => {} },
  { tab: true, back: () => void chrome.runtime.sendMessage({ t: "back" } satisfies WorkerAsk) },
);

function requested(): OpenRequest | null {
  try {
    const req = JSON.parse(decodeURIComponent(location.hash.slice(1))) as OpenRequest;
    return typeof req.url === "string" && /^https:\/\/(www\.)?saatvikgroup\.com\//.test(req.url) ? req : null;
  } catch {
    return null;
  }
}

function show(): void {
  const req = requested();
  if (!req) {
    document.body.textContent = "This document could not be opened.";
    return;
  }
  document.title = `${req.title} — Saatvik`;
  viewer.open(req).catch((error: unknown) => {
    document.body.textContent = error instanceof Error ? error.message : String(error);
  });
}

window.addEventListener("hashchange", show);
show();
