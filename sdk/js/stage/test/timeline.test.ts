import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Timeline } from "../src/timeline";
import type { StageCue } from "../src/wire.gen";

let n = 0;
function cue(at: string, before = 0, verb = "show"): StageCue {
  n++;
  return { call_ref: `c${n}`, move: `core.${verb}`, verb, args: [`arg${n}`], at, before, unit: 0 };
}

/** Let the fire chain's promises settle. */
const flush = async () => {
  for (let i = 0; i < 10; i++) await Promise.resolve();
};

describe("Timeline", () => {
  let fired: string[];
  let tl: Timeline;
  beforeEach(() => {
    vi.useFakeTimers();
    fired = [];
    tl = new Timeline(async (c) => {
      fired.push(c.call_ref);
    }, { lang: "en" });
  });
  afterEach(() => {
    tl.clear();
    vi.useRealTimers();
  });

  it("fires when the anchor's three words are heard, not before", async () => {
    const c = cue("Here is the observatory where we look up");
    tl.add(c);
    tl.speaking();
    tl.hear("Welcome to Atacama.");
    await flush();
    expect(fired).toEqual([]);
    tl.hear("Here is");
    await flush();
    expect(fired).toEqual([]);
    tl.hear("the observatory");
    await flush();
    expect(fired).toEqual([c.call_ref]);
    expect(tl.stats.anchor).toBe(1);
  });

  it("matches across scripts and accents", async () => {
    const es = new Timeline(async (c) => void fired.push(c.call_ref), { lang: "es" });
    const c = cue("Las sábanas de algodón son suaves");
    es.add(c);
    es.speaking();
    es.hear("Las SABANAS de algodon");
    await flush();
    expect(fired).toEqual([c.call_ref]);
    es.clear();

    const hi = new Timeline(async (x) => void fired.push(x.call_ref), { lang: "hi" });
    const d = cue("यह कमरा बहुत सुंदर है।");
    hi.add(d);
    hi.speaking();
    hi.hear("देखिए। यह कमरा");
    await flush();
    expect(fired).not.toContain(d.call_ref);
    hi.hear("बहुत सुंदर है।");
    await flush();
    expect(fired).toContain(d.call_ref);
    hi.clear();
  });

  it("accepts two words of three once 1.5 s late (fuzzy)", async () => {
    const c = cue("the stars above Atacama", 0);
    tl.add(c);
    tl.speaking();
    tl.hear("look at the stars of Atacama tonight");
    await flush();
    // "the stars of" has two of "the stars above" in place, but it is not late yet.
    expect(fired).toEqual([]);
    vi.advanceTimersByTime(1600);
    await flush();
    expect(fired).toEqual([c.call_ref]);
    expect(tl.stats.fuzzy).toBe(1);
  });

  it("goes by the clock when no spoken text arrives", async () => {
    const early = cue("first words here", 14); // 1 s at 14 cps
    const late = cue("later words here", 70); // 5 s
    tl.add(early);
    tl.add(late);
    tl.speaking();
    vi.advanceTimersByTime(1400);
    await flush();
    expect(fired).toEqual([]); // nothing before 1.5 s into speech
    vi.advanceTimersByTime(300);
    await flush();
    expect(fired).toEqual([early.call_ref]);
    vi.advanceTimersByTime(3500);
    await flush();
    expect(fired).toEqual([early.call_ref, late.call_ref]);
    expect(tl.stats.clock).toBe(2);
  });

  it("recalibrates its rate from the spoken text", () => {
    tl.speaking();
    tl.hear("a".repeat(100)); // 100 chars over 4 s: 25 cps
    vi.advanceTimersByTime(4000);
    tl.stopped();
    expect(tl.rate).toBeGreaterThan(14);
    expect(tl.rate).toBeLessThan(25);
  });

  it("fires an end-of-reply cue 600 ms after the voice stops", async () => {
    const c = cue("", 120);
    tl.add(c);
    tl.speaking();
    tl.hear("That is all for the lodge.");
    tl.stopped();
    vi.advanceTimersByTime(500);
    await flush();
    expect(fired).toEqual([]);
    vi.advanceTimersByTime(150);
    await flush();
    expect(fired).toEqual([c.call_ref]);
    expect(tl.stats.end).toBe(1);
  });

  it("drops what was not reached when the person talks over the voice", async () => {
    const a = cue("first we go here");
    const b = cue("then we go there");
    tl.add(a);
    tl.add(b);
    tl.speaking();
    tl.hear("first we go");
    await flush();
    const dropped = tl.interrupted();
    expect(dropped.map((c) => c.call_ref)).toEqual([b.call_ref]);
    tl.hear("then we go there");
    await flush();
    expect(fired).toEqual([a.call_ref]);
  });

  it("drops a cue whose words never come after 45 s", async () => {
    const drops: string[] = [];
    const t = new Timeline(async (c) => void fired.push(c.call_ref), { onDrop: (c, why) => drops.push(`${c.call_ref}:${why}`) });
    const c = cue("words that never come");
    t.add(c);
    vi.advanceTimersByTime(46_000);
    await flush();
    expect(fired).toEqual([]);
    expect(drops).toEqual([`${c.call_ref}:stale`]);
    t.clear();
  });

  it("fires in order, one move at a time; cues before one sentence share its anchor", async () => {
    const order: string[] = [];
    let release: () => void = () => {};
    const t = new Timeline(async (c) => {
      order.push(`start ${c.call_ref}`);
      if (c.call_ref === page.call_ref) await new Promise<void>((r) => (release = r));
      order.push(`end ${c.call_ref}`);
    });
    const page = cue("Atacama is a desert", 0, "page");
    const section = cue("Atacama is a desert", 0, "show");
    t.add(page);
    t.add(section);
    t.speaking();
    t.hear("Atacama is a desert of salt");
    await flush();
    expect(order).toEqual([`start ${page.call_ref}`]);
    release();
    await flush();
    expect(order).toEqual([`start ${page.call_ref}`, `end ${page.call_ref}`, `start ${section.call_ref}`, `end ${section.call_ref}`]);
    t.clear();
  });

  it("a later cue never fires ahead of an earlier one still waiting", async () => {
    const a = cue("alpha beta gamma");
    const b = cue("delta epsilon zeta");
    tl.add(a);
    tl.add(b);
    tl.speaking();
    tl.hear("delta epsilon zeta");
    await flush();
    expect(fired).toEqual([]);
    tl.hear("alpha beta gamma");
    await flush();
    expect(fired).toEqual([a.call_ref]);
  });

  it("clear() stops a move already waiting its turn", async () => {
    let release: () => void = () => {};
    const made: string[] = [];
    const t = new Timeline(async (c) => {
      made.push(c.call_ref);
      if (made.length === 1) await new Promise<void>((r) => (release = r));
    });
    const a = cue("one two three");
    const b = cue("one two three");
    t.add(a);
    t.add(b);
    t.hear("one two three");
    await flush();
    t.clear();
    release();
    await flush();
    expect(made).toEqual([a.call_ref]);
  });
});
