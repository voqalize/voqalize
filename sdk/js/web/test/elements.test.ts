import { LitElement, html } from "lit";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PlacementController } from "../src/controllers/placement.js";
import { coachKey, detectBrowser, detectOS } from "../src/elements/browser.js";
import { contrast, parseColour, themeColours } from "../src/elements/colour.js";
import { cssProps } from "../src/elements/css-props.js";
import { defineAllElements } from "../src/elements/define.js";
import { resolveBackground } from "../src/elements/face.js";
import { meterLevel } from "../src/elements/mic.js";
import { statusOf } from "../src/elements/status.js";
import { tagChain, translator } from "../src/elements/words.js";
import { eventName } from "../src/react.js";

beforeAll(() => defineAllElements());

afterEach(() => {
  document.body.innerHTML = "";
});

type Lit = HTMLElement & { updateComplete: Promise<unknown> };

async function make<T extends Lit>(html: string): Promise<T> {
  document.body.innerHTML = html;
  const el = document.body.firstElementChild as T;
  await el.updateComplete;
  return el;
}

describe("words", () => {
  it("falls back from the full tag to the primary subtag to English, and fills in the name", () => {
    const t = translator({ "pt-BR": { "end.again": "Ligar de novo" }, pt: { "end.close": "Fechar" } }, "pt-BR", "Emily");
    expect(t("end.again")).toBe("Ligar de novo");
    expect(t("end.close")).toBe("Fechar");
    expect(t("launcher.label")).toContain("Emily");
    expect(t("no.such.key")).toBe("no.such.key");
  });

  it("orders the tag chain most specific first", () => {
    expect(tagChain("en-GB")).toEqual(["en-GB", "en-gb", "en"]);
    expect(tagChain(undefined)).toEqual([]);
  });
});

describe("browser", () => {
  it("tells the browsers apart, including iPadOS posing as a Mac", () => {
    const mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";
    expect(detectBrowser({ userAgent: mac, maxTouchPoints: 0 })).toBe("safari");
    expect(detectBrowser({ userAgent: mac, maxTouchPoints: 5 })).toBe("ios");
    expect(detectBrowser({ userAgent: "Mozilla/5.0 Chrome/130.0 Safari/537.36 Edg/130.0" })).toBe("edge");
    expect(detectBrowser({ userAgent: "Mozilla/5.0 (Android 14) Chrome/130.0 Mobile Safari/537.36" })).toBe("android");
    expect(detectBrowser({ userAgent: "Mozilla/5.0 Gecko/20100101 Firefox/131.0" })).toBe("firefox");
  });

  it("picks the coach text by browser", () => {
    expect(coachKey("blocked", "chrome")).toBe("coach.blocked");
    expect(coachKey("blocked", "edge")).toBe("coach.blocked");
    expect(coachKey("asking", "safari")).toBe("coach.asking.safari");
    expect(coachKey("missing", "ios")).toBe("coach.missing");
  });

  it("has English for every coach key it can ask for", () => {
    const t = translator(undefined, "en", "Emily");
    for (const state of ["asking", "blocked", "missing", "check"] as const) {
      for (const b of ["chrome", "edge", "firefox", "safari", "ios", "android", "other"] as const) {
        for (const os of ["mac", "windows", "ios", "android", "other"] as const) {
          const key = coachKey(state, b, os);
          expect(t(key)).not.toBe(key);
        }
      }
    }
  });

  it("tells the operating systems apart for the mic check", () => {
    const mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";
    expect(detectOS({ userAgent: mac, maxTouchPoints: 0 })).toBe("mac");
    expect(detectOS({ userAgent: mac, maxTouchPoints: 5 })).toBe("ios");
    expect(detectOS({ userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0" })).toBe("windows");
    expect(detectOS({ userAgent: "Mozilla/5.0 (Linux; Android 14) Chrome/130.0" })).toBe("android");
    expect(detectOS({ userAgent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0" })).toBe("other");
    expect(coachKey("check", "chrome", "windows")).toBe("coach.check.windows");
    expect(coachKey("check", "safari", "other")).toBe("coach.check");
  });
});

describe("colour", () => {
  it("picks readable text on the brand and repairs unreadable ink", () => {
    expect(themeColours({ brand: "#fde047" }).onBrand).toBe("#111111");
    expect(themeColours({ brand: "#1e3a8a" }).onBrand).toBe("#ffffff");
    const repaired = themeColours({ background: "#111111", ink: "#222222" });
    expect(repaired.ink).toBe("#ffffff");
    expect(contrast(parseColour("#000")!, parseColour("#fff")!)).toBeCloseTo(21, 0);
  });
});

describe("status", () => {
  it("puts connecting and the mic ahead of the agent", () => {
    expect(statusOf("connecting", "speaking", "live").key).toBe("status.connecting");
    expect(statusOf("connected", "speaking", "blocked")).toEqual({ key: "status.blocked", tone: "warn" });
    expect(statusOf("connected", "listening", "muted").key).toBe("status.muted");
    expect(statusOf("connected", "speaking", "muted").key).toBe("status.speaking");
    expect(statusOf("connected", "idle", "live").key).toBe("status.listening");
  });
});

describe("cssProps", () => {
  class Probe extends LitElement {
    static override properties = { colour: {} };
    declare colour: string | undefined;
    protected override render() {
      return html`<div ${cssProps({ "--x": this.colour, opacity: 0.5 })}></div>`;
    }
  }
  customElements.define("vql-probe", Probe);

  it("sets custom properties through the CSSOM and removes them when unset", async () => {
    const el = await make<Probe>(`<vql-probe></vql-probe>`);
    el.colour = "red";
    await el.updateComplete;
    const div = el.shadowRoot?.querySelector("div") as HTMLDivElement;
    expect(div.style.getPropertyValue("--x")).toBe("red");
    expect(div.style.getPropertyValue("opacity")).toBe("0.5");
    el.colour = undefined;
    await el.updateComplete;
    expect(div.style.getPropertyValue("--x")).toBe("");
  });
});

describe("parts", () => {
  it("launcher: reports a launch and a single preload", async () => {
    document.body.innerHTML = `<vql-launcher variant="card" name="Emily" label="Talk to Emily"></vql-launcher>`;
    const el = document.querySelector("vql-launcher") as HTMLElement;
    const seen: string[] = [];
    el.addEventListener("vql-launch", () => seen.push("launch"));
    el.addEventListener("vql-preload", () => seen.push("preload"));
    const button = el.shadowRoot?.querySelector("button") as HTMLButtonElement;
    expect(button.getAttribute("part")).toBe("button");
    expect(el.shadowRoot?.textContent).toContain("Talk to Emily");
    button.dispatchEvent(new Event("focus"));
    button.dispatchEvent(new Event("pointerenter"));
    button.click();
    expect(seen).toEqual(["preload", "launch"]);
  });

  it("mic: toggles mute and opens the device menu", async () => {
    const el = await make<Lit & { state: string }>(`<vql-mic state="live" devices></vql-mic>`);
    const seen: unknown[] = [];
    el.addEventListener("vql-mute", (e) => seen.push((e as CustomEvent).detail));
    el.addEventListener("vql-devices", (e) => seen.push((e as CustomEvent).detail));
    const buttons = el.shadowRoot?.querySelectorAll("button") as NodeListOf<HTMLButtonElement>;
    buttons[0]?.click();
    buttons[1]?.click();
    expect(seen).toEqual([{ muted: true }, { open: true }]);
    expect(meterLevel(0)).toBe(0);
    expect(meterLevel(1)).toBe(1);
  });

  it("mic: unmutes a mic muted while the prompt was still open", async () => {
    // Muted before the mic went live: the state is still "asking", and the
    // next press must unmute, not mute again.
    const el = await make<Lit & { muted: boolean }>(`<vql-mic state="asking"></vql-mic>`);
    el.muted = true;
    await el.updateComplete;
    const seen: unknown[] = [];
    el.addEventListener("vql-mute", (e) => seen.push((e as CustomEvent).detail));
    const button = el.shadowRoot?.querySelector("button") as HTMLButtonElement;
    expect(button.getAttribute("aria-pressed")).toBe("true");
    button.click();
    expect(seen).toEqual([{ muted: false }]);
  });

  it("devices: selects a mic and closes on Escape", async () => {
    const el = await make<Lit & { mics: unknown[] }>(`<vql-devices></vql-devices>`);
    el.mics = [
      { deviceId: "a", label: "Built-in" },
      { deviceId: "b", label: "Headset" },
    ];
    await el.updateComplete;
    const seen: unknown[] = [];
    el.addEventListener("vql-select-mic", (e) => seen.push((e as CustomEvent).detail));
    el.addEventListener("vql-close", () => seen.push("close"));
    const select = el.shadowRoot?.querySelector("select") as HTMLSelectElement;
    select.value = "b";
    select.dispatchEvent(new Event("change"));
    el.shadowRoot?.firstElementChild?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, composed: true }));
    expect(seen).toEqual([{ id: "b" }, "close"]);
  });

  it("captions: announces each finished sentence once, in a polite live region", async () => {
    const el = await make<Lit & { snapshot: unknown }>(`<vql-captions></vql-captions>`);
    el.snapshot = { visible: true, lines: [{ words: [{ text: "Hi", spoken: true, current: true }] }], announcement: { id: 1, text: "Hi." } };
    await el.updateComplete;
    const live = el.shadowRoot?.querySelector("[aria-live=polite]");
    expect(live?.textContent?.trim()).toBe("Hi.");
    expect(el.shadowRoot?.querySelector("[part~=current]")?.textContent).toBe("Hi");
  });

  it("captions: announces a sentence again when the agent repeats it", async () => {
    const el = await make<Lit & { snapshot: unknown }>(`<vql-captions></vql-captions>`);
    const say = async (id: number) => {
      el.snapshot = { visible: true, lines: [], announcement: { id, text: "Sorry?" } };
      await el.updateComplete;
      return el.shadowRoot?.querySelector("[aria-live=polite] p");
    };
    const first = await say(1);
    const again = await say(2);
    expect(again?.textContent).toBe("Sorry?");
    // A new node, so the live region reads it out again.
    expect(again).not.toBe(first);
  });

  it("coach: renders only for a mic the agent cannot hear", async () => {
    const el = await make<Lit & { state: string; browser: string }>(`<vql-coach state="live"></vql-coach>`);
    expect(el.shadowRoot?.querySelector("[part=coach]")).toBeNull();
    el.state = "blocked";
    el.browser = "firefox";
    await el.updateComplete;
    expect(el.shadowRoot?.querySelector("[part=text]")?.textContent).toBe(
      translator(undefined, "en", "")("coach.blocked.firefox"),
    );
  });

  it("mic pill: says what the mic needs and asks for it when pressed", async () => {
    const el = await make<Lit & { kind: string | null }>(`<vql-mic-pill></vql-mic-pill>`);
    expect(el.shadowRoot?.querySelector("[part=pill]")).toBeNull();
    el.kind = "permission";
    await el.updateComplete;
    expect(el.shadowRoot?.querySelector("[part=text]")?.textContent).toBe("Grant mic permission");
    expect(el.shadowRoot?.querySelector("[aria-live=polite]")?.textContent).toBe("Grant mic permission");
    const seen: unknown[] = [];
    el.addEventListener("vql-pill-action", (e) => seen.push((e as CustomEvent).detail));
    el.shadowRoot?.querySelector<HTMLButtonElement>("[part=pill]")?.click();
    expect(seen).toEqual([{ kind: "permission" }]);
    el.kind = "muted";
    await el.updateComplete;
    expect(el.shadowRoot?.querySelector("[part=text]")?.textContent).toBe("You are muted");
    el.kind = "check";
    await el.updateComplete;
    expect(el.shadowRoot?.querySelector("[part=text]")?.textContent).toBe("Is your mic working?");
  });

  it("end: hangs up", async () => {
    const el = await make<Lit>(`<vql-end></vql-end>`);
    const hangup = vi.fn();
    el.addEventListener("vql-hangup", hangup);
    el.shadowRoot?.querySelector("button")?.click();
    expect(hangup).toHaveBeenCalledOnce();
  });

  it("face: resolves backgrounds and shows a wave when voice only", async () => {
    expect(resolveBackground("#112233").kind).toBe("css");
    expect(resolveBackground("linear-gradient(#000, #fff)").kind).toBe("css");
    expect(resolveBackground("https://example.com/loop.mp4").kind).toBe("video");
    expect(resolveBackground("https://example.com/sky.gif").kind).toBe("image");
    const el = await make<Lit>(`<vql-face voice-only></vql-face>`);
    expect(el.shadowRoot?.querySelector("[part=wave]")).not.toBeNull();
  });
});

describe("placement keyboard moves", () => {
  const view = { width: 1200, height: 800 };
  const size = { width: 300, height: 400 };

  it("moveTo goes to an anchor and nudge moves a free widget", () => {
    const snap = new PlacementController({ anchor: "bottom-right", move: "snap", remember: "off", offset: 16, topClear: 0 });
    snap.layout(size, view, []);
    snap.moveTo("top-left");
    expect(snap.getSnapshot().anchor).toBe("top-left");
    snap.nudge(10, 10); // ignored when not free
    expect(snap.getSnapshot().anchor).toBe("top-left");

    const free = new PlacementController({ anchor: "bottom-right", move: "free", remember: "off", offset: 16, topClear: 0 });
    free.layout(size, view, []);
    const before = free.getSnapshot().point;
    free.nudge(-16, -16);
    const after = free.getSnapshot().point;
    expect(after.x).toBe(before.x - 16);
    expect(after.y).toBe(before.y - 16);
  });

  it("a fixed widget moves only when forced", () => {
    const fixed = new PlacementController({ anchor: "bottom-right", move: "fixed", remember: "off", offset: 16, topClear: 0 });
    fixed.layout(size, view, []);
    fixed.moveTo("top-left");
    expect(fixed.getSnapshot().anchor).toBe("bottom-right");
    fixed.moveTo("top-left", true);
    expect(fixed.getSnapshot().anchor).toBe("top-left");
  });
});

describe("react", () => {
  it("maps onX props to vql-x events", () => {
    expect(eventName("onHangup")).toBe("vql-hangup");
    expect(eventName("onSelectMic")).toBe("vql-select-mic");
  });
});
