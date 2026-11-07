import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { defineElements } from "../src/elements/define.js";
import { VqlWidget, inputFromAttributes, neighbourAnchor } from "../src/elements/widget.js";
import { FakeSession } from "./support/fake-session.js";

beforeAll(() => defineElements());

afterEach(() => {
  document.body.innerHTML = "";
});

async function mount(html: string, session?: FakeSession): Promise<VqlWidget> {
  document.body.innerHTML = html;
  const w = document.querySelector("vql-widget") as VqlWidget;
  w.warn = () => {};
  if (session) w.session = session;
  await w.updateComplete;
  return w;
}

function shadow(w: VqlWidget): ShadowRoot {
  return w.shadowRoot as ShadowRoot;
}

function events(w: VqlWidget, ...types: string[]): { type: string; detail: unknown }[] {
  const seen: { type: string; detail: unknown }[] = [];
  for (const type of types) w.addEventListener(type, (e) => seen.push({ type, detail: (e as CustomEvent).detail }));
  return seen;
}

describe("configuration to render", () => {
  it("draws the pill launcher by default", async () => {
    const w = await mount(`<vql-widget></vql-widget>`);
    expect(w.view).toBe("closed");
    expect(w.form).toBe("pill");
    const launcher = shadow(w).querySelector("vql-launcher");
    expect(launcher?.getAttribute("variant")).toBe("pill");
    expect(w.getAttribute("view")).toBe("closed");
    expect(w.getAttribute("form")).toBe("pill");
  });

  it("reads attributes onto configuration fields", async () => {
    const w = await mount(`<vql-widget launcher="face" name="Emily" anchor="bottom-left" scheme="dark"></vql-widget>`);
    const c = w.resolvedConfig;
    expect(c.launcher.style).toBe("face");
    expect(c.name).toBe("Emily");
    expect(c.placement.anchor).toBe("bottom-left");
    expect(c.theme.scheme).toBe("dark");
    expect(w.getAttribute("data-scheme")).toBe("dark");
    expect(shadow(w).querySelector("vql-launcher")?.getAttribute("name")).toBe("Emily");
  });

  it("takes the config property as an object and as JSON text, with attributes over it", async () => {
    const w = await mount(`<vql-widget anchor="top-right"></vql-widget>`);
    w.config = { launcher: { style: "card" }, placement: { anchor: "bottom-left" } };
    await w.updateComplete;
    expect(w.resolvedConfig.launcher.style).toBe("card");
    expect(w.resolvedConfig.placement.anchor).toBe("top-right");
    w.setAttribute("config", JSON.stringify({ launcher: { style: "face" } }));
    await w.updateComplete;
    expect(w.resolvedConfig.launcher.style).toBe("face");
  });

  it("draws nothing for launcher none", async () => {
    const w = await mount(`<vql-widget launcher="none"></vql-widget>`);
    expect(shadow(w).querySelector("vql-launcher")).toBeNull();
  });

  it("uses the page's own launcher from the launcher slot", async () => {
    const w = await mount(`<vql-widget><button slot="launcher">Talk</button></vql-widget>`);
    expect(shadow(w).querySelector("vql-launcher")).toBeNull();
    expect(shadow(w).querySelector("slot[name=launcher]")).not.toBeNull();
  });

  it("maps avatar=false to a voice-only face", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget avatar="false"></vql-widget>`, s);
    expect(w.resolvedConfig.avatar).toBe(false);
    await w.open();
    await w.updateComplete;
    expect(shadow(w).querySelector("vql-face")?.hasAttribute("voice-only")).toBe(true);
  });

  it("applies theme colours as configuration custom properties and tokens as page tokens", async () => {
    const w = await mount(`<vql-widget></vql-widget>`);
    w.config = { theme: { brand: "#0f766e", tokens: { "--vql-radius": "4px" } } };
    await w.updateComplete;
    expect(w.style.getPropertyValue("--_vql-cfg-brand")).toBe("#0f766e");
    expect(w.style.getPropertyValue("--vql-radius")).toBe("4px");
  });

  it("parses attributes into an input", () => {
    const attrs: Record<string, string> = { anchor: "top-left", "instant-start": "false", avatar: "false" };
    const input = inputFromAttributes((n) => attrs[n] ?? null);
    expect(input).toEqual({ placement: { anchor: "top-left" }, mic: { instantStart: false }, avatar: false });
  });
});

describe("views", () => {
  it("opens into a card, connects, collapses to a bubble and opens again without reconnecting", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    const seen = events(w, "vql-open", "vql-collapse", "vql-view");
    w.sessionSource = { session_id: "s" };
    await w.open();
    await w.updateComplete;
    expect(w.view).toBe("open");
    expect(w.form).toBe("card");
    expect(s.calls).toEqual(["connect"]);
    const face = shadow(w).querySelector("vql-face");
    expect(face).not.toBeNull();

    w.collapse();
    await w.updateComplete;
    expect(w.view).toBe("collapsed");
    expect(w.form).toBe("bubble");
    // The same face element: resized, never re-mounted.
    expect(shadow(w).querySelector("vql-face")).toBe(face);

    await w.open();
    await w.updateComplete;
    expect(s.calls).toEqual(["connect"]);
    expect(shadow(w).querySelector("vql-face")).toBe(face);
    expect(seen.map((e) => e.type)).toEqual(["vql-open", "vql-view", "vql-collapse", "vql-view", "vql-open", "vql-view"]);
  });

  it("does not start a call without a source", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    await w.open();
    expect(s.calls).toEqual([]);
    expect(w.view).toBe("open");
  });

  it("collapses to a pill when collapsed.style is pill, and not at all when none", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget collapsed="pill"></vql-widget>`, s);
    await w.open();
    w.collapse();
    await w.updateComplete;
    expect(w.form).toBe("pill");
    w.setAttribute("collapsed", "none");
    await w.open();
    w.collapse();
    expect(w.view).toBe("open");
  });

  it("draws the hero form for open-style hero and for fullscreen placement", async () => {
    const w = await mount(`<vql-widget open-style="hero"></vql-widget>`, new FakeSession());
    await w.open();
    await w.updateComplete;
    expect(w.form).toBe("hero");
    w.removeAttribute("open-style");
    w.setAttribute("placement", "fullscreen");
    await w.updateComplete;
    expect(w.form).toBe("hero");
  });

  it("draws a sheet on a narrow window", async () => {
    const width = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    try {
      const w = await mount(`<vql-widget></vql-widget>`, new FakeSession());
      expect(w.form).toBe("face"); // mobile.launcher
      await w.open();
      await w.updateComplete;
      expect(w.form).toBe("sheet");
      expect(shadow(w).querySelector(".sheet-handle")).not.toBeNull();
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
    }
  });

  it("shows the end card with the reason when the call ends, and calls again", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    w.sessionSource = { session_id: "s" };
    const seen = events(w, "vql-end");
    await w.open();
    await w.updateComplete;
    s.patch({ status: "ended", end: { by: "agent", reason: "ended" } });
    await w.updateComplete;
    expect(w.view).toBe("ended");
    expect(seen).toEqual([{ type: "vql-end", detail: { reason: "ended" } }]);
    expect(shadow(w).querySelector("[part=end-reason]")?.textContent).toContain("ended");
    (shadow(w).querySelector(".again") as HTMLButtonElement).click();
    await w.updateComplete;
    expect(w.view).toBe("open");
    expect(s.calls).toEqual(["connect", "connect"]);
  });

  it("hangs up from the end button and closes back to the launcher", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    w.sessionSource = { session_id: "s" };
    await w.open();
    await w.updateComplete;
    shadow(w).querySelector("vql-end")?.dispatchEvent(new CustomEvent("vql-hangup", { bubbles: true, composed: true }));
    await w.updateComplete;
    expect(s.calls).toContain("disconnect");
    expect(w.view).toBe("ended");
    await w.close();
    await w.updateComplete;
    expect(w.view).toBe("closed");
    expect(shadow(w).querySelector("vql-launcher")).not.toBeNull();
  });

  it("collapses on Escape", async () => {
    const w = await mount(`<vql-widget></vql-widget>`, new FakeSession());
    await w.open();
    w.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(w.view).toBe("collapsed");
  });
});

describe("session events", () => {
  it("reports the mic and the agent, and mutes through the mic button", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    const seen = events(w, "vql-mic", "vql-agent");
    w.sessionSource = { session_id: "s" };
    await w.open();
    await w.updateComplete;
    expect(seen).toContainEqual({ type: "vql-mic", detail: { state: "live", hint: false } });
    expect(seen).toContainEqual({ type: "vql-agent", detail: { state: "listening" } });
    shadow(w).querySelector("vql-mic")?.dispatchEvent(new CustomEvent("vql-mute", { detail: { muted: true } }));
    expect(s.calls).toContain("mute:true");
    await w.updateComplete;
    expect(shadow(w).querySelector("vql-mic")?.getAttribute("state")).toBe("muted");
  });

  it("shows the coach mark for a blocked mic until dismissed", async () => {
    const s = new FakeSession();
    s.onConnect = (x) => {
      x.patch({ status: "connected", agent: "listening" });
      x.mic.patch({ state: "blocked", device: "blocked", permission: "denied" });
    };
    const w = await mount(`<vql-widget></vql-widget>`, s);
    w.sessionSource = { session_id: "s" };
    await w.open();
    await w.updateComplete;
    const coach = shadow(w).querySelector("vql-coach");
    expect(coach?.getAttribute("state")).toBe("blocked");
    coach?.dispatchEvent(new CustomEvent("vql-dismiss"));
    await w.updateComplete;
    expect(shadow(w).querySelector("vql-coach")).toBeNull();
  });

  it("waits before coaching a mic prompt, and never when permission is granted", async () => {
    vi.useFakeTimers();
    try {
      const s = new FakeSession();
      s.onConnect = (x) => {
        x.patch({ status: "connecting" });
        x.mic.patch({ state: "asking", device: "asking", permission: "prompt" });
      };
      const w = await mount(`<vql-widget></vql-widget>`, s);
      w.sessionSource = { session_id: "s" };
      await w.open();
      await w.updateComplete;
      expect(shadow(w).querySelector("vql-coach")).toBeNull();
      await vi.advanceTimersByTimeAsync(1000);
      await w.updateComplete;
      expect(shadow(w).querySelector("vql-coach")).not.toBeNull();
      s.mic.patch({ permission: "granted" });
      await w.updateComplete;
      expect(shadow(w).querySelector("vql-coach")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the silence hint in the card", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    w.sessionSource = { session_id: "s" };
    await w.open();
    s.mic.patch({ hint: true });
    await w.updateComplete;
    expect(shadow(w).querySelector("[part=hint]")).not.toBeNull();
  });

  it("feeds the agent's words into the captions", async () => {
    const s = new FakeSession();
    const w = await mount(`<vql-widget></vql-widget>`, s);
    w.sessionSource = { session_id: "s" };
    await w.open();
    await w.updateComplete;
    s.fire("agentStarted");
    s.fire("agentSentence", "Hello there.");
    s.fire("agentWord", "Hello");
    const captions = shadow(w).querySelector("vql-captions") as HTMLElement & { updateComplete: Promise<unknown> };
    await captions.updateComplete;
    expect(captions.shadowRoot?.textContent).toContain("Hello");
  });
});

describe("placement", () => {
  it("place() moves to an anchor and reports it", async () => {
    const w = await mount(`<vql-widget></vql-widget>`, new FakeSession());
    const seen = events(w, "vql-place");
    w.place("top-left");
    expect(seen.at(-1)?.detail).toMatchObject({ anchor: "top-left", free: false });
  });

  it("arrow keys step between anchors", () => {
    expect(neighbourAnchor("bottom-right", "ArrowLeft")).toBe("bottom-center");
    expect(neighbourAnchor("bottom-right", "ArrowUp")).toBe("middle-right");
    expect(neighbourAnchor("bottom-right", "ArrowRight")).toBe("bottom-right");
    expect(neighbourAnchor("top-left", "ArrowUp")).toBe("top-left");
  });
});
