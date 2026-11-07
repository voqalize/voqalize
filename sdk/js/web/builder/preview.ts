/**
 * One preview frame: a sample page with the real `<vql-widget>` on it, put
 * into the state the builder asks for. A configuration change is applied to
 * the widget in place, so the face and the turn carry on; a change of state,
 * page or placement mode starts the widget again.
 *
 * Imports only the package's public entry points.
 */

import { type VqlWidget, defineElements, setAvatarLoader } from "@voqalize/web/widgets";
import type { PreviewMessage, PreviewReport, PreviewState } from "./protocol.js";
import { ReplaySession, type ReplayScript, recordedTurn } from "./replay.js";
import { type Sparse, getPath } from "./schema-form.js";

// The avatar is an optional peer the builder does not bundle: the face shows its still.
setAvatarLoader(() => Promise.reject(new Error("the builder previews the still")));
defineElements();

const SCRIPTS: Record<PreviewState, ReplayScript | null> = {
  closed: null,
  speaking: { mic: "live", play: true },
  collapsed: { mic: "live", play: true },
  asking: { mic: "asking", play: true },
  blocked: { mic: "blocked", play: true },
  muted: { mic: "muted", play: true },
  silent: { mic: "silent", play: false },
  ended: { mic: "live", play: false },
};

let widget: VqlWidget | null = null;
let session: ReplaySession | null = null;
let shownKey = "";

function report(r: Omit<PreviewReport, "type">): void {
  parent.postMessage({ type: "vql-preview", ...r } satisfies PreviewReport, location.origin);
}

/** What the frame shows: the configuration with the preview's own still, and nothing remembered. */
function previewConfig(config: Sparse, talking: boolean): Sparse {
  const out = structuredClone(config);
  if (!talking) {
    delete out.agent;
    delete out.key;
  }
  const placement = (out.placement ?? {}) as Sparse;
  out.placement = { ...placement, remember: "off" };
  if (out.avatar !== false) {
    const avatar = (out.avatar ?? {}) as Sparse;
    if (avatar.still === undefined) out.avatar = { ...avatar, still: "./still.svg" };
  }
  return out;
}

function nameOf(config: Sparse): string {
  const n = getPath(config, "name");
  return typeof n === "string" && n ? n : "Emily";
}

async function rebuild(msg: PreviewMessage): Promise<void> {
  widget?.remove();
  session?.dispose();
  session = null;
  document.body.classList.toggle("dark", msg.page === "dark");

  const w = document.createElement("vql-widget");
  widget = w;
  w.config = previewConfig(msg.config, Boolean(msg.talk));
  w.addEventListener("vql-view", (e) => {
    const d = (e as CustomEvent<{ view: string; form: string }>).detail;
    report({ view: d.view, form: d.form, ...(d.view === "ended" ? { ended: true } : {}) });
  });

  if (msg.talk) {
    // A real call: the widget mints its own session from the agent and key.
    if (msg.talk.apiBase) w.apiBase = msg.talk.apiBase;
  } else {
    session = new ReplaySession(recordedTurn(nameOf(msg.config)), SCRIPTS[msg.state] ?? { mic: "live", play: false });
    w.session = session;
    w.sessionSource = { session_id: "preview" };
  }

  const inline = getPath(msg.config, "placement.mode") === "inline";
  (inline ? document.getElementById("inline-slot") : document.body)?.append(w);
  await w.updateComplete;

  if (msg.talk) {
    await w.open();
  } else if (msg.state !== "closed") {
    await w.open();
    await w.updateComplete;
    if (msg.state === "collapsed") w.collapse();
    if (msg.state === "ended") session?.endFromAgent("ended");
  }
  await w.updateComplete;
  report({ view: w.view, form: w.form });
  document.body.dataset.ready = msg.state;
}

let queue: Promise<void> = Promise.resolve();

addEventListener("message", (e: MessageEvent) => {
  if (e.origin !== location.origin) return;
  const msg = e.data as PreviewMessage;
  if (msg?.type !== "vql-builder") return;
  const key = JSON.stringify([msg.state, msg.page, msg.talk ?? null, getPath(msg.config, "placement.mode") ?? "corner"]);
  queue = queue.then(async () => {
    if (widget && key === shownKey) {
      widget.config = previewConfig(msg.config, Boolean(msg.talk));
      await widget.updateComplete;
      report({ view: widget.view, form: widget.form });
      return;
    }
    shownKey = key;
    await rebuild(msg);
  });
});

parent.postMessage({ type: "vql-preview", view: "loading", form: "" } satisfies PreviewReport, location.origin);
