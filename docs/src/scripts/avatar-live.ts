/**
 * The live call on /build/avatar: a character picker, a Talk button, and the
 * avatar explaining itself over a real Voqalize session.
 *
 * The page is markdown (`content/docs/build/avatar.md`), so this is an
 * enhancement on top of it rather than the page itself: the markdown carries an
 * empty `#avatar-live` mount with a sentence of fallback text, and `Head.astro`
 * imports this module only on a page that has one. A reader without
 * JavaScript, or an agent reading the `.md` twin, gets the whole page anyway.
 *
 * The browser half of a call is pipecat's: a stock `PipecatClient` over the
 * transport from `@voqalize/client-transport`, with `keepAcrossPageLoads` on so
 * a reload mid-call rejoins it. The only Voqalize-specific code is the request
 * that starts the call and the one line over its answer (`connectRequest`,
 * `withRealHeaders`). The face is `@voqalize/avatar`, handed that same client
 * and a character name.
 *
 * Two lanes reach this file, both typed by `avatar-actions.gen.ts`, which is
 * generated from the brain (`demos/avatar/backend/brain.py`):
 *
 *   * brain → page, as RTVI `ui-command`s: `show_section` scrolls to the
 *     heading on this page that answers the question, and `show_end_card`
 *     closes the call.
 *   * page → brain, one `ui-event`, `ready`: the data channel is open, which is
 *     what the opening wave waits for.
 *
 * **The face is chosen before the call and never during it.** Each character
 * suggests the voices that suit it, so a face and a voice are one choice; the
 * picker writes the face and its first suggested voice into the connect
 * request's `init`, the brain configures that voice before its opener, and the
 * picker locks while the call is up.
 */

import { type APIRequest, PipecatClient, RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { type AvatarInstance, type CharacterInfo, createAvatar, listCharacters } from "@voqalize/avatar";
import { VoqalizeMediaManager, createVoqalizeTransport } from "@voqalize/client-transport";
import { asUiAction, sendAppEvent, unhandledUiAction } from "./avatar-actions.gen";
// As a string, injected when the widget mounts: a stylesheet imported from a
// dynamically imported client script does not reach Astro's page CSS.
import STYLES from "../styles/avatar-live.css?inline";

// ── Wiring ──────────────────────────────────────────────────────────────────

/**
 * The agent and its publishable key, baked in at build. Both are browser-safe
 * (a `pk_` key only mints sessions for its one agent, from the origins it
 * allows), but environment-specific, so they come from the build's env rather
 * than from source. Unset — a local build, CI — the picker still renders and
 * the Talk button says why it cannot call.
 *
 * `/api/v1` is same-origin: the docs host rewrites `/api/**` to the control
 * plane, and `astro dev` proxies it.
 */
const AGENT_ID = (import.meta.env.PUBLIC_AVATAR_AGENT_ID as string | undefined) ?? "";
const PUBLISHABLE_KEY = (import.meta.env.PUBLIC_AVATAR_PK as string | undefined) ?? "";
const API_BASE = "/api/v1";

/** The face the picker starts on unless `?avatar=` names another. The brain
 *  falls back to the same face (`DEFAULT_AVATAR` in its `content.py`). */
const DEFAULT_AVATAR = "emily";

/** Our best characters, which lead the picker in this order. The rest follow
 *  in the runtime's own order, and a name here the runtime does not carry is
 *  skipped. The `/demos/avatar` strip keeps the same list (`AvatarDemo.tsx`). */
const FEATURED = ["emily", "aditya", "javier", "ananya"];

/** The roster with the featured faces first. */
function featuredFirst(characters: readonly CharacterInfo[]): CharacterInfo[] {
  const rank = (name: string) => {
    const i = FEATURED.indexOf(name);
    return i < 0 ? FEATURED.length : i;
  };
  // A stable sort: everything not featured keeps the runtime's order.
  return [...characters].sort((a, b) => rank(a.name) - rank(b.name));
}

/** Two minutes. The page only reports it; the brain enforces it. */
const LIMIT_S = 120;

/**
 * The brain's section ids, mapped to the headings of this page that answer
 * them. The brain sends an id and a heading, never prose: the page already
 * holds every word. An id this map does not know falls back to the heading's
 * own slug, and a heading the page does not have is ignored.
 */
const SECTION_HEADINGS: Record<string, string> = {
  overview: "how-it-works",
  compare: "compared-with-video-avatar-services",
  quickstart: "mount-it-in-your-page",
  states: "what-it-shows-between-turns",
  wire: "gestures-from-your-brain",
  lipsync: "how-the-mouth-stays-in-sync",
  faces: "choosing-a-character",
  limits: "limits",
};

const OPENERS = ["What are you?", "How are you different from HeyGen?", "Wave at me.", "How does the lipsync work?"];

type Phase = "idle" | "connecting" | "live" | "ended";
type Activity = "listening" | "thinking" | "speaking";

const ACTIVITY_LABEL: Record<Activity, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// ── The two Voqalize-specific functions ─────────────────────────────────────

/** The request that starts a call: pipecat's `APIRequest` with our route, the
 *  `Bearer` scheme and the body. `Content-Type` is pipecat's to set. */
function connectRequest(init: Record<string, unknown>): APIRequest {
  return {
    endpoint: `${API_BASE}/sessions.connect`,
    headers: new Headers({ Authorization: `Bearer ${PUBLISHABLE_KEY}` }),
    requestData: { agent_id: AGENT_ID, init } as APIRequest["requestData"],
  };
}

/** `sessions.connect` answers with the transport's argument; JSON has no
 *  `Headers`, so the one line a page writes makes it one again. */
function withRealHeaders(response: unknown) {
  const body = response as {
    webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> };
    session_id?: string;
  };
  return {
    ...body,
    webrtc_request_params: {
      ...body.webrtc_request_params,
      headers: new Headers(body.webrtc_request_params?.headers ?? {}),
    },
  };
}

// ── DOM helpers ─────────────────────────────────────────────────────────────

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

const titled = (name: string) => name.charAt(0).toUpperCase() + name.slice(1);

const slug = (text: string) =>
  text
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s+/g, "-");

function linkedAvatar(): string {
  try {
    return new URLSearchParams(window.location.search).get("avatar")?.toLowerCase() || DEFAULT_AVATAR;
  } catch {
    return DEFAULT_AVATAR;
  }
}

// ── The widget ──────────────────────────────────────────────────────────────

function mountLive(root: HTMLElement): void {
  const provisioned = Boolean(AGENT_ID && PUBLISHABLE_KEY);

  // The picture, and the plate over it: who and what is happening, the clock,
  // the end card. The tile docks to the corner of the window while a call is
  // up and the reader has scrolled away, so the face stays in view while the
  // brain moves the page.
  const face = el("div", { class: "avl-face", "aria-label": "Avatar" });
  const chipText = el("span", {}, "");
  const clock = el("span", { class: "avl-clock" }, "");
  const chip = el("div", { class: "avl-chip", hidden: "" }, el("span", { class: "avl-dot", "aria-hidden": "true" }), chipText, clock);
  const endTitle = el("p", { class: "avl-end-title" }, "");
  const again = el("button", { type: "button", class: "avl-button" }, "Call again");
  const endCard = el("div", { class: "avl-end", hidden: "" }, endTitle, el("p", {}, "The documentation is below."), again);
  const dockEnd = el("button", { type: "button", class: "avl-dock-end", "aria-label": "End the call", title: "End the call" }, "End");
  const tile = el("div", { class: "avl-tile" }, face, chip, endCard, dockEnd);
  const tileSlot = el("div", { class: "avl-tile-slot" }, tile);

  const captions = el("div", { class: "avl-captions", "aria-live": "polite" });

  const talk = el("button", { type: "button", class: "avl-button avl-talk", disabled: "" }, "Talk to it");
  const mute = el("button", { type: "button", class: "avl-button avl-secondary", hidden: "" }, "Mute");
  const end = el("button", { type: "button", class: "avl-button avl-hangup", hidden: "" }, "End call");
  const controls = el("div", { class: "avl-controls" }, talk, mute, end);
  const note = el(
    "p",
    { class: "avl-note" },
    provisioned
      ? "A two-minute voice call in your browser. Ask a question; the avatar answers and scrolls this page to the matching section."
      : "Live calls are not available on this build of the documentation. The characters below are the ones you can mount.",
  );
  const error = el("p", { class: "avl-error", hidden: "" });

  const pickerHead = el("p", { class: "avl-label" }, "Pick a character. Its voice comes with it.");
  const strip = el("div", { class: "avl-strip", role: "group", "aria-label": "Choose a character" });
  strip.append(el("p", { class: "avl-label" }, "Loading the characters…"));

  const openers = el(
    "div",
    { class: "avl-openers" },
    el("p", { class: "avl-label" }, "Try asking"),
    el("ul", {}, ...OPENERS.map((line) => el("li", {}, `“${line}”`))),
  );

  const side = el("div", { class: "avl-side" }, controls, note, error, pickerHead, strip, openers);
  const stage = el("div", { class: "avl-stage" }, el("div", { class: "avl-main" }, tileSlot, captions), side);
  document.head.append(el("style", {}, STYLES));
  root.replaceChildren(stage);
  root.classList.add("avl-root");

  // ── State ──
  const init = { surface: "avatar-docs", avatar: linkedAvatar(), voice: "" };
  let roster: readonly CharacterInfo[] = [];
  let phase: Phase = "idle";
  let activity: Activity = "listening";
  let startedAt: number | null = null;
  let ticker: number | undefined;
  let avatar: AvatarInstance | null = null;
  let micOn = true;

  // ── The client, built once, so the face can follow it from before the call ──
  const manager = new VoqalizeMediaManager();
  const transport = createVoqalizeTransport({ mediaManager: manager, keepAcrossPageLoads: true });
  const client = new PipecatClient({ transport, enableMic: true, enableCam: false });
  const audio = document.createElement("audio");
  audio.autoplay = true;
  manager.bindOutputElement(audio);

  client.on(RTVIEvent.TrackStarted, (track, participant) => {
    if (participant?.local || track.kind !== "audio") return;
    const playing = (audio.srcObject as MediaStream | null)?.getAudioTracks()[0];
    if (playing?.id === track.id) return;
    audio.srcObject = new MediaStream([track]);
    void audio.play().catch(() => {});
  });
  client.on(RTVIEvent.TrackStopped, (track, participant) => {
    if (participant?.local || track.kind !== "audio") return;
    const playing = (audio.srcObject as MediaStream | null)?.getAudioTracks()[0];
    if (playing?.id === track.id) audio.srcObject = null;
  });

  const mountFace = (name: string) => {
    avatar?.destroy();
    face.setAttribute("aria-label", `${titled(name)}, the avatar`);
    avatar = createAvatar({ mount: face, client, character: name });
  };

  // ── Rendering ──
  const render = () => {
    const live = phase === "live";
    root.dataset.phase = phase;
    talk.hidden = live;
    talk.disabled = !provisioned || roster.length === 0 || phase === "connecting";
    talk.textContent = phase === "connecting" ? "Connecting…" : phase === "ended" ? "Call again" : "Talk to it";
    mute.hidden = !live;
    mute.textContent = micOn ? "Mute" : "Unmute";
    mute.setAttribute("aria-pressed", String(!micOn));
    end.hidden = !live;
    chip.hidden = !live;
    chipText.textContent = micOn ? ACTIVITY_LABEL[activity] : "Muted";
    chip.dataset.activity = micOn ? activity : "muted";
    const left = startedAt === null ? LIMIT_S : Math.max(0, LIMIT_S - Math.round((Date.now() - startedAt) / 1000));
    clock.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    pickerHead.textContent = live
      ? "The character and its voice are set for this call."
      : "Pick a character. Its voice comes with it.";
    for (const button of strip.querySelectorAll<HTMLButtonElement>("button")) {
      const on = button.dataset.name === init.avatar;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", String(on));
      button.disabled = live || phase === "connecting";
    }
    strip.classList.toggle("is-locked", live);
  };

  const showError = (text: string | null) => {
    error.hidden = !text;
    error.textContent = text ?? "";
  };

  const pick = (entry: CharacterInfo) => {
    if (phase === "live" || phase === "connecting") return;
    const changed = entry.name !== init.avatar || !avatar;
    init.avatar = entry.name;
    init.voice = entry.suggestedVoices[0] ?? "";
    if (changed) mountFace(entry.name);
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get("avatar") !== entry.name) {
        url.searchParams.set("avatar", entry.name);
        window.history.replaceState(window.history.state, "", url);
      }
    } catch {
      // The URL is a convenience for sharing a face; nothing depends on it.
    }
    render();
  };

  // ── Captions: the words the synthesiser was handed, as they are spoken ──
  let liveLine: HTMLParagraphElement | null = null;
  const retire = () => {
    if (!liveLine) return;
    liveLine.classList.add("is-past");
    const line = liveLine;
    liveLine = null;
    window.setTimeout(() => line.remove(), 11000);
    while (captions.children.length > 3) captions.firstElementChild?.remove();
  };
  client.on(RTVIEvent.BotTtsText, (data: { text: string }) => {
    if (!data.text) return;
    if (!liveLine) {
      liveLine = el("p", { class: "avl-caption" });
      captions.append(liveLine);
    }
    liveLine.textContent = `${liveLine.textContent ?? ""} ${data.text}`.replace(/\s+/g, " ").trim();
    if (/[.!?…]["')\]]?\s*$/.test(data.text)) retire();
  });

  // ── Presence, from pipecat's own events ──
  const setActivity = (next: Activity) => {
    activity = next;
    render();
  };
  client.on(RTVIEvent.UserStartedSpeaking, () => setActivity("listening"));
  client.on(RTVIEvent.BotLlmStarted, () => setActivity("thinking"));
  client.on(RTVIEvent.BotStartedSpeaking, () => setActivity("speaking"));
  client.on(RTVIEvent.BotStoppedSpeaking, () => {
    retire();
    setActivity("listening");
  });

  // ── Brain → page ──
  const goTo = (id: string, title: string) => {
    const target =
      document.getElementById(SECTION_HEADINGS[id] ?? "") ?? document.getElementById(slug(title));
    if (!target) return;
    const block = target.closest(".sl-heading-wrapper") ?? target;
    block.scrollIntoView({ behavior: "smooth", block: "start" });
    for (const old of document.querySelectorAll(".avl-current")) old.classList.remove("avl-current");
    block.classList.add("avl-current");
  };
  const finish = (reason: string) => {
    if (phase === "ended") return;
    phase = "ended";
    endTitle.textContent = reason === "time_limit" ? "That’s the two minutes." : "Call ended.";
    endCard.hidden = false;
    window.clearInterval(ticker);
    retire();
    render();
  };
  client.on(RTVIEvent.UICommand, ({ command, payload }: UICommandData) => {
    const action = asUiAction(command, payload);
    if (!action) return;
    switch (action.command) {
      case "show_section":
        goTo(action.payload.id, action.payload.title);
        break;
      case "show_end_card":
        finish(action.payload.reason);
        break;
      default:
        unhandledUiAction(action);
    }
  });

  // ── Call lifecycle ──
  client.on(RTVIEvent.Connected, () => {
    phase = "live";
    activity = "listening";
    startedAt = Date.now();
    endCard.hidden = true;
    window.clearInterval(ticker);
    ticker = window.setInterval(render, 1000);
    render();
  });
  // The opening wave waits for this: a brain is dialled before the page's
  // data channel exists, so a gesture sent from its greeting would be lost.
  // Sent on BotReady, not Connected: the transport is only "connected" when
  // Connected fires, and sendUIEvent throws until it is "ready", which aborts
  // the connect() that is still awaiting.
  client.on(RTVIEvent.BotReady, () => {
    sendAppEvent((event, data) => client.sendUIEvent(event, data), { event: "ready", payload: {} });
  });
  client.on(RTVIEvent.Disconnected, () => {
    if (phase === "live") finish("hung_up");
    else if (phase === "connecting") {
      phase = "idle";
      render();
    }
  });

  const begin = async () => {
    if (!provisioned || !roster.length) return;
    if (!["initialized", "disconnected", "error"].includes(client.state)) return;
    showError(null);
    endCard.hidden = true;
    captions.replaceChildren();
    phase = "connecting";
    render();
    try {
      const response = await client.startBot(connectRequest({ ...init }));
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      phase = "idle";
      showError(`The call did not start: ${err instanceof Error ? err.message : String(err)}`);
      render();
    }
  };

  const hangUp = async () => {
    try {
      client.disconnectBot();
    } catch {
      // Not connected: there is no call to end on the server's side.
    }
    await client.disconnect();
    finish("hung_up");
  };

  talk.addEventListener("click", () => void begin());
  again.addEventListener("click", () => void begin());
  end.addEventListener("click", () => void hangUp());
  dockEnd.addEventListener("click", () => void hangUp());
  mute.addEventListener("click", () => {
    micOn = !micOn;
    client.enableMic(micOn);
    render();
  });

  // ── Dock the tile while a call is up and the stage is out of view ──
  try {
    new IntersectionObserver(
      ([entry]) => root.classList.toggle("is-away", !entry.isIntersecting),
      { threshold: 0 },
    ).observe(tileSlot);
  } catch {
    // No IntersectionObserver: the tile simply stays where it is.
  }

  // ── The roster ──
  listCharacters().then(
    (listed) => {
      const characters = featuredFirst(listed);
      roster = characters;
      strip.replaceChildren(
        ...characters.map((entry) => {
          const button = el(
            "button",
            { type: "button", class: "avl-pick", "data-name": entry.name, title: titled(entry.name) },
            el("img", { src: entry.still, alt: "", loading: "lazy", width: "64", height: "64" }),
            el("span", {}, titled(entry.name)),
          );
          button.addEventListener("click", () => pick(entry));
          return button;
        }),
      );
      const linked =
        characters.find((c) => c.name === init.avatar) ??
        characters.find((c) => c.name === DEFAULT_AVATAR) ??
        characters[0];
      if (linked) pick(linked);
      render();
    },
    (err: unknown) => {
      console.error(err);
      strip.replaceChildren();
      showError("The characters did not load. Reload the page to try again.");
      render();
    },
  );

  // A reload in the middle of a call carries on with it: the transport
  // remembers the call for this tab, and a bare `connect()` rejoins it.
  if (provisioned && transport.hasLiveCall) {
    phase = "connecting";
    client.connect().catch((err: unknown) => {
      console.info("No call to rejoin:", err);
      phase = "idle";
      render();
    });
  }

  render();
}

const root = document.getElementById("avatar-live");
if (root) mountLive(root);
