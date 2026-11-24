// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";
import { asAgent, eventLog } from "../voice/events";
import { checkSignIn, noteHand, useSession } from "./session";

const hand = () => noteHand({ isTrusted: true });
const lastEvent = () => eventLog()[eventLog().length - 1];

describe("sign-in (B7, X9)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    useSession.setState({ signedIn: false });
  });

  it("checks the shape: a 10-digit mobile from 6 to 9, a 4-digit PIN", () => {
    expect(checkSignIn("9876543210", "4321")).toBeNull();
    expect(checkSignIn("6000000000", "0000")).toBeNull();
    expect(checkSignIn("987654321", "4321")).toBe("mobile");
    expect(checkSignIn("98765432101", "4321")).toBe("mobile");
    expect(checkSignIn("1234567890", "4321")).toBe("mobile");
    expect(checkSignIn("9876543210", "432")).toBe("pin");
    expect(checkSignIn("9876543210", "123456")).toBe("pin");
  });

  it("refuses a sign-in no hand made (a script, or the agent)", () => {
    expect(useSession.getState().signIn("9876543210", "4321")).toEqual({ ok: false, problem: "hand" });
    expect(useSession.getState().signedIn).toBe(false);
    noteHand({ isTrusted: false });
    expect(useSession.getState().signIn("9876543210", "4321")).toEqual({ ok: false, problem: "hand" });
    expect(useSession.getState().signedIn).toBe(false);
  });

  it("says which field is the wrong length, never the digits", () => {
    hand();
    expect(useSession.getState().signIn("98765", "4321")).toEqual({ ok: false, problem: "mobile" });
    expect(lastEvent().event).toBe("sign_in_failed");
    expect(lastEvent().payload).toEqual({ problem: "mobile", by: "visitor" });
    expect(useSession.getState().signedIn).toBe(false);
  });

  it("signs in on the customer's own press and tells the brain who, not the number", () => {
    hand();
    expect(useSession.getState().signIn("9876543210", "4321")).toEqual({ ok: true });
    expect(useSession.getState().signedIn).toBe(true);
    const ev = lastEvent();
    expect(ev.event).toBe("signed_in");
    expect(ev.payload).toEqual({ name: "Aditi Sharma", first_name: "Aditi", by: "visitor" });
    expect(JSON.stringify(ev.payload)).not.toMatch(/9876543210|4321/);
  });

  // Last: an agent's act marks the next 600 ms as the agent's.
  it("refuses a press made while the agent is acting", () => {
    hand();
    expect(asAgent(() => useSession.getState().signIn("9876543210", "4321"))).toEqual({ ok: false, problem: "hand" });
    expect(useSession.getState().signedIn).toBe(false);
  });
});
