/**
 * The holder: Javier's call, in an offscreen document of the extension
 * (`call.html`), so it lives through every page load on ssilva.cl.
 *
 * Every link on ssilva.cl is a full page load: a project, the project list,
 * the quote page. A call held by a page went down with it and rejoined on the
 * next; here nothing reloads: the peer connection, the microphone and his
 * voice stay up, and the pages come and go around them. The service worker
 * makes this document on the first call (`background.ts`, with the reasons
 * USER_MEDIA and WEB_RTC, which keep it alive through silence).
 *
 * The holder has:
 *   - the call: stock pipecat on `@voqalize/client-transport`, connected with
 *     the `sessions.connect` answer a page minted (a page's fetch carries
 *     ssilva.cl's Origin, which the publishable key allows; this
 *     document's would be the extension's), and his voice, played here;
 *   - the relay of what the pages need to draw his face (`relay.ts`);
 *   - every open Ssilva tab, by browser tab id, with its port, where it
 *     is and whether it is in front; the brain's `tabs_changed`;
 *   - the routing of each brain Action to the tab it belongs on, and the
 *     narration that fires his cues as he speaks (`narration.ts`);
 *   - the moves meant for a tab whose page is loading, kept until that tab's
 *     next page says hello.
 *
 * Pages are followers: each draws the widget and his face from the relay,
 * runs the site adapter, performs the moves sent to it and reports what it
 * shows. The call ends on End (any tab), when the call drops, or when no
 * Ssilva page has been open for 15 s; the holder then closes.
 */

import type { PipecatClient, TransportState } from "@pipecat-ai/client-js";

import { type AppEvent, asUiAction, type Cue, sendAppEvent, type UiAction } from "./actions.gen";
import { makeClient, micState, testHooks } from "./call-client";
import { CatchUp } from "./catch-up";
import { Narration } from "./narration";
import {
  ANY_TAB, type CallState, type FromPage, type HolderAsk, isSite, OURS, PORT, SITE, SITE_COMMANDS, type ToPage,
} from "./protocol";
import { type Metering, meterVoice } from "./meter";
import { type Relaying, relayCall } from "./relay";
import type { Activity, Language, Status } from "./widget";

type Port = chrome.runtime.Port;

/** With no Ssilva page open this long, the call ends and the holder closes. */
const NO_PAGES_MS = 15_000;
/** A move for a tab whose page is loading waits this long for it. */
const PENDING_MS = 20_000;
/** A move a page is making answers within this, or counts as done. */
const MOVE_MS = 45_000;
/** A tab whose page went away and never came back is forgotten after this. */
const AWAY_MS = 20_000;
/** How long a language asked for on the toggle waits for the brain's answer. */
const SWITCH_WAIT_MS = 4000;

interface Tab {
  id: number;
  ports: Set<Port>;
  url: string;
  title: string;
  front: boolean;
  /** When its last port closed (its page went away), or 0. */
  awaySince: number;
}

interface Job {
  id: number;
  tab: number;
  command: string;
  payload: unknown;
  port: Port | null;
  timer: ReturnType<typeof setTimeout>;
  resolve: (why: string | null) => void;
}

const audio = document.getElementById("bot") as HTMLAudioElement;
const tabs = new Map<number, Tab>();
/** The ports whose page has said hello and is not leaving: the ones a move
 *  may be sent to. */
const listening = new WeakSet<Port>();
/** The moves sent to a page and not yet answered, by id. */
const inFlight = new Map<number, Job>();
/** The moves kept for a tab until its page says hello. */
const pending = new Map<number, Job[]>();
let nextJob = 1;
let active: number | null = null;
let lastSiteTab: number | null = null;

let client: PipecatClient | null = null;
let relaying: Relaying | null = null;
/** His voice's loudness, for the still on a page whose face is not up yet. */
let metering: Metering | null = null;
/** The reply in progress, for a page that arrives in the middle of it. */
const catchUp = new CatchUp();
/** Set once the brain can hear the pages (bot ready). */
let ready = false;
const state: CallState = { status: "idle", muted: false, activity: null, language: "es", ready: false };
let asked: Language | null = null;
let askedTimer: ReturnType<typeof setTimeout> | null = null;
let noPages: ReturnType<typeof setTimeout> | null = null;

const log: string[] = [];
function note(line: string): void {
  log.push(`${new Date().toISOString().slice(11, 23)} ${line}`);
  if (log.length > 400) log.shift();
}

// ─── Talking to the pages and the worker ─────────────────────────────────

function post(port: Port, msg: ToPage | { re: number; result: unknown }): void {
  try {
    port.postMessage(msg);
  } catch {
    /* Closed; onDisconnect tidies it. */
  }
}

function broadcast(msg: ToPage): void {
  for (const t of tabs.values()) for (const p of t.ports) post(p, msg);
}

async function toWorker<T>(msg: Record<string, unknown>): Promise<T | null> {
  try {
    return ((await chrome.runtime.sendMessage({ to: "sw", ...msg })) ?? null) as T | null;
  } catch {
    return null;
  }
}

function announce(): void {
  broadcast({ k: "state", ...state });
}

function paint(status: Status, message?: string): void {
  state.status = status;
  state.message = message;
  if (status !== "live") state.activity = null;
  announce();
  // An error is said once, to the pages open now; a page that loads next
  // shows the invite.
  if (status === "error") {
    state.status = "idle";
    state.message = undefined;
  }
}

function setActivity(next: Activity): void {
  if (state.activity === next) return;
  state.activity = next;
  announce();
}

function showLanguage(next: Language): void {
  state.language = next;
  asked = null;
  if (askedTimer) clearTimeout(askedTimer);
  askedTimer = null;
  announce();
}

// ─── The tabs ──────────────────────────────────────────────────────────

function portCount(): number {
  let n = 0;
  for (const t of tabs.values()) n += t.ports.size;
  return n;
}

function tabList() {
  return [...tabs.values()]
    .filter((t) => t.url)
    .map((t) => ({ tab_id: String(t.id), url: t.url, title: t.title }));
}

function sendTabs(): void {
  if (!client || !ready) return;
  if (active === null || !tabs.has(active)) active = tabs.keys().next().value ?? null;
  sendAppEvent(client.sendUIEvent.bind(client), {
    event: "tabs_changed",
    payload: { tabs: tabList(), active: active === null ? "" : String(active) },
  });
}

function setActive(id: number): void {
  const t = tabs.get(id);
  if (t && isSite(t.url)) lastSiteTab = id;
  if (id === active) return;
  active = id;
  sendTabs();
}

function forget(id: number): void {
  tabs.delete(id);
  for (const job of pending.get(id) ?? []) finish(job, "the tab was closed");
  pending.delete(id);
  if (active === id) active = null;
  if (lastSiteTab === id) lastSiteTab = null;
  sendTabs();
}

/** The tab a move belongs on: the one in front, else the site tab last in
 *  front, else any site tab (one whose page is loading counts). */
function siteTab(): number | null {
  const front = active === null ? undefined : tabs.get(active);
  if (front && isSite(front.url)) return front.id;
  if (lastSiteTab !== null && tabs.has(lastSiteTab)) return lastSiteTab;
  for (const t of tabs.values()) if (isSite(t.url)) return t.id;
  return null;
}

// ─── Moves on a page ─────────────────────────────────────────────────────

function finish(job: Job, why: string | null): void {
  clearTimeout(job.timer);
  inFlight.delete(job.id);
  const list = pending.get(job.tab);
  if (list) {
    const i = list.indexOf(job);
    if (i >= 0) list.splice(i, 1);
  }
  job.resolve(why);
}

function send(job: Job, port: Port): void {
  job.port = port;
  inFlight.set(job.id, job);
  clearTimeout(job.timer);
  job.timer = setTimeout(() => finish(job, null), MOVE_MS);
  note(`perform ${job.command} → tab ${job.tab}`);
  post(port, { k: "perform", id: job.id, command: job.command, payload: job.payload });
}

/** Perform an Action on tab `to`: at once when its page is up, else on its
 *  next page's hello. The reason it failed, or `null`. A move that loads
 *  another page counts as done when the page goes; that page reports how it
 *  ended. */
function performOn(to: number, command: string, payload: unknown): Promise<string | null> {
  return new Promise((resolve) => {
    const job: Job = { id: nextJob++, tab: to, command, payload, port: null, timer: 0 as never, resolve };
    const port = newest(to);
    if (port) return send(job, port);
    note(`pending ${command} for tab ${to}`);
    job.timer = setTimeout(() => finish(job, `the page did not come back for ${command}`), PENDING_MS);
    (pending.get(to) ?? pending.set(to, []).get(to)!).push(job);
  });
}

/** The tab's newest page that is up and not leaving. */
function newest(tab: number): Port | null {
  const ports = [...(tabs.get(tab)?.ports ?? [])].filter((p) => listening.has(p));
  return ports.length ? ports[ports.length - 1] : null;
}

/** Send a page Action to the tab it belongs on: a move to another page to a
 *  site tab (the one in front, else the one last in front, brought to the
 *  front, else a new one), anything else to the tab in front. */
async function dispatch(command: string, payload: unknown): Promise<string | null> {
  if (SITE_COMMANDS.has(command)) {
    const to = siteTab();
    if (to === null) {
      // No site tab is open: one opens, and makes the move once up.
      const url = new URL((payload as { path?: string }).path ?? "/", SITE).href;
      const got = await toWorker<{ ok: boolean; tab?: number; error?: string }>({ op: "open_tab", url });
      if (!got?.ok || got.tab === undefined) return got?.error ?? "the tab did not open";
      tabs.set(got.tab, { id: got.tab, ports: new Set(), url, title: "", front: true, awaySince: Date.now() });
      return performOn(got.tab, command, payload);
    }
    if (to !== active) await toWorker({ op: "focus_tab", tab: to });
    return performOn(to, command, payload);
  }
  const to = active ?? siteTab();
  return to === null ? `no tab to ${command} on` : performOn(to, command, payload);
}

/** A cue, as the page Action it stands for. */
function cueMove(cue: Cue): [string, unknown] {
  if (cue.path) return ["navigate", { path: cue.path, heading: cue.heading, text: cue.text, typology: cue.typology }];
  // A project's card on the list, as he names it.
  if (cue.card) return ["show_card", { path: cue.card, name: cue.text }];
  if (cue.photo) return ["show_photos", { which: cue.photos ?? "gallery", index: cue.photo, fullscreen: true }];
  if (cue.typology) return ["select_typology", { label: cue.typology }];
  return ["show_section", { heading: cue.heading, text: cue.text }];
}

/** Whether the tab in front is running a slideshow, as its page last said. */
let slideshowOn = false;

// The screen follows his voice; see `narration.ts`. A cue that misses is
// reported as `cue`, which the brain takes quietly: he has spoken past it.
const narration = new Narration(async (cue) => {
  const [command, payload] = cueMove(cue);
  const why = await dispatch(command, payload);
  if (why) toBrain(null, { event: "command_failed", payload: { command: "cue", reason: why } });
});

async function route(on: PipecatClient, command: string, payload: unknown): Promise<void> {
  const action = asUiAction(command, payload);
  if (!action) {
    console.warn("voqalize: an Action this extension does not know:", command);
    return;
  }
  note(`action ${command}`);
  if (action.command === "cue") {
    narration.add(action.payload);
    return;
  }
  const why = OURS.has(action.command) ? await ours(action) : await dispatch(action.command, action.payload);
  if (why && client === on) toBrain(null, { event: "command_failed", payload: { command, reason: why } });
}

/** The Actions the holder performs itself. A failure comes back as words. */
async function ours(action: UiAction): Promise<string | null> {
  switch (action.command) {
    case "focus_tab": {
      const tab = Number(action.payload.tab_id);
      const got = Number.isInteger(tab) ? await toWorker<{ ok: boolean }>({ op: "focus_tab", tab }) : null;
      return got?.ok ? null : `no tab ${action.payload.tab_id} to bring forward`;
    }
    // The brain's word that the call's language moved, by the toggle, by
    // voice or on request: the toggle follows at once, on every tab.
    case "language_changed":
      showLanguage(action.payload.language);
      return null;
    default:
      return `the call cannot ${action.command}`;
  }
}

/** A page event for the brain: only the front tab's, except those any tab
 *  may send. `from` null: the holder's own. */
function toBrain(from: number | null, event: AppEvent): void {
  if (!client || !ready) return;
  if (from !== null && from !== active && !ANY_TAB.has(event.event)) return;
  sendAppEvent(client.sendUIEvent.bind(client), event);
}

// ─── The call ──────────────────────────────────────────────────────────

/** `sessions.connect` answers with the transport's argument; its `headers`
 *  arrive as JSON and pipecat reads them as a `Headers`. */
function withRealHeaders(response: unknown) {
  const body = response as { webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> } };
  return {
    ...body,
    webrtc_request_params: {
      ...body.webrtc_request_params,
      headers: new Headers(body.webrtc_request_params?.headers ?? {}),
    },
  };
}

async function start(session: unknown, language: Language): Promise<{ ok: boolean; error?: string }> {
  if (client) return { ok: false, error: "a call is already on" };
  state.language = language === "en" ? "en" : "es";
  state.muted = false;
  ready = false;
  state.ready = false;
  const next: PipecatClient = makeClient(audio, {
    onTransportStateChanged: (s: TransportState) => {
      if (client !== next) return;
      note(`transport ${s}`);
      if ((s === "connected" || s === "ready") && state.status !== "live") paint("live");
      if (s === "disconnected" && state.status === "live") end();
    },
    onBotReady: () => {
      if (client !== next || ready) return;
      ready = true;
      state.ready = true;
      note("bot ready");
      announce();
      sendTabs();
    },
    // The avatar draws and never plays a sound, so the bot's track is ours.
    onTrackStarted: (track, participant) => {
      if (participant?.local || track.kind !== "audio") return;
      audio.srcObject = new MediaStream([track]);
      void audio.play().catch((e: unknown) => note(`audio play refused: ${String(e)}`));
      metering?.stop();
      metering = meterVoice(track, (m) => broadcast({ k: "level", m }));
    },
    // A microphone that never opened is a call Javier cannot hear: end it
    // and say why, rather than leave a widget that says "live".
    onDeviceError: (error) => {
      if (client !== next || !error.devices.includes("mic")) return;
      note(`mic error ${error.type}`);
      end(micFailure(error.type, state.language));
    },
    onUICommand: ({ command, payload }) => void route(next, command, payload),
  });
  client = next;
  watch(next);
  relaying = relayCall(next, (msg) => {
    catchUp.saw(msg);
    broadcast(msg);
  });
  paint("connecting");
  try {
    await next.connect(withRealHeaders(session) as never);
    note(`connected ${(session as { session_id?: string }).session_id ?? ""}`);
    return { ok: true };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    note(`connect failed ${text}`);
    if (client === next) end(reason(text, state.language));
    return { ok: false, error: text };
  }
}

function watch(on: PipecatClient): void {
  const heard = (data: unknown) => {
    const d = data as { text?: string; spoken?: boolean; will_be_spoken?: boolean } | undefined;
    if (state.activity !== "speaking") setActivity("speaking");
    if (!d?.text || d.spoken === false || d.will_be_spoken === false) return;
    narration.hear(d.text);
  };
  on.on("botOutput" as never, heard as never);
  on.on("botTtsText" as never, heard as never);
  on.on("userStartedSpeaking" as never, (() => {
    setActivity("listening");
    narration.interrupted();
    // The visitor speaking stops the slideshow on the photo they are looking at.
    if (slideshowOn) {
      slideshowOn = false;
      void dispatch("slideshow", { play: false, which: null, seconds: null });
    }
  }) as never);
  on.on("botLlmStarted" as never, (() => setActivity("thinking")) as never);
  on.on("botStartedSpeaking" as never, (() => {
    setActivity("speaking");
    narration.speaking();
    // The brain answers `language_requested` by moving both legs and
    // confirming aloud in the new language, so his next words are the switch.
    if (asked) showLanguage(asked);
  }) as never);
  on.on("botStoppedSpeaking" as never, (() => {
    setActivity("listening");
    narration.stopped();
  }) as never);
}

function end(message?: string): void {
  const live = client;
  if (!live) return;
  note(`end${message ? `: ${message}` : ""}`);
  client = null;
  ready = false;
  state.ready = false;
  relaying?.stop();
  relaying = null;
  metering?.stop();
  metering = null;
  catchUp.clear();
  narration.clear();
  for (const job of [...inFlight.values()]) finish(job, null);
  for (const [, list] of pending) for (const job of [...list]) finish(job, null);
  pending.clear();
  audio.srcObject = null;
  state.muted = false;
  asked = null;
  paint(message ? "error" : "idle", message);
  try {
    live.disconnectBot();
  } catch {
    // Not connected: there is no call to end on the server's side.
  }
  void live.disconnect().catch(() => {});
}

function toggleMute(): void {
  if (!client) return;
  state.muted = !state.muted;
  client.enableMic(!state.muted);
  announce();
}

/** The toggle, pressed in a call on any tab: the brain is asked, and the
 *  language moves when he next speaks (his confirmation in it), or at once on
 *  the brain's `language_changed`. */
function chooseLanguage(want: Language): void {
  if (!client) return;
  asked = want === state.language ? null : want;
  toBrain(null, { event: "language_requested", payload: { language: want } });
  if (askedTimer) clearTimeout(askedTimer);
  askedTimer = setTimeout(() => {
    asked = null;
    askedTimer = null;
  }, SWITCH_WAIT_MS);
}

// ─── The ports ─────────────────────────────────────────────────────────

async function answer(ask: HolderAsk): Promise<unknown> {
  switch (ask.op) {
    case "mic":
      return { state: await micState() };
    case "call":
      return start(ask.session, ask.language);
  }
}

function handle(tab: Tab, port: Port, msg: FromPage | { ask: HolderAsk; id: number }): void {
  if ("ask" in msg) {
    void answer(msg.ask)
      .catch((error: unknown) => ({ ok: false, error: String(error) }))
      .then((result) => post(port, { re: msg.id, result }));
    return;
  }
  switch (msg.k) {
    case "hello":
    case "where": {
      const moved = tab.url !== msg.url || tab.title !== msg.title;
      tab.url = msg.url;
      tab.title = msg.title;
      tab.front = msg.front;
      if (msg.k === "hello") {
        listening.add(port);
        post(port, { k: "state", ...state });
        // The moves kept for this tab while its page loaded.
        const kept = pending.get(tab.id) ?? [];
        pending.delete(tab.id);
        for (const job of kept) send(job, port);
      }
      if (msg.front) {
        if (tab.id !== active) return setActive(tab.id);
        if (isSite(tab.url)) lastSiteTab = tab.id;
      }
      if (moved || msg.k === "hello") sendTabs();
      return;
    }
    case "catchup":
      // A face just made on this page: the reply so far, after everything
      // already sent to it, which it drops for this.
      post(port, { k: "catchup", msgs: catchUp.replay() });
      return;
    case "leaving":
      note(`tab ${tab.id} leaving`);
      listening.delete(port);
      return;
    case "app":
      if (active === null) active = tab.id;
      if (msg.event === "photo_shown") slideshowOn = Boolean((msg.payload as { playing?: boolean })?.playing);
      else if (msg.event === "viewer_closed" || msg.event === "page_changed") slideshowOn = false;
      toBrain(tab.id, { event: msg.event, payload: msg.payload } as AppEvent);
      return;
    case "report":
      if (tab.id === active) client?.sendClientMessage("avatar", msg.data as never);
      return;
    case "done": {
      const job = inFlight.get(msg.id);
      if (!job) return;
      const outcome = msg.outcome;
      if (outcome?.event === "command_failed") {
        note(`failed ${job.command}: ${String(outcome.payload.reason ?? "")}`);
        return finish(job, String(outcome.payload.reason ?? "failed"));
      }
      note(`done ${job.command}`);
      if (outcome) toBrain(job.tab, outcome as AppEvent);
      return finish(job, null);
    }
    case "mute":
      return toggleMute();
    case "end":
      return end();
    case "lang":
      return chooseLanguage(msg.language);
  }
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PORT) return;
  const id = port.sender?.tab?.id;
  if (id === undefined) return port.disconnect();
  let tab = tabs.get(id);
  if (!tab) {
    tab = { id, ports: new Set(), url: port.sender?.url ?? "", title: "", front: false, awaySince: 0 };
    tabs.set(id, tab);
  }
  tab.ports.add(port);
  tab.awaySince = 0;
  if (noPages) clearTimeout(noPages);
  noPages = null;
  const mine = tab;
  port.onMessage.addListener((msg) => handle(mine, port, msg));
  port.onDisconnect.addListener(() => {
    mine.ports.delete(port);
    // A move that page was making went with it: it loaded the next page,
    // which reports how it ended.
    for (const job of [...inFlight.values()]) if (job.port === port) finish(job, null);
    if (!mine.ports.size) {
      mine.awaySince = Date.now();
      setTimeout(() => {
        if (tabs.get(mine.id) === mine && !mine.ports.size && Date.now() - mine.awaySince >= AWAY_MS) forget(mine.id);
      }, AWAY_MS + 50);
    }
    watchForPages();
  });
});

/** No Ssilva page for `NO_PAGES_MS`: the call ends, and the holder goes. */
function watchForPages(): void {
  if (portCount() || noPages) return;
  noPages = setTimeout(() => {
    noPages = null;
    if (portCount()) return;
    note("no pages: closing");
    end();
    void toWorker({ op: "holder_idle" });
  }, NO_PAGES_MS);
}

chrome.runtime.onMessage.addListener((msg: { to?: string; op?: string; tab?: number }) => {
  if (msg?.to !== "holder") return;
  if (msg.op === "tab_removed" && msg.tab !== undefined && tabs.has(msg.tab)) forget(msg.tab);
});

const MIC_WORDS: Record<Language, Record<string, string>> = {
  es: {
    permissions: "Javier no te escucha: Chrome bloquea el micrófono para la extensión. Permítelo y vuelve a empezar.",
    "in-use": "Javier no te escucha: otra aplicación está usando el micrófono.",
    "not-found": "Javier no te escucha: no se encontró un micrófono.",
    other: "Javier no te escucha: el micrófono no se abrió.",
  },
  en: {
    permissions: "Javier can't hear you: Chrome blocks the microphone for the extension. Allow it, then start again.",
    "in-use": "Javier can't hear you: another app is using the microphone.",
    "not-found": "Javier can't hear you: no microphone was found.",
    other: "Javier can't hear you: the microphone did not open.",
  },
};

function micFailure(type: string, language: Language): string {
  return MIC_WORDS[language][type] ?? MIC_WORDS[language].other;
}

function reason(text: string, language: Language): string {
  const lead = language === "es" ? "No se pudo iniciar la llamada" : "Could not start the call";
  return text.trim() ? `${lead}: ${text}` : `${lead}.`;
}

testHooks({ state, tabs, pending, log, end, client: () => client, route: (c: string, p: unknown) => client && route(client, c, p) });

// Up: every Ssilva page opens its port now (`bridge.ts`).
void toWorker({ op: "holder_up" });
watchForPages();
