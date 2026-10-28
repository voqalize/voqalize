import { afterEach, describe, expect, it, vi } from "vitest";

import { attachStage, type StageClient } from "../src/attach";
import { reveal, setValue } from "../src/dom";
import { Moves } from "../src/moves";
import { stagePage } from "../src/page";
import { Spotlight } from "../src/spotlight";
import { Timeline } from "../src/timeline";
import type { StageCue } from "../src/wire.gen";
import { isSitePage, matchPattern } from "../src/extension/site";
import { mountWidget } from "../src/extension/widget";
import { readKept, writeKept } from "../src/extension/persist";

/** Enough of a pipecat client: its events and `sendUIEvent`. */
function fakeClient() {
  const handlers = new Map<string, Set<(d?: unknown) => void>>();
  const sent: { event: string; payload: unknown }[] = [];
  const client = {
    on(name: string, fn: (d?: unknown) => void) {
      (handlers.get(name) ?? handlers.set(name, new Set()).get(name)!).add(fn);
      return client;
    },
    off(name: string, fn: (d?: unknown) => void) {
      handlers.get(name)?.delete(fn);
      return client;
    },
    sendUIEvent(event: string, payload?: unknown) {
      sent.push({ event, payload });
    },
  };
  const emit = (name: string, data?: unknown) => handlers.get(name)?.forEach((fn) => fn(data));
  return { client: client as unknown as StageClient, emit, sent, handlers };
}

const cue: StageCue = { call_ref: "k1", move: "core.show", verb: "show", args: ["Rooms"], at: "the rooms are", before: 0, unit: 0 };

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("attachStage", () => {
  it("routes Stage's commands, hands the rest to the site, and detaches", () => {
    const f = fakeClient();
    const cues: StageCue[] = [];
    const moves: unknown[] = [];
    const site: string[] = [];
    const a = attachStage(f.client, { onCue: (c) => cues.push(c), onMove: (m) => moves.push(m), onSiteCommand: (c) => site.push(c) });
    f.emit("uiCommand", { command: "stage_cue", payload: cue });
    f.emit("uiCommand", { command: "stage_move", payload: { call_ref: "m1", move: "x", args: {}, when: "now" } });
    f.emit("uiCommand", { command: "language_changed", payload: { language: "es" } });
    expect(cues).toEqual([cue]);
    expect(moves).toHaveLength(1);
    expect(site).toEqual(["language_changed"]);
    a.detach();
    expect([...f.handlers.values()].every((s) => s.size === 0)).toBe(true);
  });

  it("feeds the timeline, prefers botOutput, and reports interrupted cues as refused", async () => {
    vi.useFakeTimers();
    const f = fakeClient();
    const fired: string[] = [];
    const tl = new Timeline(async (c) => void fired.push(c.call_ref));
    attachStage(f.client, { timeline: tl, onMove: () => {} });
    f.emit("uiCommand", { command: "stage_cue", payload: cue });
    f.emit("uiCommand", { command: "stage_cue", payload: { ...cue, call_ref: "k2", at: "never said words" } });
    f.emit("botStartedSpeaking");
    f.emit("botOutput", { text: "Here the rooms are wide", spoken: true });
    f.emit("botTtsText", { text: "never said words" }); // ignored: botOutput wins
    await vi.advanceTimersByTimeAsync(0);
    expect(fired).toEqual(["k1"]);
    f.emit("userStartedSpeaking");
    expect(f.sent).toEqual([
      {
        event: "stage_result",
        payload: { call_ref: "k2", move: "core.show", outcome: "refused", detail: "interrupted", refused: [{ arg: "show", why: "interrupted" }], moved: false, ms: 0 },
      },
    ]);
    tl.clear();
  });

  it("stagePage: a cue becomes a move and its result goes back", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `<h2>Rooms</h2>`;
    const f = fakeClient();
    const moves = new Moves(new Spotlight({ color: "#000", dwellMs: 0 }));
    moves.register<{ heading: string }>("core.show", "look", async ({ heading }) => `showed ${heading}`, { params: ["heading"] });
    const p = stagePage(f.client, moves);
    f.emit("uiCommand", { command: "stage_cue", payload: cue });
    f.emit("botStartedSpeaking");
    f.emit("botOutput", { text: "and the rooms are wide" });
    await vi.advanceTimersByTimeAsync(10);
    expect(f.sent[0]).toMatchObject({ event: "stage_result", payload: { call_ref: "k1", outcome: "applied", detail: "showed Rooms" } });
    p.detach();
  });
});

describe("dom", () => {
  it("setValue goes through the native setter and fires the events a site listens for", () => {
    document.body.innerHTML = `<input id="q">`;
    const input = document.getElementById("q") as HTMLInputElement;
    const seen: string[] = [];
    for (const t of ["input", "change", "keyup", "blur"]) input.addEventListener(t, () => seen.push(t));
    setValue(input, "Atacama");
    expect(input.value).toBe("Atacama");
    expect(seen).toEqual(["input", "change", "keyup", "blur"]);
  });

  it("reveal opens a closed <details> and an aria-expanded trigger", async () => {
    document.body.innerHTML = `
      <details id="d"><summary>More</summary><p id="in">Inside</p></details>
      <button aria-controls="panel" aria-expanded="false" id="t">Open</button>
      <div id="panel" hidden><p id="deep">Deep</p></div>`;
    const t = document.getElementById("t")!;
    t.addEventListener("click", () => {
      t.setAttribute("aria-expanded", "true");
      document.getElementById("panel")!.hidden = false;
    });
    await reveal(document.getElementById("in")!);
    expect((document.getElementById("d") as HTMLDetailsElement).open).toBe(true);
    await reveal(document.getElementById("deep")!);
    expect(t.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("extension pieces", () => {
  it("matchPattern and isSitePage read the manifest's patterns", () => {
    expect(matchPattern("https://*.explora.com/*").test("https://reservations.explora.com/ibe/paso1")).toBe(true);
    expect(matchPattern("https://*.explora.com/*").test("https://explora.com/")).toBe(true);
    expect(matchPattern("https://cannonhome.cl/*").test("https://evil.cl/cannonhome.cl/")).toBe(false);
    const site = { id: "t", matches: ["https://www.example.com/*"], home: "https://www.example.com/", opening: "en", widget: {} as never };
    expect(isSitePage(site, "https://www.example.com/a")).toBe(true);
    expect(isSitePage(site, "https://example.org/")).toBe(false);
  });

  it("the widget mounts in a shadow root on <html> and speaks the toggle's language", () => {
    const words = (invite: string) => ({
      invite, role: "", inviteLabel: invite, minimise: "", mute: "", unmute: "", hang: "", credit: "", language: "",
      connecting: "", failed: "", grant: "", blocked: "", settings: "",
      activity: { listening: "", thinking: "", speaking: "" },
    });
    const w = mountWidget({
      name: "Javier",
      languages: [{ code: "es", label: "Español" }, { code: "en", label: "English" }],
      words: { es: words("Habla con Javier"), en: words("Talk to Javier") },
      corner: "left",
    });
    const host = [...document.documentElement.children].find((e) => e.getAttribute("data-voqalize") === "widget")!;
    const text = () => host.shadowRoot!.querySelector(".invite-name")!.textContent;
    expect(text()).toBe("Habla con Javier");
    w.setLanguage("en");
    expect(text()).toBe("Talk to Javier");
    host.remove();
  });

  it("persist keeps a live call for the next page, and forgets a stale one", () => {
    writeKept("t", { status: "live", muted: false, activity: null, language: "es", still: null, home: { side: 24, bottom: 24 }, minimised: false });
    expect(readKept("t")?.language).toBe("es");
    expect(readKept("t", Date.now() + 61_000)).toBeNull();
  });
});
