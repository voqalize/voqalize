/**
 * Developer mode: a page names its things in markup, a script-tag page gets
 * Stage from its spec alone, and a React app wires it with four hooks.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { findPart, findThing, partsOf, place, things } from "../src/markup";
import { type ReactHooks, stageHooks } from "../src/react";
import { defineScene } from "../src/scene";
import { attach } from "../src/script";

function box(el: Element): void {
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 100, height: 20, right: 100, bottom: 20, x: 0, y: 0, toJSON() {} }) as DOMRect;
}

function page(): void {
  document.body.innerHTML = `
    <main data-stage-place="catalog">
      <section data-stage-thing="rooms" data-stage-label="Our rooms"><h2>Our rooms</h2></section>
      <section data-stage-thing="spa"><h2>The Spa</h2></section>
      <aside data-stage-thing="filters">
        <a data-stage-part="Tamaño:King">King</a> <a data-stage-part="Color:Blanco">Blanco</a>
        <a data-stage-part="Color:Beige">Beige</a>
      </aside>
    </main>`;
  for (const el of document.body.querySelectorAll("*")) box(el);
}

/** A pipecat client, as far as Stage uses one. */
function fakeClient() {
  const handlers = new Map<string, Set<(...a: any[]) => void>>();
  const sent: [string, any][] = [];
  return {
    sent,
    on(name: string, fn: (...a: any[]) => void) {
      (handlers.get(name) ?? handlers.set(name, new Set()).get(name)!).add(fn);
    },
    off(name: string, fn: (...a: any[]) => void) {
      handlers.get(name)?.delete(fn);
    },
    sendUIEvent(event: string, payload?: unknown) {
      sent.push([event, payload]);
    },
    emit(name: string, data?: unknown) {
      handlers.get(name)?.forEach((fn) => fn(data));
    },
  };
}

const move = (call_ref: string, id: string, args: Record<string, unknown>) => ({
  command: "stage_move",
  payload: { call_ref, move: id, args, when: "now" },
});

const results = (c: ReturnType<typeof fakeClient>) => c.sent.filter(([e]) => e === "stage_result").map(([, p]) => p);

afterEach(() => {
  document.documentElement.querySelectorAll("[data-voqalize]").forEach((n) => n.remove());
  document.body.innerHTML = "";
});

describe("data-stage-* markup", () => {
  it("finds things by name, by label and by the label's start, and parts by facet", () => {
    page();
    expect(things().map((t) => [t.name, t.label])).toEqual([
      ["rooms", "Our rooms"],
      ["spa", "The Spa"],
      ["filters", "King Blanco Beige"],
    ]);
    expect(findThing("rooms")?.getAttribute("data-stage-thing")).toBe("rooms");
    expect(findThing("our ROOMS")?.getAttribute("data-stage-thing")).toBe("rooms");
    expect(findThing("the spa")?.getAttribute("data-stage-thing")).toBe("spa");
    expect(findThing("The")?.getAttribute("data-stage-thing")).toBe("spa");
    expect(findThing("garage")).toBeNull();
    expect(findPart("tamano", "king")?.textContent).toBe("King");
    expect(partsOf("Color")).toEqual(["Blanco", "Beige"]);
    expect(place()).toBe("catalog");
  });
});

const shop = defineScene({
  stage: 1,
  id: "shop",
  moves: [
    { id: "core.show", verb: "show", class: "look", args: [{ name: "target" }] },
    { id: "commerce.filter", verb: "filter", class: "reversible", args: [{ name: "facet" }, { name: "value", optional: true }] },
    { id: "commerce.sort", verb: "sort", class: "reversible", args: [{ name: "order" }] },
  ],
  slices: [{ id: "listing", fields: [{ name: "sort", optional: true }, { name: "count", type: "integer", optional: true }] }],
  events: [{ id: "listing.sorted", slice: "listing" }],
});

describe("the script-tag host", () => {
  it("binds the stock performers to the markup, and says what it cannot perform", async () => {
    page();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const client = fakeClient();
    const stage = await attach(client, { spec: shop.spec as never, theme: { color: "#000", beatMs: 0, dwellMs: 0 } });
    expect(stage.unbound).toEqual(["commerce.sort"]);
    expect(warn).toHaveBeenCalledWith("stage: nothing on this page performs commerce.sort");
    const pressed: string[] = [];
    document.querySelectorAll("[data-stage-part]").forEach((a) => a.addEventListener("click", () => pressed.push(a.textContent!)));
    client.emit("uiCommand", move("c1", "commerce.filter", { facet: "Color", value: "Blanco, Beige" }));
    client.emit("uiCommand", move("c2", "core.show", { target: "garage" }));
    await vi.waitFor(() => expect(results(client)).toHaveLength(2), { timeout: 8000 });
    expect(pressed).toEqual(["Blanco", "Beige"]);
    expect(results(client)[0]).toMatchObject({ call_ref: "c1", outcome: "applied", detail: "Color Blanco, Beige pressed" });
    expect(results(client)[1]).toMatchObject({
      call_ref: "c2",
      outcome: "refused",
      refused: [{ arg: "target", options: ["Our rooms", "The Spa", "King Blanco Beige"] }],
    });
    stage.detach();
    warn.mockRestore();
  });
});

/** Just enough React to mount a component, re-render it and unmount it:
 *  state, refs and effects with their dependencies, run after each render. */
function tinyReact() {
  const slots: unknown[] = [];
  const effects: { deps?: readonly unknown[]; cleanup?: void | (() => void) }[] = [];
  let i = 0;
  let e = 0;
  let pending: (() => void)[] = [];
  let rerender = () => {};
  /** A state set while rendering or running effects renders once after, as React batches it. */
  let busy = false;
  let dirty = false;
  const React: ReactHooks = {
    useState<T>(initial: T) {
      const at = i++;
      if (!(at in slots)) slots[at] = initial;
      return [
        slots[at] as T,
        (v: T) => {
          slots[at] = v;
          if (busy) dirty = true;
          else rerender();
        },
      ];
    },
    useRef<T>(initial: T) {
      const at = i++;
      if (!(at in slots)) slots[at] = { current: initial };
      return slots[at] as { current: T };
    },
    useEffect(effect, deps) {
      const at = e++;
      const old = effects[at];
      if (old && deps && old.deps && deps.every((d, k) => Object.is(d, old.deps![k]))) return;
      pending.push(() => {
        if (typeof old?.cleanup === "function") old.cleanup();
        effects[at] = { deps, cleanup: effect() };
      });
    },
  };
  const mount = (component: () => void) => {
    rerender = () => {
      if (busy) {
        dirty = true;
        return;
      }
      do {
        dirty = false;
        busy = true;
        i = 0;
        e = 0;
        component();
        const run = pending;
        pending = [];
        run.forEach((f) => f());
        busy = false;
      } while (dirty);
    };
    rerender();
    return {
      rerender,
      unmount: () => effects.forEach((x) => typeof x?.cleanup === "function" && x.cleanup()),
    };
  };
  return { React, mount };
}

describe("the React hooks", () => {
  it("attach Stage, perform with the latest closure, and name state changes", async () => {
    const { React, mount } = tinyReact();
    const { useStage, useMove, useSlice, useNavigated } = stageHooks(React);
    const client = fakeClient();
    let sort = "relevance";
    let path = "/sabanas";
    const component = () => {
      const stage = useStage(client, shop, { theme: { color: "#000", beatMs: 0, dwellMs: 0 } });
      const now = sort;
      useMove(stage, "commerce.sort", async ({ order }) => {
        sort = order;
        app.rerender();
        return `sorted by ${order}, was ${now}`;
      });
      useSlice(stage, sort, (prev, next) => (prev !== undefined && prev !== next ? (["listing.sorted", { sort: next }] as const) : null));
      useNavigated(stage, path);
    };
    const app = mount(component);
    client.emit("uiCommand", move("c1", "commerce.sort", { order: "price_asc" }));
    await vi.waitFor(() => expect(results(client)).toHaveLength(1), { timeout: 8000 });
    expect(results(client)[0]).toMatchObject({ outcome: "applied", detail: "sorted by price_asc, was relevance" });
    const events = () => client.sent.filter(([ev]) => ev === "stage_event").map(([, p]) => p);
    expect(events()).toEqual([{ name: "listing.sorted", by: "agent", call_ref: "c1", data: { sort: "price_asc" } }]);

    // The visitor sorts, later: theirs.
    await new Promise((r) => setTimeout(r, 600));
    sort = "newest";
    app.rerender();
    expect(events()[1]).toEqual({ name: "listing.sorted", by: "visitor", data: { sort: "newest" } });

    // A route change says hello again; the first render did not.
    const hellos = () => client.sent.filter(([ev]) => ev === "stage_hello").length;
    const before = hellos();
    path = "/toallas";
    app.rerender();
    expect(hellos()).toBe(before + 1);

    app.unmount();
    client.emit("uiCommand", move("c2", "commerce.sort", { order: "price_desc" }));
    await new Promise((r) => setTimeout(r, 20));
    expect(results(client)).toHaveLength(1);
  });
});
