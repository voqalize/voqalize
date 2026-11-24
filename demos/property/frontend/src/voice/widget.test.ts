import { describe, expect, it } from "vitest";
import { PERSONA, jobFor, roleFor } from "../data/persona";
import { stillUrl } from "./Face";

describe("the guide's widget", () => {
  it("labels the dock by the job on the page, as the brain picks it", () => {
    expect(jobFor("/")).toBe("guide");
    expect(jobFor("/listings")).toBe("guide");
    expect(jobFor("/listing/BLR-101")).toBe("booker");
    expect(roleFor("/listing/BLR-101")).toBe(PERSONA.roles.booker);
    expect(roleFor("/compare")).toBe(PERSONA.roles.guide);
  });

  it("has a still photo for the persona's character", () => {
    expect(stillUrl).toBeTruthy();
    expect(stillUrl).toContain(PERSONA.character);
  });
});
