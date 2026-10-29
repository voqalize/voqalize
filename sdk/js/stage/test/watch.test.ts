/**
 * The watchers a site starts when it wants the agent to know what the visitor
 * does: the part they stay on (not one they scroll past), and the forms they
 * fill in, by field name only, once they pause.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { attach } from "../src/script";
import { type FormState, formState, type Viewed, watchForms, watchThings } from "../src/watch";

/** Lay `el` out at `top` for `height` pixels in a 1000 × 800 window. */
function at(el: Element, top: number, height: number): void {
  el.getBoundingClientRect = () =>
    ({ left: 0, top, width: 1000, height, right: 1000, bottom: top + height, x: 0, y: top, toJSON() {} }) as DOMRect;
}

function page(): HTMLElement[] {
  document.body.innerHTML = `
    <section data-stage-thing="rooms" data-stage-label="Our rooms"><h2>Our rooms</h2></section>
    <section data-stage-thing="spa"><h2>The Spa</h2></section>
    <form data-stage-form="Enquiry">
      <input name="first_name" required>
      <input name="email" type="email" required>
      <input name="phone">
      <input name="consent" type="checkbox">
      <input type="hidden" name="token" value="x">
    </form>`;
  return [...document.querySelectorAll("section")];
}

beforeEach(() => {
  vi.useFakeTimers();
  Object.assign(window, { innerWidth: 1000, innerHeight: 800 });
});
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("watchThings", () => {
  it("reports the part held in the window, not one scrolled past, and once", () => {
    const [rooms, spa] = page();
    at(rooms!, 0, 700);
    at(spa!, 700, 700);
    const seen: Viewed[] = [];
    const stop = watchThings((v) => seen.push(v), { dwellMs: 1500 });
    vi.advanceTimersByTime(1600);
    expect(seen).toEqual([{ thing: "rooms", label: "Our rooms" }]);
    // Scrolled past the spa in half a second, back to the rooms: nothing new.
    at(rooms!, -700, 700);
    at(spa!, 0, 700);
    window.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(500);
    at(rooms!, 0, 700);
    at(spa!, 700, 700);
    window.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(2000);
    expect(seen).toHaveLength(1);
    // Stays on the spa: it is reported.
    at(rooms!, -700, 700);
    at(spa!, 0, 700);
    window.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(1700);
    expect(seen).toEqual([
      { thing: "rooms", label: "Our rooms" },
      { thing: "spa", label: "The Spa" },
    ]);
    stop();
  });
});

describe("watchForms", () => {
  it("reports field names once typing pauses, never what was typed", () => {
    page();
    const states: FormState[] = [];
    const stop = watchForms((s) => states.push(s), { quietMs: 1200 });
    const name = document.querySelector<HTMLInputElement>("[name=first_name]")!;
    for (const ch of "Ana") {
      name.value += ch;
      name.dispatchEvent(new Event("input", { bubbles: true }));
      vi.advanceTimersByTime(200);
    }
    expect(states).toEqual([]);
    vi.advanceTimersByTime(1200);
    expect(states).toEqual([{ form: "Enquiry", filled: ["first_name"], missing: ["email"], left: 1, done: false }]);
    expect(JSON.stringify(states)).not.toContain("Ana");
    // The same state again is not reported twice.
    name.dispatchEvent(new Event("change", { bubbles: true }));
    vi.advanceTimersByTime(1300);
    expect(states).toHaveLength(1);
    stop();
  });

  it("counts a ticked box as filled and leaves hidden fields out", () => {
    page();
    document.querySelector<HTMLInputElement>("[name=consent]")!.checked = true;
    const state = formState(document.querySelector("form")!);
    expect(state.filled).toEqual(["consent"]);
    expect(state.missing).toEqual(["first_name", "email"]);
  });
});

describe("the script host", () => {
  it("starts the watchers only for a spec that takes the watch kit", async () => {
    const [rooms] = page();
    at(rooms!, 0, 700);
    const sent: [string, any][] = [];
    const client = { on() {}, off() {}, sendUIEvent: (e: string, p?: unknown) => sent.push([e, p]) };
    const spec = {
      stage: 1 as const,
      id: "lodge",
      moves: [],
      slices: [
        { id: "view", fields: [{ name: "thing" }, { name: "label" }] },
        { id: "form", fields: [{ name: "form" }, { name: "filled", type: "array" as const }] },
      ],
      events: [
        { id: "view.changed", slice: "view", op: "set" as const },
        { id: "form.changed", slice: "form", op: "set" as const },
      ],
    };
    const stage = await attach(client, { spec, theme: { color: "#000" }, watch: { dwellMs: 100 } });
    vi.advanceTimersByTime(200);
    expect(sent.filter(([e]) => e === "stage_event").map(([, p]) => p)).toEqual([
      { name: "view.changed", by: "visitor", data: { thing: "rooms", label: "Our rooms" } },
    ]);
    stage.detach();

    sent.length = 0;
    const plain = await attach(client, { spec: { stage: 1, id: "lodge", moves: [] }, theme: { color: "#000" } });
    vi.advanceTimersByTime(5000);
    expect(sent.filter(([e]) => e === "stage_event")).toEqual([]);
    plain.detach();
  });
});
