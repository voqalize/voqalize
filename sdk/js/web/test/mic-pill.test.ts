import { describe, expect, it } from "vitest";
import type { MicSnapshot } from "../src/controllers/mic.js";
import { micPillOf } from "../src/controllers/mic-pill.js";
import { IDLE_MIC } from "./support/fake-session.js";

const snap = (patch: Partial<MicSnapshot>): MicSnapshot => ({ ...IDLE_MIC, ...patch });

describe("micPillOf", () => {
  it("shows nothing for an idle or healthy mic", () => {
    expect(micPillOf(undefined)).toBeNull();
    expect(micPillOf(IDLE_MIC)).toBeNull();
    expect(micPillOf(snap({ state: "live", device: "live", permission: "granted" }))).toBeNull();
  });

  it("asks for permission when blocked, denied, or asked and not yet answered", () => {
    expect(micPillOf(snap({ state: "blocked", device: "blocked" }))).toBe("permission");
    expect(micPillOf(snap({ state: "missing", device: "missing", permission: "denied" }))).toBe("permission");
    expect(micPillOf(snap({ state: "asking", device: "asking", permission: "prompt" }))).toBe("permission");
    expect(micPillOf(snap({ state: "asking", device: "asking", permission: "prompt" }), { askingSettled: false })).toBeNull();
    expect(micPillOf(snap({ state: "asking", device: "asking", permission: "granted" }))).toBeNull();
  });

  it("says muted for the visitor's mute, ahead of a check", () => {
    expect(micPillOf(snap({ state: "muted", device: "live", muted: true, trackMuted: true }))).toBe("muted");
  });

  it("asks for a check on the silence hint, a muted track, and a missing mic", () => {
    expect(micPillOf(snap({ state: "live", device: "live", hint: true }))).toBe("check");
    expect(micPillOf(snap({ state: "missing", device: "live", trackMuted: true }))).toBe("check");
    expect(micPillOf(snap({ state: "missing", device: "missing" }))).toBe("check");
  });
});
