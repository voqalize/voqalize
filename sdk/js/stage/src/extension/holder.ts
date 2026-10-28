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
 *     next page is ready for them: up, its site's scripts going, and the
 *     move the last page carried to it finished — so they run after it, in
 *     the order they came. A job that page took and never started, because
 *     the page went, goes to the next page the same way; one it started is
 *     `unknown`, never `applied`;
 *   - each move's progress, passed to the agent, so a move that is slow is
 *     not taken for one that failed;
 *   - the moves a page carried to its next page (`loadThen`, `keep`): each is
 *     owed one final result from there, and fails when no page reports it in
 *     time.
 *
 * Pages are followers: each draws the widget and the face from the relay,
 * makes the moves sent to it and reports what it shows. The call ends on End
 * (any tab), when the call drops, or when no page of the site has been open
 * for 15 s; the holder then closes.
 */

import { type Attached, attachStage, type ClientHandler, interruptedResult, staleResult, type StageClient } from "../attach";
import { type FireInfo, Timeline, withFire } from "../timeline";
import { sendAppEvent, type StageCue, type StageMove, type StageProgress, type StageResult } from "../wire.gen";
import { CatchUp } from "./catch-up";
import type { CallState, FromPage, HolderAsk, Job, MicState, ToPage } from "./protocol";
import { PORT, takenFromAnyTab } from "./protocol";
import { type Relaying, relayCall } from "./relay";
import { isSitePage, type SiteConfig } from "./site";
import type { Activity, Language, Status } from "./widget";

type Port = chrome.runtime.Port;

/**
 * What the holder uses of the call's pipecat client, written out rather than
 * imported (as `StageClient` is), so the site's `PipecatClient`, of whatever
 * version in the peer range, fits as it is.
 */
export interface HolderClient extends StageClient {
  connect(params?: unknown): Promise<unknown>;
  disconnect(): Promise<void>;
  disconnectBot(): void;
  enableMic(enable: boolean): void;
  sendClientMessage(type: string, data?: unknown): void;
  /** Read for its peer connection (`pc`), for the face's mouth clock. */
  readonly transport: unknown;
}

/** The callbacks the holder hands `makeClient`, for pipecat's options. */
export interface HolderCallbacks {
  onTransportStateChanged(state: string): void;
  onBotReady(): void;
  onTrackStarted(track: MediaStreamTrack, participant?: { local?: boolean }): void;
  onDeviceError(error: { devices: string[]; type: string }): void;
}

/** With no page of the site open this long, the call ends and the holder closes. */
export const NO_PAGES_MS = 15_000;
/** A job for a tab whose page is loading waits this long for it. */
const PENDING_MS = 20_000;
/** A job a page is making answers within this. */
const MOVE_MS = 45_000;
/** A move carried to the next page is answered from there within this. */
const CARRIED_MS = PENDING_MS;
/** A page that said hello and never said it is ready gets its jobs anyway
 *  after this (a page that cannot say so). */
const READY_WAIT_MS = 25_000;
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
  makeClient(output: HTMLAudioElement, callbacks: HolderCallbacks): HolderClient;
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
  // The page went away with it (it loaded another) after starting it.
  | { k: "gone"; started: boolean }
  | { k: "timeout" };

interface Running {
  id: number;
  tab: number;
  job: Job;
  port: Port | null;
  timer: ReturnType<typeof setTimeout>;
  resolve: (ended: Ended) => void;
  /** The page began it (it rang or acted, or began a site job). */
  started: boolean;
  /** Sent on to the next page once already, its first page gone. */
  requeued: boolean;
}

const refOf = (job: Job): string | null => (job.kind === "site" ? null : job.call_ref);

export function startHolder(site: SiteConfig, config: HolderConfig): void {
  const audio = (document.getElementById("bot") as HTMLAudioElement | null) ?? document.body.appendChild(document.createElement("audio"));
  audio.autoplay = true;
  const isSite = (url: string) => isSitePage(site, url);
  const anyTab = new Set(["stage_result", ...(config.anyTab ?? [])]);

  const tabs = new Map<number, Tab>();
  const listening = new WeakSet<Port>();
  /** Pages ready for jobs (`ready`), and the wait for one that never says so. */
  const readyPorts = new WeakSet<Port>();
  const readyWaits = new WeakMap<Port, ReturnType<typeof setTimeout>>();
  /** When each cue reached the holder, for its timings. */
  const cueReceived = new Map<string, number>();
  const inFlight = new Map<number, Running>();
  const pending = new Map<number, Running[]>();
  let nextJob = 1;
  /** Moves a page carried to its next page, by call: the timer that fails
   *  one no page reported, once its page has gone. */
  const carried = new Map<string, { move: string; timer: ReturnType<typeof setTimeout> | null }>();
  let active: number | null = null;
  let lastSiteTab: number | null = null;

  let client: HolderClient | null = null;
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
    note(`perform ${job.job.kind === "site" ? job.job.command : job.job.move} → tab ${job.tab}`);
    post(port, { k: "perform", id: job.id, job: job.job });
  }

  /** The tab's newest page that is ready for jobs. */
  function newest(tab: number): Port | null {
    const ports = [...(tabs.get(tab)?.ports ?? [])].filter((p) => listening.has(p) && readyPorts.has(p));
    return ports.length ? ports[ports.length - 1]! : null;
  }

  /** Whether the tab has a page up that is not ready for jobs yet. */
  const settling = (tab: number) => [...(tabs.get(tab)?.ports ?? [])].some((p) => listening.has(p) && !readyPorts.has(p));

  /** Tell the agent where a Stage job is, before its result. */
  function progress(job: Job, phase: StageProgress["phase"]): void {
    if (job.kind === "site" || !client || !ready) return;
    const since = job.received_at ?? Date.now();
    stage?.send({ call_ref: job.call_ref, move: job.move, phase, ms: Math.max(0, Date.now() - since) });
  }

  /** Keep a job for tab `to`'s next ready page. `first` puts it before the
   *  rest: it came before them. */
  function hold(running: Running, why: string, first = false): void {
    note(`pending for tab ${running.tab}`);
    running.port = null;
    clearTimeout(running.timer);
    running.timer = setTimeout(() => finish(running, { k: "failed", why }), PENDING_MS);
    const list = pending.get(running.tab) ?? pending.set(running.tab, []).get(running.tab)!;
    if (first) list.unshift(running);
    else list.push(running);
    progress(running.job, settling(running.tab) ? "queued" : "loading");
  }

  /** Make a job on tab `to`: at once when its page is ready for it, else
   *  once its next page is. */
  function performOn(to: number, job: Job): Promise<Ended> {
    return new Promise((resolve) => {
      const running: Running = {
        id: nextJob++, tab: to, job, port: null, timer: 0 as never, resolve, started: false, requeued: false,
      };
      const port = newest(to);
      if (port) return send(running, port);
      hold(running, "the page did not come back");
    });
  }

  /** A page is ready for jobs: the ones kept for its tab go now, in order. */
  function markReady(tab: Tab, port: Port): void {
    const wait = readyWaits.get(port);
    if (wait) clearTimeout(wait);
    readyWaits.delete(port);
    if (!listening.has(port)) return;
    readyPorts.add(port);
    const kept = pending.get(tab.id) ?? [];
    pending.delete(tab.id);
    if (kept.length) note(`tab ${tab.id} ready: ${kept.length} job(s)`);
    for (const job of kept) send(job, port);
  }

  /** A page said hello, not yet ready: its jobs wait for it, a while. */
  function awaitReady(tab: Tab, port: Port): void {
    readyPorts.delete(port);
    for (const job of pending.get(tab.id) ?? []) progress(job.job, "queued");
    armReady(tab, port);
  }

  /** (Re)start the wait for a page to say it is ready: a page still at work
   *  on its carried move (it says so with progress) is waited for again. */
  function armReady(tab: Tab, port: Port): void {
    const prior = readyWaits.get(port);
    if (prior) clearTimeout(prior);
    readyWaits.set(
      port,
      setTimeout(() => {
        note(`tab ${tab.id} never said ready; sending its jobs`);
        markReady(tab, port);
      }, READY_WAIT_MS),
    );
    for (const job of pending.get(tab.id) ?? []) {
      clearTimeout(job.timer);
      job.timer = setTimeout(() => finish(job, { k: "failed", why: "the page never got ready" }), READY_WAIT_MS + PENDING_MS);
    }
  }

  /** A job's page went away with it: one it never started goes to the next
   *  page, once; one it started has an end nobody saw. */
  function gone(job: Running): void {
    inFlight.delete(job.id);
    if (client && !job.started && !job.requeued && tabs.has(job.tab)) {
      job.requeued = true;
      note(`${job.job.kind === "site" ? job.job.command : job.job.move}: its page went before it ran; for the next page`);
      return hold(job, "the page did not come back", true);
    }
    finish(job, { k: "gone", started: job.started });
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

  /** The result a Stage job reports, however it ended: its final one, or,
   *  for a move carried to the next page, an interim `moved` one (the final
   *  comes from that page, or fails here in `CARRIED_MS`). */
  function resultOf(job: Extract<Job, { kind: "stage" }>, ended: Ended): StageResult | null {
    const base = { call_ref: job.call_ref, move: job.move, refused: [], ms: 0 };
    switch (ended.k) {
      case "result": {
        const r = ended.result;
        if (r && !r.moved) {
          settleCarried(r.call_ref);
          return r;
        }
        // Handed to the next page (`loadThen`), or ended there (`null`).
        if (carried.has(job.call_ref)) return awaitCarried(job.call_ref, job.move);
        // It went on to another page that owes nothing: what it did there
        // nobody saw.
        return { ...base, outcome: "unknown", detail: "the page went on to another before it said what it did", moved: false };
      }
      case "failed":
        settleCarried(job.call_ref);
        return { ...base, outcome: "failed", detail: ended.why, moved: false };
      case "gone":
        // The page went with the move: it is the next page's when it kept it.
        if (carried.has(job.call_ref)) return awaitCarried(job.call_ref, job.move);
        // Never `applied`: a load cut it off, and what it did is not known.
        return {
          ...base,
          outcome: "unknown",
          detail: ended.started ? "the page left while it ran" : "the page left before it ran",
          moved: false,
        };
      case "timeout":
        settleCarried(job.call_ref);
        return { ...base, outcome: "unknown", detail: "the page did not answer", moved: false };
    }
  }

  /** A carried move's page has gone: its result is the next page's, and an
   *  interim one says so now. */
  function awaitCarried(callRef: string, move: string): StageResult {
    const entry = carried.get(callRef) ?? { move, timer: null };
    carried.set(callRef, entry);
    armCarried(callRef, entry);
    return { call_ref: callRef, move: entry.move, outcome: "applied", detail: "loading the next page", refused: [], moved: true, ms: 0 };
  }

  /** (Re)start the wait for the page that owes a carried move its result:
   *  each progress from it starts the wait again. */
  function armCarried(callRef: string, entry: { move: string; timer: ReturnType<typeof setTimeout> | null }): void {
    if (entry.timer) clearTimeout(entry.timer);
    entry.timer = setTimeout(() => {
      carried.delete(callRef);
      note(`carried ${entry.move} (${callRef}): no page reported it`);
      if (client && ready) {
        stage?.send({
          call_ref: callRef, move: entry.move, outcome: "failed", detail: "no page came up to finish it after the load",
          refused: [], moved: false, ms: CARRIED_MS,
        });
      }
    }, CARRIED_MS);
  }

  function settleCarried(callRef: string): void {
    const entry = carried.get(callRef);
    if (entry?.timer) clearTimeout(entry.timer);
    carried.delete(callRef);
  }

  async function makeStage(
    job: Extract<Job, { kind: "stage" }>, move: StageMove | null, on: HolderClient, fired?: FireInfo,
  ): Promise<void> {
    const receivedAt = job.received_at ?? Date.now();
    job.received_at = receivedAt;
    if (move?.when === "quiet") progress(job, "queued");
    if (config.pace) await config.pace(job, move, api);
    else if (move?.when === "quiet") await settle(QUIET_WAIT_MS, false);
    if (client !== on) return;
    const queuedAt = Date.now();
    const result = resultOf(job, await route(job));
    if (!result || client !== on) return;
    if (result.moved) return stage?.send(result);
    const timed: StageResult = { ...result, received_ms: result.received_ms ?? Math.max(0, Date.now() - receivedAt) };
    stage?.send(
      fired
        ? withFire(timed, fired, receivedAt)
        : { ...timed, fired: move?.when ?? "now", queued_ms: Math.max(0, queuedAt - receivedAt) },
    );
  }

  const cueJob = (cue: StageCue): Extract<Job, { kind: "stage" }> => {
    const received = cueReceived.get(cue.call_ref);
    cueReceived.delete(cue.call_ref);
    return { kind: "stage", move: cue.move, args: cue.args, call_ref: cue.call_ref, received_at: received ?? Date.now() };
  };

  /** The next move is due: whatever a page is making stops waiting for its
   *  scroll. */
  function hurry(): void {
    for (const job of inFlight.values()) if (job.port && job.job.kind !== "site") post(job.port, { k: "hurry" });
  }

  // The screen follows the voice: cues fire as their words are heard, one
  // move at a time, on the tab in front.
  const timeline = new Timeline(
    async (cue, info) => {
      if (client) await makeStage(cueJob(cue), null, client, info);
    },
    {
      lang: state.language,
      onDrop: (cue) => {
        cueReceived.delete(cue.call_ref);
        stage?.send(staleResult(cue));
      },
      onFire: (cue, how) => note(`cue ${cue.verb} (${how})`),
      onQueued: (cue) => {
        hurry();
        progress({ kind: "stage", move: cue.move, args: cue.args, call_ref: cue.call_ref, received_at: cueReceived.get(cue.call_ref) }, "queued");
      },
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
    if (from !== null && from !== active && !takenFromAnyTab(anyTab, event, payload)) return;
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

  async function siteCommand(on: HolderClient, command: string, payload: unknown): Promise<void> {
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
    const next: HolderClient = config.makeClient(audio, {
      onTransportStateChanged: (s: string) => {
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
      await next.connect(withRealHeaders(session));
      note(`connected ${(session as { session_id?: string }).session_id ?? ""}`);
      return { ok: true };
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      note(`connect failed ${text}`);
      if (client === next) end(failure(text));
      return { ok: false, error: text };
    }
  }

  function watch(on: HolderClient): void {
    stage = attachStage(on, {
      timeline,
      onCue: (cue) => {
        cueReceived.set(cue.call_ref, Date.now());
        if (config.fireEarly?.(cue, api) && !timeline.pending().length) void makeStage(cueJob(cue), null, on);
        else timeline.add(cue);
      },
      onMove: (m) =>
        void makeStage({ kind: "stage", move: m.move, args: m.args, call_ref: m.call_ref, received_at: Date.now() }, m, on),
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
        for (const cue of dropped) cueReceived.delete(cue.call_ref);
        if (dropped.length) note(`interrupted: ${dropped.length} cue(s) dropped`);
      },
    });
    const thinking: ClientHandler = () => setActivity("thinking");
    on.on("botLlmStarted", thinking);
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
    cueReceived.clear();
    botSpeaking = false;
    for (const job of [...inFlight.values()]) finish(job, { k: "gone", started: job.started });
    for (const [, list] of pending) for (const job of [...list]) finish(job, { k: "gone", started: false });
    pending.clear();
    for (const entry of carried.values()) if (entry.timer) clearTimeout(entry.timer);
    carried.clear();
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
          // Its jobs wait until it is ready: the move the last page carried
          // here goes first. A page from a build that never says whether it
          // is ready (no `ready` at all) gets them at once, as before.
          if (msg.ready !== false) markReady(tab, port);
          else awaitReady(tab, port);
        }
        if (msg.front) {
          if (tab.id !== active) return setActive(tab.id);
          if (isSite(tab.url)) lastSiteTab = tab.id;
        }
        if (moved || msg.k === "hello") sendTabs();
        return;
      }
      case "ready":
        note(`tab ${tab.id} ready`);
        return markReady(tab, port);
      case "progress": {
        const p = msg.progress;
        if (p.phase !== "queued" && p.phase !== "loading") {
          for (const job of inFlight.values()) if (refOf(job.job) === p.call_ref) job.started = true;
        }
        // The page that owes a carried move is up and working on it: its
        // result, and its readiness for the jobs behind it, are waited for again.
        const entry = carried.get(p.call_ref);
        if (entry?.timer) armCarried(p.call_ref, entry);
        if (readyWaits.has(port)) armReady(tab, port);
        if (client && ready) stage?.send(p);
        return;
      }
      case "started": {
        const job = inFlight.get(msg.id);
        if (job) job.started = true;
        return;
      }
      case "catchup":
        post(port, { k: "catchup", msgs: catchUp.replay() });
        return;
      case "leaving":
        note(`tab ${tab.id} leaving`);
        listening.delete(port);
        readyPorts.delete(port);
        return;
      case "app":
        if (active === null) active = tab.id;
        toAgent(tab.id, msg.event, msg.payload);
        return;
      case "report":
        if (tab.id === active) client?.sendClientMessage("avatar", msg.data);
        return;
      case "done": {
        const job = inFlight.get(msg.id);
        if (!job) return;
        note(`done ${job.job.kind === "site" ? job.job.command : `${job.job.move} ${msg.result?.outcome ?? "deferred"}`}`);
        return finish(job, { k: "result", result: msg.result, deferred: msg.deferred });
      }
      case "result":
        if (!msg.result.moved) settleCarried(msg.result.call_ref);
        if (client && ready) stage?.send(msg.result);
        return;
      case "carried":
        if (!carried.has(msg.call_ref)) carried.set(msg.call_ref, { move: msg.move, timer: null });
        return;
      case "uncarried":
        return settleCarried(msg.call_ref);
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
      readyPorts.delete(port);
      const wait = readyWaits.get(port);
      if (wait) clearTimeout(wait);
      // A job that page was making went with it: it loaded the next page.
      for (const job of [...inFlight.values()]) if (job.port === port) gone(job);
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
    state, tabs, pending, carried, log, end, timeline, api,
    client: () => client,
    command: (command: string, payload: unknown) => client && siteCommand(client, command, payload),
    interrupted: () => timeline.interrupted().map(interruptedResult),
    sendAppEvent: (event: string, payload: unknown) => client && sendAppEvent(client.sendUIEvent.bind(client), { event, payload } as never),
  });

  // Up: every page of the site opens its port now.
  void toWorker({ op: "holder_up" });
  watchForPages();
}
