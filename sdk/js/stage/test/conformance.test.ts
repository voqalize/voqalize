/**
 * The Stage conformance checks catches a page that breaks Stage's rules: a move with
 * no performer or the wrong class, a change made before the spotlight rang it,
 * a look that shows nothing.
 */

import { afterEach, describe, expect, it } from "vitest";

import { checkRegistry, conformance } from "../src/conformance";
import { Moves } from "../src/moves";
import { defineScene } from "../src/scene";
import { Spotlight } from "../src/spotlight";

const scene = defineScene({
  stage: 1,
  id: "shop",
  moves: [
    { id: "core.show", verb: "show", class: "look", args: [{ name: "target" }] },
    { id: "listing.sort", verb: "sort", class: "reversible", args: [{ name: "order" }] },
    { id: "cart.add", class: "confirmed", args: [{ name: "path" }] },
  ],
});

function box(el: Element): void {
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 100, height: 20, right: 100, bottom: 20, x: 0, y: 0, toJSON() {} }) as DOMRect;
}

function page(): void {
  document.body.innerHTML = `<h2 id="h">Rooms</h2><select id="sort"><option>relevance</option><option>price_asc</option></select><button id="add">Add</button>`;
  for (const el of document.body.querySelectorAll("*")) box(el);
}

const $ = (id: string) => document.getElementById(id)!;

afterEach(() => {
  document.documentElement.querySelectorAll("[data-voqalize]").forEach((n) => n.remove());
  document.body.innerHTML = "";
});

function moves(): Moves {
  return new Moves(new Spotlight({ color: "#000", beatMs: 0, dwellMs: 0 }));
}

describe("checkRegistry", () => {
  it("wants every declared move, under its class, and nothing else", () => {
    const m = moves();
    scene.register(m, "core.show", async () => "shown");
    m.register("listing.sort", "look", async () => "sorted");
    m.register("cart.remove", "confirmed", async () => "removed");
    expect(checkRegistry(scene, m)).toEqual([
      { level: "error", move: "listing.sort", message: "registered as look, declared reversible" },
      { level: "error", move: "cart.add", message: "declared, but no performer is registered" },
      { level: "warning", move: "cart.remove", message: "registered, but the spec declares no such move" },
    ]);
  });
});

describe("conformance", () => {
  it("passes a page that rings before it acts", async () => {
    const m = moves();
    scene.registerAll(m, {
      "core.show": async (_, c) => (await c.ring($("h")), "shown"),
      "listing.sort": async (a, c) => {
        await c.ring($("sort"));
        ($("sort") as HTMLSelectElement).value = a.order;
        $("sort").setAttribute("data-order", a.order);
        return "sorted";
      },
      "cart.add": async (_, c) => {
        await c.ring($("add"));
        $("add").textContent = "Added";
        return "added";
      },
    });
    expect(checkRegistry(scene, m)).toEqual([]);
    const found = await conformance(scene, m, [
      { move: "core.show", args: { target: "Rooms" }, setup: page },
      { move: "listing.sort", args: { order: "price_asc" }, setup: page },
      { move: "cart.add", args: { path: "/x" }, setup: page },
    ]);
    expect(found).toEqual([]);
  });

  it("catches a change before the ring, a change with none, and a look that shows nothing", async () => {
    const m = moves();
    scene.registerAll(m, {
      "core.show": async () => "shown",
      "listing.sort": async (a, c) => {
        $("sort").setAttribute("data-order", a.order);
        await c.ring($("sort"));
        return "sorted";
      },
      "cart.add": async () => {
        $("add").textContent = "Added";
        return "added";
      },
    });
    const found = await conformance(scene, m, [
      { move: "core.show", args: { target: "Rooms" }, setup: page },
      { move: "listing.sort", args: { order: "price_asc" }, setup: page },
      { move: "cart.add", args: { path: "/x" }, setup: page },
    ]);
    expect(found).toEqual([
      { level: "warning", move: "core.show", message: "applied, and rang nothing: the visitor sees no change" },
      { level: "error", move: "listing.sort", message: "changed the page before the spotlight rang what it touched" },
      { level: "error", move: "cart.add", message: "changed the page before the spotlight rang what it touched" },
    ]);
  });

  it("a refusal changes nothing and breaks no rule", async () => {
    const m = moves();
    scene.register(m, "listing.sort", async (_, c) => c.refuse("order", "no such order", ["price_asc"]));
    expect(await conformance(scene, m, [{ move: "listing.sort", args: { order: "cheapest" }, setup: page }])).toEqual([]);
  });
});
