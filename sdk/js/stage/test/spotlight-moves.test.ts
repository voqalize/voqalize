import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { locate } from "../src/dom";
import { Moves } from "../src/moves";
import { Spotlight } from "../src/spotlight";

/** happy-dom lays nothing out: give an element a box. */
function box(el: Element, left: number, top: number, width: number, height: number): void {
  el.getBoundingClientRect = () =>
    ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON() {} }) as DOMRect;
}

function page(html: string): void {
  document.body.innerHTML = html;
}

afterEach(() => {
  document.documentElement.querySelectorAll("[data-voqalize]").forEach((n) => n.remove());
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("Spotlight", () => {
  beforeEach(() => vi.useFakeTimers());

  it("draws in its own shadow root over the target, never touching the target's styles", async () => {
    page(`<section id="obs" style="color: red">The Observatory</section>`);
    const target = document.getElementById("obs")!;
    box(target, 100, 200, 300, 50);
    const before = target.getAttribute("style");
    const classes = target.className;
    const s = new Spotlight({ color: "#C2410C", dwellMs: 1500 });
    const done = s.ring(target, { label: "The Observatory" });

    const host = [...document.documentElement.children].find((e) => e.getAttribute("data-voqalize") === "spotlight") as HTMLElement | undefined;
    expect(host).toBeDefined();
    expect(host!.shadowRoot).not.toBeNull();
    const ring = host!.shadowRoot!.querySelector<HTMLElement>(".ring")!;
    expect(ring).not.toBeNull();
    // Document coordinates, padded 6 px round the target.
    expect(ring.style.transform).toBe("translate(94px, 194px)");
    expect(ring.style.width).toBe("312px");
    expect(ring.style.height).toBe("62px");
    expect(host!.shadowRoot!.querySelector("[aria-live=polite]")!.textContent).toBe("The Observatory");
    // The site's element is untouched, and nothing was added inside <body>.
    expect(target.getAttribute("style")).toBe(before);
    expect(target.className).toBe(classes);
    expect(document.body.querySelector("[data-voqalize]")).toBeNull();

    await vi.advanceTimersByTimeAsync(1600);
    await done;
  });

  it("holds the move for the dwell, then leaves the ring up until it is replaced", async () => {
    page(`<p id="a">A</p><p id="b">B</p>`);
    const a = document.getElementById("a")!;
    const b = document.getElementById("b")!;
    box(a, 0, 0, 10, 10);
    box(b, 0, 50, 10, 10);
    const s = new Spotlight({ color: "#a01a1a", width: 3, dwellMs: 1500, holdMs: 5500 });
    let dwelt = false;
    void s.ring(a).then(() => (dwelt = true));
    await vi.advanceTimersByTimeAsync(1400);
    expect(dwelt).toBe(false);
    await vi.advanceTimersByTimeAsync(200);
    expect(dwelt).toBe(true);
    const rings = () => s.element!.shadowRoot!.querySelectorAll(".ring");
    expect(rings().length).toBe(1);
    // The next ring replaces it at once.
    void s.ring(b);
    expect(rings().length).toBe(1);
    // And it goes by itself after holdMs.
    await vi.advanceTimersByTimeAsync(5600);
    expect(rings().length).toBe(0);
  });

  it("rings a group as one box", async () => {
    page(`<p id="a">A</p><p id="b">B</p>`);
    const a = document.getElementById("a")!;
    const b = document.getElementById("b")!;
    box(a, 10, 10, 100, 20);
    box(b, 50, 100, 200, 20);
    const s = new Spotlight({ color: "#000", pad: 0, dwellMs: 0 });
    await s.ring([a, b]);
    const ring = s.element!.shadowRoot!.querySelector<HTMLElement>(".ring")!;
    expect(ring.style.transform).toBe("translate(10px, 10px)");
    expect(ring.style.width).toBe("240px");
    expect(ring.style.height).toBe("110px");
  });

  it("does nothing for a target that is not laid out", async () => {
    page(`<p id="a">A</p>`);
    const s = new Spotlight({ color: "#000" });
    await s.ring(document.getElementById("a")!);
    expect(s.element).toBeNull();
  });
});

describe("Moves", () => {
  it("builds applied, refused, failed and moved results", async () => {
    page(`<h2 id="rooms">Rooms</h2>`);
    box(document.getElementById("rooms")!, 0, 0, 100, 20);
    const moves = new Moves(new Spotlight({ color: "#000", dwellMs: 0 }));
    moves.register<{ heading: string }>("core.show", "look", async ({ heading }, c) => {
      const el = locate({ text: heading });
      if (!el) return c.refuse("heading", `no heading "${heading}" here`, ["Rooms"]);
      await c.ring(el);
      return `rang ${heading}`;
    }, { params: ["heading"] });
    moves.register("core.page", "navigate", async () => null);
    moves.register("core.boom", "reversible", async () => {
      throw new Error("the form is gone");
    });

    const applied = await moves.run("core.show", ["Rooms"], "r1");
    expect(applied).toMatchObject({ call_ref: "r1", move: "core.show", outcome: "applied", detail: "rang Rooms", moved: false, refused: [] });
    expect(typeof applied!.ms).toBe("number");

    const refused = await moves.run("core.show", ["Spa"], "r2");
    expect(refused).toMatchObject({
      outcome: "refused",
      refused: [{ arg: "heading", why: 'no heading "Spa" here', options: ["Rooms"] }],
      moved: false,
    });

    expect(await moves.run("core.page", { path: "/x" }, "r3")).toMatchObject({ outcome: "applied", moved: true, detail: null });
    expect(await moves.run("core.boom", {}, "r4")).toMatchObject({ outcome: "failed", detail: "the form is gone" });
    expect(await moves.run("core.nope", {}, "r5")).toMatchObject({ outcome: "failed", call_ref: "r5" });
  });

  it("runs one move at a time, in order", async () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    const order: string[] = [];
    moves.register<{ id: string; ms: number }>("m", "look", async ({ id, ms }) => {
      order.push(`start ${id}`);
      await new Promise((r) => setTimeout(r, ms));
      order.push(`end ${id}`);
      return id;
    });
    await Promise.all([moves.run("m", { id: "a", ms: 30 }, "1"), moves.run("m", { id: "b", ms: 1 }, "2")]);
    expect(order).toEqual(["start a", "end a", "start b", "end b"]);
  });
});

describe("locate", () => {
  it("returns the one match, or null when none or several", () => {
    page(`
      <button data-testid="add">Add</button>
      <button aria-label="Close dialog">×</button>
      <a href="/a">Rooms</a><a href="/b">Rooms</a>
      <nav><a href="/spa">Spa &amp; pools</a></nav>
      <h2 id="faq">Questions</h2>
    `);
    expect(locate({ testId: "add" })?.textContent).toBe("Add");
    expect(locate({ ariaLabel: "close dialog" })?.textContent).toBe("×");
    expect(locate({ role: "link", name: "Rooms" })).toBeNull(); // two
    expect(locate({ role: "link", name: "spa & pools" })?.getAttribute("href")).toBe("/spa");
    expect(locate({ role: "heading", name: "Questions" })?.id).toBe("faq");
    expect(locate({ id: "faq" })?.tagName).toBe("H2");
    expect(locate({ css: "a" })).toBeNull();
    expect(locate({ text: "Spa & pools" })?.tagName).toBe("A");
    expect(locate({ css: "::invalid((" })).toBeNull();
  });

  it("any_of: the first strategy that finds exactly one wins", () => {
    page(`<a href="/a" class="x">One</a><a href="/b" class="x">Two</a><span data-testid="two">Two</span>`);
    expect(locate({ any_of: [{ css: ".x" }, { text: "Two", within: "a" }, { testId: "two" }] })?.getAttribute("href")).toBe("/b");
    expect(locate({ any_of: [{ css: ".x" }, { testId: "two" }] })?.tagName).toBe("SPAN");
    expect(locate({ any_of: [{ css: ".x" }, { css: ".missing" }] })).toBeNull();
  });

  it("ignores the extension's own elements", () => {
    page(`<button data-voqalize="widget">Call</button><button>Call</button>`);
    expect(locate({ role: "button", name: "Call" })?.hasAttribute("data-voqalize")).toBe(false);
  });
});
