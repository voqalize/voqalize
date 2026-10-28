import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { locate } from "../src/dom";
import { arrived, type Carried, type Carrier, Moves } from "../src/moves";
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

  it("holds the move only a beat, while the ring stays up its dwell and then until replaced", async () => {
    page(`<p id="a">A</p><p id="b">B</p>`);
    const a = document.getElementById("a")!;
    const b = document.getElementById("b")!;
    box(a, 0, 0, 10, 10);
    box(b, 0, 50, 10, 10);
    const s = new Spotlight({ color: "#a01a1a", width: 3, dwellMs: 1500, holdMs: 5500 });
    let acted = false;
    void s.ring(a).then(() => (acted = true));
    await vi.advanceTimersByTimeAsync(400);
    expect(acted).toBe(false);
    await vi.advanceTimersByTimeAsync(100);
    // The default beat is 450 ms: the move acts with the ring showing.
    expect(acted).toBe(true);
    const rings = () => s.element!.shadowRoot!.querySelectorAll(".ring");
    expect(rings().length).toBe(1);
    // The next ring replaces it at once, dwell or not.
    void s.ring(b);
    expect(rings().length).toBe(1);
    // And it goes by itself after holdMs.
    await vi.advanceTimersByTimeAsync(5600);
    expect(rings().length).toBe(0);
  });

  it("takes a beat per call", async () => {
    page(`<p id="a">A</p>`);
    const a = document.getElementById("a")!;
    box(a, 0, 0, 10, 10);
    const s = new Spotlight({ color: "#000" });
    let acted = false;
    void s.ring(a, { beatMs: 100 }).then(() => (acted = true));
    await vi.advanceTimersByTimeAsync(110);
    expect(acted).toBe(true);
  });

  it("keeps a ring up its dwell through a clear(), then takes it down", async () => {
    page(`<p id="a">A</p>`);
    const a = document.getElementById("a")!;
    box(a, 0, 0, 10, 10);
    const s = new Spotlight({ color: "#000", dwellMs: 1500 });
    const done = s.ring(a);
    await vi.advanceTimersByTimeAsync(500);
    await done;
    const rings = () => s.element!.shadowRoot!.querySelectorAll(".ring").length;
    s.clear();
    expect(rings()).toBe(1);
    await vi.advanceTimersByTimeAsync(900);
    expect(rings()).toBe(1);
    await vi.advanceTimersByTimeAsync(200);
    expect(rings()).toBe(0);
    // A ring older than its dwell is cleared at once.
    void s.ring(a);
    await vi.advanceTimersByTimeAsync(1600);
    s.clear();
    expect(rings()).toBe(0);
  });

  it("rings a group as one box", async () => {
    page(`<p id="a">A</p><p id="b">B</p>`);
    const a = document.getElementById("a")!;
    const b = document.getElementById("b")!;
    box(a, 10, 10, 100, 20);
    box(b, 50, 100, 200, 20);
    const s = new Spotlight({ color: "#000", pad: 0, beatMs: 0 });
    await s.ring([a, b]);
    const ring = s.element!.shadowRoot!.querySelector<HTMLElement>(".ring")!;
    expect(s.element!.shadowRoot!.querySelectorAll(".ring").length).toBe(1);
    expect(ring.style.transform).toBe("translate(10px, 10px)");
    expect(ring.style.width).toBe("240px");
    expect(ring.style.height).toBe("110px");
  });

  it("rings several separately, one box each, skipping what is not laid out", async () => {
    page(`<p id="a">A</p><p id="b">B</p><p id="c">C</p>`);
    const a = document.getElementById("a")!;
    const b = document.getElementById("b")!;
    const c = document.getElementById("c")!;
    box(a, 10, 10, 100, 20);
    box(b, 50, 100, 200, 20);
    const s = new Spotlight({ color: "#000", pad: 0, beatMs: 0 });
    await s.ring([a, b, c], { separate: true });
    const rings = [...s.element!.shadowRoot!.querySelectorAll<HTMLElement>(".ring")];
    expect(rings.map((r) => [r.style.transform, r.style.width, r.style.height])).toEqual([
      ["translate(10px, 10px)", "100px", "20px"],
      ["translate(50px, 100px)", "200px", "20px"],
    ]);
    // The next ring replaces them all.
    await s.ring(a);
    expect(s.element!.shadowRoot!.querySelectorAll(".ring").length).toBe(1);
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
    const moves = new Moves(new Spotlight({ color: "#000", beatMs: 0 }));
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

describe("Moves carried to the next page", () => {
  function carrier(): Carrier & { kept: Carried[]; dropped: string[]; loaded: string[] } {
    const kept: Carried[] = [];
    const dropped: string[] = [];
    const loaded: string[] = [];
    return {
      kept, dropped, loaded,
      async keep(c) {
        kept.push(c);
      },
      async drop(callRef) {
        dropped.push(callRef);
      },
      load(url) {
        loaded.push(url);
      },
    };
  }

  it("loadThen without a follow-up carries the move itself, expecting the page it loads", async () => {
    const carry = carrier();
    const moves = new Moves(new Spotlight({ color: "#000" }), { carrier: carry });
    moves.register<{ path: string }>("site.navigate", "navigate", async ({ path }, c) => c.loadThen!(`https://x.test${path}`));
    expect(await moves.run("site.navigate", { path: "/rooms" }, "c7")).toBeNull();
    expect(carry.kept).toMatchObject([{ kind: "carried", call_ref: "c7", move: "site.navigate", expect: "https://x.test/rooms" }]);
    expect(typeof carry.kept[0]!.received_at).toBe("number");
    expect(carry.loaded).toEqual(["https://x.test/rooms"]);
    expect(carry.dropped).toEqual([]);
  });

  it("the next page finishes it under the move's own id and call", async () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    moves.register<{ heading: string }>("site.arrive_show", "look", async ({ heading }, c) => `${c.move} showed ${heading}`);
    const done = await moves.resume({
      kind: "carried", call_ref: "c7", move: "site.navigate", then: { move: "site.arrive_show", args: { heading: "Spa" } },
    });
    // The performer runs as itself; the result is the move the agent asked for.
    expect(done).toMatchObject({ call_ref: "c7", move: "site.navigate", outcome: "applied", detail: "site.arrive_show showed Spa", moved: false });
    // With no follow-up, the page coming up is the move done.
    const here = await moves.resume({ kind: "carried", call_ref: "c8", move: "site.navigate" });
    expect(here).toMatchObject({ call_ref: "c8", move: "site.navigate", outcome: "applied", moved: false });
  });

  it("a page that came up where it was asked is applied; elsewhere, partial, saying where", () => {
    const c: Carried = { kind: "carried", call_ref: "c1", move: "site.navigate", expect: "https://www.x.test/rooms/" };
    expect(arrived(c, "https://x.test/rooms?ref=1")).toMatchObject({ outcome: "applied", detail: "opened /rooms" });
    const off = arrived(c, "https://x.test/login");
    expect(off.outcome).toBe("partial");
    expect(off.detail).toContain("/login");
  });

  it("keep() keeps the rest for a press that may load; a move that ends here drops it by itself", async () => {
    const carry = carrier();
    const moves = new Moves(new Spotlight({ color: "#000" }), { carrier: carry });
    moves.register("shop.add", "confirmed", async (_a, c) => {
      await c.keep({ move: "shop.verify", args: { sku: "1" } });
      return "added";
    });
    moves.register("shop.press", "confirmed", async (_a, c) => {
      await c.keep();
      await c.drop();
      return "pressed";
    });
    moves.register("shop.leave", "navigate", async (_a, c) => {
      await c.keep();
      return null;
    });
    expect(await moves.run("shop.add", {}, "k1")).toMatchObject({ outcome: "applied", detail: "added" });
    expect(carry.kept[0]).toMatchObject({ kind: "carried", call_ref: "k1", move: "shop.add", then: { move: "shop.verify", args: { sku: "1" } } });
    expect(carry.dropped).toEqual(["k1"]);
    await moves.run("shop.press", {}, "k2");
    expect(carry.dropped).toEqual(["k1", "k2"]);
    // A move that went on to the next page keeps what it kept.
    expect(await moves.run("shop.leave", {}, "k3")).toMatchObject({ moved: true });
    expect(carry.dropped).toEqual(["k1", "k2"]);
  });

  it("without a carrier, keep and drop do nothing and there is no loadThen", async () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    moves.register("m", "look", async (_a, c) => {
      await c.keep({ move: "x", args: {} });
      await c.drop();
      return c.loadThen ? "can load" : "cannot load";
    });
    expect(await moves.run("m", {}, "1")).toMatchObject({ outcome: "applied", detail: "cannot load" });
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
