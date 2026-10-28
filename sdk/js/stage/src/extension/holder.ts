/**
 * The holder: the call, in an offscreen document of the extension
 * (`call.html`), so it lives through every page load on every host of the
 * site and every load between them. Nothing reloads here: the peer
 * connection, the microphone and the voice stay up, and the pages come and go
 * around them. The service worker makes this document on the first call.
 *
 * The holder has:
 *   - the call: pipecat, made by the site's `makeClient` and connected with
 *     the `sessions.connect` answer a page minted (a page's fetch carries the
 *     site's Origin, which the publishable key allows), and the voice, played
 *     here;
 *   - the relay of what the pages need to draw the face;
 *   - every open tab of the site, by browser tab id, with its port, where it
 *     is and whether it is in front; the agent's `tabs_changed`;
 *   - Stage: the timeline that fires the reply's cues as the voice reaches
 *     them, the moves a tool asks for (now, or once the voice is quiet), each
 *     made on the tab in front, and one `stage_result` per move back to the
 *     agent; the site's own Actions, routed the same way;
 *   - the jobs meant for a tab whose page is loading, kept until that tab's
 *     next page says hello.
 *
 * Pages are followers: each draws the widget and the face from the relay,
 * makes the moves sent to it and reports what it shows. The call ends on End
 * (any tab), when the call drops, or when no page of the site has been open
 * for 15 s; the holder then closes.
 */

import type { PipecatClient, PipecatClientOptions, TransportState } from "@pipecat-ai/client-js";

import { type Attached, attachStage, interruptedResult, staleResult } from "../attach";
import { Timeline } from "../timeline";
import { sendAppEvent, type StageCue, type StageMove, type StageResult } from "../wire.gen";
import { CatchUp } from "./catch-up";
import type { CallState, FromPage, HolderAsk, Job, MicState, ToPage } from "./protocol";
import { PORT } from "./protocol";
import { type Relaying, relayCall } from "./relay";
import { isSitePage, type SiteConfig } from "./site";
import type { Activity, Language, Status } from "./widget";

type Port = chrome.runtime.Port;
type Callbacks = NonNullable<PipecatClientOptions["callbacks"]>;

/** With no page of the site open this long, the call ends and the holder closes. */
export const NO_PAGES_MS = 15_000;
/** A job for a tab whose page is loading waits this long for it. */
const PENDING_MS = 20_000;
/** A job a page is making answers within this. */
const MOVE_MS = 45_000;
/** A tab whose page went away and never came back is forgotten after this. */
const AWAY_MS = 20_000;
/** How long a language asked for on the toggle waits for the agent's answer. */
const SWITCH_WAIT_MS = 4000;

/** Pacing against the voice (see `settle`). */
const WORDS_PER_S = 2.8;
const START_WAIT_MS = 4000;
const AFTER_WORDS_SLACK_MS = 6000;
export const QUIET_WAIT_MS = 3000;
const QUIET_HOLD_MS = 300;

/** What the site's hooks may do with the call. */
export interface HolderApi {
  readonly state: Readonly<CallState>;
  /** The call is live and the agent hears the pages. */
  live(): boolean;
  /** Show `language` as the call's, on every page. */
  setLanguage(language: Language): void;
  /** Wait for the voice to start (when `waitStart`, up to 4 s) and then to
   *  stop and stay quiet, all within `capMs`. Off a call, nothing. */
  settle(capMs: number, waitStart: boolean): Promise<void>;
  /** Hold a load until `afterWords` words of the voice have been said (the
   *  pacing the page loads are written against). */
  paced(afterWords: number): Promise<void>;
  /** Make a job on the tab it belongs on; why it could not, or `null`. */
  dispatch(job: Job): Promise<string | null>;
  /** Send one of the site's events to the agent. */
  toAgent(event: string, payload: unknown): void;
  /** The URL of the tab a move would be made on. */
  frontUrl(): string | null;
  /** Counts the moves sent to pages: a wait can tell one came after it. */
  seq(): number;
  note(line: string): void;
}

export interface HolderConfig {
  /** Make the call's pipecat client, with the site's transport and media.
   *  The voice plays in `output`. */
  makeClient(output: HTMLAudioElement, callbacks: Callbacks): PipecatClient;
  /** The extension's microphone permission (the Permissions API by default). */
  micState?(): Promise<MicState>;
  /** The site's own Actions the holder makes itself, rather than a page:
   *  why it failed, or `null`. */
  holderCommands?: Record<string, (payload: unknown, api: HolderApi) => Promise<string | null>>;
  /** Called before a job is sent to a page: hold it against the voice. By
   *  default a `when: "quiet"` move waits for quiet. */
  pace?(job: Job, move: StageMove | null, api: HolderApi): Promise<void>;
  /** The page a new tab opens on for a job, when no tab of the site is open. */
  firstPage?(job: Job, api: HolderApi): string;
  /** A cue to make at once rather than on its words (a reply that opens on
   *  another page loads it while the voice starts). */
  fireEarly?(cue: StageCue, api: HolderApi): boolean;
  /** The site's events the agent takes from any tab, not only the front one. */
  anyTab?: readonly string[];
  /** A site Action that could not be made. */
  onSiteFailed?(command: string, why: string, api: HolderApi): void;
  /** Words for a microphone that did not open, and a call that did not start. */
  micFailure?(type: string, language: Language): string;
  failure?(text: string, language: Language): string;
  /** Tests reach into the holder through this; nothing in a real build. */
  testHooks?(holder: unknown): void;
}

interface Tab {
  id: number;
  ports: Set<Port>;
  url: string;
  title: string;
  front: boolean;
  awaySince: number;
}

/** How a job ended, as the holder sees it. */
type Ended =
  | { k: "result"; result: StageResult | null; deferred?: boolean }
  | { k: "failed"; why: string }
  // The page went away with it (it loaded another), or never answered.
  | { k: "gone" }
  | { k: "timeout" };

interface Running {
  id: number;
  tab: number;
  job: Job;
  port: Port | null;
  timer: ReturnType<typeof setTimeout>;
  resolve: (ended: Ended) => void;
}

export function startHolder(site: SiteConfig, config: HolderConfig): void {
  const audio = (document.getElementById("bot") as HTMLAudioElement | null) ?? document.body.appendChild(document.createElement("audio"));
  audio.autoplay = true;
  const isSite = (url: string) => isSitePage(site, url);
  const anyTab = new Set(["stage_result", ...(config.anyTab ?? [])]);

  const tabs = new Map<number, Tab>();
  const listening = new WeakSet<Port>();
  const inFlight = new Map<number, Running>();
  const pending = new Map<number, Running[]>();
  let nextJob = 1;
  let active: number | null = null;
  let lastSiteTab: number | null = null;

  let client: PipecatClient | null = null;
  let stage: Attached | null = null;
  let relaying: Relaying | null = null;
  const catchUp = new CatchUp();
  let ready = false;
  const state: CallState = { status: "idle", muted: false, activity: null, language: site.opening, ready: false };
  let asked: Language | null = null;
  let askedTimer: ReturnType<typeof setTimeout> | null = null;
  let noPages: ReturnType<typeof setTimeout> | null = null;
  let botSpeaking = false;
  let botStarts = 0;
  let seq = 0;

  const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
  const log: string[] = [];
  function note(line: string): void {
    log.push(`${new Date().toISOString().slice(11, 23)} ${line}`);
    if (log.length > 400) log.shift();
  }

  // ─── Talking to the pages and the worker ───────────────────────────────

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

  const announce = () => broadcast({ k: "state", ...state });

  function paint(status: Status, message?: string): void {
    state.status = status;
    state.message = message;
    if (status !== "live") state.activity = null;
    announce();
    // An error is said once, to the pages open now.
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
    timeline.setLang(next);
    asked = null;
    if (askedTimer) clearTimeout(askedTimer);
    askedTimer = null;
    announce();
  }

  // ─── The tabs ──────────────────────────────────────────────────────────

  const portCount = () => [...tabs.values()].reduce((n, t) => n + t.ports.size, 0);

  function sendTabs(): void {
    if (!client || !ready) return;
    if (active === null || !tabs.has(active)) active = tabs.keys().next().value ?? null;
    const list = [...tabs.values()].filter((t) => t.url).map((t) => ({ tab_id: String(t.id), url: t.url, title: t.title }));
    client.sendUIEvent("tabs_changed", { tabs: list, active: active === null ? "" : String(active) });
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
    for (const job of pending.get(id) ?? []) finish(job, { k: "failed", why: "the tab was closed" });
    pending.delete(id);
    if (active === id) active = null;
    if (lastSiteTab === id) lastSiteTab = null;
    sendTabs();
  }

  /** The tab a job belongs on: the one in front, else the site tab last in
   *  front, else any site tab (one whose page is loading counts). */
  function siteTab(): number | null {
    const front = active === null ? undefined : tabs.get(active);
    if (front && isSite(front.url)) return front.id;
    if (lastSiteTab !== null && tabs.has(lastSiteTab)) return lastSiteTab;
    for (const t of tabs.values()) if (isSite(t.url)) return t.id;
    return null;
  }

  const frontUrl = () => {
    const t = siteTab();
    return t === null ? null : (tabs.get(t)?.url ?? null);
  };

  // ─── Jobs on a page ────────────────────────────────────────────────────

  function finish(job: Running, ended: Ended): void {
    clearTimeout(job.timer);
    inFlight.delete(job.id);
    const list = pending.get(job.tab);
    if (list) {
      const i = list.indexOf(job);
      if (i >= 0) list.splice(i, 1);
    }
    job.resolve(ended);
  }

  function send(job: Running, port: Port): void {
    job.port = port;
    inFlight.set(job.id, job);
    clearTimeout(job.timer);
    job.timer = setTimeout(() => finish(job, { k: "timeout" }), MOVE_MS);
    note(`perform ${job.job.kind === "stage" ? job.job.move : job.job.command} → tab ${job.tab}`);
    post(port, { k: "perform", id: job.id, job: job.job });
  }

  function newest(tab: number): Port | null {
    const ports = [...(tabs.get(tab)?.ports ?? [])].filter((p) => listening.has(p));
    return ports.length ? ports[ports.length - 1]! : null;
  }

  /** Make a job on tab `to`: at once when its page is up, else on its next
   *  page's hello. */
  function performOn(to: number, job: Job): Promise<Ended> {
    return new Promise((resolve) => {
      const running: Running = { id: nextJob++, tab: to, job, port: null, timer: 0 as never, resolve };
      const port = newest(to);
      if (port) return send(running, port);
      note(`pending for tab ${to}`);
      running.timer = setTimeout(() => finish(running, { k: "failed", why: "the page did not come back" }), PENDING_MS);
      (pending.get(to) ?? pending.set(to, []).get(to)!).push(running);
    });
  }

  /** Send a job to the tab it belongs on: a site tab (the one in front, else
   *  the one last in front, brought to the front, else a new one). */
  async function route(job: Job): Promise<Ended> {
    seq++;
    const to = siteTab();
    if (to === null) {
      const url = config.firstPage?.(job, api) ?? site.home;
      const got = await toWorker<{ ok: boolean; tab?: number; error?: string }>({ op: "open_tab", url });
      if (!got?.ok || got.tab === undefined) return { k: "failed", why: got?.error ?? "the tab did not open" };
      tabs.set(got.tab, { id: got.tab, ports: new Set(), url, title: "", front: true, awaySince: Date.now() });
      return performOn(got.tab, job);
    }
    if (to !== active) await toWorker({ op: "focus_tab", tab: to });
    return performOn(to, job);
  }

  /** The one result a Stage job reports, however it ended. */
  function resultOf(job: Extract<Job, { kind: "stage" }>, ended: Ended): StageResult | null {
    const base = { call_ref: job.call_ref, move: job.move, refused: [], ms: 0 };
    switch (ended.k) {
      case "result":
        return ended.result;
      case "failed":
        return { ...base, outcome: "failed", detail: ended.why, moved: false };
      case "gone":
        return { ...base, outcome: "applied", detail: "the page loaded another", moved: true };
      case "timeout":
        return { ...base, outcome: "unknown", detail: "the page did not answer", moved: false };
    }
  }

  async function makeStage(job: Extract<Job, { kind: "stage" }>, move: StageMove | null, on: PipecatClient): Promise<void> {
    if (config.pace) await config.pace(job, move, api);
    else if (move?.when === "quiet") await settle(QUIET_WAIT_MS, false);
    if (client !== on) return;
    const result = resultOf(job, await route(job));
    if (result && client === on) stage?.send(result);
  }

  const cueJob = (cue: StageCue): Extract<Job, { kind: "stage" }> => ({
    kind: "stage",
    move: cue.move,
    args: cue.args,
    call_ref: cue.call_ref,
  });

  // The screen follows the voice: cues fire as their words are heard, one
  // move at a time, on the tab in front.
  const timeline = new Timeline(
    async (cue) => {
      if (client) await makeStage(cueJob(cue), null, client);
    },
    {
      lang: state.language,
      onDrop: (cue) => stage?.send(staleResult(cue)),
      onFire: (cue, how) => note(`cue ${cue.verb} (${how})`),
    },
  );

  async function until(test: () => boolean, ms: number): Promise<boolean> {
    const end = Date.now() + Math.max(0, ms);
    while (!test()) {
      if (Date.now() >= end) return false;
      await sleep(50);
    }
    return true;
  }

  async function settle(cap: number, waitStart: boolean): Promise<void> {
    if (!client) return;
    const t0 = Date.now();
    const left = () => cap - (Date.now() - t0);
    if (waitStart) {
      const starts = botStarts;
      await until(() => botSpeaking || botStarts > starts, Math.min(START_WAIT_MS, left()));
    }
    while (left() > 0) {
      if (!(await until(() => !botSpeaking, left()))) break;
      await sleep(QUIET_HOLD_MS);
      if (!botSpeaking) break;
    }
  }

  async function paced(afterWords: number): Promise<void> {
    const cap = afterWords > 0 ? (afterWords / WORDS_PER_S) * 1000 + AFTER_WORDS_SLACK_MS : QUIET_WAIT_MS;
    await settle(cap, afterWords > 0);
  }

  function toAgent(from: number | null, event: string, payload: unknown): void {
    if (!client || !ready) return;
    if (from !== null && from !== active && !anyTab.has(event)) return;
    client.sendUIEvent(event, payload);
  }

  const api: HolderApi = {
    state,
    live: () => Boolean(client && ready),
    setLanguage: showLanguage,
    settle,
    paced,
    async dispatch(job) {
      const ended = await route(job);
      if (ended.k === "failed") return ended.why;
      if (ended.k === "result" && ended.result && ended.result.outcome !== "applied") return ended.result.detail ?? ended.result.outcome;
      return null;
    },
    toAgent: (event, payload) => toAgent(null, event, payload),
    frontUrl,
    seq: () => seq,
    note,
  };

  async function siteCommand(on: PipecatClient, command: string, payload: unknown): Promise<void> {
    note(`action ${command}`);
    const own = config.holderCommands?.[command];
    const why = own ? await own(payload, api) : await api.dispatch({ kind: "site", command, payload });
    if (why && client === on) {
      note(`${command} failed: ${why}`);
      config.onSiteFailed?.(command, why, api);
    }
  }

  // ─── The call ──────────────────────────────────────────────────────────

  /** `sessions.connect` answers with the transport's argument; its `headers`
   *  arrive as JSON and pipecat reads them as a `Headers`. */
  function withRealHeaders(response: unknown) {
    const body = response as { webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> } };
    return {
      ...body,
      webrtc_request_params: { ...body.webrtc_request_params, headers: new Headers(body.webrtc_request_params?.headers ?? {}) },
    };
  }

  const micFailure = (type: string) =>
    config.micFailure?.(type, state.language) ?? `The microphone did not open (${type}).`;
  const failure = (text: string) =>
    config.failure?.(text, state.language) ?? (text.trim() ? `Could not start the call: ${text}` : "Could not start the call.");

  async function start(session: unknown, language: Language): Promise<{ ok: boolean; error?: string }> {
    if (client) return { ok: false, error: "a call is already on" };
    const known = site.widget.languages.some((l) => l.code === language);
    state.language = known ? language : site.opening;
    timeline.setLang(state.language);
    state.muted = false;
    ready = false;
    state.ready = false;
    const next: PipecatClient = config.makeClient(audio, {
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
      },
      // A microphone that never opened is a call nobody can hear: end it and
      // say why.
      onDeviceError: (error) => {
        if (client !== next || !error.devices.includes("mic")) return;
        note(`mic error ${error.type}`);
        end(micFailure(error.type));
      },
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
      if (client === next) end(failure(text));
      return { ok: false, error: text };
    }
  }

  function watch(on: PipecatClient): void {
    stage = attachStage(on, {
      timeline,
      onCue: (cue) => {
        if (config.fireEarly?.(cue, api) && !timeline.pending().length) void makeStage(cueJob(cue), null, on);
        else timeline.add(cue);
      },
      onMove: (m) =>
        void makeStage({ kind: "stage", move: m.move, args: m.args, call_ref: m.call_ref }, m, on),
      onSiteCommand: (command, payload) => void siteCommand(on, command, payload),
      onHeard: () => {
        if (state.activity !== "speaking") setActivity("speaking");
      },
      onBotStarted: () => {
        botSpeaking = true;
        botStarts++;
        setActivity("speaking");
        // The agent answers `language_requested` by moving both legs and
        // confirming aloud in the new language, so the next words are the switch.
        if (asked) showLanguage(asked);
      },
      onBotStopped: () => {
        botSpeaking = false;
        setActivity("listening");
      },
      onUserStarted: (dropped) => {
        setActivity("listening");
        if (dropped.length) note(`interrupted: ${dropped.length} cue(s) dropped`);
      },
    });
    on.on("botLlmStarted" as never, (() => setActivity("thinking")) as never);
  }

  function end(message?: string): void {
    const live = client;
    if (!live) return;
    note(`end${message ? `: ${message}` : ""}`);
    client = null;
    ready = false;
    state.ready = false;
    stage?.detach();
    stage = null;
    relaying?.stop();
    relaying = null;
    catchUp.clear();
    timeline.clear();
    botSpeaking = false;
    for (const job of [...inFlight.values()]) finish(job, { k: "gone" });
    for (const [, list] of pending) for (const job of [...list]) finish(job, { k: "gone" });
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

  /** The toggle, pressed in a call on any tab: the agent is asked, and the
   *  language moves when the voice next speaks (its confirmation in it), or
   *  at once when a site hook calls `setLanguage`. */
  function chooseLanguage(want: Language): void {
    if (!client) return;
    asked = want === state.language ? null : want;
    toAgent(null, "language_requested", { language: want });
    if (askedTimer) clearTimeout(askedTimer);
    askedTimer = setTimeout(() => {
      asked = null;
      askedTimer = null;
    }, SWITCH_WAIT_MS);
  }

  async function micState(): Promise<MicState> {
    if (config.micState) return config.micState();
    try {
      const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
      return status.state;
    } catch {
      return "prompt";
    }
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
        post(port, { k: "catchup", msgs: catchUp.replay() });
        return;
      case "leaving":
        note(`tab ${tab.id} leaving`);
        listening.delete(port);
        return;
      case "app":
        if (active === null) active = tab.id;
        toAgent(tab.id, msg.event, msg.payload);
        return;
      case "report":
        if (tab.id === active) client?.sendClientMessage("avatar", msg.data as never);
        return;
      case "done": {
        const job = inFlight.get(msg.id);
        if (!job) return;
        note(`done ${job.job.kind === "stage" ? `${job.job.move} ${msg.result?.outcome ?? "deferred"}` : job.job.command}`);
        return finish(job, { k: "result", result: msg.result, deferred: msg.deferred });
      }
      case "result":
        if (client && ready) stage?.send(msg.result);
        return;
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
      // A job that page was making went with it: it loaded the next page.
      for (const job of [...inFlight.values()]) if (job.port === port) finish(job, { k: "gone" });
      if (!mine.ports.size) {
        mine.awaySince = Date.now();
        setTimeout(() => {
          if (tabs.get(mine.id) === mine && !mine.ports.size && Date.now() - mine.awaySince >= AWAY_MS) forget(mine.id);
        }, AWAY_MS + 50);
      }
      watchForPages();
    });
  });

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

  config.testHooks?.({
    state, tabs, pending, log, end, timeline, api,
    client: () => client,
    command: (command: string, payload: unknown) => client && siteCommand(client, command, payload),
    interrupted: () => timeline.interrupted().map(interruptedResult),
    sendAppEvent: (event: string, payload: unknown) => client && sendAppEvent(client.sendUIEvent.bind(client), { event, payload } as never),
  });

  // Up: every page of the site opens its port now.
  void toWorker({ op: "holder_up" });
  watchForPages();
}
