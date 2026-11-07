/**
 * One preview frame: a sample page with the real `<vql-widget>` on it, put
 * into the state the builder asks for. A configuration change is applied to
 * the widget in place, so the face and the turn carry on; a change of state,
 * page or placement mode starts the widget again.
 *
 * The face is the real avatar, bundled here and handed to the widget with
 * `setAvatarLoader`. In a replay it follows the preview's voice (`voice.ts`);
 * in a real call, the call's own client.
 *
 * Imports only the package's public entry points.
 */

import { type VqlWidget, defineElements, setAvatarLoader } from "@voqalize/web/widgets";
import type { PreviewMessage, PreviewReport, PreviewState } from "./protocol.js";
import { ReplaySession, type ReplayScript, recordedTurn } from "./replay.js";
import { type Sparse, getPath } from "./schema-form.js";
import { PreviewVoice, spokenTurn } from "./voice.js";

const avatarModule = () => import("@voqalize/avatar");
setAvatarLoader(avatarModule);
defineElements();

/** The character a preview shows when the form names none: the widget's own examples use her. */
const DEFAULT_CHARACTER = "emily";

/** One voice per frame, kept across rebuilds: a page may hold only so many audio contexts. */
const voice = new PreviewVoice();
// Reachable from the console and the builder's own checks, to read the level and the clock.
(globalThis as { vqlPreviewVoice?: PreviewVoice }).vqlPreviewVoice = voice;
// A click inside the frame starts the audio clock as well as one in the builder does.
for (const type of ["pointerdown", "keydown"]) addEventListener(type, () => void voice.resume(), { capture: true });

/** Each character's still, from the avatar's own roster, shown until the face has drawn. */
let stills: Promise<Map<string, string>> | null = null;
function stillOf(character: string): Promise<string | undefined> {
  stills ??= avatarModule()
    .then((m) => m.listCharacters())
    .then((list) => new Map(list.map((c) => [c.name, c.still])))
    .catch(() => new Map());
  const timeout = new Promise<undefined>((r) => setTimeout(() => r(undefined), 1500));
  return Promise.race([stills.then((m) => m.get(character)), timeout]);
}

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

/** The character the frame shows: the form's, or the default one. */
function characterOf(config: Sparse): string | undefined {
  if (getPath(config, "avatar") === false) return undefined;
  const c = getPath(config, "avatar.character");
  return typeof c === "string" && c ? c : DEFAULT_CHARACTER;
}

/**
 * What the frame shows: the configuration with a character (the default one
 * where the form names none) and its still, and nothing remembered.
 */
function previewConfig(config: Sparse, talking: boolean, still?: string): Sparse {
  const out = structuredClone(config);
  if (!talking) {
    delete out.agent;
    delete out.key;
  }
  const placement = (out.placement ?? {}) as Sparse;
  out.placement = { ...placement, remember: "off" };
  const character = characterOf(config);
  if (character) {
    const avatar: Sparse = { ...((out.avatar ?? {}) as Sparse), character };
    if (avatar.still === undefined) avatar.still = still ?? "./still.svg";
    out.avatar = avatar;
  }
  return out;
}

async function rebuild(msg: PreviewMessage): Promise<void> {
  widget?.remove();
  session?.dispose();
  session = null;
  document.body.classList.toggle("dark", msg.page === "dark");

  const w = document.createElement("vql-widget");
  widget = w;
  // A call's agent and key may come from the page address or the local file
  // rather than the form, so they go into the config here.
  const character = characterOf(msg.config);
  const config = previewConfig(msg.config, Boolean(msg.talk), character ? await stillOf(character) : undefined);
  if (msg.talk) {
    config.agent = msg.talk.agent;
    config.key = msg.talk.key;
  }
  w.config = config;
  w.addEventListener("vql-view", (e) => {
    const d = (e as CustomEvent<{ view: string; form: string }>).detail;
    report({ view: d.view, form: d.form, ...(d.view === "ended" ? { ended: true } : {}) });
  });

  if (msg.talk) {
    // A real call: the widget mints its own session from the agent and key.
    if (msg.talk.apiBase) w.apiBase = msg.talk.apiBase;
  } else {
    const spoken = character ? spokenTurn(character) : undefined;
    session = new ReplaySession(recordedTurn(spoken), SCRIPTS[msg.state] ?? { mic: "live", play: false }, character ? voice : undefined);
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
  // A new character starts the turn again, in that character's voice.
  // Heard or not changes at once. Every frame starts its audio clock once a
  // click in the builder allows it, heard or not, because the face moves its
  // lips to the voice on the track.
  voice.setAudible(Boolean(msg.sound));
  void voice.resume();
  const key = JSON.stringify([msg.state, msg.page, msg.talk ?? null, getPath(msg.config, "placement.mode") ?? "corner", characterOf(msg.config) ?? null, msg.run ?? 0]);
  queue = queue.then(async () => {
    if (widget && key === shownKey) {
      const character = characterOf(msg.config);
      widget.config = previewConfig(msg.config, Boolean(msg.talk), character ? await stillOf(character) : undefined);
      await widget.updateComplete;
      report({ view: widget.view, form: widget.form });
      return;
    }
    shownKey = key;
    await rebuild(msg);
  });
});

parent.postMessage({ type: "vql-preview", view: "loading", form: "" } satisfies PreviewReport, location.origin);
