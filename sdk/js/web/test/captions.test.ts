import { describe, expect, it } from "vitest";
import { CaptionsController, type CaptionsOptions, type CaptionsSnapshot } from "../src/controllers/captions.js";

function timers() {
  const pending: { fn: () => void; ms: number }[] = [];
  return {
    setTimeout: (fn: () => void, ms: number) => {
      const t = { fn, ms };
      pending.push(t);
      return t;
    },
    clearTimeout: (h: unknown) => {
      const i = pending.indexOf(h as (typeof pending)[number]);
      if (i >= 0) pending.splice(i, 1);
    },
    flush: () => pending.splice(0).forEach((t) => t.fn()),
    pending,
  };
}

function make(options: CaptionsOptions = {}) {
  const t = timers();
  const captions = new CaptionsController({ setTimeout: t.setTimeout, clearTimeout: t.clearTimeout, ...options });
  return { captions, t };
}

function text(snap: CaptionsSnapshot) {
  return snap.lines.map((l) => l.words.map((w) => (w.spoken ? w.text.toUpperCase() : w.text)).join(" "));
}

function say(c: CaptionsController, words: string) {
  for (const w of words.split(" ")) c.agentWord(w);
}

describe("karaoke", () => {
  it("lays out the sentence and lights words as they play", () => {
    const { captions } = make();
    captions.agentStarted();
    captions.agentSentence("We have a plan for every team.");
    expect(text(captions.getSnapshot())).toEqual(["We have a plan for every team."]);
    say(captions, "We have");
    const snap = captions.getSnapshot();
    expect(text(snap)).toEqual(["WE HAVE a plan for every team."]);
    expect(snap.lines[0]?.words.find((w) => w.current)?.text).toBe("have");
    expect(snap.visible).toBe(true);
  });

  it("shows only up to the line being spoken, and at most `lines` of them", () => {
    const { captions } = make({ charsPerLine: 12, lines: 2 });
    captions.agentSentence("one two three four five six seven eight nine ten");
    say(captions, "one two");
    expect(text(captions.getSnapshot())).toEqual(["ONE TWO"]);
    say(captions, "three four five six seven eight");
    const lines = text(captions.getSnapshot());
    expect(lines).toHaveLength(2);
    expect(lines.at(-1)).toContain("EIGHT");
    expect(lines.join(" ")).not.toContain("ONE");
  });

  it("drops unspoken words on a barge-in and clears after linger", () => {
    const { captions, t } = make({ lingerMs: 4000 });
    captions.agentSentence("The starter plan includes unlimited calls.");
    say(captions, "The starter plan");
    captions.agentStopped();
    expect(text(captions.getSnapshot())).toEqual(["THE STARTER PLAN"]);
    expect(captions.getSnapshot().announcement?.text).toBe("The starter plan");
    expect(t.pending[0]?.ms).toBe(4000);
    t.flush();
    expect(captions.getSnapshot()).toMatchObject({ visible: false, lines: [] });
  });

  it("keeps the captions if the agent starts again within linger, then starts a new block", () => {
    const { captions, t } = make();
    captions.agentSentence("First.");
    say(captions, "First.");
    captions.agentStopped();
    captions.agentStarted();
    expect(t.pending).toHaveLength(0);
    expect(text(captions.getSnapshot())).toEqual(["FIRST."]);
    captions.agentSentence("Second.");
    expect(text(captions.getSnapshot())).toEqual(["Second."]);
  });

  it("announces each finished sentence once", () => {
    const { captions } = make();
    const seen: string[] = [];
    captions.subscribe(() => {
      const a = captions.getSnapshot().announcement;
      if (a && !seen.includes(`${a.id}:${a.text}`)) seen.push(`${a.id}:${a.text}`);
    });
    captions.agentSentence("Your order ships today.");
    captions.agentSentence("Anything else?");
    say(captions, "Your order ships today. Anything else?");
    captions.agentStopped();
    expect(seen).toEqual(["1:Your order ships today.", "2:Anything else?"]);
  });

  it("skips a word the voice said differently without lighting out of order", () => {
    const { captions } = make();
    captions.agentSentence("It costs $5 today.");
    say(captions, "It costs five dollars today.");
    expect(text(captions.getSnapshot())).toEqual(["IT COSTS $5 TODAY."]);
  });

  it("moves on to the next sentence when the last word of one was said differently", () => {
    const { captions } = make();
    const seen: string[] = [];
    captions.subscribe(() => {
      const a = captions.getSnapshot().announcement;
      if (a && !seen.includes(a.text)) seen.push(a.text);
    });
    captions.agentSentence("It costs $5.");
    say(captions, "It costs five dollars.");
    captions.agentSentence("Anything else?");
    say(captions, "Anything else?");
    expect(text(captions.getSnapshot()).join(" ")).toContain("ANYTHING ELSE?");
    expect(seen).toEqual(["It costs $5.", "Anything else?"]);
  });

  it("shows words that arrive before their sentence", () => {
    const { captions } = make();
    say(captions, "Hello there");
    expect(text(captions.getSnapshot())).toEqual(["HELLO THERE"]);
    captions.agentSentence("Hello there, friend.");
    expect(text(captions.getSnapshot())).toEqual(["HELLO THERE, friend."]);
    captions.agentWord("friend.");
    expect(captions.getSnapshot().announcement?.text).toBe("Hello there, friend.");
  });
});

describe("modes and options", () => {
  it("rolling shows spoken words only", () => {
    const { captions } = make({ mode: "rolling" });
    captions.agentSentence("We have a plan.");
    expect(captions.getSnapshot().visible).toBe(false);
    say(captions, "We have");
    expect(text(captions.getSnapshot())).toEqual(["WE HAVE"]);
  });

  it("off shows nothing but still announces", () => {
    const { captions } = make({ mode: "off" });
    captions.agentSentence("Hi.");
    captions.agentWord("Hi.");
    expect(captions.getSnapshot()).toMatchObject({ visible: false, lines: [] });
    expect(captions.getSnapshot().announcement?.text).toBe("Hi.");
  });

  it("shows the visitor's final line only with showUser", () => {
    const off = make().captions;
    off.userTranscript("hello", true);
    expect(off.getSnapshot().user).toBeUndefined();
    const { captions } = make({ showUser: true });
    captions.userTranscript("hel", false);
    expect(captions.getSnapshot().user).toBeUndefined();
    captions.userTranscript("hello", true);
    expect(captions.getSnapshot()).toMatchObject({ user: "hello", visible: true });
  });

  it("takes new lines, linger and showUser on a running controller", () => {
    const { captions, t } = make({ charsPerLine: 12, lines: 1 });
    captions.configure({ lines: 2, lingerMs: 900, showUser: true });
    captions.agentSentence("one two three four five six");
    say(captions, "one two three four five six");
    expect(captions.getSnapshot().lines).toHaveLength(2);
    captions.userTranscript("hello", true);
    expect(captions.getSnapshot().user).toBe("hello");
    captions.agentStopped();
    expect(t.pending.at(-1)?.ms).toBe(900);
    captions.configure({ showUser: false });
    expect(captions.getSnapshot().user).toBeUndefined();
  });

  it("re-wraps when the width changes", () => {
    const { captions } = make({ charsPerLine: 100 });
    captions.agentSentence("aaaa bbbb cccc dddd");
    say(captions, "aaaa bbbb cccc dddd");
    expect(captions.getSnapshot().lines).toHaveLength(1);
    captions.setCharsPerLine(9);
    expect(captions.getSnapshot().lines).toHaveLength(2);
  });

  it("resets", () => {
    const { captions, t } = make({ showUser: true });
    captions.agentSentence("Hi.");
    captions.userTranscript("yo", true);
    captions.agentStopped();
    captions.reset();
    expect(t.pending).toHaveLength(0);
    expect(captions.getSnapshot()).toMatchObject({ visible: false, lines: [], user: undefined });
  });
});
