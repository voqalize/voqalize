/**
 * The widget's hold on its session across removal from the page. The
 * session module is replaced, so the session the widget starts itself is a
 * fake whose disposal the tests can see.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { defineElements } from "../src/elements/define.js";
import type { VqlWidget } from "../src/elements/widget.js";
import { FakeSession } from "./support/fake-session.js";

const started: OwnSession[] = [];

class OwnSession extends FakeSession {
  disposed = false;
  constructor() {
    super();
    started.push(this);
  }
  dispose(): void {
    this.disposed = true;
    if (this.getSnapshot().status === "connected") void this.disconnect();
  }
}

vi.mock("../src/session/adapter.js", () => ({
  WidgetSession: class extends OwnSession {},
  mintSession: () => Promise.resolve({ session_id: "s" }),
}));

beforeAll(() => defineElements());

afterEach(() => {
  document.body.innerHTML = "";
  started.length = 0;
});

async function mount(session?: FakeSession): Promise<VqlWidget> {
  document.body.innerHTML = `<vql-widget></vql-widget>`;
  const w = document.querySelector("vql-widget") as VqlWidget;
  w.warn = () => {};
  if (session) w.session = session;
  w.sessionSource = { session_id: "s" };
  await w.updateComplete;
  return w;
}

const microtasks = () => new Promise((r) => setTimeout(r, 0));

describe("removal from the page", () => {
  it("hangs up a call the widget started itself", async () => {
    const w = await mount();
    await w.open();
    const own = started[0] as OwnSession;
    expect(own.getSnapshot().status).toBe("connected");
    w.remove();
    await microtasks();
    expect(own.disposed).toBe(true);
    expect(own.calls).toContain("disconnect");
    expect(w.session).toBeUndefined();
    expect(w.view).toBe("closed");
  });

  it("keeps the call when the page only moves the widget", async () => {
    const w = await mount();
    await w.open();
    const own = started[0] as OwnSession;
    const other = document.createElement("div");
    document.body.append(other);
    other.append(w);
    await microtasks();
    expect(own.disposed).toBe(false);
    expect(w.session).toBe(own);
    own.mic.patch({ muted: true, state: "muted" });
    await w.updateComplete;
    expect(w.shadowRoot?.querySelector("vql-mic")?.getAttribute("state")).toBe("muted");
  });

  it("leaves a session the page passed in to the page, and follows it again when put back", async () => {
    const s = new FakeSession();
    const w = await mount(s);
    await w.open();
    w.remove();
    await microtasks();
    expect(s.calls).not.toContain("disconnect");
    expect(w.session).toBe(s);
    document.body.append(w);
    await w.updateComplete;
    s.mic.patch({ muted: true, state: "muted" });
    await w.updateComplete;
    expect(w.shadowRoot?.querySelector("vql-mic")?.getAttribute("state")).toBe("muted");
  });

  it("ends the call it started when the page hands it another session", async () => {
    const w = await mount();
    await w.open();
    const own = started[0] as OwnSession;
    w.session = new FakeSession();
    await w.updateComplete;
    expect(own.disposed).toBe(true);
  });
});

describe("mute before the mic is live", () => {
  it("shows the mic as muted while the prompt is still open", async () => {
    const s = new FakeSession();
    s.onConnect = (x) => {
      x.patch({ status: "connected", agent: "listening" });
      x.mic.patch({ state: "asking", micHint: "grant" });
    };
    const w = await mount(s);
    await w.open();
    s.setMuted(true);
    s.mic.patch({ state: "asking" });
    await w.updateComplete;
    const mic = w.shadowRoot?.querySelector("vql-mic") as HTMLElement & { muted: boolean; updateComplete: Promise<unknown> };
    expect(mic.muted).toBe(true);
    await mic.updateComplete;
    expect(mic.shadowRoot?.querySelector("button")?.getAttribute("aria-pressed")).toBe("true");
  });
});

describe("configuration JSON cannot write", () => {
  it("survives a cyclic or BigInt configuration", async () => {
    const w = await mount();
    const cyclic: Record<string, unknown> = { name: "Emily" };
    cyclic.self = cyclic;
    w.config = cyclic as never;
    await w.updateComplete;
    expect(w.resolvedConfig.name).toBe("Emily");
    w.config = { name: "Ira", extra: 10n } as never;
    await w.updateComplete;
    expect(w.resolvedConfig.name).toBe("Ira");
  });
});
