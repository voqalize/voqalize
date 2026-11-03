/**
 * The Site Agent on a page of the site: the adapter the shared page host runs
 * (`defineSiteExtension({ adapters })`), made of the paste-in snippet's own
 * parts, so the extension shows the site exactly as the published Site Agent
 * would: its watcher, its executor and its two Stage moves, run on the
 * configuration embed.config serves (`agent.ts`). Nothing here is specific to
 * a site; the site's pages, regions, tools and navigation are all in that
 * configuration.
 *
 * Page → brain (the watcher, `startWatcher`), once the brain hears this page:
 * `page_viewed` with the page's digest, `tools_available`, `item_viewed`,
 * `listing_viewed`, `cart_viewed`, `dialog_opened`/`closed`, and
 * `screen_seen` once per utterance (when the visitor starts speaking). Every
 * page first says `stage_hello`: the Site Agent's brain sends no cues to a
 * page that has not, and the shared host's holder never sends one.
 *
 * Brain → page (the site's own Actions, as the holder routes them to the tab
 * in front): `run_site_tool`, `read_site`, `open_page`, `open_item`,
 * `open_listing` through the executor (`runAction`), answered with the
 * snippet's own result events (`outcomeEvents`: `tool_ran` and its companion,
 * `site_read`, or `action_failed`); `show_note` as a note card. Site tools run
 * one at a time, in the order sent; a visitor's own navigation in the middle
 * of one stops it, and one a full page load interrupted goes on on the next
 * page (`resumeSiteTool`), as in the snippet's `call/session.ts`.
 *
 * Stage's two moves (`site.page {page}`, `site.show {region}`) are the
 * snippet's own performers (`call/stage.ts`), registered on the shared host's
 * `Moves`, so they ring with this extension's spotlight and a move that loads
 * a page is carried across it by the service worker.
 */

import type { Adapter, PageKit, SiteHooks } from "@voqalize/stage/extension";
import { domSettled, type Moves } from "@voqalize/stage";
import type { Adapter as SiteAdapter } from "@snippet/bundle.gen";
import { STAGE_PAGE_MOVE, STAGE_SHOW_MOVE } from "@snippet/constants.gen";
import { resumeSiteTool, runAction } from "@snippet/executor";
import { LIVE_PACE } from "@snippet/executor/pace";
import { startIdleBaseline } from "@snippet/executor/requests";
import type { ExecContext, RunResult } from "@snippet/executor/types";
import { couponLedger, runLedger, toolHealth } from "@snippet/call/session";
import { outcomeEvents, parseCommand } from "@snippet/call/outcome";
import { hello, type StageDeps } from "@snippet/call/stage";
import { HOST_ID } from "@snippet/loader/widget";
import { startWatcher, type Watcher } from "@snippet/watcher";
import type { AppEvent, UiAction } from "@snippet/vocabulary.gen";
import { openPage, showRegion } from "snippet-stage-moves";

import { agent, fallbackLanguage, servedLanguages } from "./agent";
import { endCall, joinCall, ledgerStorage, sharedPageSeq } from "./call-store";
import { SITE_LANGUAGES } from "./holder-events";
import { type NotePanel, notePanel } from "./notes";
import { SPOTLIGHT } from "./site";

/** What the visitor's voice does, from the face's client (`content.ts`). */
export const voice = {
  started: () => {},
  stopped: () => {},
};

/** One call on this page. */
interface Live {
  exec: ExecContext;
  watcher: Watcher | null;
  notes: NotePanel;
  stopIdle: () => void;
  /** Site tools and navigations, one at a time, in the order sent. */
  queue: Promise<void>;
  /** The site tool running now: a visitor's navigation stops it. */
  inflight: { abort: AbortController } | null;
  ended: boolean;
}

/** The snippet's watcher and executor skip their own widget (`#voqalize-site`):
 *  the shared host's widget takes its id, so the digest, the screen and the
 *  scroll that lifts a target above the widget all know it. */
function markWidget(): void {
  const host = document.querySelector('[data-voqalize="widget"]');
  if (host && !host.id) host.id = HOST_ID;
}

export function siteAgent(): Adapter {
  return (moves: Moves, kit: PageKit): SiteHooks => {
    markWidget();
    let live: Live | null = null;
    let heardAt = 0;

    const emit = (event: AppEvent) => {
      if (!live?.ended) kit.emit(event.event, event.payload);
    };

    /** The executor's context off a call (the console's moves): nothing sent. */
    const idleExec = (): ExecContext => ({
      emit: () => {},
      assist: agent.config?.settings.assist ?? null,
      pageType: () => "other",
      reread: () => {},
      markAgentAction: () => {},
      ringColour: SPOTLIGHT.color,
    });
    const exec = () => live?.exec ?? idleExec();

    async function deps(): Promise<StageDeps> {
      await agent.ready;
      const config = agent.config;
      if (!config) throw new Error("the Site Agent's configuration is not here");
      return {
        // The two performers never use it: the holder talks to the brain.
        client: null as unknown as StageDeps["client"],
        adapter: config.adapter,
        exec: exec(),
        win: window,
        runAction: (action) => run(config.adapter, action, exec()),
      };
    }

    moves.register<{ page: string | null }>(STAGE_PAGE_MOVE, "navigate", async (a, c) => openPage(a?.page ?? "", c, await deps()), {
      params: ["page"],
    });
    moves.register<{ region: string | null }>(STAGE_SHOW_MOVE, "look", async (a, c) => showRegion(a?.region ?? "", c, await deps()), {
      params: ["region"],
    });

    async function run(adapter: SiteAdapter, action: UiAction, ctx: ExecContext): Promise<RunResult> {
      try {
        return await runAction(adapter, action, ctx);
      } catch (e) {
        // The executor never throws; if it does, that is our bug, reported as one.
        return {
          ok: false, code: "unsupported_action", step_index: null,
          detail: `the page could not run ${action.command}: ${String(e)}`.slice(0, 200),
        };
      }
    }

    function enqueue(job: () => Promise<void>): void {
      if (!live) return;
      live.queue = live.queue.then(job, job);
    }

    /** A site tool, with its own abort; its ToolRan, then the tools again. */
    async function runTool(adapter: SiteAdapter, action: Extract<UiAction, { command: "run_site_tool" }> | null): Promise<void> {
      const here = live;
      if (!here || here.ended) return;
      const abort = new AbortController();
      here.inflight = { abort };
      try {
        const ctx: ExecContext = { ...here.exec, signal: abort.signal };
        let result: RunResult | null = null;
        try {
          result = action ? await runAction(adapter, action, ctx) : await resumeSiteTool(adapter, ctx);
        } catch (e) {
          console.warn(`voqalize: a site tool could not run (${String((e as Error)?.name ?? "error")})`);
        }
        if (!result || here.ended) return;
        // A late result of a run that was stopped is dropped, never sent.
        if (abort.signal.aborted || result.aborted || result.continued) return;
        const placeholder = action ?? ({
          command: "run_site_tool",
          payload: { tool_id: "", args: {}, call_ref: "", page_seq: 0, text_args: [], confirmed_leave: false },
        } as unknown as UiAction);
        for (const event of outcomeEvents(placeholder, result)) emit(event);
        here.watcher?.refreshTools?.();
      } finally {
        if (here.inflight?.abort === abort) here.inflight = null;
      }
    }

    function begin(): void {
      const config = agent.config;
      if (!config || live) return;
      const call = joinCall();
      const store = ledgerStorage(call);
      const callWin = { sessionStorage: store } as unknown as Window;
      const health = toolHealth(callWin, true);
      const pageSeq = sharedPageSeq(store);
      const here: Live = {
        exec: {
          emit,
          assist: config.settings.assist ?? null,
          toolHealth: health,
          coupons: couponLedger(callWin, true),
          reversibleRuns: runLedger(callWin, true),
          pageType: () => here.watcher?.pageType() ?? "other",
          reread: (what) => here.watcher?.reread(what),
          markAgentAction: () => here.watcher?.markAgentAction(),
          ringColour: SPOTLIGHT.color,
          heardAt: () => heardAt,
          // The visitor watches: actions at a pace a person can follow.
          pace: LIVE_PACE,
        },
        watcher: null,
        notes: notePanel(config.settings.human_contact),
        // What the page sends on its own while the call is on, so a tool's
        // run does not take a token refresh for its own act.
        stopIdle: startIdleBaseline(),
        queue: Promise.resolve(),
        inflight: null,
        ended: false,
      };
      live = here;
      // The languages the site serves, for the toggle (the holder keeps this).
      kit.emit(SITE_LANGUAGES, { served: servedLanguages(), fallback: fallbackLanguage() });
      here.watcher = startWatcher({
        adapter: config.adapter,
        emit,
        pageTypeOverride: () => null,
        assist: config.settings.assist ?? null,
        tools: { toolHealth: health },
        pageSeq,
        onView: ({ by, first }) => {
          // The visitor went elsewhere in the middle of a tool: stop it; no ToolRan.
          if (by === "visitor" && here.inflight) here.inflight.abort.abort();
          // A tool the last page load interrupted goes on here.
          if (first) enqueue(() => runTool(config.adapter, null));
        },
      });
    }

    function stop(): void {
      const here = live;
      live = null;
      if (!here) return;
      here.ended = true;
      here.watcher?.stop();
      here.inflight?.abort.abort();
      here.notes.destroy();
      here.stopIdle();
    }

    voice.started = () => {
      // What the visitor has in view, once per utterance; nothing on a private page.
      const seen = live?.watcher?.screenSeen?.();
      if (seen) emit({ event: "screen_seen", payload: seen });
    };
    voice.stopped = () => {
      heardAt = Date.now();
    };

    return {
      context: () => ({}),
      ready: () => Promise.all([agent.ready, domSettled()]).then(() => {}),
      // The page as it stands: its hello first (no cue comes before it), then,
      // on a tab back in front, its view again.
      report(send) {
        send("stage_hello", hello(window));
        live?.watcher?.reread("page");
      },
      start() {
        let stopped = false;
        void agent.ready.then(() => {
          if (!stopped) begin();
        });
        return () => {
          stopped = true;
          stop();
          // The call is over (a page only stops on its end): its ledgers go.
          endCall();
        };
      },
      async command(command, payload) {
        await agent.ready;
        const config = agent.config;
        const here = live;
        if (!config || !here || here.ended) return;
        // The parse and ActionFailed are the snippet's.
        const parsed = parseCommand(command, payload);
        if ("failed" in parsed) return emit(parsed.failed);
        const action = parsed.action;
        switch (action.command) {
          case "show_note":
            here.notes.show(action.payload);
            return;
          case "language_set":
            // The holder's: it moves the toggle on every tab.
            return;
          case "run_site_tool":
            enqueue(() => runTool(config.adapter, action));
            return;
          case "read_site":
            // A background read touches no page: it waits behind no tool run.
            void run(config.adapter, action, here.exec).then((result) => {
              if (!here.ended) for (const event of outcomeEvents(action, result)) emit(event);
            });
            return;
          default:
            enqueue(async () => {
              if (here.ended) return;
              for (const event of outcomeEvents(action, await run(config.adapter, action, here.exec))) emit(event);
            });
        }
      },
    };
  };
}
