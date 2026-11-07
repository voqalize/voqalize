import { describe, expect, it, vi } from "vitest";
import {
  MicController,
  SILENCE_HINT_AFTER_MS,
  SILENCE_HINT_FLOOR,
  micStateForError,
  watchMicPermission,
} from "../src/controllers/mic.js";

function clock() {
  let t = 0;
  return { now: () => t, advance: (ms: number) => (t += ms) };
}

/** Feed level samples every 100 ms, as the transport does, for `ms`. */
function feed(mic: MicController, c: ReturnType<typeof clock>, level: number, ms: number) {
  for (let elapsed = 0; elapsed <= ms; elapsed += 100) {
    mic.level(level);
    c.advance(100);
  }
}

describe("MicController states", () => {
  it("goes idle → asking → live", () => {
    const mic = new MicController();
    expect(mic.getSnapshot().state).toBe("idle");
    mic.asking();
    expect(mic.getSnapshot().state).toBe("asking");
    mic.live();
    expect(mic.getSnapshot()).toMatchObject({ state: "live", everLive: true });
  });

  it("classifies device errors into blocked and missing", () => {
    expect(micStateForError("permissions")).toBe("blocked");
    expect(micStateForError("undefined-mediadevices")).toBe("blocked");
    for (const type of ["not-found", "in-use", "constraints", "unknown", undefined]) {
      expect(micStateForError(type)).toBe("missing");
    }
    const mic = new MicController();
    mic.asking();
    mic.failed("permissions");
    expect(mic.getSnapshot()).toMatchObject({ state: "blocked", errorType: "permissions", everLive: false });
    mic.asking();
    mic.live();
    expect(mic.getSnapshot().errorType).toBeUndefined();
  });

  it("reads muted only over a live mic", () => {
    const mic = new MicController();
    mic.asking();
    mic.setMuted(true);
    expect(mic.getSnapshot().state).toBe("asking");
    mic.live();
    expect(mic.getSnapshot().state).toBe("muted");
    mic.setMuted(false);
    expect(mic.getSnapshot().state).toBe("live");
  });

  it("does not drop a live mic back to asking", () => {
    const mic = new MicController();
    mic.live();
    mic.asking();
    expect(mic.getSnapshot().state).toBe("live");
  });

  it("notifies subscribers only on a change, with a new snapshot", () => {
    const mic = new MicController();
    const listener = vi.fn();
    mic.subscribe(listener);
    const before = mic.getSnapshot();
    mic.asking();
    mic.asking();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(mic.getSnapshot()).not.toBe(before);
  });

  it("keeps the permission across a reset", () => {
    const mic = new MicController();
    mic.setPermission("denied");
    mic.failed("permissions");
    mic.reset();
    expect(mic.getSnapshot()).toMatchObject({ state: "idle", permission: "denied", everLive: false });
  });
});

describe("silence hint", () => {
  it("has placeholder constants pending real calls", () => {
    expect(SILENCE_HINT_FLOOR).toBeGreaterThan(0);
    expect(SILENCE_HINT_AFTER_MS).toBeGreaterThan(0);
  });

  it("shows after the wait of silence while the agent listens, and clears on sound", () => {
    const c = clock();
    const mic = new MicController({ now: c.now, afterMs: 1000 });
    mic.live();
    mic.setAgentListening(true);
    feed(mic, c, 0, 900);
    expect(mic.getSnapshot().hint).toBe(false);
    feed(mic, c, 0, 200);
    expect(mic.getSnapshot().hint).toBe(true);
    mic.level(0.2);
    expect(mic.getSnapshot().hint).toBe(false);
  });

  it("does not count time the agent is speaking", () => {
    const c = clock();
    const mic = new MicController({ now: c.now, afterMs: 1000 });
    mic.live();
    mic.setAgentListening(true);
    feed(mic, c, 0, 600);
    mic.setAgentListening(false);
    feed(mic, c, 0, 5000);
    expect(mic.getSnapshot().hint).toBe(false);
    mic.setAgentListening(true);
    feed(mic, c, 0, 500);
    expect(mic.getSnapshot().hint).toBe(true);
  });

  it("hides while the agent speaks, and when muted", () => {
    const c = clock();
    const mic = new MicController({ now: c.now, afterMs: 500 });
    mic.live();
    mic.setAgentListening(true);
    feed(mic, c, 0, 700);
    expect(mic.getSnapshot().hint).toBe(true);
    mic.setAgentListening(false);
    expect(mic.getSnapshot().hint).toBe(false);
    mic.setAgentListening(true);
    feed(mic, c, 0, 700);
    mic.setMuted(true);
    expect(mic.getSnapshot()).toMatchObject({ state: "muted", hint: false });
  });

  it("does not count a gap in the meter as silence", () => {
    const c = clock();
    const mic = new MicController({ now: c.now, afterMs: 1000 });
    mic.live();
    mic.setAgentListening(true);
    mic.level(0);
    c.advance(10_000);
    mic.level(0);
    expect(mic.getSnapshot().hint).toBe(false);
  });

  it("never shows when turned off", () => {
    const c = clock();
    const mic = new MicController({ now: c.now, afterMs: 100, silenceHint: false });
    mic.live();
    mic.setAgentListening(true);
    feed(mic, c, 0, 2000);
    expect(mic.getSnapshot().hint).toBe(false);
  });
});

describe("watchMicPermission", () => {
  it("reports the state and its changes, and stops", async () => {
    const listeners: (() => void)[] = [];
    const status = {
      state: "prompt" as PermissionState,
      addEventListener: (_: string, l: () => void) => listeners.push(l),
      removeEventListener: vi.fn(),
    };
    const seen: string[] = [];
    const stop = watchMicPermission((s) => seen.push(s), {
      query: () => Promise.resolve(status as unknown as PermissionStatus),
    });
    await Promise.resolve();
    await Promise.resolve();
    status.state = "granted";
    listeners.forEach((l) => l());
    stop();
    expect(seen).toEqual(["prompt", "granted"]);
    expect(status.removeEventListener).toHaveBeenCalled();
  });

  it("never throws without the Permissions API", async () => {
    expect(() => watchMicPermission(() => {}, undefined)()).not.toThrow();
    const stop = watchMicPermission(() => {}, { query: () => Promise.reject(new TypeError("no")) });
    await Promise.resolve();
    stop();
    expect(() =>
      watchMicPermission(() => {}, {
        query: () => {
          throw new Error("sync");
        },
      }),
    ).not.toThrow();
  });
});

describe("track mute and the permission", () => {
  it("shows a muted track as missing over a live device, and ignores its level", () => {
    const c = clock();
    const mic = new MicController({ now: c.now, afterMs: 100 });
    mic.live();
    mic.setAgentListening(true);
    mic.setTrackMuted(true);
    expect(mic.getSnapshot()).toMatchObject({ state: "missing", device: "live", trackMuted: true });
    feed(mic, c, 0, 1000);
    expect(mic.getSnapshot().hint).toBe(false);
    mic.setTrackMuted(false);
    expect(mic.getSnapshot()).toMatchObject({ state: "live", trackMuted: false });
  });

  it("reads every failure as blocked while the permission is denied", () => {
    const mic = new MicController();
    mic.live();
    mic.setPermission("denied");
    mic.failed("track-ended");
    expect(mic.getSnapshot().state).toBe("blocked");
  });
});
