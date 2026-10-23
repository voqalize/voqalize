/**
 * The bridge between the page and the hub (`background.ts`).
 *
 * The call runs in the page's own JavaScript world (`content.ts`), where
 * extension messaging does not exist; this script runs in the extension's
 * isolated world on the same page, where it does. It carries `window` messages
 * tagged `voqalize:out` to the hub, and the hub's messages back as
 * `voqalize:in`. A service worker that was stopped is reconnected, and what the
 * page sent meanwhile is kept and sent once it is back.
 */

const OUT = "voqalize:out";
const IN = "voqalize:in";

let port: chrome.runtime.Port | null = null;
const queue: unknown[] = [];

function connect(): chrome.runtime.Port {
  const p = chrome.runtime.connect({ name: "voqalize" });
  p.onMessage.addListener((msg: unknown) => {
    window.postMessage({ [IN]: msg }, location.origin);
  });
  p.onDisconnect.addListener(() => {
    if (port === p) port = null;
  });
  return p;
}

let retry: ReturnType<typeof setTimeout> | null = null;

function flush(): void {
  retry = null;
  while (queue.length) {
    try {
      port ??= connect();
      port.postMessage(queue[0]);
      queue.shift();
    } catch {
      // The worker was stopped, or the extension reloaded under this page.
      // Keep the newest few and try again shortly.
      port = null;
      if (queue.length > 200) queue.splice(0, queue.length - 200);
      retry ??= setTimeout(flush, 250);
      return;
    }
  }
}

function send(msg: unknown): void {
  queue.push(msg);
  if (!retry) flush();
}

window.addEventListener("message", (e: MessageEvent) => {
  if (e.source !== window) return;
  const data = e.data as Record<string, unknown> | null;
  if (data && typeof data === "object" && OUT in data) send(data[OUT]);
});

// Connected from the start, so the hub knows this tab before the page asks.
port = connect();
