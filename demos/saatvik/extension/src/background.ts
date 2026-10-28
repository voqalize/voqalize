/**
 * The service worker: the tabs a page cannot open or focus by itself.
 *
 * Sunny opens a document in a tab of its own, beside the Saatvik tab the call
 * is in (`doc.html`), and reuses that tab for the next document rather than
 * opening one per document. The call stays in the Saatvik tab, which keeps
 * playing her voice and hearing the visitor while it is in the background;
 * when she moves the site again, the page asks to be brought back to the
 * front first (`focus_me`), and the document tab's own button does the same
 * (`back`).
 *
 * Which document tab belongs to which Saatvik tab is kept in session storage:
 * a service worker may be stopped between messages.
 */

import type { WorkerAnswer, WorkerAsk } from "./tabs-protocol";

const DOC_PAGE = chrome.runtime.getURL("doc.html");

type Links = Record<string, number>;

async function links(): Promise<{ docOf: Links; siteOf: Links }> {
  const got = await chrome.storage.session.get(["docOf", "siteOf"]);
  return { docOf: (got.docOf as Links) ?? {}, siteOf: (got.siteOf as Links) ?? {} };
}

async function link(site: number, doc: number): Promise<void> {
  const { docOf, siteOf } = await links();
  docOf[site] = doc;
  siteOf[doc] = site;
  await chrome.storage.session.set({ docOf, siteOf });
}

async function alive(id: number | undefined): Promise<chrome.tabs.Tab | null> {
  if (id === undefined) return null;
  try {
    return await chrome.tabs.get(id);
  } catch {
    return null;
  }
}

async function focus(tab: chrome.tabs.Tab): Promise<void> {
  if (tab.id === undefined) return;
  await chrome.tabs.update(tab.id, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
}

async function answer(ask: WorkerAsk, sender: chrome.runtime.MessageSender): Promise<WorkerAnswer> {
  const from = sender.tab;
  if (!from || from.id === undefined) return { ok: false, error: "not asked from a tab" };
  switch (ask.t) {
    case "open_doc": {
      const url = `${DOC_PAGE}#${encodeURIComponent(JSON.stringify(ask.req))}`;
      const { docOf } = await links();
      const doc = await alive(docOf[from.id]);
      if (doc?.id !== undefined) {
        await chrome.tabs.update(doc.id, { url });
        await focus(doc);
        return { ok: true };
      }
      const made = await chrome.tabs.create({
        url,
        index: from.index + 1,
        openerTabId: from.id,
        windowId: from.windowId,
        active: true,
      });
      if (made.id !== undefined) await link(from.id, made.id);
      return { ok: true };
    }
    case "close_doc": {
      const { docOf } = await links();
      const doc = await alive(docOf[from.id]);
      if (doc?.id === undefined) return { ok: false, error: "no document is open" };
      await focus(from);
      await chrome.tabs.remove(doc.id);
      return { ok: true };
    }
    case "focus_me":
      await focus(from);
      return { ok: true };
    case "back": {
      const { siteOf } = await links();
      const site = await alive(siteOf[from.id]);
      if (!site) return { ok: false, error: "the Saatvik tab is closed" };
      await focus(site);
      return { ok: true };
    }
  }
}

chrome.runtime.onMessage.addListener((ask: WorkerAsk, sender, reply) => {
  answer(ask, sender)
    .then(reply)
    .catch((error: unknown) => reply({ ok: false, error: error instanceof Error ? error.message : String(error) }));
  return true;
});

chrome.tabs.onRemoved.addListener((id) => {
  void links().then(({ docOf, siteOf }) => {
    if (siteOf[id] !== undefined) delete docOf[siteOf[id]];
    if (docOf[id] !== undefined) delete siteOf[docOf[id]];
    delete siteOf[id];
    delete docOf[id];
    return chrome.storage.session.set({ docOf, siteOf });
  });
});
