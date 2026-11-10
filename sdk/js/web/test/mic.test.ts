import { describe, expect, it } from "vitest";
import { MicController, micIsOff } from "../src/controllers/mic.js";

describe("MicController", () => {
  it("mirrors the manager's state and remembers a live mic", () => {
    const mic = new MicController();
    expect(mic.getSnapshot()).toMatchObject({ state: "idle", micHint: "none", everLive: false });
    mic.setState("asking");
    expect(mic.getSnapshot()).toMatchObject({ state: "asking", everLive: false });
    mic.setState("live");
    expect(mic.getSnapshot()).toMatchObject({ state: "live", everLive: true });
    mic.setState("missing");
    expect(mic.getSnapshot()).toMatchObject({ state: "missing", everLive: true });
  });

  it("drops the level when the mic is not live", () => {
    const mic = new MicController();
    mic.setState("live");
    mic.level(0.5);
    expect(mic.getSnapshot().level).toBe(0.5);
    mic.setState("blocked");
    expect(mic.getSnapshot().level).toBe(0);
  });

  it("clamps levels and reads a bad one as zero", () => {
    const mic = new MicController();
    mic.level(4);
    expect(mic.getSnapshot().level).toBe(1);
    mic.level(-1);
    expect(mic.getSnapshot().level).toBe(0);
    mic.level(Number.NaN);
    expect(mic.getSnapshot().level).toBe(0);
  });

  it("shows the silence hint only for `silent`, and only when the configuration allows it", () => {
    const mic = new MicController();
    mic.setHint("silent");
    expect(mic.getSnapshot()).toMatchObject({ micHint: "silent", hint: true });
    mic.setHint("missing");
    expect(mic.getSnapshot()).toMatchObject({ micHint: "missing", hint: false });
    const off = new MicController({ silenceHint: false });
    off.setHint("silent");
    expect(off.getSnapshot()).toMatchObject({ micHint: "silent", hint: false });
  });

  it("keeps the visitor's mute apart from the manager's state", () => {
    const mic = new MicController();
    mic.setMuted(true);
    expect(mic.getSnapshot()).toMatchObject({ muted: true, state: "idle" });
  });

  it("resets for a new call from what the manager says now", () => {
    const mic = new MicController();
    mic.setState("live");
    mic.setMuted(true);
    mic.level(0.4);
    mic.reset("blocked", "blocked");
    expect(mic.getSnapshot()).toEqual({
      state: "blocked",
      micHint: "blocked",
      muted: false,
      hint: false,
      level: 0,
      everLive: false,
    });
    mic.reset("live", "silent");
    expect(mic.getSnapshot()).toMatchObject({ state: "live", everLive: true, hint: true });
  });
});

describe("micIsOff", () => {
  it("is true only for the hints that mean the mic is not reaching the call", () => {
    expect(micIsOff("grant")).toBe(true);
    expect(micIsOff("blocked")).toBe(true);
    expect(micIsOff("missing")).toBe(true);
    expect(micIsOff("silent")).toBe(false);
    expect(micIsOff("none")).toBe(false);
  });
});
