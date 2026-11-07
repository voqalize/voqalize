import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { VqlWidget } from "../src/elements/widget.js";
import { VoqalizeEnd, VoqalizeLauncher, VoqalizeWidget, useMicState, useSessionState } from "../src/react.js";
import { FakeSession } from "./support/fake-session.js";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.innerHTML = "";
});

function mount(node: ReturnType<typeof createElement>) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => root.render(node));
  return { host, root };
}

describe("React wrappers", () => {
  it("passes objects as properties, not as attributes", () => {
    const config = { name: "Emily", launcher: { style: "card" as const } };
    const { host } = mount(createElement(VoqalizeWidget, { config }));
    const w = host.querySelector("vql-widget") as VqlWidget;
    expect(w.config).toBe(config);
    expect(w.getAttribute("config")).toBeNull();
  });

  it("sets attributes on an element that has no properties, and listens for vql events", async () => {
    const seen: string[] = [];
    const { host } = mount(
      createElement("div", null, [
        createElement(VoqalizeLauncher, { key: "l", variant: "face", name: "Emily" }),
        createElement(VoqalizeEnd, { key: "e", onHangup: () => seen.push("hangup") }),
      ]),
    );
    expect(host.querySelector("vql-launcher")?.getAttribute("variant")).toBe("face");
    const end = host.querySelector("vql-end") as HTMLElement & { updateComplete: Promise<unknown> };
    await end.updateComplete;
    end.shadowRoot?.querySelector("button")?.click();
    expect(seen).toEqual(["hangup"]);
  });

  it("puts back a prop the page stops passing", () => {
    const config = { name: "Emily" };
    const { host, root } = mount(
      createElement("div", null, [
        createElement(VoqalizeWidget, { key: "w", config }),
        createElement(VoqalizeLauncher, { key: "l", variant: "face" }),
      ]),
    );
    const w = host.querySelector("vql-widget") as VqlWidget;
    const original = (document.createElement("vql-widget") as VqlWidget).config;
    expect(w.config).toBe(config);
    act(() =>
      root.render(
        createElement("div", null, [createElement(VoqalizeWidget, { key: "w" }), createElement(VoqalizeLauncher, { key: "l" })]),
      ),
    );
    expect(w.config).toEqual(original);
    expect(host.querySelector("vql-launcher")?.hasAttribute("variant")).toBe(false);
  });

  it("re-renders hooks on store changes", () => {
    const s = new FakeSession();
    const seen: string[] = [];
    function Probe() {
      const session = useSessionState(s);
      const mic = useMicState(s);
      seen.push(`${session?.status}/${mic?.state}`);
      return null;
    }
    mount(createElement(Probe));
    act(() => {
      void s.connect({});
    });
    expect(seen.at(-1)).toBe("connected/live");
  });
});
