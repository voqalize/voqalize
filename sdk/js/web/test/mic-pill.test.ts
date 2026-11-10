import { describe, expect, it } from "vitest";
import type { MicSnapshot } from "../src/controllers/mic.js";
import { micPillOf } from "../src/controllers/mic-pill.js";
import { IDLE_MIC } from "./support/fake-session.js";

const snap = (patch: Partial<MicSnapshot>): MicSnapshot => ({ ...IDLE_MIC, ...patch });

describe("micPillOf", () => {
  it("shows nothing for an idle or healthy mic", () => {
    expect(micPillOf(undefined)).toBeNull();
    expect(micPillOf(IDLE_MIC)).toBeNull();
    expect(micPillOf(snap({ state: "idle", micHint: "blocked" }))).toBeNull();
    expect(micPillOf(snap({ state: "live", micHint: "none" }))).toBeNull();
  });

  it("asks for permission when the hint is blocked, or grant once the ask has settled", () => {
    expect(micPillOf(snap({ state: "blocked", micHint: "blocked" }))).toBe("permission");
    expect(micPillOf(snap({ state: "asking", micHint: "grant" }))).toBe("permission");
    expect(micPillOf(snap({ state: "asking", micHint: "grant" }), { askingSettled: false })).toBeNull();
    expect(micPillOf(snap({ state: "asking", micHint: "none" }))).toBeNull();
  });

  it("says muted for the visitor's mute, ahead of a check", () => {
    expect(micPillOf(snap({ state: "muted", muted: true, micHint: "none" }))).toBe("muted");
    expect(micPillOf(snap({ state: "muted", muted: true, hint: true, micHint: "silent" }))).toBe("muted");
  });

  it("asks for a check on the silence hint and a missing mic", () => {
    expect(micPillOf(snap({ state: "live", micHint: "silent", hint: true }))).toBe("check");
    expect(micPillOf(snap({ state: "live", micHint: "silent", hint: false }))).toBeNull();
    expect(micPillOf(snap({ state: "missing", micHint: "missing" }))).toBe("check");
  });
});
