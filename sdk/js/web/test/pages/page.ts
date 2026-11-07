/**
 * The component page: one widget, put into the state the URL's `?state=`
 * names, with a session that has no network. Served under a strict CSP by
 * `serve.mjs`; the Playwright suite screenshots every state.
 */

// The element modules themselves, not the `widgets` entry, which imports
// every element statically: this page loads what a page using the widget
// loads, so the lazy elements arrive as their own files.
import { defineElements } from "../../src/elements/define.js";
import { setAvatarLoader } from "../../src/elements/face.js";
import type { VqlWidget } from "../../src/elements/widget.js";
import type { WidgetConfigInput } from "../../src/config/types.js";
import { FakeSession } from "../support/fake-session.js";

// No avatar on this page: the face shows its still, as it does before the avatar draws.
setAvatarLoader(() => Promise.reject(new Error("no avatar on the component page")));
defineElements();

const violations: string[] = [];
document.addEventListener("securitypolicyviolation", (e) => {
  violations.push(`${e.violatedDirective} ${e.blockedURI}`);
});
(window as unknown as { __violations: string[] }).__violations = violations;

const params = new URLSearchParams(location.search);
const state = params.get("state") ?? "closed-pill";
/** `?scheme=dark` draws any state in the dark scheme. */
const dark = params.get("scheme") === "dark";

const mic = (id: string, label: string) => ({ deviceId: id, label, kind: "audioinput", groupId: "" }) as MediaDeviceInfo;
const speaker = (id: string, label: string) => ({ deviceId: id, label, kind: "audiooutput", groupId: "" }) as MediaDeviceInfo;

const session = new FakeSession({
  devices: {
    mics: [mic("default", "MacBook Pro Microphone"), mic("usb", "Jabra Evolve2 65")],
    speakers: [speaker("default", "MacBook Pro Speakers"), speaker("usb", "Jabra Evolve2 65")],
    micId: "default",
    speakerId: "default",
    canPickSpeaker: true,
  },
});
session.onConnect = (s) => {
  s.patch({ status: "connected", agent: "speaking" });
  s.mic.patch({ state: "live", device: "live", everLive: true, permission: "granted", level: 0.16 });
};

const base: WidgetConfigInput = {
  name: "Emily",
  avatar: { character: "emily", still: "still.svg", shape: "rounded" },
  theme: { brand: "#c2410c" },
  placement: { remember: "off" },
};

const scenarios: Record<
  string,
  { config?: WidgetConfigInput; real?: boolean; run?: (w: VqlWidget) => Promise<void> | void; setup?: () => void }
> = {
  "closed-pill": {},
  "closed-face": { config: { launcher: { style: "face" } } },
  "closed-card": { config: { launcher: { style: "card", tagline: "Ask me about sofas, sizes and delivery." } } },
  "closed-none": {
    config: { launcher: { style: "none" } },
    setup: () => {
      const b = document.createElement("button");
      b.className = "own-launcher";
      b.textContent = "Talk to us";
      document.querySelector("main")?.append(b);
    },
  },
  "closed-slotted": {
    setup: () => {
      const b = document.createElement("button");
      b.className = "own-launcher";
      b.slot = "launcher";
      b.textContent = "Ask Emily";
      document.querySelector("vql-widget")?.append(b);
    },
  },
  "open-card": { run: speak },
  "open-card-circle": { config: { avatar: { character: "emily", still: "still.svg", shape: "circle" } }, run: speak },
  "open-card-side": {
    setup: () => {
      const side = document.createElement("div");
      side.slot = "side";
      side.className = "side-panel";
      const h = document.createElement("h3");
      h.textContent = "Linden 3-seater";
      const p = document.createElement("p");
      p.textContent = "Oak legs, washable linen cover, 212 cm wide.";
      side.append(h, p);
      document.querySelector("vql-widget")?.append(side);
    },
    run: speak,
  },
  "open-hero": { config: { open: { style: "hero" } }, run: speak },
  "open-large-top-left": { config: { open: { size: "large" }, placement: { anchor: "top-left", remember: "off", topClear: 64 } }, run: speak },
  inline: { config: { placement: { mode: "inline" } }, run: speak },
  "collapsed-bubble": { run: async (w) => (await speak(w), w.collapse()) },
  "collapsed-pill": { config: { collapsed: { style: "pill" } }, run: async (w) => (await speak(w), w.collapse()) },
  "collapsed-muted": { run: async (w) => (await open(w), session.setMuted(true), w.collapse()) },
  "mic-asking": {
    run: async (w) => {
      session.onConnect = (s) => {
        s.patch({ status: "connecting", agent: "idle" });
        s.mic.patch({ state: "asking", device: "asking", permission: "prompt" });
      };
      await open(w);
      await new Promise((r) => setTimeout(r, 900));
    },
  },
  "mic-blocked": {
    run: async (w) => {
      session.onConnect = (s) => {
        s.patch({ status: "connected", agent: "listening" });
        s.mic.patch({ state: "blocked", device: "blocked", permission: "denied" });
      };
      await open(w);
    },
  },
  "mic-muted": { run: async (w) => (await open(w), session.setMuted(true)) },
  "mic-hint-devices": {
    run: async (w) => {
      await open(w);
      session.patch({ agent: "listening" });
      session.mic.patch({ hint: true, level: 0.01 });
      await w.updateComplete;
      const micEl = w.shadowRoot?.querySelector("vql-mic");
      micEl?.dispatchEvent(new CustomEvent("vql-devices", { detail: { open: true } }));
    },
  },
  ended: { run: async (w) => (await speak(w), session.patch({ status: "ended", agent: "idle", end: { by: "agent", reason: "ended" } })) },
  "voice-only": { config: { avatar: false }, run: speak },
  "face-background": {
    config: { avatar: { character: "emily", still: "still.svg", background: "linear-gradient(160deg, #fde68a, #fb923c)" } },
    run: speak,
  },
  dark: { config: { theme: { scheme: "dark", brand: "#fb923c" } }, setup: () => document.body.classList.add("dark"), run: speak },
  "dark-closed": { config: { theme: { scheme: "dark" }, launcher: { style: "card" } }, setup: () => document.body.classList.add("dark") },
  "captions-under": { config: { captions: { position: "under" } }, run: speak },
  "mobile-launcher": {},
  "mobile-sheet": { run: speak },
  "mobile-collapsed": { run: async (w) => (await speak(w), w.collapse()) },

  // The mic pill. These with a fake session put the mic in a state by hand.
  "pill-permission": {
    run: async (w) => {
      session.onConnect = (s) => {
        s.patch({ status: "connected", agent: "listening" });
        s.mic.patch({ state: "blocked", device: "blocked", permission: "denied" });
      };
      await open(w);
    },
  },
  "pill-asking": {
    run: async (w) => {
      session.onConnect = (s) => {
        s.patch({ status: "connecting", agent: "idle" });
        s.mic.patch({ state: "asking", device: "asking", permission: "prompt" });
      };
      await open(w);
      await new Promise((r) => setTimeout(r, 900));
    },
  },
  "pill-muted": { run: async (w) => (await open(w), session.patch({ agent: "listening" }), session.setMuted(true)) },
  "pill-check-hint": {
    run: async (w) => {
      await open(w);
      session.patch({ agent: "listening" });
      session.mic.patch({ hint: true, level: 0.01 });
    },
  },
  "pill-check-phone": {
    run: async (w) => {
      await open(w);
      session.patch({ agent: "listening" });
      session.mic.patch({ hint: true, level: 0.01 });
    },
  },
  // These run the package's own session over a fake track, permission and
  // device list; the test moves them through `window.__vql`.
  "pill-real": { real: true, run: open },
  "pill-off": { config: { mic: { pill: false } }, real: true, run: open },
  // Captions, the device menu and the coach mark all off, and a healthy mic:
  // none of their chunks, nor the pill's, should load.
  lean: {
    config: { captions: { mode: "off" }, controls: { devices: false }, mic: { coach: false } },
    run: speak,
  },
};

async function open(w: VqlWidget): Promise<void> {
  w.sessionSource = { session_id: "page" };
  await w.open();
  await w.updateComplete;
}

async function speak(w: VqlWidget): Promise<void> {
  await open(w);
  session.fire("agentStarted");
  session.fire("agentSentence", "Hi, I'm Emily. Which room is the sofa for?");
  for (const word of ["Hi,", "I'm", "Emily.", "Which", "room"]) session.fire("agentWord", word);
}

async function main(): Promise<void> {
  const scenario = scenarios[state];
  if (!scenario) throw new Error(`no scenario ${state}`);
  const w = document.createElement("vql-widget");
  w.warn = (m) => console.warn(m);
  w.config = { ...base, ...scenario.config, ...(dark ? { theme: { scheme: "dark", brand: "#fb923c" } } : {}) };
  if (dark) document.body.classList.add("dark");
  if (scenario.real) {
    const { realSession } = await import("./real-session.js");
    const real = await realSession();
    (window as unknown as { __vql: unknown }).__vql = real.controls;
    w.session = real.session;
  } else {
    w.session = session;
  }
  const inline = scenario.config?.placement?.mode === "inline";
  (inline ? document.getElementById("inline-slot") : document.body)?.append(w);
  scenario.setup?.();
  await w.updateComplete;
  await scenario.run?.(w);
  await w.updateComplete;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  document.body.dataset.ready = state;
}

void main();
