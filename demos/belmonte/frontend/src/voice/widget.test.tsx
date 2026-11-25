/**
 * The concierge's widget: a circle by default, before and during a call; a tap
 * expands it (Talk before a call; exactly Mute and End in one; no minimise);
 * it folds back by itself after a few seconds untouched, and on Escape.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { COLLAPSE_MS, Widget } from "./Widget";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLElement;
let root: ReturnType<typeof createRoot>;

function render(props: Partial<Parameters<typeof Widget>[0]> = {}) {
  const calls = { mute: 0, end: 0, talk: 0 };
  act(() => {
    root.render(
      <MemoryRouter initialEntries={["/spa"]}>
        <Widget
          live={false}
          state="listening"
          muted={false}
          onMute={() => calls.mute++}
          onEnd={() => calls.end++}
          onTalk={() => calls.talk++}
          {...props}
        >
          <img alt="Kasia" />
        </Widget>
      </MemoryRouter>,
    );
  });
  return calls;
}
const face = () => host.querySelector<HTMLButtonElement>(".bw-face")!;
const buttons = () => [...host.querySelectorAll<HTMLButtonElement>(".bw-panel button")].map((b) => b.getAttribute("aria-label") ?? b.textContent?.trim());
const click = (el: Element) => act(() => (el as HTMLElement).click());

describe("the concierge's widget", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = '<div id="screen"></div>';
    host = document.getElementById("screen")!;
    root = createRoot(host);
  });
  afterEach(() => {
    act(() => root.unmount());
    vi.useRealTimers();
  });

  it("is a circle with her face before a call; a tap offers Talk", () => {
    const calls = render();
    expect(host.querySelector(".bw.is-closed")).not.toBeNull();
    expect(face().getAttribute("aria-expanded")).toBe("false");
    expect(face().getAttribute("aria-label")).toContain("Kasia");
    expect(host.querySelector(".bw-panel")).toBeNull();
    click(face());
    expect(face().getAttribute("aria-expanded")).toBe("true");
    expect(host.querySelector(".bw-role")?.textContent).toBe("Spa and activities");
    click(host.querySelector(".bw-talk")!);
    expect(calls.talk).toBe(1);
  });

  it("in a call it is still a circle; expanded it has exactly Mute and End", () => {
    const calls = render({ live: true, state: "speaking" });
    expect(host.querySelector(".bw.is-closed.is-live.is-speaking")).not.toBeNull();
    click(face());
    expect(buttons()).toEqual(["Turn microphone off", "End the call"]);
    expect(host.textContent).not.toMatch(/minimi[sz]e/i);
    click(host.querySelector(".bw-btn")!);
    click(host.querySelector(".bw-end")!);
    expect(calls).toMatchObject({ mute: 1, end: 1 });
  });

  it("folds back by itself after a few seconds untouched, and a touch keeps it open", () => {
    render({ live: true });
    click(face());
    act(() => vi.advanceTimersByTime(COLLAPSE_MS - 1000));
    act(() => host.querySelector(".bw")!.dispatchEvent(new Event("pointerdown", { bubbles: true })));
    act(() => vi.advanceTimersByTime(COLLAPSE_MS - 1000));
    expect(host.querySelector(".bw.is-open")).not.toBeNull();
    act(() => vi.advanceTimersByTime(1500));
    expect(host.querySelector(".bw.is-closed")).not.toBeNull();
    expect(COLLAPSE_MS).toBeGreaterThanOrEqual(4000);
    expect(COLLAPSE_MS).toBeLessThanOrEqual(5000);
  });

  it("folds on Escape and on a second tap of the face", () => {
    render({ live: true });
    click(face());
    act(() => host.querySelector(".bw")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(host.querySelector(".bw.is-closed")).not.toBeNull();
    click(face());
    click(face());
    expect(host.querySelector(".bw.is-closed")).not.toBeNull();
  });

  it("opens by itself to show a connection error", () => {
    render({ status: "Kasia could not connect." });
    expect(host.querySelector(".bw-role")?.textContent).toBe("Kasia could not connect.");
  });
});
